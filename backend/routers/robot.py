"""
机器人控制路由 — 发送指令、E-Stop、获取状态
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from models.database import get_db, User, LogEntry
from models.schemas import RobotCommand, RobotStatus, SafetyConfigUpdate
from routers.auth import get_current_user, require_supervisor
from services.mock_robot import mock_robot   # 切换真实机器人时改这里
from config import settings

router = APIRouter()


@router.get("/status", response_model=RobotStatus)
async def get_robot_status(current_user: User = Depends(get_current_user)):
    """获取机器人当前状态"""
    return await mock_robot.get_status()


@router.post("/command")
async def send_command(
    cmd: RobotCommand,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    发送控制指令给机器人
    所有指令都记录到日志
    """
    # 执行指令
    result = await mock_robot.execute_command(cmd.command, cmd.params)

    # 写日志
    log = LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="CMD",
        event=cmd.command,
        detail=str(cmd.params) if cmd.params else None,
    )
    db.add(log)
    await db.commit()

    return {"success": True, "result": result}


@router.post("/estop")
async def emergency_stop(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    软件紧急停止 — 任何角色都可触发
    记录为高优先级日志
    """
    await mock_robot.estop()

    log = LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="ERR",
        event="E-STOP",
        detail=f"Activated by {current_user.role}: {current_user.username}",
    )
    db.add(log)
    await db.commit()

    return {"success": True, "message": "E-Stop activated"}


@router.post("/estop/release")
async def release_estop(current_user: User = Depends(get_current_user)):
    """释放E-Stop"""
    await mock_robot.release_estop()
    return {"success": True}


@router.post("/arm")
async def arm_motion(
    armed: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """解锁/锁定运动权限"""
    await mock_robot.set_armed(armed)
    log = LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=current_user.username,
        entry_type="CMD",
        event="MOTION_ARM" if armed else "MOTION_DISARM",
        detail=None,
    )
    db.add(log)
    await db.commit()
    return {"success": True, "armed": armed}


@router.put("/safety-config")
async def update_safety_config(
    config: SafetyConfigUpdate,
    supervisor: User = Depends(require_supervisor),  # 只有Supervisor能调
    db: AsyncSession = Depends(get_db)
):
    """
    更新安全参数（仅限Supervisor）
    - 速度上限、转向速率、力矩限制、温度阈值、地理围栏
    """
    from models.database import SafetyConfig
    from sqlalchemy import select

    result = await db.execute(select(SafetyConfig).order_by(SafetyConfig.id.desc()))
    current = result.scalar_one_or_none()

    if not current:
        current = SafetyConfig()
        db.add(current)

    for field, value in config.model_dump(exclude_none=True).items():
        setattr(current, field, value)
    current.updated_by = supervisor.username
    current.updated_at = datetime.utcnow()

    # 同步到机器人桥接层
    await mock_robot.apply_safety_config(config.model_dump(exclude_none=True))

    await db.commit()

    log = LogEntry(
        session_id=mock_robot.current_session_id or "NO_SESSION",
        operator=supervisor.username,
        entry_type="CMD",
        event="SAFETY_CONFIG_UPDATE",
        detail=str(config.model_dump(exclude_none=True)),
    )
    db.add(log)
    await db.commit()

    return {"success": True, "message": "安全参数已更新"}


@router.get("/safety-config")
async def get_safety_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前安全参数（所有角色可查看）"""
    from models.database import SafetyConfig
    from sqlalchemy import select

    result = await db.execute(select(SafetyConfig).order_by(SafetyConfig.id.desc()))
    config = result.scalar_one_or_none()
    if not config:
        return {"max_speed": 0.4, "turn_rate": 30, "max_torque_pct": 40,
                "temp_warn": 60, "temp_stop": 70, "active_zone": "LAB G12"}
    return config
