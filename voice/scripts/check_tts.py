"""Check the TTS router against the real Sarvam API.

The router is the one piece of this project that cannot be checked by reading
the code: the claim it makes is that three speaker ids work and that the
right one is picked for the right script. So this runs all three languages
through the router exactly the way the framework does, and reports the audio
it got back.

    cd voice && .venv/bin/python scripts/check_tts.py
"""
from __future__ import annotations

import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from livekit.agents.utils import http_context  # noqa: E402

from agent.tts_router import SarvamLanguageRouter, detect_language  # noqa: E402

SAMPLES = {
    "en-IN": (
        "Under the Dowry Prohibition Act, 1961, demanding dowry is an offence."
    ),
    "hi-IN": (
        "दहेज प्रथा निषेध अधिनियम, 1961 के तहत दहेज मांगना अपराध है।"
    ),
    "kn-IN": (
        "ದೋಹ ಪ್ರತಿಬಂಧ ಕಾಯ್ದೆ, 1961 ಪ್ರಕಾರ ದೋಹ ಕೋಲಿಕೆ ಮಾಡುವುದು ಅಪರಾಧ."
    ),
}


async def speak(router: SarvamLanguageRouter, text: str) -> tuple[int, float]:
    """Synthesize one string the way the framework's StreamAdapter does."""
    frames = 0
    duration = 0.0
    async with router.synthesize(text) as stream:
        async for event in stream:
            frames += 1
            duration += event.frame.duration
    return frames, duration


async def main() -> int:
    router = SarvamLanguageRouter()
    failures = 0
    try:
        # The Sarvam plugin wants a job context for its shared HTTP session.
        # Outside a worker there is none, so one is opened by hand.
        async with http_context.open():
            for expected, text in SAMPLES.items():
                picked = detect_language(text)
                frames, duration = await speak(router, text)
                ok = picked == expected and frames > 0 and duration > 0.5
                failures += 0 if ok else 1
                print(
                    f"{'OK ' if ok else 'FAIL'} expected={expected} picked={picked} "
                    f"frames={frames} audio={duration:.2f}s text={text[:40]!r}"
                )
    finally:
        await router.aclose()
    print("all three languages produced audio" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
