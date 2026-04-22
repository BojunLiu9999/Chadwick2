"""
Robot control routes.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import LogEntry, User, get_db
from models.schemas import RobotCommand, RobotStatus, SafetyConfigUpdate
from routers.auth import get_current_user, require_supervisor
from services.mock_robot import mock_robot

router = APIRouter()


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
    result = await mock_robot.execute_command(cmd.command, cmd.params)

    db.add(LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="CMD",
        event=cmd.command,
        detail=encode_detail(cmd.params),
    ))
    await db.commit()

    return {"success": True, "result": result}


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
