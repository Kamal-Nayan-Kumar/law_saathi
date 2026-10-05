"""Per-run observability for the agent.

The question "how do we, as developers, see that it is agentic?" has a simple
answer: record what each node decided and let it be queried. LangSmith does this
when a key is present, but it is off on most free tiers and it is a network
service — so the run also writes a local JSONL line it never needed permission
for.

What is recorded per run:

    id, user, lang, tone, query, duration_ms, provider
    nodes[]        which nodes ran, in order
    decisions[]    what each one decided, with its reason
    tools[]        what was searched, and what came back
    verify         verdict, confidence, retry count

That is enough to graph node frequency, latency, retry rate, provider split and
distinct execution paths over any window, which is exactly what
`api/scripts/agent_stats.py` reads back.

    LAWSAATHI_OBS_LOG=./tmp/agent-runs.jsonl uvicorn app.main:app
    python3 api/scripts/agent_stats.py
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_LOG_LOCK = threading.Lock()

# Node order for the pipeline view. Kept here so a reader does not have to open
# agent.py to know the shape of the system.
NODE_ORDER = ("intent", "planner", "tools", "reason", "verifier", "response")


def log_path() -> Optional[str]:
    path = os.environ.get("LAWSAATHI_OBS_LOG", "").strip()
    return path or None


class RunRecorder:
    """Collects one run and writes it as a single JSONL line when finished."""

    def __init__(self, run_id: str, user_id: Any = None, lang: str = "en",
                 tone: str = "simple", query: str = "") -> None:
        self.run_id = run_id
        self.started = time.time()
        self.record: Dict[str, Any] = {
            "id": run_id,
            "ts": self.started,
            "user": str(user_id) if user_id is not None else None,
            "lang": lang,
            "tone": tone,
            "query": query[:400],
            "nodes": [],
            "decisions": [],
            "tools": [],
            "verify": {},
        }
        self._seen: set = set()

    def note(self, node: str, detail: str) -> None:
        """Record that a node ran and what it decided.

        Nodes outside the main pipeline (contextualize) are kept, not dropped: a
        follow-up taking the rewrite path is exactly the kind of thing you
        cannot see from the pipeline diagram alone.
        """
        if node not in self._seen:
            self._seen.add(node)
            self.record["nodes"].append(node)
        self.record["decisions"].append({
            "node": node, "detail": (detail or "")[:400],
        })

    def tool(self, name: str, query: str, hits: int) -> None:
        self.record["tools"].append({
            "tool": name, "query": query[:120], "hits": hits,
        })

    def verified(self, ok: bool, confidence: float, retries: int) -> None:
        self.record["verify"] = {
            "verified": bool(ok),
            "confidence": round(float(confidence), 4),
            "retries": int(retries),
        }

    def finish(self, provider: str = "", answer_len: int = 0,
               clarification: bool = False, oos: bool = False) -> None:
        path = log_path()
        if not path:
            return
        self.record["duration_ms"] = int((time.time() - self.started) * 1000)
        self.record["provider"] = provider
        self.record["answer_len"] = answer_len
        self.record["clarification"] = clarification
        self.record["oos"] = oos
        try:
            with _LOG_LOCK, open(path, "a") as fh:
                fh.write(json.dumps(self.record, ensure_ascii=False) + "\n")
        except OSError as e:  # noqa: BLE001 — observability must never break chat
            logger.warning("agent obs log write failed (%r)", e)


def new_run(user_id: Any = None, lang: str = "en", tone: str = "simple",
            query: str = "") -> Optional[RunRecorder]:
    """Start recording a run, or return None when the log is switched off."""
    if not log_path():
        return None
    return RunRecorder(run_id=uuid.uuid4().hex[:12], user_id=user_id,
                       lang=lang, tone=tone, query=query)


def record_run(recorder: Optional[RunRecorder], state: Dict[str, Any]) -> None:
    """Fold one finished agent run into the log.

    Kept out of agent.py on purpose: recording is a property of serving a
    request, not of running the graph, so the graph stays free of HTTP and file
    concerns and its tests do not need to know about either.
    """
    if recorder is None:
        return
    for step in state.get("trace_detail") or []:
        recorder.note(str(step.get("node", "")), str(step.get("detail", "")))

    n_acts = n_web = 0
    for hit in state.get("evidence") or []:
        payload = hit.get("payload") or {} if isinstance(hit, dict) else {}
        if payload.get("url"):
            n_web += 1
        else:
            n_acts += 1
    if n_acts:
        recorder.tool("search_acts", "", n_acts)
    if n_web:
        recorder.tool("search_web", "", n_web)

    recorder.verified(bool(state.get("verified")),
                      float(state.get("confidence") or 0.0),
                      int(state.get("retries") or 0))
    recorder.finish(provider=str(state.get("provider", "")),
                    answer_len=len(str(state.get("answer") or "")),
                    clarification=bool(state.get("clarification")),
                    oos=bool(state.get("oos_redirect")))


def read(path: str) -> List[Dict[str, Any]]:
    """Every recorded run, oldest first. Unparseable lines are skipped."""
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows
