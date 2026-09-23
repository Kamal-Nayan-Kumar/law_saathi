"""Download the filtered family-acts subset of vaquill/open-india-law.

Streams ONLY in_central_legislation.parquet (never the full ~54GB dump),
keeps rows matching the 6-7 family acts, and saves them locally as JSONL:

    .venv/bin/python api/scripts/download_corpus.py --limit 50   # smoke test
    .venv/bin/python api/scripts/download_corpus.py              # full pull

Needs HF_TOKEN in api/.env AND access approved on the gated dataset page:
https://huggingface.co/datasets/vaquill/open-india-law
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.ingest import canonical_act  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = REPO / "data" / "corpus" / "open-india-law-family-acts.jsonl"


def matching_act(row: dict):
    title = str(row.get("title") or row.get("act") or row.get("name") or "")
    hit = canonical_act(title)
    if hit:
        return hit
    blob = " ".join(str(row.get(k, "")) for k in row.keys())[:500]
    return canonical_act(blob)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download filtered family-acts corpus")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None,
                    help="max MATCHED rows to save (default: all)")
    ap.add_argument("--scan-limit", type=int, default=None,
                    help="max rows to scan (default: whole file)")
    args = ap.parse_args(argv)

    from datasets import load_dataset

    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("HF_TOKEN is empty — add it to api/.env")
        return 1
    ds = load_dataset("vaquill/open-india-law",
                      data_files="in_central_legislation.parquet",
                      split="train", streaming=True, token=token)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    scanned = saved = 0
    with out.open("w", encoding="utf-8") as f:
        for row in ds:
            scanned += 1
            act = matching_act(dict(row))
            if act is None:
                if args.scan_limit and scanned >= args.scan_limit:
                    break
                continue
            record = {"act": act,
                      "row": {k: (v if isinstance(v, (str, int, float, bool))
                                  or v is None else str(v))
                              for k, v in row.items()}}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            counts[act] += 1
            saved += 1
            if saved % 100 == 0:
                print("scanned %d, saved %d" % (scanned, saved), flush=True)
            if args.limit and saved >= args.limit:
                break
            if args.scan_limit and scanned >= args.scan_limit:
                break
    print("done: scanned %d rows, saved %d" % (scanned, saved))
    for act, n in counts.most_common():
        print("  %-55s %d" % (act, n))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
