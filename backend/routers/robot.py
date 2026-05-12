"""
Robot control routes.
"""
import subprocess
import json
import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import LogEntry, User, get_db
from models.schemas import RobotCommand, RobotStatus, SafetyConfigUpdate
from routers.auth import get_current_user, require_supervisor
from services import robot as mock_robot

router = APIRouter()
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROBOT_COMMANDS_DIR = BACKEND_ROOT / "robot_commands"
AUDIO_DIR = BACKEND_ROOT / "audio"


def resolve_robot_env() -> dict:
    env = os.environ.copy()
    configured_pythonpath = (settings.ROBOT_SDK_PYTHONPATH or settings.CAMERA_PYTHONPATH or "").strip()

    if configured_pythonpath:
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            configured_pythonpath
            if not existing_pythonpath
            else f"{configured_pythonpath}{os.pathsep}{existing_pythonpath}"
        )

    return env


def resolve_robot_python_bin() -> str:
    return (settings.ROBOT_PYTHON_BIN or "python3").strip()


def resolve_robot_iface() -> str:
    return (settings.ROBOT_IFACE or "eth0").strip()


def resolve_audio_wav_path() -> str:
    configured = (settings.ROBOT_AUDIO_WAV or "").strip()
    return configured or str(AUDIO_DIR / "test.wav")


def run_robot_script(script_path: Path, *args: str, timeout: int = 10):
    return subprocess.run(
        [resolve_robot_python_bin(), str(script_path), resolve_robot_iface(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(BACKEND_ROOT),
        env=resolve_robot_env(),
    )


def encode_detail(data: dict | None) -> str | None:
    if not data:
        return None
    return json.dumps(data, ensure_ascii=False)


@router.get("/status", response_model=RobotStatus)
async def get_robot_status(current_user: User = Depends(get_current_user)):
    return await mock_robot.get_status()


@router.post("/connect")
async def connect_robot(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        status = await mock_robot.connect()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="INFO",
        event="ROBOT_CONNECTED",
        detail=encode_detail({
            "connection": status["connection"],
            "connected_at": status["connected_at"],
        }),
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": "ROBOT_CONNECTED",
        "message": "Robot connected",
        "timestamp": datetime.utcnow().isoformat(),
        **status,
    }


@router.post("/disconnect")
async def disconnect_robot(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    status = await mock_robot.disconnect()

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="INFO",
        event="ROBOT_DISCONNECTED",
        detail=None,
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": "ROBOT_DISCONNECTED",
        "message": "Robot disconnected",
        "timestamp": datetime.utcnow().isoformat(),
        **status,
    }


@router.post("/command")
async def send_command(
    cmd: RobotCommand,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    loco_commands = {"MOVE_FWD", "MOVE_BACK", "TURN_LEFT", "TURN_RIGHT", "MOVE_LEFT", "MOVE_RIGHT", "STOP"}

    if cmd.command in loco_commands:
        result = run_robot_script(
            ROBOT_COMMANDS_DIR / "run_loco_command.py",
            cmd.command,
            timeout=10,
        )

        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=result.stderr or result.stdout)

        command_result = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    else:
        command_result = await mock_robot.execute_command(cmd.command, cmd.params)

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="CMD",
        event=cmd.command,
        detail=encode_detail(cmd.params),
    ))
    await db.commit()

    return {"success": True, "result": command_result}


@router.post("/estop")
async def emergency_stop(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mock_robot.estop()
    status = await mock_robot.get_status()

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="ERR",
        event="ESTOP_TRIGGERED",
        detail=encode_detail({
            "role": current_user.role,
            "operator": current_user.username,
        }),
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": "ESTOP_TRIGGERED",
        "message": "E-Stop activated",
        "timestamp": datetime.utcnow().isoformat(),
        **status,
    }


@router.post("/estop/release")
async def release_estop(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mock_robot.release_estop()
    status = await mock_robot.get_status()

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="INFO",
        event="ESTOP_RELEASED",
        detail=None,
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": "ESTOP_RELEASED",
        "message": "E-Stop released",
        "timestamp": datetime.utcnow().isoformat(),
        **status,
    }


@router.post("/arm")
async def arm_motion(
    armed: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await mock_robot.set_armed(armed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    status = await mock_robot.get_status()
    event_type = "MOTION_ARMED" if armed else "MOTION_DISARMED"
    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="CMD",
        event=event_type,
        detail=None,
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": event_type,
        "message": "Motion armed" if armed else "Motion disarmed",
        "timestamp": datetime.utcnow().isoformat(),
        **status,
    }


@router.put("/safety-config")
async def update_safety_config(
    config: SafetyConfigUpdate,
    supervisor: User = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from models.database import SafetyConfig

    result = await db.execute(select(SafetyConfig).order_by(SafetyConfig.id.desc()))
    current = result.scalar_one_or_none()

    if not current:
        current = SafetyConfig()
        db.add(current)

    for field, value in config.model_dump(exclude_none=True).items():
        setattr(current, field, value)
    current.updated_by = supervisor.username
    current.updated_at = datetime.utcnow()

    await mock_robot.apply_safety_config(config.model_dump(exclude_none=True))
    await db.commit()

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=supervisor.username,
        entry_type="CMD",
        event="SAFETY_CONFIG_UPDATE",
        detail=encode_detail(config.model_dump(exclude_none=True)),
    ))
    await db.commit()

    return {"success": True, "message": "Safety configuration updated"}


@router.get("/safety-config")
async def get_safety_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from models.database import SafetyConfig

    result = await db.execute(select(SafetyConfig).order_by(SafetyConfig.id.desc()))
    config = result.scalar_one_or_none()
    if not config:
        return {
            "max_speed": 0.4,
            "turn_rate": 30,
            "max_torque_pct": 40,
            "temp_warn": 60,
            "temp_stop": 70,
            "active_zone": "LAB G12",
        }
    return config
    
@router.post("/audio")
def run_audio_command():
    try:
        result = subprocess.run(
            [
                resolve_robot_python_bin(),
                str(AUDIO_DIR / "g1_audio_client_play_wav.py"),
                resolve_robot_iface(),
                resolve_audio_wav_path(),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(BACKEND_ROOT),
            env=resolve_robot_env(),
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
        
@router.post("/high-level/{command}")
async def run_high_level_command(
    command: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = run_robot_script(
            ROBOT_COMMANDS_DIR / "run_arm_action.py",
            command,
            timeout=15,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if result.returncode != 0:
        try:
            db.add(LogEntry(
                session_id=mock_robot.current_session_id or "NO_SESSION",
                operator=current_user.username,
                entry_type="ERR",
                event=command.upper(),
                detail=encode_detail({
                    "command": command,
                    "returncode": result.returncode,
                    "stderr": result.stderr[:500] if result.stderr else None,
                }),
            ))
            await db.commit()
        except Exception as e:
            import sys
            print(f"[audit log failed] {e}", file=sys.stderr)
        raise HTTPException(
            status_code=400,
            detail=(result.stderr or result.stdout or f"High-level command failed: {command}").strip(),
        )

    try:
        db.add(LogEntry(
            session_id=mock_robot.current_session_id or "NO_SESSION",
            operator=current_user.username,
            entry_type="CMD",
            event=command.upper(),
            detail=encode_detail({
                "command": command,
                "returncode": result.returncode,
                "stderr": result.stderr[:500] if result.stderr else None,
            }),
        ))
        await db.commit()
    except Exception as e:
        import sys
        print(f"[audit log failed] {e}", file=sys.stderr)

    return {
        "success": True,
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
@router.post("/loco/{command}")
async def run_locomotion_command(
    command: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed_commands = {
        "MOVE_FWD",
        "MOVE_BACK",
        "TURN_LEFT",
        "TURN_RIGHT",
        "MOVE_LEFT",
        "MOVE_RIGHT",
        "STOP",
    }

    if command not in allowed_commands:
        return {
            "success": False,
            "error": "Locomotion command not allowed"
        }

    try:
        result = run_robot_script(
            ROBOT_COMMANDS_DIR / "run_loco_command.py",
            command,
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if result.returncode != 0:
        try:
            db.add(LogEntry(
                session_id=mock_robot.current_session_id or "NO_SESSION",
                operator=current_user.username,
                entry_type="ERR",
                event=command.upper(),
                detail=encode_detail({
                    "command": command,
                    "returncode": result.returncode,
                    "stderr": result.stderr[:500] if result.stderr else None,
                }),
            ))
            await db.commit()
        except Exception as e:
            import sys
            print(f"[audit log failed] {e}", file=sys.stderr)
        raise HTTPException(
            status_code=400,
            detail=(result.stderr or result.stdout or f"Locomotion command failed: {command}").strip(),
        )

    try:
        db.add(LogEntry(
            session_id=mock_robot.current_session_id or "NO_SESSION",
            operator=current_user.username,
            entry_type="CMD",
            event=command.upper(),
            detail=encode_detail({
                "command": command,
                "returncode": result.returncode,
                "stderr": result.stderr[:500] if result.stderr else None,
            }),
        ))
        await db.commit()
    except Exception as e:
        import sys
        print(f"[audit log failed] {e}", file=sys.stderr)

    return {
        "success": True,
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@router.get("/_debug/dds")
async def debug_dds():
    """Diagnostic counters for the in-process DDS bridge. No auth — read-only."""
    now = time.monotonic()
    low_recv = getattr(mock_robot, "_low_state_recv_at", None)
    bms_recv = getattr(mock_robot, "_bms_state_recv_at", None)
    return {
        "low_state_count": getattr(mock_robot, "_low_state_count", None),
        "low_state_recv_at": low_recv,
        "low_state_age_ms": (now - low_recv) * 1000 if low_recv is not None else None,
        "bms_state_count": getattr(mock_robot, "_bms_state_count", None),
        "bms_state_recv_at": bms_recv,
        "bms_state_age_ms": (now - bms_recv) * 1000 if bms_recv is not None else None,
        "double_init_recoveries": getattr(mock_robot, "_double_init_recoveries", None),
        "now_monotonic": now,
    }
