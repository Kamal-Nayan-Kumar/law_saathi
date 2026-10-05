#!/usr/bin/env python3
"""Screenshot local routes at several viewport sizes via ego-browser.

    python3 scripts/shots.py / landing 1440x900 390x844

Reports horizontal overflow per size, which is the failure mode that a single
desktop screenshot never shows.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JOB = os.path.join(HERE, ".shot-job.json")
RUNNER = os.path.join(HERE, "shots.mjs")

ROUTES = {
    "landing": "/",
    "login": "/login",
    "signup": "/login?mode=register",
    "chat": "/chat",
}

# The ego-browser task space to shoot in. Passed rather than hardcoded in the
# runner, so closing a space does not break this script.
SPACE = os.environ.get("EGO_SPACE", "1")

SIZES = {
    "xl": "2560x1440",
    "lg": "1920x1080",
    "laptop": "1440x900",
    "small": "1024x768",
    "tablet": "768x1024",
    "phone": "390x844",
    "tiny": "360x740",
}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("routes:", " ".join(ROUTES))
        print("sizes: ", " ".join(f"{k}={v}" for k, v in SIZES.items()))
        return 1

    what = sys.argv[1]
    names = what.split(",")
    sizes = sys.argv[2:] or ["laptop"]

    route = ROUTES.get(names[0], names[0])
    label = names[0]

    resolved = [SIZES.get(s, s) for s in sizes]
    with open(JOB, "w") as fh:
        json.dump({"route": route, "name": label, "sizes": resolved,
                   "space": int(SPACE)}, fh)

    with open(RUNNER) as fh:
        proc = subprocess.run(
            ["ego-browser", "nodejs"], stdin=fh, capture_output=True, text=True
        )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())