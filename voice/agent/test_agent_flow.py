import asyncio
import os
import sys
from pathlib import Path

# Add paths
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import MultilingualSarvamTTS, clean_for_speech, LawSaathiLLM
from livekit.agents import llm
from livekit.agents.types import APIConnectOptions


async def verify_tts():
    print("--- 1. Testing MultilingualSarvamTTS ---")
    tts_engine = MultilingualSarvamTTS()
    test_cases = [
        ("en", "You have the right to claim maintenance from your husband under the law."),
        ("hi", "कानून के अनुसार आप अपने पति से भरण-पोषण पाने की हकदार हैं।"),
        ("kn", "ಕಾನೂನಿನ ಪ್ರಕಾರ ನಿಮ್ಮ ಗಂಡನಿಂದ ಜೀವನಾಂಶ ಪಡೆಯುವ ಹಕ್ಕು ನಿಮಗಿದೆ."),
    ]
    for lang, text in test_cases:
        selected = tts_engine._select(text)
        print(f"[{lang.upper()}] Selected speaker: {selected._opts.speaker} ({selected._opts.target_language_code})")
        stream = tts_engine.synthesize(text)
        frames = []
        async for frame in stream:
            frames.append(frame)
        print(f"[{lang.upper()}] Synthesized audio chunks: {len(frames)}")
        assert len(frames) > 0, f"No audio frames for {lang}"
    print("TTS test PASSED!\n")


async def verify_llm_integration():
    print("--- 2. Testing LawSaathiLLM with FastAPI Backend ---")
    model = LawSaathiLLM()
    chat_ctx = llm.ChatContext()
    chat_ctx.add_message(
        role="user",
        content="पति से भरण-पोषण कैसे मांग सकते हैं?",
    )

    stream = model.chat(chat_ctx=chat_ctx)
    chunks = []
    async for chunk in stream:
        if chunk.delta and chunk.delta.content:
            chunks.append(chunk.delta.content)

    full_reply = "".join(chunks)
    print(f"Received reply ({len(full_reply)} chars):")
    print(full_reply[:300] + "...")
    assert len(full_reply) > 20, "Reply is too short"
    print("LLM integration test PASSED!\n")


async def main():
    import livekit.agents.utils.http_context as http_context
    async with http_context.open():
        await verify_tts()
        await verify_llm_integration()
    print("ALL LIVEKIT AGENT INTEGRATION TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(main())
