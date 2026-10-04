"""Print a persona run in a form a person can actually read.

    python3 api/scripts/show_qa.py tmp/qa-maintenance.json
"""
import json
import sys


def main(path):
    data = json.load(open(path))
    runs = data if isinstance(data, list) else [data]
    for run in runs:
        print("#" * 78)
        print(f"{run['persona']} — {run['who']}  [lang={run['lang']}]")
        print("#" * 78)
        for i, t in enumerate(run["turns"], 1):
            print(f"\n--- turn {i} ({t.get('ms', '?')}ms) ---")
            print(f"USER: {t['q']}")
            if t.get("error"):
                print(f"ERROR: {t['error']}")
                continue
            print(f"[verified={t.get('verified')} conf={t.get('confidence')} "
                  f"clarification={t.get('clarification')} retries={t.get('retries')} "
                  f"provider={t.get('provider')}]")
            print(t.get("answer"))
            if t.get("citations"):
                print("CITES:")
                for n, c in enumerate(t["citations"], 1):
                    print(f"  [{n}] {c}")
            print("TRACE:", " -> ".join(t.get("trace") or []))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))