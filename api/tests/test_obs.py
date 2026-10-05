"""The observability log is for looking at runs, so it has to be trustworthy."""

import json
import os

from app import obs


def test_nothing_is_recorded_when_the_log_is_off(monkeypatch):
    """Off by default: an unwritable path must never break a user's answer."""
    monkeypatch.delenv("LAWSAATHI_OBS_LOG", raising=False)
    assert obs.new_run(user_id=1) is None


def test_a_run_is_written_as_one_json_line(tmp_path, monkeypatch):
    path = str(tmp_path / "runs.jsonl")
    monkeypatch.setenv("LAWSAATHI_OBS_LOG", path)
    rec = obs.new_run(user_id="u1", lang="hi", tone="simple", query="my husband stopped paying")
    assert rec is not None
    rec.note("intent", "Detected topic maintenance")
    rec.tool("search_acts", "maintenance wife", 6)
    rec.verified(True, 0.93, 1)
    rec.finish(provider="groq:gpt-oss", answer_len=900)

    rows = obs.read(path)
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["lang"] == "hi"
    assert r["user"] == "u1"
    assert r["nodes"] == ["intent"]
    assert r["decisions"][0]["node"] == "intent"
    assert r["tools"][0] == {"tool": "search_acts", "query": "maintenance wife", "hits": 6}
    assert r["verify"] == {"verified": True, "confidence": 0.93, "retries": 1}
    assert r["provider"] == "groq:gpt-oss"
    assert r["duration_ms"] >= 0


def test_a_repeated_node_keeps_every_decision(tmp_path, monkeypatch):
    """The verifier retrying and searching again is the behaviour most worth
    seeing, so a second visit must add a decision without losing the path."""
    monkeypatch.setenv("LAWSAATHI_OBS_LOG", str(tmp_path / "r.jsonl"))
    rec = obs.new_run(query="q")
    rec.note("verifier", "Rejected the draft")
    rec.note("tools", "searched again")
    rec.note("verifier", "Accepted the draft")
    rec.finish(provider="groq")
    r = obs.read(str(tmp_path / "r.jsonl"))[0]
    assert r["nodes"] == ["verifier", "tools"], r["nodes"]
    assert [d["node"] for d in r["decisions"]] == \
        ["verifier", "tools", "verifier"]


def test_bare_act_and_web_results_are_counted_separately(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWSAATHI_OBS_LOG", str(tmp_path / "r.jsonl"))
    rec = obs.new_run(query="q")
    obs.record_run(rec, {
        "trace_detail": [{"node": "tools", "detail": "searched"}],
        "evidence": [
            {"payload": {"act": "HMA", "section": "Section 24"}},
            {"payload": {"act": "HAMA", "section": "Section 18"}},
            {"payload": {"url": "https://example.com", "title": "web"}},
        ],
        "verified": True, "confidence": 0.8, "retries": 0,
        "provider": "groq", "answer": "x",
    })
    r = obs.read(str(tmp_path / "r.jsonl"))[0]
    tools = {t["tool"]: t["hits"] for t in r["tools"]}
    assert tools == {"search_acts": 2, "search_web": 1}, tools


def test_an_unwritable_log_does_not_raise(tmp_path, monkeypatch):
    """Recording is best-effort. If it can never break a user's answer, that has
    to be true even when the path is bad."""
    monkeypatch.setenv("LAWSAATHI_OBS_LOG", str(tmp_path / "nope" / "x" / "r.jsonl"))
    rec = obs.new_run(query="q")
    rec.note("intent", "x")
    rec.finish(provider="groq")  # must not raise, and must not write


def test_the_stats_script_reads_the_same_shape(tmp_path, monkeypatch):
    import importlib.util
    import os

    monkeypatch.setenv("LAWSAATHI_OBS_LOG", str(tmp_path / "r.jsonl"))
    rec = obs.new_run(query="maintenance")
    rec.note("intent", "topic")
    rec.verified(True, 0.9, 0)
    rec.finish(provider="groq:gpt-oss")

    # Loaded by path: api/scripts is a directory of scripts, not a package.
    spec = importlib.util.spec_from_file_location(
        "agent_stats",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "agent_stats.py"))
    agent_stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent_stats)

    rows = agent_stats.load(str(tmp_path / "r.jsonl"))
    assert len(rows) == 1
    assert agent_stats.load(str(tmp_path / "missing.jsonl")) == []


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    """A half-written line from a killed process must not break the report."""
    path = tmp_path / "r.jsonl"
    path.write_text('{"id": "a"}\nnot json\n\n{"id": "b"}\n')
    rows = obs.read(str(path))
    assert [r["id"] for r in rows] == ["a", "b"], rows