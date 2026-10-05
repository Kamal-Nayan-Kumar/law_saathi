"""Read the SSE ask endpoint the way the browser does, and time each step.

    python3 api/scripts/stream_probe.py "my husband stopped paying maintenance"

Prints the wall-clock delay before each step, which is the number the chat
actually feels like.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import probe  # noqa: E402


def main(argv):
    query = argv[1] if len(argv) > 1 else "how do I get a mutual consent divorce?"
    sid = probe.new_session(1, "stream probe")

    body = json.dumps({"query": query, "lang": "en", "tone": "simple"}).encode()
    req = urllib.request.Request(
        "%s/sessions/%d/ask/stream" % (probe.API, sid),
        data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-internal-secret", probe.SECRET)
    req.add_header("x-user-id", "1")
    req.add_header("x-user-email", "qa@example.com")
    req.add_header("Accept", "text/event-stream")

    t0 = time.time()
    event = None
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                at = time.time() - t0
                data = json.loads(line[6:])
                if event == "step":
                    print("  %6.2fs  %-10s %s" % (
                        at, data.get("node"), (data.get("detail") or "")[:88]))
                elif event == "error":
                    print("  %6.2fs  ERROR %s" % (at, data.get("message")))
                    return 1
                elif event == "done":
                    print("  %6.2fs  DONE  verified=%s conf=%.2f provider=%s"
                          % (at, data.get("verified"), data.get("confidence"),
                             data.get("provider")))
                    print("\n" + (data.get("answer") or ""))
    print("\ntotal %.2fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))