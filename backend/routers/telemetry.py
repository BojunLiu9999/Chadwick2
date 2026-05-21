"""
遥测路由 — WebSocket 实时推送遥测数据
"""
import asyncio
import json
import sys
import time
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy import select

from config import settings
from models.database import AsyncSessionLocal, LogEntry, SafetyConfig, TelemetrySample
from services import robot as mock_robot

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Telemetry logger
#
# A single background asyncio task that, at 1 Hz:
#   - reads the same get_telemetry() the WS pushes already use
#   - writes a TelemetrySample row when a session is active
#   - emits LogEntry rows + WS alert frames on threshold transitions
#   - emits TELEMETRY_STALL when the DDS low_state callback ages past
#     _STALL_AGE_S (real bridge only; mock bridge has no recv_at)
#
# Kept separate from per-WS push loops so multiple WS clients don't each
# duplicate sample writes. WS clients still get the same telemetry frames
# they did before, plus new "alert" frames broadcast from this task.
# ---------------------------------------------------------------------------
_BATTERY_LOW_PCT = 20.0
_BATTERY_CRITICAL_PCT = 10.0
_STALL_AGE_S = 2.5
_LOGGER_TICK_S = 1.0

_alert_state: dict[str, str] = {"temp": "OK", "battery": "OK", "stall": "OK"}
_telemetry_logger_task: "asyncio.Task | None" = None


def _classify_temp(value: float | None, warn: float, stop: float) -> str:
    if value is None:
        return "OK"
    if value >= stop:
        return "STOP"
    if value >= warn:
        return "WARN"
    return "OK"


def _classify_battery(value: float | None) -> str:
    if value is None:
        return "OK"
    if value <= _BATTERY_CRITICAL_PCT:
        return "CRITICAL"
    if value <= _BATTERY_LOW_PCT:
        return "LOW"
    return "OK"


async def _get_temp_thresholds() -> tuple[float, float]:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SafetyConfig).order_by(SafetyConfig.id.desc()))
            cfg = result.scalar_one_or_none()
            if cfg:
                return float(cfg.temp_warn), float(cfg.temp_stop)
    except Exception:
        pass
    return 60.0, 70.0


async def _emit_alert(session_id: str | None, entry_type: str, event: str, detail: dict) -> None:
    sid = session_id or "NO_SESSION"
    try:
        async with AsyncSessionLocal() as db:
            db.add(LogEntry(
                session_id=sid,
                operator="telemetry",
                entry_type=entry_type,
                event=event,
                detail=json.dumps(detail, ensure_ascii=False),
            ))
            await db.commit()
    except Exception as exc:
        print(f"[telemetry-logger] LogEntry write failed: {exc}", file=sys.stderr)

    try:
        await manager.broadcast({
            "type": "alert",
            "level": entry_type,
            "event": event,
            "detail": detail,
            "session_id": sid,
            "timestamp": f"{datetime.utcnow().isoformat()}Z",
        })
    except Exception as exc:
        print(f"[telemetry-logger] alert broadcast failed: {exc}", file=sys.stderr)


def _write_sample_fire_and_forget(session_id: str, sample_kwargs: dict) -> None:
    async def _writer():
        try:
            async with AsyncSessionLocal() as db:
                db.add(TelemetrySample(session_id=session_id, **sample_kwargs))
                await db.commit()
        except Exception as exc:
            print(f"[telemetry-logger] sample write failed: {exc}", file=sys.stderr)
    asyncio.create_task(_writer())


async def _telemetry_logger_loop() -> None:
    while True:
        try:
            await asyncio.sleep(_LOGGER_TICK_S)

            telemetry = await mock_robot.get_telemetry()
            session_id = getattr(mock_robot, "current_session_id", None)
            temp_warn, temp_stop = await _get_temp_thresholds()

            tilt = telemetry.get("imu_tilt_deg")
            temp = telemetry.get("core_temp_c")
            battery = telemetry.get("battery_pct")
            latency = telemetry.get("latency_ms")
            motor_loads = telemetry.get("motor_loads") or {}
            try:
                motor_load_pct = max(motor_loads.values()) if motor_loads else None
            except Exception:
                motor_load_pct = None

            # Stall detection (real bridge populates _low_state_recv_at; mock leaves it None)
            recv_at = getattr(mock_robot, "_low_state_recv_at", None)
            now_mono = time.monotonic()
            stalled = recv_at is not None and (now_mono - recv_at) > _STALL_AGE_S
            new_stall = "STALL" if stalled else "OK"
            if new_stall != _alert_state["stall"]:
                level = "WARN" if new_stall == "STALL" else "INFO"
                age_ms = int((now_mono - recv_at) * 1000) if recv_at is not None else None
                await _emit_alert(
                    session_id,
                    level,
                    f"TELEMETRY_{new_stall}",
                    {"age_ms": age_ms, "threshold_ms": int(_STALL_AGE_S * 1000)},
                )
                _alert_state["stall"] = new_stall

            # Temperature transitions
            new_temp = _classify_temp(temp, temp_warn, temp_stop)
            if new_temp != _alert_state["temp"]:
                level = "ERR" if new_temp == "STOP" else "WARN" if new_temp == "WARN" else "INFO"
                await _emit_alert(
                    session_id,
                    level,
                    f"TEMP_{new_temp}",
                    {
                        "from": _alert_state["temp"],
                        "to": new_temp,
                        "core_temp_c": temp,
                        "warn": temp_warn,
                        "stop": temp_stop,
                    },
                )
                _alert_state["temp"] = new_temp

            # Battery transitions
            new_bat = _classify_battery(battery)
            if new_bat != _alert_state["battery"]:
                level = "ERR" if new_bat == "CRITICAL" else "WARN" if new_bat == "LOW" else "INFO"
                await _emit_alert(
                    session_id,
                    level,
                    f"BATTERY_{new_bat}",
                    {
                        "from": _alert_state["battery"],
                        "to": new_bat,
                        "battery_pct": battery,
                    },
                )
                _alert_state["battery"] = new_bat

            # Persist sample only while a session is active and data isn't stale.
            if session_id and not stalled:
                _write_sample_fire_and_forget(
                    session_id,
                    {
                        "tilt_deg": tilt,
                        "motor_load_pct": motor_load_pct,
                        "core_temp_c": temp,
                        "battery_pct": battery,
                        "latency_ms": latency,
                    },
                )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[telemetry-logger] loop error: {exc}", file=sys.stderr)


def start_telemetry_logger() -> None:
    """Idempotent: start the logger task on the running event loop."""
    global _telemetry_logger_task
    if _telemetry_logger_task is not None and not _telemetry_logger_task.done():
        return
    _telemetry_logger_task = asyncio.create_task(
        _telemetry_logger_loop(), name="telemetry-logger"
    )


async def stop_telemetry_logger() -> None:
    global _telemetry_logger_task
    if _telemetry_logger_task is None:
        return
    _telemetry_logger_task.cancel()
    try:
        await _telemetry_logger_task
    except asyncio.CancelledError:
        pass
    _telemetry_logger_task = None


@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    """
    WebSocket 端点：每秒推送一次遥测数据
    前端通过 ws://localhost:8000/api/ws/telemetry 连接

    连接后发送 Token 验证:
      { "token": "<jwt_token>" }
    """
    await manager.connect(websocket)
    authenticated = False

    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        token = auth_msg.get("token", "")
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            authenticated = True
            username = payload.get("sub", "unknown")
        except JWTError:
            await websocket.send_json({"error": "Invalid token"})
            await websocket.close()
            return

        await websocket.send_json({"type": "connected", "message": f"Welcome {username}"})

        while True:
            telemetry = await mock_robot.get_telemetry()
            await websocket.send_json({
                "type": "telemetry",
                "data": telemetry,
            })
            await asyncio.sleep(1.0)

    except asyncio.TimeoutError:
        await websocket.send_json({"error": "Auth timeout"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
