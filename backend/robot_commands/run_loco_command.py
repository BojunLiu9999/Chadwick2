import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

if len(sys.argv) < 3:
    print("Usage: python3 run_loco_command.py <interface> <command>")
    sys.exit(1)

iface = sys.argv[1]
command = sys.argv[2]

ChannelFactoryInitialize(0, iface)

client = LocoClient()
client.SetTimeout(10.0)
client.Init()

# SAFE slow speeds first
if command == "MOVE_FWD":
    client.Move(0.1, 0, 0)

elif command == "MOVE_BACK":
    client.Move(-0.1, 0, 0)

elif command == "TURN_LEFT":
    client.Move(0, 0, 0.15)

elif command == "TURN_RIGHT":
    client.Move(0, 0, -0.15)

elif command == "STOP":
    client.Move(0, 0, 0)

elif command == "high stand":
    client.HighStand()

else:
    print(f"Invalid locomotion command: {command}")
    sys.exit(1)

print(f"DONE: {command}")
time.sleep(0.2)
