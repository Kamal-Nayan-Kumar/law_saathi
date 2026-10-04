#!/usr/bin/env python3
"""Write a ChatGPT image job, run it through ego-browser, print the result.

The ego nodejs runtime sees neither the parent env nor extra CLI args, so the
job is staged in scripts/.gpt-job.json and the script is piped in on stdin.

    python3 scripts/gpt_job.py --out web/public/images/x.png "prompt text"
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JOB = os.path.join(HERE, ".gpt-job.json")
RUNNER = os.path.join(HERE, "gpt-asset.mjs")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--space", type=int, default=6)
    ap.add_argument("--wait", type=int, default=240000, help="ms to wait for the image")
    ap.add_argument("prompt")
    args = ap.parse_args()

    with open(JOB, "w") as fh:
        json.dump(
            {"space": args.space, "out": args.out, "prompt": args.prompt, "waitMs": args.wait},
            fh,
        )
    with open(RUNNER) as fh:
        proc = subprocess.run(
            ["ego-browser", "nodejs"], stdin=fh, capture_output=True, text=True
        )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())