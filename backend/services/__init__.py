from config import settings

if settings.ROBOT_MODE == "real":
    from .robot_bridge import real_robot as robot
    print(f"[services] using REAL robot bridge on iface={settings.ROBOT_IFACE}")
else:
    from .mock_robot import mock_robot as robot
    print("[services] using MOCK robot")

__all__ = ["robot"]
