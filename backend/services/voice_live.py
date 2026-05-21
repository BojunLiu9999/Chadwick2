"""
Azure VoiceLive WebSocket client.

Wraps the Azure OpenAI Realtime protocol so the rest of the backend just opens
a session, pushes 24 kHz PCM mic frames in, and receives transcript / audio
events back. Wake-word gating (default "Chadwick") is enforced via the system
prompt — the model is instructed to stay silent on utterances that do not
address it.

Audio format on both ends defaults to 24 kHz mono 16-bit little-endian PCM
(Azure Realtime default). The voice router downsamples replies to 16 kHz
before handing them to the robot speaker.
"""
import asyncio
import base64
import json
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import websockets
from websockets.client import WebSocketClientProtocol

from config import settings


PCM_SAMPLE_RATE_HZ = 24000


def _system_prompt(wake_word: str) -> str:
    return (
        f"You are {wake_word}, a friendly AI assistant embodied in a Unitree "
        f"G1 humanoid robot at the USYD TechLab.\n\n"
        f"WAKE-WORD BEHAVIOUR:\n"
        f"- Only respond when the user addresses you as \"{wake_word}\" "
        f"(or \"Hey {wake_word}\", \"Hi {wake_word}\").\n"
        f"- If the user's most recent utterance does NOT mention "
        f"\"{wake_word}\", stay completely silent: emit no audio and no text. "
        f"Do not acknowledge, apologise, or ask for clarification.\n"
        f"- Once addressed, reply naturally like a helpful AI assistant in "
        f"1-2 short sentences (under 30 words). Be warm, conversational, "
        f"concise."
    )


@dataclass
class VoiceEvent:
    """One event surfaced by VoiceLiveSession.events()."""
    kind: str  # user_transcript | assistant_text_delta | assistant_text_done
               # | assistant_audio_delta | response_done | error
    text: Optional[str] = None
    audio_pcm_24k: Optional[bytes] = None


def _build_url() -> str:
    base = (settings.AZURE_VOICE_LIVE_ENDPOINT or "").strip()
    if not base:
        raise RuntimeError("AZURE_VOICE_LIVE_ENDPOINT not configured")

    parsed = urlparse(base)
    existing: dict[str, str] = {}
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                existing[k] = v
    if "api-version" not in existing:
        existing["api-version"] = "2024-10-01-preview"
    if "model" not in existing and settings.AZURE_VOICE_LIVE_MODEL:
        existing["model"] = settings.AZURE_VOICE_LIVE_MODEL
    return urlunparse(parsed._replace(query=urlencode(existing)))


class VoiceLiveSession:
    """One conversation with Azure VoiceLive."""

    def __init__(self) -> None:
        self._ws: Optional[WebSocketClientProtocol] = None

    async def __aenter__(self) -> "VoiceLiveSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(self) -> None:
        api_key = (settings.AZURE_VOICE_LIVE_API_KEY or "").strip()
        if not api_key:
            raise RuntimeError("AZURE_VOICE_LIVE_API_KEY not configured")

        url = _build_url()
        self._ws = await websockets.connect(
            url,
            extra_headers={"api-key": api_key},
            max_size=16 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )

        wake_word = (settings.AZURE_VOICE_LIVE_WAKE_WORD or "Chadwick").strip()
        await self._send({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": _system_prompt(wake_word),
                "voice": (settings.AZURE_VOICE_LIVE_VOICE or "alloy").strip(),
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
            },
        })

    async def send_audio_chunk(self, pcm16_24k: bytes) -> None:
        if not pcm16_24k:
            return
        if self._ws is None:
            raise RuntimeError("VoiceLive session is not connected")
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm16_24k).decode("ascii"),
        })

    async def events(self) -> AsyncIterator[VoiceEvent]:
        if self._ws is None:
            raise RuntimeError("VoiceLive session is not connected")
        async for raw in self._ws:
            try:
                msg = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else None
            except json.JSONDecodeError:
                continue
            if not msg:
                continue
            t = msg.get("type", "")

            if t == "conversation.item.input_audio_transcription.completed":
                yield VoiceEvent(kind="user_transcript", text=msg.get("transcript", "") or "")
            elif t == "response.audio_transcript.delta":
                yield VoiceEvent(kind="assistant_text_delta", text=msg.get("delta", "") or "")
            elif t == "response.audio_transcript.done":
                yield VoiceEvent(kind="assistant_text_done", text=msg.get("transcript", "") or "")
            elif t == "response.audio.delta":
                b64 = msg.get("delta", "") or ""
                if b64:
                    try:
                        yield VoiceEvent(kind="assistant_audio_delta", audio_pcm_24k=base64.b64decode(b64))
                    except Exception:
                        pass
            elif t == "response.done":
                yield VoiceEvent(kind="response_done")
            elif t == "error":
                err = msg.get("error") or msg
                yield VoiceEvent(kind="error", text=json.dumps(err)[:500])

    async def _send(self, payload: dict) -> None:
        if self._ws is None:
            raise RuntimeError("VoiceLive session is not connected")
        await self._ws.send(json.dumps(payload))

    async def close(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
