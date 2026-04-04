"""
Pydantic 数据模型 — 定义API请求和响应的数据格式
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── 认证 ──
class LoginRequest(BaseModel):
    username: str
    password: str
    role: str           # "operator" | "supervisor"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"

class UserInfo(BaseModel):
    username: str
    display_name: str
    role: str


# ── 机器人指令 ──
class RobotCommand(BaseModel):
    command: str        # MOVE_FWD / MOVE_BACK / TURN_LEFT / TURN_RIGHT / STOP / HOME_POSE / WAVE
    duration_ms: Optional[int] = None
    params: Optional[dict] = None

class RobotStatus(BaseModel):
    connected: bool
    motion_armed: bool
    current_mode: str
    battery_pct: float
    estop_active: bool
    system_status: Optional[str] = None
    status_message: Optional[str] = None
    updated_at: Optional[datetime] = None


# ── 遥测数据 ──
class TelemetrySnapshot(BaseModel):
    timestamp: datetime
    battery_pct: float
    imu_tilt_deg: float
    latency_ms: float
    core_temp_c: float
    signal_dbm: float
    motor_loads: dict    # {"L_HIP": 34, "R_HIP": 36, ...}
    pose: Optional[dict] = None


# ── 会话 ──
class SessionStartRequest(BaseModel):
    mode: str           # "mobility_drills" | "telepresence" | "choreography"

class SessionTagRequest(BaseModel):
    tag: str
    note: Optional[str] = None

class LogEntryOut(BaseModel):
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


# ── 安全配置 ──
class SafetyConfigUpdate(BaseModel):
    max_speed: Optional[float] = None
    turn_rate: Optional[float] = None
    max_torque_pct: Optional[float] = None
    temp_warn: Optional[float] = None
    temp_stop: Optional[float] = None
    active_zone: Optional[str] = None
