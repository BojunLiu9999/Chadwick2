"""
模拟机器人服务 — 开发阶段使用，不需要真实机器人
当 ROBOT_MODE=real 时，替换为 robot_bridge.py

负责人：组员C（后续对接真实 ROS2 / Unitree SDK）
"""
import random, asyncio
from datetime import datetime


class MockRobot:
    """模拟 Unitree G1 机器人，返回假数据用于开发"""

    def __init__(self):
        self.connected = True
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

    def _system_status(self) -> str:
        if not self.connected:
            return "disconnected"
        if self.motion_armed and not self.estop_active:
            return "ready"
        return "connected"

    async def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "motion_armed": self.motion_armed,
            "current_mode": self.current_mode,
            "battery_pct": self._battery,
            "estop_active": self.estop_active,
            "system_status": self._system_status(),
            "status_message": "Robot connected, motion disarmed" if self.connected and not self.motion_armed else "Robot ready" if self.motion_armed else "Robot disconnected",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    async def get_telemetry(self) -> dict:
        """每次调用返回略微随机的遥测数据（模拟传感器噪声）"""
        self._battery = max(0, self._battery - 0.002)
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
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
            "system_status": self._system_status(),
        }

    async def execute_command(self, command: str, params: dict = None) -> str:
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
        if self.estop_active and armed:
            raise ValueError("Cannot arm while E-Stop is active")
        self.motion_armed = armed

    async def apply_safety_config(self, config: dict):
        self._safety_config.update(config)


mock_robot = MockRobot()
