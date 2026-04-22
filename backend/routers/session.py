"""
Session routes for start, pause, stop, tags, and exports.
"""
import csv
import io
import json
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import LogEntry, Session as RobotSession, User, get_db
from models.schemas import LogEntryOut, SessionStartRequest, SessionTagRequest
from routers.auth import get_current_user
from services.mock_robot import mock_robot

router = APIRouter()


def generate_session_id() -> str:
    return f"SES-{random.randint(1000, 9999)}"


def encode_detail(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


async def get_active_session(db: AsyncSession, operator_id: int) -> RobotSession | None:
    result = await db.execute(
        select(RobotSession).where(
            RobotSession.operator_id == operator_id,
            RobotSession.is_active == True,
        )
    )
    return result.scalar_one_or_none()


@router.post("/start")
async def start_session(
    req: SessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    old_session = await get_active_session(db, current_user.id)
    if old_session:
        old_session.is_active = False
        old_session.ended_at = now
        db.add(LogEntry(
            session_id=old_session.session_id,
            operator=current_user.username,
            entry_type="INFO",
            event="SESSION_STOPPED",
            detail=encode_detail({
                "reason": "restarted",
                "ended_at": now.isoformat(),
            }),
        ))

    session_id = generate_session_id()
    new_session = RobotSession(
        session_id=session_id,
        operator_id=current_user.id,
        mode=req.mode,
        started_at=now,
        is_active=True,
    )
    db.add(new_session)
    db.add(LogEntry(
        session_id=session_id,
        operator=current_user.username,
        entry_type="INFO",
        event="SESSION_STARTED",
        detail=encode_detail({"mode": req.mode}),
    ))
    await db.commit()

    mock_robot.current_session_id = session_id
    return {
        "success": True,
        "event_type": "SESSION_STARTED",
        "session_id": session_id,
        "mode": req.mode,
        "message": "Session started",
        "timestamp": now.isoformat(),
    }


@router.post("/pause")
async def pause_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    now = datetime.utcnow()
    db.add(LogEntry(
        session_id=session.session_id,
        operator=current_user.username,
        entry_type="WARN",
        event="SESSION_PAUSED",
        detail=encode_detail({"mode": session.mode}),
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": "SESSION_PAUSED",
        "session_id": session.session_id,
        "message": "Session paused",
        "timestamp": now.isoformat(),
    }


@router.post("/stop")
async def stop_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    now = datetime.utcnow()
    session.is_active = False
    session.ended_at = now
    duration = (session.ended_at - session.started_at).total_seconds()
    db.add(LogEntry(
        session_id=session.session_id,
        operator=current_user.username,
        entry_type="INFO",
        event="SESSION_STOPPED",
        detail=encode_detail({
            "duration_seconds": round(duration, 2),
            "mode": session.mode,
        }),
    ))
    await db.commit()

    mock_robot.current_session_id = None
    return {
        "success": True,
        "event_type": "SESSION_STOPPED",
        "session_id": session.session_id,
        "duration_seconds": duration,
        "message": "Session stopped",
        "timestamp": now.isoformat(),
    }


@router.post("/tag")
async def add_tag(
    req: SessionTagRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    now = datetime.utcnow()
    db.add(LogEntry(
        session_id=session.session_id,
        operator=current_user.username,
        entry_type="TAG",
        event="TAG_ADDED",
        detail=encode_detail({
            "tag": req.tag,
            "note": req.note,
        }),
    ))
    await db.commit()

    return {
        "success": True,
        "event_type": "TAG_ADDED",
        "session_id": session.session_id,
        "message": "Tag added",
        "timestamp": now.isoformat(),
    }


@router.get("/current")
async def get_current_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, current_user.id)
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
    session_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = session_id or mock_robot.current_session_id
    if not sid:
        return []

    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.session_id == sid)
        .order_by(LogEntry.timestamp.asc())
    )
    entries = result.scalars().all()
    return [LogEntryOut.model_validate(entry) for entry in entries]


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = "csv",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LogEntry)
        .where(LogEntry.session_id == session_id)
        .order_by(LogEntry.timestamp.asc())
    )
    entries = result.scalars().all()

    if format == "json":
        data = [
            {
                "timestamp": entry.timestamp.isoformat(),
                "session_id": entry.session_id,
                "operator": entry.operator,
                "type": entry.entry_type,
                "event": entry.event,
                "detail": entry.detail,
            }
            for entry in entries
        ]
        return StreamingResponse(
            io.BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={session_id}.json"},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Session ID", "Operator", "Type", "Event", "Detail"])
    for entry in entries:
        writer.writerow([
            entry.timestamp.isoformat(),
            entry.session_id,
            entry.operator,
            entry.entry_type,
            entry.event,
            entry.detail or "",
        ])
    output.seek(0)

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={session_id}.csv"},
    )
