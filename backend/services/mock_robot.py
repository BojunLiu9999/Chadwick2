"""
Mock robot service used during development and frontend integration.
"""
import asyncio
import random
from datetime import datetime
from enum import Enum


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"


class MockRobot:
    """A lightweight Unitree G1 mock."""

    def __init__(self):
        self.connection: ConnectionState = ConnectionState.DISCONNECTED
        self.last_error: str | None = None
        self.connected_at: float | None = None
        self._conn_lock = asyncio.Lock()

        self.motion_armed = False
        self.estop_active = False
        self.current_mode = "mobility_drills"
        self.current_session_id = None
        self._battery = 72.0
        self._safety_config = {
            "max_speed": 0.4,
            "turn_rate": 30.0,
            "max_torque_pct": 40.0,
            "temp_warn": 60.0,
            "temp_stop": 70.0,
            "active_zone": "LAB G12",
        }

    @property
    def is_connected(self) -> bool:
        return self.connection in (ConnectionState.CONNECTED, ConnectionState.READY)

    @property
    def connected(self) -> bool:
        return self.is_connected

    def _get_system_status(self) -> str:
        if self.connection == ConnectionState.DISCONNECTED:
            return "disconnected"
        if self.connection == ConnectionState.CONNECTING:
            return "connecting"
        if self.connection == ConnectionState.READY and self.motion_armed and not self.estop_active:
            return "ready"
        return "connected"

    def _get_status_message(self) -> str:
        if self.connection == ConnectionState.DISCONNECTED:
            return "Robot disconnected"
        if self.connection == ConnectionState.CONNECTING:
            return "Robot connection in progress"
        if self.estop_active:
            return "Robot connected, E-Stop active"
        if self.motion_armed:
            return "Robot ready for teleoperation"
        if self.connection == ConnectionState.READY:
            return "Robot connected, ready for arming"
        return "Robot connected"

    async def connect(self) -> dict:
        async with self._conn_lock:
            if self.connection != ConnectionState.DISCONNECTED:
                raise ValueError(f"cannot connect from state: {self.connection.value}")

            self.connection = ConnectionState.CONNECTING
            self.last_error = None

        try:
            await self._do_handshake()

            async with self._conn_lock:
                self.connection = ConnectionState.CONNECTED
                self.connected_at = datetime.utcnow().timestamp()

            await self._do_post_init()

            async with self._conn_lock:
                self.connection = ConnectionState.READY

            return await self.get_status()
        except Exception as exc:
            async with self._conn_lock:
                self.connection = ConnectionState.DISCONNECTED
                self.last_error = str(exc)
                self.connected_at = None
                self.motion_armed = False
            raise

    async def disconnect(self) -> dict:
        async with self._conn_lock:
            if self.connection == ConnectionState.DISCONNECTED:
                return await self.get_status()

        try:
            await self._do_teardown()
        finally:
            async with self._conn_lock:
                self.connection = ConnectionState.DISCONNECTED
                self.connected_at = None
                self.last_error = None
                self.motion_armed = False

        return await self.get_status()

    async def _do_handshake(self):
        await asyncio.sleep(0.8)

    async def _do_post_init(self):
        await asyncio.sleep(0.3)

    async def _do_teardown(self):
        await asyncio.sleep(0.1)

    async def get_status(self) -> dict:
        return {
            "connection": self.connection.value,
            "last_error": self.last_error,
            "connected_at": self.connected_at,
            "connected": self.is_connected,
            "motion_armed": self.motion_armed,
            "current_mode": self.current_mode,
            "battery_pct": self._battery,
            "estop_active": self.estop_active,
            "system_status": self._get_system_status(),
            "status_message": self._get_status_message(),
            "updated_at": f"{datetime.utcnow().isoformat()}Z",
        }

    async def get_telemetry(self) -> dict:
        self._battery = max(0, self._battery - 0.002)
        return {
            "timestamp": f"{datetime.utcnow().isoformat()}Z",
            "battery_pct": round(self._battery, 1),
            "imu_tilt_deg": round(random.uniform(0, 1.5), 2),
            "latency_ms": round(random.uniform(14, 24), 1),
            "core_temp_c": round(random.uniform(52, 56), 1),
            "signal_dbm": round(random.uniform(-65, -58), 1),
            "motor_loads": {
                "L_HIP": round(random.uniform(30, 40)),
                "R_HIP": round(random.uniform(32, 42)),
                "L_KNEE": round(random.uniform(65, 75)),
                "R_KNEE": round(random.uniform(40, 50)),
                "L_ANKLE": round(random.uniform(24, 32)),
                "R_ANKLE": round(random.uniform(26, 34)),
            },
            "estop_active": self.estop_active,
            "motion_armed": self.motion_armed,
            "current_mode": self.current_mode,
            "system_status": self._get_system_status(),
        }

    async def execute_command(self, command: str, params: dict | None = None) -> str:
        if command.startswith("MODE_"):
            self.current_mode = command.removeprefix("MODE_").lower()
            await asyncio.sleep(0.02)
            return f"Mode set to {self.current_mode}"

        if not self.is_connected:
            return "BLOCKED: robot is disconnected"
        if self.connection != ConnectionState.READY:
            return f"BLOCKED: robot not ready (state: {self.connection.value})"
        if self.estop_active:
            return "BLOCKED: E-Stop is active"
        if not self.motion_armed and command not in ("STOP", "HOME_POSE"):
            return "BLOCKED: Motion not armed"

        await asyncio.sleep(0.05)

        command_map = {
            "MOVE_FWD": "Moving forward",
            "MOVE_BACK": "Moving backward",
            "TURN_LEFT": "Turning left",
            "TURN_RIGHT": "Turning right",
            "STOP": "Stopped",
            "HOME_POSE": "Returning to home pose",
            "WAVE": "Waving",
            "STAND_STILL": "Standing still",
        }
        return command_map.get(command, f"Unknown command: {command}")

    async def estop(self):
        self.estop_active = True
        self.motion_armed = False

    async def release_estop(self):
        self.estop_active = False

    async def set_armed(self, armed: bool):
        if armed and self.connection != ConnectionState.READY:
            raise ValueError("Cannot arm while robot is not ready")
        if self.estop_active and armed:
            raise ValueError("Cannot arm while E-Stop is active")
        self.motion_armed = armed

    async def apply_safety_config(self, config: dict):
        self._safety_config.update(config)


mock_robot = MockRobot()
