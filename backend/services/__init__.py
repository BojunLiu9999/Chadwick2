"""
Robot service factory.
根据 settings.ROBOT_MODE 决定加载哪个实现。
其他模块都通过 `from services import robot` 来引用，
这样切换 mock / real 不需要动业务代码。
"""
from config import settings

if settings.ROBOT_MODE == "real":
    from .robot_bridge import real_robot as robot
    print(f"[services] using REAL robot bridge on iface={settings.ROBOT_IFACE}")
else:
    from .mock_robot import mock_robot as robot
    print("[services] using MOCK robot")

__all__ = ["robot"]