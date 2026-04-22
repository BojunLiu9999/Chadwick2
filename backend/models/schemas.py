"""
Pydantic schemas for request and response payloads.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str


class UserInfo(BaseModel):
    username: str
    display_name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class RobotCommand(BaseModel):
    command: str
    duration_ms: Optional[int] = None
    params: Optional[dict] = None


class RobotStatus(BaseModel):
    connection: str
    last_error: Optional[str] = None
    connected_at: Optional[float] = None
    connected: bool
    motion_armed: bool
    current_mode: str
    battery_pct: float
    estop_active: bool
    system_status: Optional[str] = None
    status_message: Optional[str] = None
    updated_at: Optional[datetime] = None


class TelemetrySnapshot(BaseModel):
    timestamp: datetime
    battery_pct: float
    imu_tilt_deg: float
    latency_ms: float
    core_temp_c: float
    signal_dbm: float
    motor_loads: dict
    estop_active: Optional[bool] = None
    motion_armed: Optional[bool] = None
    current_mode: Optional[str] = None
    system_status: Optional[str] = None
    pose: Optional[dict] = None


class SessionStartRequest(BaseModel):
    mode: str


class SessionTagRequest(BaseModel):
    tag: str
    note: Optional[str] = None


class LogEntryOut(BaseModel):
    session_id: str
    timestamp: datetime
    operator: str
    entry_type: str
    event: str
    detail: Optional[str]

    class Config:
        from_attributes = True


class SessionSummary(BaseModel):
    session_id: str
    operator: str
    mode: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[float]
    command_count: int
    incident_count: int
    log_entries: List[LogEntryOut]


class SafetyConfigUpdate(BaseModel):
    max_speed: Optional[float] = None
    turn_rate: Optional[float] = None
    max_torque_pct: Optional[float] = None
    temp_warn: Optional[float] = None
    temp_stop: Optional[float] = None
    active_zone: Optional[str] = None
