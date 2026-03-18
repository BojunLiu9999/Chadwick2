"""
会话管理路由 — 开始/结束会话、标签、导出
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
import json, csv, io, random

from models.database import get_db, User, Session as RobotSession, LogEntry
from models.schemas import SessionStartRequest, SessionTagRequest, SessionSummary, LogEntryOut
from routers.auth import get_current_user
from services.mock_robot import mock_robot

router = APIRouter()


def generate_session_id() -> str:
    return f"SES-{random.randint(1000, 9999)}"


@router.post("/start")
async def start_session(
    req: SessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """开始新的操作会话"""
    # 关闭旧的活跃会话
    result = await db.execute(
        select(RobotSession).where(
            RobotSession.operator_id == current_user.id,
            RobotSession.is_active == True
        )
    )
    old = result.scalar_one_or_none()
    if old:
        old.is_active = False
        old.ended_at = datetime.utcnow()

    session_id = generate_session_id()
    new_session = RobotSession(
        session_id=session_id,
        operator_id=current_user.id,
        mode=req.mode,
    )
    db.add(new_session)

    # 写入日志
    db.add(LogEntry(
        session_id=session_id,
        operator=current_user.username,
        entry_type="INFO",
        event="SESSION_START",
        detail=f"Mode: {req.mode}",
    ))
    await db.commit()

    mock_robot.current_session_id = session_id
    return {"session_id": session_id, "mode": req.mode, "started_at": datetime.utcnow()}


@router.post("/stop")
async def stop_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """结束当前会话"""
    result = await db.execute(
        select(RobotSession).where(
            RobotSession.operator_id == current_user.id,
            RobotSession.is_active == True
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="没有活跃的会话")

    session.is_active = False
    session.ended_at = datetime.utcnow()
    duration = (session.ended_at - session.started_at).total_seconds()

    db.add(LogEntry(
        session_id=session.session_id,
        operator=current_user.username,
        entry_type="INFO",
        event="SESSION_END",
        detail=f"Duration: {duration:.0f}s",
    ))
    await db.commit()

    mock_robot.current_session_id = None
    return {"session_id": session.session_id, "duration_seconds": duration}


@router.post("/tag")
async def add_tag(
    req: SessionTagRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """在当前会话中添加事件标签"""
    session_id = mock_robot.current_session_id or "NO_SESSION"
    db.add(LogEntry(
        session_id=session_id,
        operator=current_user.username,
        entry_type="TAG",
        event=req.tag,
        detail=req.note,
    ))
    await db.commit()
    return {"success": True}


@router.get("/current")
async def get_current_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前活跃会话信息"""
    result = await db.execute(
        select(RobotSession).where(
            RobotSession.operator_id == current_user.id,
            RobotSession.is_active == True
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return {"active": False}
    return {
        "active": True,
        "session_id": session.session_id,
        "mode": session.mode,
        "started_at": session.started_at,
    }


@router.get("/logs")
async def get_session_logs(
    session_id: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取会话日志列表"""
    sid = session_id or mock_robot.current_session_id
    if not sid:
        return []
    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.session_id == sid)
        .order_by(LogEntry.timestamp.asc())
    )
    entries = result.scalars().all()
    return [LogEntryOut.model_validate(e) for e in entries]


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = "csv",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    导出会话日志
    - format=csv  → 下载 CSV 文件
    - format=json → 下载 JSON 文件
    """
    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.session_id == session_id)
        .order_by(LogEntry.timestamp.asc())
    )
    entries = result.scalars().all()

    if format == "json":
        data = [
            {
                "timestamp": e.timestamp.isoformat(),
                "operator": e.operator,
                "type": e.entry_type,
                "event": e.event,
                "detail": e.detail,
            }
            for e in entries
        ]
        return StreamingResponse(
            io.BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={session_id}.json"},
        )

    # 默认 CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Operator", "Type", "Event", "Detail"])
    for e in entries:
        writer.writerow([e.timestamp.isoformat(), e.operator, e.entry_type, e.event, e.detail or ""])
    output.seek(0)

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={session_id}.csv"},
    )
