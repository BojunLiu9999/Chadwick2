import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

if len(sys.argv) < 3:
    print("Usage: python3 run_loco_command.py <interface> <command>", file=sys.stderr)
    sys.exit(1)

iface = sys.argv[1]
command = sys.argv[2]

VX = 0.3
VY = 0.3
VYAW = 0.5

velocity_by_command = {
    "MOVE_FWD":   (VX, 0.0, 0.0),
    "MOVE_BACK":  (-VX, 0.0, 0.0),
    "MOVE_LEFT":  (0.0, VY, 0.0),
    "MOVE_RIGHT": (0.0, -VY, 0.0),
    "TURN_LEFT":  (0.0, 0.0, VYAW),
    "TURN_RIGHT": (0.0, 0.0, -VYAW),
    "STOP":       (0.0, 0.0, 0.0),
}

if command not in velocity_by_command and command != "high stand":
    print(f"Invalid locomotion command: {command}", file=sys.stderr)
    sys.exit(1)

ChannelFactoryInitialize(0, iface)

client = LocoClient()
client.SetTimeout(10.0)
client.Init()

if command == "high stand":
    ret = client.HighStand()
else:
    vx, vy, vyaw = velocity_by_command[command]
    ret = client.Move(vx, vy, vyaw)

if ret is not None and ret != 0:
    print(
        f"FAIL: {command} returned {ret}. "
        f"Robot likely not in sport_mode - operator press R2+A on the handheld controller.",
        file=sys.stderr,
    )
    sys.exit(2)

print(f"DONE: {command}")
time.sleep(0.2)
