"""
OpenAI-backed chat + TTS for the robot's speech-only mode.

Chat: gpt-4o-mini, single-turn (UI carries the transcript).
TTS:  tts-1 → raw PCM 24 kHz mono 16-bit → resampled to 16 kHz mono for
      G1 AudioClient.PlayStream (which expects 16 kHz mono).
"""
import asyncio
import struct
from dataclasses import dataclass

from config import settings


SYSTEM_PROMPT = (
    "You are a friendly Unitree G1 humanoid robot greeting visitors at the "
    "USYD TechLab capstone demo. Reply in 1-2 short English sentences. "
    "Keep it warm, conversational, and under 30 words."
)


@dataclass
class ChatResult:
    reply: str
    pcm_16k_mono: bytes


def _downsample_24k_to_16k(pcm_24k: bytes) -> bytes:
    # G1 PlayStream wants 16 kHz mono 16-bit signed little-endian PCM.
    # OpenAI tts-1 with response_format="pcm" returns 24 kHz mono LE16.
    # Linear interpolation is good enough for speech at this rate ratio.
    samples = struct.unpack(f"<{len(pcm_24k) // 2}h", pcm_24k)
    n_in = len(samples)
    n_out = (n_in * 2) // 3
    out = [0] * n_out
    for i in range(n_out):
        src = i * 1.5
        idx = int(src)
        frac = src - idx
        a = samples[idx]
        b = samples[idx + 1] if idx + 1 < n_in else a
        v = int(a + (b - a) * frac)
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        out[i] = v
    return struct.pack(f"<{n_out}h", *out)


def _chat_and_tts_sync(user_message: str) -> ChatResult:
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    # Import lazily so the backend boots even when the openai package is
    # absent (e.g. someone running ROBOT_MODE=mock without the chat dep).
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    chat = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
        max_tokens=120,
    )
    reply = (chat.choices[0].message.content or "").strip()
    if not reply:
        raise RuntimeError("LLM returned empty reply")

    speech = client.audio.speech.create(
        model=settings.OPENAI_TTS_MODEL,
        voice=settings.OPENAI_TTS_VOICE,
        input=reply,
        response_format="pcm",
    )
    pcm_24k = speech.read() if hasattr(speech, "read") else speech.content
    pcm_16k = _downsample_24k_to_16k(pcm_24k)
    return ChatResult(reply=reply, pcm_16k_mono=pcm_16k)


async def chat_and_tts(user_message: str) -> ChatResult:
    return await asyncio.to_thread(_chat_and_tts_sync, user_message)
