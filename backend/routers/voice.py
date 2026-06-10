"""
Voice chat WebSocket — bridges the browser mic to Azure VoiceLive and plays
replies back through the robot's onboard speaker. Also implements the
voice-triggered movement gate (password-protected; see "movement gate" below).

Protocol with the browser:

  client → server:  first message  : {"token": "<jwt>"}
                    audio frames   : binary, 24 kHz mono 16-bit LE PCM
                    control msg    : {"type": "stop"}        (optional)

  server → client:  {"type": "ready"}
                    {"type": "user_transcript", "text": "..."}
                    {"type": "assistant_text_delta", "text": "..."}
                    {"type": "response_done",
                     "user_transcript": "...", "assistant_text": "..."}
                    {"type": "voice_event", "event": "MOVE_STATE", "detail": {...}}
                    {"type": "error", "text": "..."}

Wake-word gating is enforced server-side by VoiceLive's system prompt — the
model stays silent on utterances that do not address Chadwick, so no
`response_done` arrives for those and the robot says nothing.

Movement gate:
  Voice can trigger short locomotion pulses (MOVE_FWD/MOVE_BACK/TURN_LEFT/
  TURN_RIGHT) and immediate STOP. The gate is per-WS-connection:
    LOCKED  → first movement keyword prompts for the password
    AWAITING_PASSWORD → user must say VOICE_MOVE_PASSWORD
    UNLOCKED → movement keywords dispatch; auto-relock after VOICE_UNLOCK_TIMEOUT_S
                of no movement. STOP always works in any state.
  Existing route-level safety gates (connected + e-stop clear + motion armed)
  still apply; voice cannot move the robot in any state the panel wouldn't.
"""
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from config import settings
from models.database import AsyncSessionLocal, LogEntry
from services import robot
from services.llm import _downsample_24k_to_16k
from services.voice_live import VoiceLiveSession
from services.voice_prompts import get_prompt_pcm


router = APIRouter()

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROBOT_COMMANDS_DIR = BACKEND_ROOT / "robot_commands"


# ---------------------------------------------------------------------------
# Intent parser
# ---------------------------------------------------------------------------
# Movement intents are recognized by a small regex set rather than via the
# LLM's tool calling — the LLM is for chat, and the safety gate must live in
# our code, not in a system prompt the model might rephrase.

# Whisper consistently mishears "Chadwick" as Chetwick/Chatwick/Shadwick/etc.
# Accept the phonetic family: (c|ch|sh) + vowel(s) + (d|t) + w + vowel(s) + ck.
_WAKE_WORD_RX = re.compile(
    r"\b[cs]h?[aeiou]+[dt]w[aeiou]+ck\b",
    re.IGNORECASE,
)

# stop is checked first and on its own — it's the kid-safety override and
# fires even without a wake word.
_STOP_RX = re.compile(r"\b(stop|halt|freeze)\b", re.IGNORECASE)

# "stand still" / "stand up" — safety-positive "go to known pose" command.
# Wake word required (it's a deliberate action, not a panic halt).
_STAND_RX = re.compile(r"\bstand(\s+(still|up))?\b", re.IGNORECASE)

# Movement keyword → loco command. First match in the transcript wins;
# patterns ordered so more specific phrasings win over single words.
_MOVE_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\b(turn|rotate)\s+left\b", re.IGNORECASE),  "TURN_LEFT",  None),
    (re.compile(r"\b(turn|rotate)\s+right\b", re.IGNORECASE), "TURN_RIGHT", None),
    (re.compile(r"\b(move|walk|go|step)\s+(forward|forwards|ahead)\b", re.IGNORECASE), "MOVE_FWD",  None),
    (re.compile(r"\b(move|walk|go|step)\s+(back|backward|backwards)\b", re.IGNORECASE), "MOVE_BACK", None),
    (re.compile(r"\b(forward|forwards|ahead)\b", re.IGNORECASE), "MOVE_FWD",  None),
    (re.compile(r"\b(backward|backwards)\b", re.IGNORECASE),    "MOVE_BACK", None),
]

# Scripted arm-only routines. Each entry is (pattern, routine name, spoken
# intro, requires_password). All still subject to the connected/e-stop/armed
# route gates. The password flag lets us mix kid-friendly free routines with
# flashier gated ones in the same registry.
_ROUTINE_PATTERNS: list[tuple[re.Pattern, str, str, bool]] = [
    (re.compile(r"\bslow\s*dance\b", re.IGNORECASE),  "slow_dance",  "Let's slow dance!",  False),
    (re.compile(r"\bshake\s*dance\b", re.IGNORECASE), "shake_dance", "Let's shake dance!", True),
]

# Per-direction step counts. forward gets the user-requested 4 steps;
# back/turn get shorter pulses for safety.
_STEPS_BY_COMMAND = {
    "MOVE_FWD":   4.0,
    "MOVE_BACK":  2.0,
    "TURN_LEFT":  2.0,
    "TURN_RIGHT": 2.0,
}


def _classify_intent(transcript: str) -> tuple[str, Optional[str]]:
    """Return (intent, target) where intent is STOP|STAND|MOVE|ROUTINE|NONE.

    - STOP fires on "stop"/"halt"/"freeze" anywhere in the transcript (no wake word).
    - STAND requires wake word + "stand"/"stand still"/"stand up". Safety-positive
      pose command; password-free, beats ROUTINE/MOVE in ordering.
    - MOVE requires the wake word AND a movement keyword; target is the loco command.
    - ROUTINE requires the wake word AND a routine phrase (e.g. "slow dance");
      target is the routine name dispatched to run_dance.py.
    - PASSWORD is matched separately by the state machine.
    """
    if not transcript:
        return ("NONE", None)
    if _STOP_RX.search(transcript):
        return ("STOP", "STOP")
    has_wake = bool(_WAKE_WORD_RX.search(transcript.lower()))
    if has_wake:
        # STAND wins over ROUTINE/MOVE — it's a safety-positive override that
        # should never be misread as anything else.
        if _STAND_RX.search(transcript):
            return ("STAND", "STAND")
        # Routines next — "slow dance" shouldn't be misread as a movement
        # keyword (it isn't today, but future routine phrases might overlap).
        for pattern, routine, _prompt, _gated in _ROUTINE_PATTERNS:
            if pattern.search(transcript):
                return ("ROUTINE", routine)
        for pattern, command, _ in _MOVE_PATTERNS:
            if pattern.search(transcript):
                return ("MOVE", command)
    return ("NONE", None)


def _routine_prompt(routine: str) -> str:
    """Lookup the spoken intro phrase for a routine. Empty string if unknown."""
    for _pattern, name, prompt, _gated in _ROUTINE_PATTERNS:
        if name == routine:
            return prompt
    return ""


def _routine_requires_password(routine: str) -> bool:
    for _pattern, name, _prompt, gated in _ROUTINE_PATTERNS:
        if name == routine:
            return gated
    return False


def _transcript_has_password(transcript: str) -> bool:
    pw = (settings.VOICE_MOVE_PASSWORD or "").strip()
    if not pw or not transcript:
        return False
    # Case-insensitive substring; tolerates surrounding punctuation/words.
    return pw.lower() in transcript.lower()


# ---------------------------------------------------------------------------
# Per-WS movement gate state
# ---------------------------------------------------------------------------
@dataclass
class MoveGate:
    state: str = "LOCKED"  # LOCKED | AWAITING_PASSWORD | UNLOCKED
    last_activity_ts: float = 0.0
    active_proc: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)
    active_kind: str = ""  # "" | "walk" | "dance"
    # When a gated command prompts for the password, remember it so a correct
    # password fires the command without the user re-saying it.
    pending_intent: str = ""   # "" | "MOVE" | "ROUTINE"
    pending_target: str = ""   # MOVE_FWD | TURN_LEFT | slow_dance | …

    def maybe_autorelock(self) -> bool:
        """Drop to LOCKED if UNLOCKED and idle past the timeout. Returns True if relocked."""
        if self.state != "UNLOCKED":
            return False
        timeout = float(settings.VOICE_UNLOCK_TIMEOUT_S or 60.0)
        if (time.monotonic() - self.last_activity_ts) > timeout:
            self.state = "LOCKED"
            return True
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _audit(operator: str, event: str, detail: Optional[dict]) -> None:
    """Write one LogEntry. Swallow errors so a broken audit never kills voice."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(LogEntry(
                session_id=getattr(robot, "current_session_id", None) or "NO_SESSION",
                operator=operator,
                entry_type="CMD",
                event=event,
                detail=json.dumps(detail, ensure_ascii=False) if detail else None,
            ))
            await db.commit()
    except Exception as exc:
        print(f"[voice audit log failed] {exc}", file=sys.stderr)


async def _speak(text: str) -> str:
    """Synthesize `text` via OpenAI tts-1 (cached) and play through the robot speaker.

    Returns a short status string suitable for inclusion in audit detail.
    """
    pcm = await get_prompt_pcm(text)
    if pcm is None:
        return "tts_unavailable"
    try:
        await robot.say(pcm)
        return "played"
    except RuntimeError as exc:
        return f"skipped:{exc}"
    except Exception as exc:
        print(f"[voice _speak] robot.say failed: {exc}", file=sys.stderr)
        return f"error:{exc}"


def _robot_env() -> dict:
    env = os.environ.copy()
    configured = (settings.ROBOT_SDK_PYTHONPATH or settings.CAMERA_PYTHONPATH or "").strip()
    if configured:
        existing = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = configured if not existing else f"{configured}{os.pathsep}{existing}"
    return env


def _check_route_gates() -> Optional[str]:
    """Mirror the gates the HTTP route handlers apply; return None if OK or a reason string."""
    if not getattr(robot, "is_connected", False):
        return "not_connected"
    if getattr(robot, "estop_active", False):
        return "estop_active"
    if not getattr(robot, "motion_armed", False):
        return "not_armed"
    return None


async def _spawn(script_name: str, *args: str) -> asyncio.subprocess.Process:
    iface = (settings.ROBOT_IFACE or "eth0").strip()
    python_bin = (settings.ROBOT_PYTHON_BIN or sys.executable).strip()
    script = str(ROBOT_COMMANDS_DIR / script_name)
    return await asyncio.create_subprocess_exec(
        python_bin, script, iface, *args,
        cwd=str(BACKEND_ROOT),
        env=_robot_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _dispatch_walk(gate: MoveGate, command: str) -> tuple[str, dict]:
    """Spawn the voice-walk sidecar. Returns (status, detail)."""
    duration = max(0.1, min(10.0, float(settings.VOICE_STEP_SEC or 1.0) * _STEPS_BY_COMMAND[command]))
    proc = await _spawn("run_voice_walk.py", command, f"{duration:.2f}")
    gate.active_proc = proc
    gate.active_kind = "walk"
    try:
        stdout, stderr = await proc.communicate()
    finally:
        gate.active_proc = None
        gate.active_kind = ""

    rc = proc.returncode
    detail = {
        "command": command,
        "duration_s": round(duration, 2),
        "returncode": rc,
        "stderr": (stderr.decode(errors="replace")[:300] if stderr else None),
    }
    status = "ok" if rc == 0 else f"fail:{rc}"
    return status, detail


async def _dispatch_routine(gate: MoveGate, routine: str) -> tuple[str, dict]:
    """Spawn the arm-routine sidecar. Returns (status, detail)."""
    proc = await _spawn("run_dance.py", routine)
    gate.active_proc = proc
    gate.active_kind = "dance"
    try:
        stdout, stderr = await proc.communicate()
    finally:
        gate.active_proc = None
        gate.active_kind = ""

    rc = proc.returncode
    detail = {
        "routine": routine,
        "returncode": rc,
        "stderr": (stderr.decode(errors="replace")[:300] if stderr else None),
    }
    status = "ok" if rc == 0 else f"fail:{rc}"
    return status, detail


async def _dispatch_stand(gate: MoveGate) -> tuple[str, dict]:
    """Interrupt any active walk/routine and pose the robot in HighStand.

    Kills the current motion subprocess, fires `LocoClient.HighStand()` via
    run_loco_command.py's "high stand" path, and (if a dance was active)
    follows up with `release arm` so the arms come down before standing.
    """
    was_kind = gate.active_kind
    if gate.active_proc is not None and gate.active_proc.returncode is None:
        try:
            gate.active_proc.kill()
        except ProcessLookupError:
            pass

    # release arm first if a dance was interrupted — HighStand looks weird
    # mid-heart-pose. Order matters: arms down, then pose to stand.
    release_rc: Optional[int] = None
    release_stderr: Optional[str] = None
    if was_kind == "dance":
        release_proc = await _spawn("run_arm_action.py", "release arm")
        _, release_stderr_bytes = await release_proc.communicate()
        release_rc = release_proc.returncode
        release_stderr = release_stderr_bytes.decode(errors="replace")[:200] if release_stderr_bytes else None

    stand_proc = await _spawn("run_loco_command.py", "high stand")
    _, stand_stderr = await stand_proc.communicate()
    stand_rc = stand_proc.returncode

    detail = {
        "command": "STAND_STILL",
        "was_active": was_kind or None,
        "stand_returncode": stand_rc,
        "stand_stderr": (stand_stderr.decode(errors="replace")[:200] if stand_stderr else None),
        "release_returncode": release_rc,
        "release_stderr": release_stderr,
    }
    status = "ok" if stand_rc == 0 else f"fail:{stand_rc}"
    return status, detail


async def _dispatch_stop(gate: MoveGate) -> tuple[str, dict]:
    """Kill any in-progress walk/routine and bring motion back to a safe rest.

    For walks: spawns the STOP sidecar (loco velocity → 0).
    For dance routines: also spawns run_arm_action.py "release arm" so the arms
    return to neutral after a mid-routine interrupt.
    """
    was_kind = gate.active_kind
    if gate.active_proc is not None and gate.active_proc.returncode is None:
        try:
            gate.active_proc.kill()
        except ProcessLookupError:
            pass
        # Don't await communicate — the original dispatch awaits it.

    # Always fire loco STOP. Idempotent even when nothing was walking; the
    # cost is one ~3 s sidecar spawn — acceptable for a safety override.
    stop_proc = await _spawn("run_loco_command.py", "STOP")
    _, stop_stderr = await stop_proc.communicate()
    stop_rc = stop_proc.returncode

    release_rc: Optional[int] = None
    release_stderr: Optional[str] = None
    if was_kind == "dance":
        release_proc = await _spawn("run_arm_action.py", "release arm")
        _, release_stderr_bytes = await release_proc.communicate()
        release_rc = release_proc.returncode
        release_stderr = release_stderr_bytes.decode(errors="replace")[:200] if release_stderr_bytes else None

    detail = {
        "command": "STOP",
        "was_active": was_kind or None,
        "stop_returncode": stop_rc,
        "stop_stderr": (stop_stderr.decode(errors="replace")[:200] if stop_stderr else None),
        "release_returncode": release_rc,
        "release_stderr": release_stderr,
    }
    status = "ok" if stop_rc == 0 else f"fail:{stop_rc}"
    return status, detail


async def _dispatch_intent(
    websocket: WebSocket, username: str, gate: MoveGate, intent: str, command: str,
) -> None:
    """Run the actual MOVE/ROUTINE side effects: route gates, speak, spawn,
    audit. Used both for the original direct path and for the queued command
    that fires after a successful password unlock."""
    block_reason = _check_route_gates()
    if block_reason is not None:
        speak_status = await _speak("Movement is not allowed right now.")
        detail = {"intent": intent, "target": command, "reason": block_reason, "speaker": speak_status}
        await websocket.send_json({"type": "voice_event", "event": "VOICE_REFUSED", "detail": detail})
        await _audit(username, "VOICE_REFUSED", detail)
        return

    if intent == "MOVE":
        feedback = {
            "MOVE_FWD":   "Walking forward.",
            "MOVE_BACK":  "Walking back.",
            "TURN_LEFT":  "Turning left.",
            "TURN_RIGHT": "Turning right.",
        }[command]
        speak_status = await _speak(feedback)
        status, detail = await _dispatch_walk(gate, command)
        if gate.state == "UNLOCKED":
            gate.last_activity_ts = time.monotonic()
        detail["speaker"] = speak_status
        detail["status"] = status
        await websocket.send_json({"type": "voice_event", "event": "VOICE_WALK", "detail": detail})
        await _audit(username, "VOICE_WALK", detail)
    else:  # ROUTINE
        intro = _routine_prompt(command) or "Let's go."
        speak_status = await _speak(intro)
        status, detail = await _dispatch_routine(gate, command)
        if gate.state == "UNLOCKED":
            gate.last_activity_ts = time.monotonic()
        detail["speaker"] = speak_status
        detail["status"] = status
        await websocket.send_json({"type": "voice_event", "event": "VOICE_ROUTINE", "detail": detail})
        await _audit(username, "VOICE_ROUTINE", detail)


# ---------------------------------------------------------------------------
# Per-utterance gate handler
# ---------------------------------------------------------------------------
async def _process_utterance(
    websocket: WebSocket, username: str, gate: MoveGate, transcript: str,
) -> None:
    """React to one user_transcript event. Returns nothing; side effects only."""
    if not (settings.VOICE_MOVE_PASSWORD or "").strip():
        # Feature disabled (no password set) — voice walk path is inert.
        return

    # Silent auto-relock on idle.
    if gate.maybe_autorelock():
        await websocket.send_json({
            "type": "voice_event", "event": "MOVE_RELOCKED", "detail": {"reason": "idle"},
        })
        await _audit(username, "VOICE_RELOCKED", {"reason": "idle"})

    intent, command = _classify_intent(transcript)

    # --- STOP — always allowed, even mid-walk, regardless of state.
    if intent == "STOP":
        # Clear any queued password-pending command — STOP overrides intent.
        gate.pending_intent = ""
        gate.pending_target = ""
        status, detail = await _dispatch_stop(gate)
        speak_status = await _speak("Stopped.")
        detail["speaker"] = speak_status
        await websocket.send_json({"type": "voice_event", "event": "VOICE_STOP", "detail": detail})
        await _audit(username, "VOICE_STOP", detail)
        return

    # --- STAND_STILL — wake-word + safety-positive pose. Password-free; still
    # subject to connected/e-stop/armed route gates because HighStand IS motion.
    if intent == "STAND":
        block_reason = _check_route_gates()
        if block_reason is not None:
            speak_status = await _speak("I can't stand right now.")
            detail = {"command": "STAND_STILL", "reason": block_reason, "speaker": speak_status}
            await websocket.send_json({
                "type": "voice_event", "event": "VOICE_REFUSED", "detail": detail,
            })
            await _audit(username, "VOICE_REFUSED", detail)
            return
        speak_status = await _speak("Standing still.")
        status, detail = await _dispatch_stand(gate)
        detail["speaker"] = speak_status
        detail["status"] = status
        await websocket.send_json({"type": "voice_event", "event": "VOICE_STAND", "detail": detail})
        await _audit(username, "VOICE_STAND", detail)
        return

    # --- Password handling.
    if gate.state == "AWAITING_PASSWORD":
        if _transcript_has_password(transcript):
            gate.state = "UNLOCKED"
            gate.last_activity_ts = time.monotonic()
            # If a command was queued by the prompt, fire it directly so the
            # user doesn't have to re-say "move forward". Skip the "Movement
            # unlocked" preamble — the per-intent feedback below ("Walking
            # forward.") doubles as confirmation.
            pending_intent = gate.pending_intent
            pending_target = gate.pending_target
            gate.pending_intent = ""
            gate.pending_target = ""
            await websocket.send_json({
                "type": "voice_event", "event": "MOVE_UNLOCKED",
                "detail": {"pending": pending_intent or None},
            })
            await _audit(username, "VOICE_UNLOCKED", {"pending": pending_intent or None})
            if pending_intent and pending_target:
                await _dispatch_intent(websocket, username, gate, pending_intent, pending_target)
            else:
                speak_status = await _speak("Movement unlocked.")
                await websocket.send_json({
                    "type": "voice_event", "event": "MOVE_UNLOCKED",
                    "detail": {"speaker": speak_status},
                })
        else:
            gate.state = "LOCKED"
            gate.pending_intent = ""
            gate.pending_target = ""
            speak_status = await _speak("Sorry, wrong password.")
            await websocket.send_json({
                "type": "voice_event", "event": "MOVE_PASSWORD_FAIL",
                "detail": {"speaker": speak_status},
            })
            await _audit(username, "VOICE_PASSWORD_FAIL", {"speaker": speak_status})
        return

    # Below here: MOVE and ROUTINE intents only.
    if intent not in ("MOVE", "ROUTINE") or command is None:
        return

    # Decide if the password gate applies. MOVE always needs it; ROUTINE only
    # when the registry says so (slow dance free, shake dance gated).
    requires_password = (intent == "MOVE") or (
        intent == "ROUTINE" and _routine_requires_password(command)
    )

    # Gated + still LOCKED → queue the command, prompt for password, don't dispatch.
    if requires_password and gate.state == "LOCKED":
        gate.state = "AWAITING_PASSWORD"
        gate.pending_intent = intent
        gate.pending_target = command
        speak_status = await _speak("Please say the password to unlock movement.")
        await websocket.send_json({
            "type": "voice_event", "event": "MOVE_PASSWORD_REQUIRED",
            "detail": {"intent": intent, "target": command, "speaker": speak_status},
        })
        await _audit(username, "VOICE_PASSWORD_PROMPT", {
            "intent": intent, "target": command, "speaker": speak_status,
        })
        return

    # Either ungated routine, or gated + UNLOCKED.
    await _dispatch_intent(websocket, username, gate, intent, command)


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    # ---- auth ----------------------------------------------------------
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "text": "Auth timeout"})
        await websocket.close()
        return
    except WebSocketDisconnect:
        return

    try:
        payload = jwt.decode(
            auth_msg.get("token", ""),
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        username = payload.get("sub") or "unknown"
    except JWTError:
        await websocket.send_json({"type": "error", "text": "Invalid token"})
        await websocket.close()
        return

    # ---- open VoiceLive session ---------------------------------------
    session = VoiceLiveSession()
    try:
        await session.connect()
    except Exception as exc:
        await websocket.send_json({"type": "error", "text": f"VoiceLive connect failed: {exc}"})
        await websocket.close()
        return

    await websocket.send_json({"type": "ready", "message": f"Hello {username}"})

    gate = MoveGate()

    # ---- bridge loops -------------------------------------------------
    async def browser_to_azure() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    return
                if "bytes" in msg and msg["bytes"] is not None:
                    await session.send_audio_chunk(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    try:
                        ctrl = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    if ctrl.get("type") == "stop":
                        return
        except WebSocketDisconnect:
            return

    async def azure_to_browser() -> None:
        accumulated_pcm = bytearray()
        user_transcript = ""
        assistant_text_parts: list[str] = []

        async for event in session.events():
            if event.kind == "user_transcript":
                user_transcript = event.text or ""
                await websocket.send_json({"type": "user_transcript", "text": user_transcript})
                # Process movement-gate intent independently of the LLM reply.
                # Fire-and-forget so a slow walk doesn't block subsequent events.
                asyncio.create_task(
                    _process_utterance(websocket, username, gate, user_transcript)
                )

            elif event.kind == "assistant_text_delta":
                if event.text:
                    assistant_text_parts.append(event.text)
                    await websocket.send_json({"type": "assistant_text_delta", "text": event.text})

            elif event.kind == "assistant_text_done":
                if event.text:
                    assistant_text_parts = [event.text]

            elif event.kind == "assistant_audio_delta":
                if event.audio_pcm_24k:
                    accumulated_pcm.extend(event.audio_pcm_24k)

            elif event.kind == "response_done":
                assistant_text = "".join(assistant_text_parts).strip()

                speaker_status = "skipped"
                if accumulated_pcm:
                    try:
                        pcm_16k = _downsample_24k_to_16k(bytes(accumulated_pcm))
                        await robot.say(pcm_16k)
                        speaker_status = "played"
                    except RuntimeError as exc:
                        speaker_status = f"skipped:{exc}"
                    except Exception as exc:
                        speaker_status = f"error:{exc}"
                        print(f"[voice] robot.say failed: {exc}", file=sys.stderr)

                await websocket.send_json({
                    "type": "response_done",
                    "user_transcript": user_transcript,
                    "assistant_text": assistant_text,
                    "speaker": speaker_status,
                })

                await _audit(username, "VOICE_CHAT", {
                    "user_transcript": user_transcript,
                    "assistant_text": assistant_text,
                    "pcm_bytes": len(accumulated_pcm),
                    "speaker": speaker_status,
                    "ts": f"{datetime.utcnow().isoformat()}Z",
                })

                accumulated_pcm = bytearray()
                user_transcript = ""
                assistant_text_parts = []

            elif event.kind == "error":
                await websocket.send_json({"type": "error", "text": event.text or "VoiceLive error"})

    sender = asyncio.create_task(browser_to_azure(), name="voice-browser-to-azure")
    receiver = asyncio.create_task(azure_to_browser(), name="voice-azure-to-browser")

    try:
        done, pending = await asyncio.wait(
            {sender, receiver},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                print(f"[voice] task error: {exc!r}", file=sys.stderr)
    finally:
        # If a walk or routine is still in progress when the WS closes, fire
        # the unified STOP path which handles both kinds.
        if gate.active_proc is not None and gate.active_proc.returncode is None:
            try:
                await _dispatch_stop(gate)
            except Exception as exc:
                print(f"[voice] final STOP failed: {exc}", file=sys.stderr)
        await session.close()
        try:
            await websocket.close()
        except Exception:
            pass
