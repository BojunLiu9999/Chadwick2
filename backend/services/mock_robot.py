"""
模拟机器人服务 — 开发阶段使用，不需要真实机器人
当 ROBOT_MODE=real 时，替换为 robot_bridge.py

负责人：组员C（后续对接真实 ROS2 / Unitree SDK）
"""
import random, asyncio
from datetime import datetime
from enum import Enum


class ConnectionState(str, Enum):
    """连接状态机：disconnected → connecting → connected → ready"""
    DISCONNECTED = "disconnected"
    CONNECTING   = "connecting"
    CONNECTED    = "connected"
    READY        = "ready"


class MockRobot:
    """模拟 Unitree G1 机器人，返回假数据用于开发"""

    def __init__(self):
        # ── 连接状态（1号成员负责）──
        self.connection: ConnectionState = ConnectionState.DISCONNECTED
        self.last_error: str | None = None
        self.connected_at: float | None = None
        self._conn_lock = asyncio.Lock()   # 防止并发点"连接"搞乱状态

        # ── 安全/运动状态（2号成员负责，别动）──
        self.motion_armed = False
        self.estop_active = False

        # ── 其他 ──
        self.current_mode = "idle"
        self.current_session_id = None
        self._battery = 72.0
        self._safety_config = {
            "max_speed": 0.4,
            "turn_rate": 30.0,
            "max_torque_pct": 40.0,
        }

    # ────────────────────────────────────────────
    # 连接管理（1号成员任务核心）
    # ────────────────────────────────────────────
    @property
    def is_connected(self) -> bool:
        """给旧代码用的向后兼容属性（2号成员的逻辑可能在读）"""
        return self.connection in (ConnectionState.CONNECTED, ConnectionState.READY)

    async def connect(self) -> dict:
        """
        触发连接流程：disconnected → connecting → connected → ready
        失败则回到 disconnected 并记录 last_error。
        """
        # 第一步：抢锁并切到 connecting
        async with self._conn_lock:
            if self.connection != ConnectionState.DISCONNECTED:
                raise ValueError(
                    f"cannot connect from state: {self.connection.value}"
                )
            self.connection = ConnectionState.CONNECTING
            self.last_error = None

        # 握手过程不加锁（真实 SDK 会慢，不能卡住 /status）
        try:
            await self._do_handshake()

            async with self._conn_lock:
                self.connection = ConnectionState.CONNECTED
                self.connected_at = datetime.utcnow().timestamp()

            await self._do_post_init()

            async with self._conn_lock:
                self.connection = ConnectionState.READY

            return await self.get_status()

        except Exception as e:
            async with self._conn_lock:
                self.connection = ConnectionState.DISCONNECTED
                self.last_error = str(e)
                self.connected_at = None
            raise

    async def disconnect(self) -> dict:
        """断开连接（幂等：已经断开的话直接返回）"""
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
                # 安全起见：断开时也撤销 arm 状态
                self.motion_armed = False
        return await self.get_status()

    # ── 以下三个是"真实 SDK 接入时"要改的地方 ──
    async def _do_handshake(self):
        """接真实 Unitree SDK 时，换成 ChannelFactoryInitialize + 订阅 LowState"""
        await asyncio.sleep(0.8)   # 模拟握手耗时，前端就能看到 connecting
        # 想测失败分支时取消注释：
        # raise RuntimeError("handshake timeout")

    async def _do_post_init(self):
        await asyncio.sleep(0.3)

    async def _do_teardown(self):
        await asyncio.sleep(0.1)

    # ────────────────────────────────────────────
    # 状态查询
    # ────────────────────────────────────────────
    async def get_status(self) -> dict:
        return {
            # 新字段（1号）
            "connection":   self.connection.value,
            "last_error":   self.last_error,
            "connected_at": self.connected_at,
            # 旧字段（向后兼容，2号和前端现有代码在用）
            "connected":    self.is_connected,
            "motion_armed": self.motion_armed,
            "current_mode": self.current_mode,
            "battery_pct":  self._battery,
            "estop_active": self.estop_active,
        }

    async def get_telemetry(self) -> dict:
        """每次调用返回略微随机的遥测数据（模拟传感器噪声）"""
        self._battery = max(0, self._battery - 0.002)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "battery_pct": round(self._battery, 1),
            "imu_tilt_deg": round(random.uniform(0, 1.5), 2),
            "latency_ms": round(random.uniform(14, 24), 1),
            "core_temp_c": round(random.uniform(52, 56), 1),
            "signal_dbm": round(random.uniform(-65, -58), 1),
            "motor_loads": {
                "L_HIP":   round(random.uniform(30, 40)),
                "R_HIP":   round(random.uniform(32, 42)),
                "L_KNEE":  round(random.uniform(65, 75)),
                "R_KNEE":  round(random.uniform(40, 50)),
                "L_ANKLE": round(random.uniform(24, 32)),
                "R_ANKLE": round(random.uniform(26, 34)),
            },
            "estop_active": self.estop_active,
            "motion_armed": self.motion_armed,
        }

    # ────────────────────────────────────────────
    # 指令执行（加一条：未 ready 不能接指令）
    # ────────────────────────────────────────────
    async def execute_command(self, command: str, params: dict = None) -> str:
        if self.connection != ConnectionState.READY:
            return f"BLOCKED: robot not ready (state: {self.connection.value})"
        if self.estop_active:
            return "BLOCKED: E-Stop is active"
        if not self.motion_armed and command not in ("STOP", "HOME_POSE"):
            return "BLOCKED: Motion not armed"

        await asyncio.sleep(0.05)

        command_map = {
            "MOVE_FWD":    "Moving forward",
            "MOVE_BACK":   "Moving backward",
            "TURN_LEFT":   "Turning left",
            "TURN_RIGHT":  "Turning right",
            "STOP":        "Stopped",
            "HOME_POSE":   "Returning to home pose",
            "WAVE":        "Waving",
            "STAND_STILL": "Standing still",
        }
        return command_map.get(command, f"Unknown command: {command}")

    # ── 以下是 2 号成员的领地，没改 ──
    async def estop(self):
        self.estop_active = True
        self.motion_armed = False

    async def release_estop(self):
        self.estop_active = False

    async def set_armed(self, armed: bool):
        if self.estop_active and armed:
            raise ValueError("Cannot arm while E-Stop is active")
        if not self.is_connected and armed:
            raise ValueError("Cannot arm while robot is disconnected")
        self.motion_armed = armed

    async def apply_safety_config(self, config: dict):
        self._safety_config.update(config)


mock_robot = MockRobot()