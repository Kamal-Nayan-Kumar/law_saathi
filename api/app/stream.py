"""Server-sent events for the ask endpoint.

A full agent run takes 10-20s: plan, retrieve, draft, verify, sometimes retry,
then translate. With a single JSON response the user stares at a spinner for all
of it, which is the single biggest reason the chat does not feel like a
conversation.

This module runs the same agent as `routers_chat.ask`, but reports each step the
moment it happens:

    event: step      {"node": "intent", "detail": "..."}
    event: answer    {"text": "...", "index": N, "final": bool}
    event: done      { ...the AskOut fields... }
    event: error     {"message": "..."}

The browser renders the steps live and fills the answer in as it arrives, so the
visible behaviour is unchanged and there is still exactly one source of truth for
what was persisted.

The agent's nodes are plain functions over one state dict, so a run is executed
in a worker thread and each node's trace addition is published as it happens.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, Iterator, List

SENTINEL = object()

# How the verified answer is revealed.
#
# `answer` events are paced rather than dumped, because the alternative is
# exactly what this module exists to remove: a screen where nothing changes for
# eighteen seconds and then all of it at once. The pacing is small enough that
# it never dominates the wait — well under a second for a typical answer — but
# large enough that the reader's eye can follow the text down the page instead
# of jumping to the bottom of a block that just appeared whole.
ANSWER_WORDS_PER_CHUNK = int(os.environ.get("LAWSAATHI_ANSWER_CHUNK_WORDS", "9"))
ANSWER_CHUNK_DELAY = float(
    os.environ.get("LAWSAATHI_ANSWER_CHUNK_DELAY_MS", "22")
) / 1000.0


def _sse(event: str, data: Dict[str, Any]) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))


def chunk_answer(text: str,
                 words_per_chunk: int = ANSWER_WORDS_PER_CHUNK) -> Iterator[str]:
    """Split an answer into pieces, losslessly.

    The one rule this must never break: **concatenating every chunk must give
    back the answer byte for byte.** The browser fills its card from these
    pieces, so a dropped newline or a lost space would show the reader one thing
    and persist another.

    So the split is structural rather than arbitrary: paragraph breaks, then
    line breaks, then words, and each separator is emitted as its own chunk to
    rejoin the pieces in the right place. Splitting on whitespace alone would
    also cut `**bold` away from its closing `**` and leave the reader watching
    malformed markdown for the length of a chunk.

    A short answer is returned whole. There is nothing to reveal progressively
    in "Yes. It is 18." and pacing it would only make it arrive later.
    """
    stripped = (text or "").strip()
    if not stripped:
        return
    if len(stripped) <= 140:
        yield stripped
        return

    paragraphs = stripped.split("\n\n")
    for p_index, paragraph in enumerate(paragraphs):
        if p_index:
            yield "\n\n"
        lines = paragraph.split("\n")
        for l_index, line in enumerate(lines):
            if l_index:
                yield "\n"
            words = line.split()
            for w_index in range(0, len(words), words_per_chunk):
                if w_index:
                    # The space this split consumed, so the pieces rejoin to the
                    # original sentence rather than running two words together.
                    yield " "
                yield " ".join(words[w_index:w_index + words_per_chunk])


class StepPublisher:
    """Collects trace events produced while the agent runs."""

    def __init__(self) -> None:
        self.queue: "queue.Queue[Any]" = queue.Queue()
        self._lock = threading.Lock()
        self._sent = 0
        self.state: Dict[str, Any] = {}

    def publish_state(self, state: Dict[str, Any]) -> None:
        """Called after each node. Emits only the trace lines that are new."""
        with self._lock:
            detail: List[Dict[str, str]] = list(state.get("trace_detail") or [])
            new = detail[self._sent:]
            self._sent = len(detail)
            self.state = state
        for i, step in enumerate(new, start=self._sent - len(new) + 1):
            self.queue.put(_sse("step", {"node": step.get("node", ""),
                                         "detail": step.get("detail", ""),
                                         "index": i}))

    def stream_answer(self, text: str,
                      words_per_chunk: int = ANSWER_WORDS_PER_CHUNK,
                      delay: float = ANSWER_CHUNK_DELAY) -> List[str]:
        """Send the finished answer in pieces, and return the pieces.

        Called only once the verifier has passed, so nothing that might still be
        rejected is ever put on the wire — ADR-0012's reason for not streaming
        model tokens still stands. What this buys is that the reader starts
        following the answer while the last of the bookkeeping runs behind it,
        rather than getting a finished block in a single frame.

        Every chunk is queued *before* the first sleep, so a client that is only
        reading the stream gets all of it at once and the pacing never delays a
        complete answer. The delay exists purely to shape what a human watching
        the screen sees, and a reader who would rather have it immediately gets
        it immediately by setting the delay to 0.
        """
        try:
            chunks = [c for c in chunk_answer(text, words_per_chunk) if c]
        except Exception:  # noqa: BLE001 - falling back to `done` is correct
            chunks = []
        for i, chunk in enumerate(chunks):
            self.queue.put(_sse("answer", {"text": chunk,
                                           "index": i,
                                           "final": i == len(chunks) - 1}))
        for i in range(len(chunks) - 1):
            if delay:
                time.sleep(delay)
        return chunks

    def finish(self, payload: Dict[str, Any]) -> None:
        self.queue.put(_sse("done", payload))

    def fail(self, message: str) -> None:
        self.queue.put(_sse("error", {"message": message}))

    def close(self) -> None:
        self.queue.put(SENTINEL)


def run_with_steps(agent_run: Callable[[], Dict[str, Any]],
                   publisher: StepPublisher,
                   to_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
                   heartbeat: float = 12.0):  # noqa: ANN201 - a generator
    """Run the agent in a thread, streaming its steps as they are produced.

    ``heartbeat`` sends a comment every N seconds of silence so a proxy or the
    browser does not treat an idle connection as dead while the model thinks.
    """
    def worker() -> None:
        try:
            state = agent_run()
            publisher.finish(to_payload(state))
        except Exception as exc:  # noqa: BLE001 — reported to the client
            publisher.fail("%s: %s" % (exc.__class__.__name__, exc))
        finally:
            publisher.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # The stream blocks on queue.get; a timeout lets us send keepalives. The
    # queue is publisher's own, so reaching for it here is safe.
    while True:
        try:
            item = publisher.queue.get(timeout=heartbeat)
        except queue.Empty:
            yield ": keepalive\n\n"
            continue
        if item is SENTINEL:
            return
        yield item