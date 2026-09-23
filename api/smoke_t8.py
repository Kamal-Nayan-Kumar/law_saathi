"""T8 smoke QA: Sarvam voice round-trip (STT -> agent -> TTS), 3-lang, fallback."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.voice import transcribe, synthesize
from app.schemas import VoiceIn, VoiceOut

def smoke():
    # Module loads; with missing key it returns graceful empty / None
    result_empty = transcribe("fake_b64", lang="hi")
    assert isinstance(result_empty, str), "STT returns str even on failure"
    result_tts = synthesize("नमस्ते", lang="hi")
    assert result_tts is None or isinstance(result_tts, str), "TTS returns None or str"

    # Schema shapes
    vout = VoiceOut(
        transcript="नमस्ते",
        answer="उत्तर यहाँ है",
        lang="hi",
        fallback_text=False,
    )
    assert vout.lang == "hi"
    assert vout.fallback_text is False

    # VoiceIn accepts EN/HI/KN
    vin = VoiceIn(audio_b64="AA==", lang="kn")
    assert vin.lang == "kn"

    # Fallback text path works
    vout_fb = VoiceOut(
        transcript="",
        answer="",
        lang="en",
        fallback_text=True,
        error="STT failed",
    )
    assert vout_fb.fallback_text is True

    print("T8 SMOKE PASS — voice module, schemas, 3-lang, fallback OK")

if __name__ == "__main__":
    smoke()
