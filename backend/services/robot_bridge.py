"""
Real robot bridge using Unitree SDK2 Python.

支持：
  - unitree_mujoco 仿真器（设 ROBOT_IFACE=lo）
  - 真实 G1 EDU（设 ROBOT_IFACE=eth0 或 enp2s0，机器人 IP 在 192.168.123.x 网段）

依赖：
  pip install unitree-sdk2py  (或从源码 pip install -e .)
  必须 Python 3.10
  必须设置 CYCLONEDDS_HOME 环境变量

外部接口与 MockRobot 保持一致：
  connect/disconnect, get_status, get_telemetry, execute_command,
  estop/release_estop, set_armed, apply_safety_config
"""
import asyncio
import threading
import time
from datetime import datetime
from enum import Enum

from config import settings
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import BmsState_


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"


class RealRobotBridge:
    

    def __init__(self):
        
        self.connection: ConnectionState = ConnectionState.DISCONNECTED
        self.last_error: str | None = None
        self.connected_at: float | None = None
        self._conn_lock = asyncio.Lock()

        
        self.motion_armed = False
        self.estop_active = False
        self.current_mode = "mobility_drills"
        self.current_session_id = None

        
        self._loco_client = None
        self._low_state = None
        self._low_state_count = 0
        self._low_state_recv_at = None
        self._state_lock = threading.Lock()
        self._sub = None

        self._bms_state = None
        self._bms_state_count = 0
        self._bms_state_recv_at = None
        self._bms_sub = None

        self._double_init_recoveries = 0


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
            return "Connecting to robot via Unitree SDK..."
        if self.estop_active:
            return "Robot connected, E-Stop active"
        if self.motion_armed:
            return "Robot ready for teleoperation"
        if self.connection == ConnectionState.READY:
            return "Robot connected, ready for arming"
        return "Robot connected"

    # ───────────── 连接管理 ─────────────
    async def connect(self) -> dict:
        async with self._conn_lock:
            if self.connection != ConnectionState.DISCONNECTED:
                raise ValueError(f"cannot connect from state: {self.connection.value}")
            self.connection = ConnectionState.CONNECTING
            self.last_error = None

        try:
            # SDK 初始化是阻塞的，扔到线程池
            await asyncio.to_thread(self._sdk_init)

            async with self._conn_lock:
                self.connection = ConnectionState.CONNECTED
                self.connected_at = datetime.utcnow().timestamp()

            # 等第一帧 LowState 到达，确认通信通了
            await self._wait_first_state(timeout=3.0)

            async with self._conn_lock:
                self.connection = ConnectionState.READY
            return await self.get_status()

        except Exception as exc:
            async with self._conn_lock:
                self.connection = ConnectionState.DISCONNECTED
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.connected_at = None
                self.motion_armed = False
            raise

    async def disconnect(self) -> dict:
        async with self._conn_lock:
            if self.connection == ConnectionState.DISCONNECTED:
                return await self.get_status()

        try:
            # 软急停一下，避免机器人保持运动
            if self._loco_client is not None:
                try:
                    await asyncio.to_thread(self._loco_client.Damp)
                except Exception:
                    pass
        finally:
            async with self._conn_lock:
                self.connection = ConnectionState.DISCONNECTED
                self.connected_at = None
                self.last_error = None
                self.motion_armed = False
                self._low_state = None
                self._bms_state = None
                # SDK 没有显式 close，下次 connect 重新 Init
                self._loco_client = None
                self._sub = None
                self._bms_sub = None

        return await self.get_status()

    def _sdk_init(self):
        """阻塞调用，跑在线程池里。"""
        # 延迟 import：让 ROBOT_MODE=mock 时不需要装 SDK
        from unitree_sdk2py.core.channel import (
            ChannelFactoryInitialize, ChannelSubscriber,
        )
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
        from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

        # G1 用的是 unitree_hg IDL（不是 unitree_go），别搞错
        # Disconnect → Reconnect within the same backend process: the SDK's
        # ChannelFactoryInitialize is effectively a module-level singleton —
        # calling it twice raises. Tolerate that one case and reuse the
        # existing factory; any other failure still bubbles up. See audit
        # for the known Disconnect → Reconnect issue.
        try:
            ChannelFactoryInitialize(settings.ROBOT_DOMAIN_ID, settings.ROBOT_IFACE)
        except Exception as e:
            if "already" in str(e).lower():
                import sys
                print(
                    f"[real_robot] ChannelFactory already initialized, reusing: {e}",
                    file=sys.stderr,
                )
                self._double_init_recoveries += 1
            else:
                raise

        # 订阅 LowState（包含 IMU、电机、电池等）
        self._sub = ChannelSubscriber("rt/lowstate", LowState_)
        self._sub.Init(self._on_low_state, 10)

        # 订阅 BMS（rt/bmsstate 才是真电量 SOC；失败不影响主链路）
        try:
            self._bms_sub = ChannelSubscriber('rt/bmsstate', BmsState_)
            self._bms_sub.Init(self._on_bms_state, 10)
        except Exception as e:
            import sys
            print(f"[real_robot] BMS subscription failed (continuing without battery): {e!r}",
                  file=sys.stderr)
            self._bms_sub = None

        # 高层运动客户端
        self._loco_client = LocoClient()
        self._loco_client.SetTimeout(10.0)
        self._loco_client.Init()

    def _on_low_state(self, msg):
        """SDK 的回调，跑在 SDK 自己的线程，不能 await。"""
        with self._state_lock:
            self._low_state = msg
            self._low_state_count += 1
            self._low_state_recv_at = time.monotonic()
            cnt = self._low_state_count
            bms = self._bms_state
            bms_cnt = self._bms_state_count

        # DEBUG: remove after temp/battery investigation
        if cnt % 200 == 0:
            try:
                import sys
                m0 = msg.motor_state[0]
                print(f"[DBG] tick={msg.tick}, "
                      f"motor[0].temp={list(m0.temperature)}, "
                      f"bms_count={bms_cnt}, "
                      f"bms_soc={bms.soc if bms else None}",
                      file=sys.stderr)
            except Exception as e:
                import sys
                print(f"[DBG] {e!r}", file=sys.stderr)

    def _on_bms_state(self, msg):
        """SDK 的回调，跑在 SDK 自己的线程，不能 await。"""
        with self._state_lock:
            self._bms_state = msg
            self._bms_state_count += 1
            self._bms_state_recv_at = time.monotonic()

    async def _wait_first_state(self, timeout: float):
        start = time.time()
        while time.time() - start < timeout:
            with self._state_lock:
                if self._low_state is not None:
                    return
            await asyncio.sleep(0.05)
        raise TimeoutError(
            f"No LowState received in {timeout}s. "
            f"Check: (1) iface={settings.ROBOT_IFACE} (2) simulator/robot is running "
            f"(3) robot is NOT in debug mode"
        )

    # ───────────── 状态查询 ─────────────
    async def get_status(self) -> dict:
        battery = self._read_battery()
        return {
            "connection":     self.connection.value,
            "last_error":     self.last_error,
            "connected_at":   self.connected_at,
            "connected":      self.is_connected,
            "motion_armed":   self.motion_armed,
            "current_mode":   self.current_mode,
            "battery_pct":    battery,
            "estop_active":   self.estop_active,
            "system_status":  self._get_system_status(),
            "status_message": self._get_status_message(),
            "updated_at":     f"{datetime.utcnow().isoformat()}Z",
        }

    async def get_telemetry(self) -> dict:
        """从 LowState 翻译成前端能认的格式（字段名跟 mock 完全一致）。"""
        with self._state_lock:
            s = self._low_state

        if s is None:
            # 还没收到状态，返回安全默认值
            return {
                "timestamp":     f"{datetime.utcnow().isoformat()}Z",
                "battery_pct":   0,
                "imu_tilt_deg":  0,
                "latency_ms":    0,
                "core_temp_c":   0,
                "signal_dbm":    0,
                "motor_loads":   {"L_HIP": 0, "R_HIP": 0, "L_KNEE": 0, "R_KNEE": 0,
                                  "L_ANKLE": 0, "R_ANKLE": 0},
                "estop_active":  self.estop_active,
                "motion_armed":  self.motion_armed,
                "current_mode":  self.current_mode,
                "system_status": self._get_system_status(),
            }

        # G1 23DoF 关节索引（从官方 G1JointIndex 推导，可能要按实测调整）
        # 参考: https://support.unitree.com/home/en/G1_developer/about_G1
        # left_hip_pitch=0, left_knee=3, left_ankle_pitch=4
        # right_hip_pitch=6, right_knee=9, right_ankle_pitch=10
        try:
            tilt = abs(s.imu_state.rpy[1]) * 57.2958  # rad → deg
        except Exception:
            tilt = 0.0

        try:
            motor_loads = {
                "L_HIP":   self._motor_load_pct(s, 0),
                "R_HIP":   self._motor_load_pct(s, 6),
                "L_KNEE":  self._motor_load_pct(s, 3),
                "R_KNEE":  self._motor_load_pct(s, 9),
                "L_ANKLE": self._motor_load_pct(s, 4),
                "R_ANKLE": self._motor_load_pct(s, 10),
            }
        except Exception:
            motor_loads = {"L_HIP": 0, "R_HIP": 0, "L_KNEE": 0,
                           "R_KNEE": 0, "L_ANKLE": 0, "R_ANKLE": 0}

        return {
            "timestamp":     f"{datetime.utcnow().isoformat()}Z",
            "battery_pct":   self._read_battery(),
            "imu_tilt_deg":  round(tilt, 2),
            "latency_ms":    20,   # SDK 没有直接给延迟，先固定
            "core_temp_c":   self._read_max_temp(s),
            "signal_dbm":    -60,  # 仿真器没有，先固定
            "motor_loads":   motor_loads,
            "estop_active":  self.estop_active,
            "motion_armed":  self.motion_armed,
            "current_mode":  self.current_mode,
            "system_status": self._get_system_status(),
        }

    def _read_battery(self):
        # SOC 来自 rt/bmsstate（uint8, 0-100）。BMS 还没收到时返回 None，
        # 让上层把"没数据"和"电量为 0"区分开。
        try:
            with self._state_lock:
                bms = self._bms_state
            if bms is None:
                return None
            return int(bms.soc)
        except Exception:
            return None

    def _read_max_temp(self, s) -> float:
        try:
            # motor_state[i].temperature is [coil, mos]; flatten across all
            # 23 joints and take the max so the surfaced number reflects
            # whichever component is hottest.
            temps = [t for m in s.motor_state[:23] for t in m.temperature]
            return float(max(temps)) if temps else 0.0
        except (TypeError, ValueError, IndexError, AttributeError):
            return 0.0

    def _motor_load_pct(self, s, idx: int) -> int:
        """把电机扭矩估值换算成百分比（max_torque_pct 配置作为分母）。"""
        try:
            tau = abs(s.motor_state[idx].tau_est)
            # G1 髋/膝最大扭矩约 88 Nm，踝约 50 Nm；这里用粗略上限
            max_tau = 88.0
            pct = round(tau / max_tau * 100)
            return max(0, min(100, pct))
        except Exception:
            return 0

    # ───────────── 指令下发 ─────────────
    async def execute_command(self, command: str, params: dict | None = None) -> str:
        # MODE_* 是纯前端状态切换，不下发到机器人
        if command.startswith("MODE_"):
            self.current_mode = command.removeprefix("MODE_").lower()
            return f"Mode set to {self.current_mode}"

        if not self.is_connected:
            return "BLOCKED: robot is disconnected"
        if self.connection != ConnectionState.READY:
            return f"BLOCKED: robot not ready (state: {self.connection.value})"
        if self.estop_active:
            return "BLOCKED: E-Stop is active"
        if not self.motion_armed and command not in ("STOP", "HOME_POSE"):
            return "BLOCKED: Motion not armed"

        try:
            await asyncio.to_thread(self._execute_sync, command, params or {})
            return f"OK: {command}"
        except Exception as exc:
            return f"FAIL: {type(exc).__name__}: {exc}"

    def _execute_sync(self, command: str, params: dict):
        """阻塞 SDK 调用。max_speed 等参数从 _safety_config 读。"""
        c = self._loco_client
        if c is None:
            raise RuntimeError("LocoClient not initialized")

        v = float(self._safety_config.get("max_speed", 0.3))
        w = float(self._safety_config.get("turn_rate", 30.0)) * 0.0174533  # deg/s → rad/s

        if   command == "MOVE_FWD":     c.Move(v, 0, 0)
        elif command == "MOVE_BACK":    c.Move(-v, 0, 0)
        elif command == "TURN_LEFT":    c.Move(0, 0, w)
        elif command == "TURN_RIGHT":   c.Move(0, 0, -w)
        elif command == "STOP":         c.Move(0, 0, 0)
        elif command == "HOME_POSE":    c.HighStand()
        elif command == "STAND_STILL":  c.HighStand()
        elif command == "WAVE":         c.WaveHand()
        elif command == "SHAKE":        c.ShakeHand()
        elif command == "SQUAT":        c.StandUp2Squat()
        elif command == "STAND_FROM_SQUAT": c.Squat2StandUp()
        elif command == "STAND_FROM_LIE":   c.Lie2StandUp()
        elif command == "ZERO_TORQUE":  c.ZeroTorque()
        else:
            raise ValueError(f"Unknown command: {command}")

    # ───────────── 安全 ─────────────
    async def estop(self):
        self.estop_active = True
        self.motion_armed = False
        if self._loco_client is not None:
            try:
                await asyncio.to_thread(self._loco_client.Damp)
            except Exception:
                pass

    async def release_estop(self):
        self.estop_active = False

    async def set_armed(self, armed: bool):
        if armed and self.connection != ConnectionState.READY:
            raise ValueError("Cannot arm while robot is not ready")
        if armed and self.estop_active:
            raise ValueError("Cannot arm while E-Stop is active")
        self.motion_armed = armed

    async def apply_safety_config(self, config: dict):
        self._safety_config.update(config)


# 模块级单例
real_robot = RealRobotBridge()
