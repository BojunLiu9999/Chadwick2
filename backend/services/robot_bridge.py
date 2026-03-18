"""
真实机器人桥接层（占位文件）
负责人：组员C

当 .env 中 ROBOT_MODE=real 时，main.py 改为 import 这个模块。

TODO 清单：
1. 连接 Unitree SDK / ROS2 节点
2. 订阅遥测话题（/imu, /battery, /joint_states 等）
3. 发布控制话题（/cmd_vel, /action 等）
4. 实现 E-Stop（/emergency_stop 话题）
5. 地理围栏检测（订阅 /odom，与允许区域对比）

参考文档：
- Unitree SDK: https://github.com/unitreerobotics/unitree_sdk2_python
- ROS2 文档: https://docs.ros.org/en/foxy/
"""

class RealRobotBridge:
    def __init__(self):
        self.current_session_id = None
        # TODO: 初始化 ROS2 节点
        # import rclpy
        # rclpy.init()
        # self.node = rclpy.create_node('chadwick_bridge')
        raise NotImplementedError("真实机器人桥接层尚未实现，请先使用 mock 模式")

    async def get_status(self): ...
    async def get_telemetry(self): ...
    async def execute_command(self, command, params=None): ...
    async def estop(self): ...
    async def release_estop(self): ...
    async def set_armed(self, armed): ...
    async def apply_safety_config(self, config): ...
