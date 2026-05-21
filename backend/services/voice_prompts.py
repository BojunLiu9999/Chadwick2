"""
TTS helper for canned voice prompts (password gate, walk feedback, errors).

Why this exists: the LLM stays silent on utterances that don't address the
wake word, and even when it does respond we can't depend on the model to
phrase safety-critical prompts ("please say the password"). We synthesize
those ourselves via OpenAI tts-1 and cache them in-memory after first use
so the password prompt sounds instant.
"""
import asyncio
import sys
from typing import Optional

from config import settings
from services.llm import _downsample_24k_to_16k


_cache: dict[str, bytes] = {}
_cache_lock = asyncio.Lock()


def _synthesize_sync(text: str) -> bytes:
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot synthesize voice prompt")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    speech = client.audio.speech.create(
        model=settings.OPENAI_TTS_MODEL,
        voice=settings.OPENAI_TTS_VOICE,
        input=text,
        response_format="pcm",
    )
    pcm_24k = speech.read() if hasattr(speech, "read") else speech.content
    return _downsample_24k_to_16k(pcm_24k)


async def get_prompt_pcm(text: str) -> Optional[bytes]:
    """Return cached 16 kHz mono PCM for `text`, synthesizing on first miss.

    Returns None if synthesis fails (no API key, network error). Callers should
    treat None as "speak nothing" — the gate still works, just without audio
    feedback.
    """
    if not text:
        return None
    cached = _cache.get(text)
    if cached is not None:
        return cached

    async with _cache_lock:
        cached = _cache.get(text)
        if cached is not None:
            return cached
        try:
            pcm = await asyncio.to_thread(_synthesize_sync, text)
        except Exception as exc:
            print(f"[voice_prompts] TTS failed for {text!r}: {exc}", file=sys.stderr)
            return None
        _cache[text] = pcm
        return pcm
