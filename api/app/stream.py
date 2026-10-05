"""Server-sent events for the ask endpoint.

A full agent run takes 10-20s: plan, retrieve, draft, verify, sometimes retry,
then translate. With a single JSON response the user stares at a spinner for all
of it, which is the single biggest reason the chat does not feel like a
conversation.

This module runs the same agent as `routers_chat.ask`, but reports each step the
moment it happens:

    event: step      {"node": "intent", "detail": "..."}
    event: answer    {"text": "..."}          (the final markdown answer)
    event: done      { ...the AskOut fields... }
    event: error     {"message": "..."}

The browser renders the steps live and only swaps in the answer on `done`, so the
visible behaviour is unchanged and there is still exactly one source of truth for
what was persisted.

The agent's nodes are plain functions over one state dict, so a run is executed
in a worker thread and each node's trace addition is published as it happens.
"""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Callable, Dict, List

SENTINEL = object()


def _sse(event: str, data: Dict[str, Any]) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))


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


