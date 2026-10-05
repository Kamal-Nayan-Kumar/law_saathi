"""Read the agent observability log and draw what the agent is doing.

    LAWSAATHI_OBS_LOG=./tmp/agent-runs.jsonl   # the server writes this
    python3 api/scripts/agent_stats.py --last 50
    python3 api/scripts/agent_stats.py --pipeline

The pipeline view is the one that answers "is it actually agentic?": it shows,
for a window of real runs, which nodes ran, how often each one decided
something, how long each took, and where the retries went. A run that always
takes the same path through the same nodes is a pipeline wearing a graph's
clothes, and this is how you see that at a glance.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.obs import NODE_ORDER  # noqa: E402

DEFAULT_LOG = os.environ.get("LAWSAATHI_OBS_LOG", "./tmp/agent-runs.jsonl")


def load(path: str, last: int = 0) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-last:] if last else rows


def bar(value: float, maximum: float, width: int = 24,
        ch: str = "#") -> str:
    if maximum <= 0:
        return ""
    n = int(round((value / maximum) * width))
    return ch * max(0, n)


def pipeline(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    if not total:
        print("no runs logged yet")
        return

    node_runs = Counter()
    node_decisions: Counter = Counter()
    node_ms: Dict[str, List[float]] = defaultdict(list)
    providers = Counter()
    outcomes = Counter()
    langs = Counter()
    retries = 0
    durations: List[float] = []

    for r in rows:
        for n in r.get("nodes") or []:
            node_runs[n] += 1
        for step in r.get("decisions") or []:
            node_decisions[step.get("node", "")] += 1
        durations.append(float(r.get("duration_ms") or 0))
        providers[(r.get("provider") or "none").split(":")[0] or "none"] += 1
        langs[r.get("lang") or "?"] += 1
        retries += int((r.get("verify") or {}).get("retries") or 0)
        if r.get("oos"):
            outcomes["out of scope"] += 1
        elif r.get("clarification"):
            outcomes["clarified"] += 1
        elif (r.get("verify") or {}).get("verified"):
            outcomes["verified answer"] += 1
        else:
            outcomes["unverified"] += 1

    print(f"\n{total} runs\n")
    print("Runs means: how many of these questions took that node at all.")
    print("Says means: how many times it produced a recorded decision — a")
    print("retried verifier or a re-planned tools step raises this, not the first.\n")

    # Time is attributed evenly across the decisions a run made. That is an
    # estimate, not a measurement, and it is labelled as one: there is no
    # per-node clock inside the graph, and adding one would mean threading
    # timing through every node for a number nobody reads precisely.
    for r in rows:
        n_dec = max(1, len(r.get("decisions") or []))
        share = float(r.get("duration_ms") or 0) / n_dec
        for step in r.get("decisions") or []:
            node_ms[step.get("node", "")].append(share)
    max_ms = max([sum(v) / len(v) for v in node_ms.values()] or [1]) or 1

    print(f"{'NODE':16}{'RAN':>5}{'%':>7}{'SAYS':>6}{'%':>7}{'ms*':>8}")
    print("-" * 52)
    ordered = list(NODE_ORDER) + [n for n in node_runs if n not in NODE_ORDER]
    for node in ordered:
        ran = node_runs[node]
        if not ran and node_decisions[node] == 0:
            continue
        times = node_ms.get(node) or []
        mean = sum(times) / len(times) if times else 0
        print(f"{node:16}{ran:5}{100*ran/total:6.1f}%"
              f"{node_decisions[node]:6}{100*node_decisions[node]/max(1, len(rows)):6.1f}%"
              f"{mean:8.0f}  {bar(mean, max_ms, 10)}")
    print("* time per node is estimated: see run_golden for why")

    print("\nOUTCOMES")
    for name, n in outcomes.most_common():
        print(f"  {name:18} {n:5}  {100*n/total:5.1f}%  "
              f"{bar(n, total, 20)}")

    print("\nPROVIDERS")
    for name, n in providers.most_common():
        print(f"  {name:18} {n:5}  {100*n/total:5.1f}%  {bar(n, total, 20)}")

    print("\nLANGUAGES")
    for name, n in langs.most_common():
        print(f"  {name:18} {n:5}  {100*n/total:5.1f}%  {bar(n, total, 20)}")

    # "none" means no provider was reached at all — every key exhausted. That
    # is the failure mode worth catching before a user does, so it is called out
    # rather than left as a bar in the chart.
    none_pct = 100 * providers.get("none", 0) / total
    if none_pct > 25:
        print(f"\n  ! {none_pct:.0f}% of runs reached no LLM provider at all.")
        print("    Every key is exhausted or rate-limited. Answers fell back to")
        print("    the template. Check GROQ / OPENROUTER / OPENCODE keys.")

    d = sorted(durations)
    p50 = d[len(d) // 2] if d else 0
    p95 = d[int(len(d) * 0.95)] if d else 0
    print(f"\nLATENCY   p50 {p50/1000:.1f}s   p95 {p95/1000:.1f}s   "
          f"max {max(d, default=0)/1000:.1f}s")
    print(f"RETRIES   {retries} total, {100*retries/max(1,total):.1f}% of runs")

    # The real signal of agentic behaviour: how often the run took a different
    # path. Identical paths across every run is a pipeline, not an agent.
    shapes = Counter(tuple(r.get("nodes") or []) for r in rows)
    print(f"\nPATHS     {len(shapes)} distinct")
    for shape, n in shapes.most_common(6):
        print(f"  {n:5} x  {' -> '.join(shape)}")


def sample(rows: List[Dict[str, Any]], n: int = 3) -> None:
    """Print full decision logs, so a run can be read end to end."""
    for r in rows[-n:]:
        print("=" * 74)
        print(f"run {r['id']}  lang={r['lang']}  provider={r.get('provider')}")
        print(f"q: {r.get('query')}")
        print(f"{r.get('duration_ms', 0)/1000:.1f}s  "
              f"verified={(r.get('verify') or {}).get('verified')}  "
              f"conf={(r.get('verify') or {}).get('confidence')}")
        for step in r.get("decisions") or []:
            print(f"  [{step['node']:14}] {step['detail']}")
        for t in r.get("tools") or []:
            print(f"  [tool {t['tool']:12}] {t.get('query','')} -> {t.get('hits')} hits")
        print()


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--last", type=int, default=50)
    ap.add_argument("--pipeline", action="store_true",
                    help="aggregate view (default)")
    ap.add_argument("--show", type=int, default=0,
                    help="print N full run logs instead of the aggregate")
    args = ap.parse_args(argv[1:])

    rows = load(args.log, args.last)
    if not rows:
        print(f"no runs in {args.log}\n"
              f"start the API with LAWSAATHI_OBS_LOG={args.log} and ask something")
        return 1
    if args.show:
        sample(rows, args.show)
    else:
        pipeline(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))