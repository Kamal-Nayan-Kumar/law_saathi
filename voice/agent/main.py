"""Entry point for the Law Saathi voice worker.

Run it with the LiveKit CLI in development mode, which is what the README
tells you to do:

    lk agent dev

or directly:

    python -m agent.main download-files
    python -m agent.main start

The worker talks to the LiveKit server over `LIVEKIT_URL`, so a local
`livekit-server --dev` on ws://localhost:7880 is enough. No LiveKit Cloud
account is needed for the demo.

The agent is started by the server, not by this process: `AgentServer` exposes
an HTTP endpoint that the LiveKit server calls when someone joins a room, so
the worker has to be running before the room is opened, not after.
"""
from __future__ import annotations

import logging

from livekit import agents
from livekit.agents import JobContext

from . import config
from .saathi import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("law-saathi-voice")

server = agents.AgentServer()


@server.rtc_session(agent_name="law-saathi")
async def saathi(ctx: JobContext) -> None:
    await run(ctx)


def main() -> None:
    missing = config.missing_keys()
    if missing:
        # Failing here is better than failing later: the worker would join the
        # room, look mute, and never answer.
        raise SystemExit(
            "Missing keys: " + ", ".join(missing) + ". They are read from api/.env."
        )
    logger.info(
        "worker starting: livekit=%s api=%s", config.LIVEKIT_URL, config.LAWSAATHI_API
    )
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
