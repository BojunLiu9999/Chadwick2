import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map

if len(sys.argv) < 3:
    print("Usage: python3 run_arm_action.py <interface> <command>")
    sys.exit(1)

iface = sys.argv[1]
command = sys.argv[2]

ChannelFactoryInitialize(0, iface)

client = G1ArmActionClient()
client.SetTimeout(10.0)
client.Init()

if command not in action_map:
    print("Invalid command")
    sys.exit(1)

ret = client.ExecuteAction(action_map.get(command))
print(f"ExecuteAction return: {ret}")

# Optional: auto release
time.sleep(2)

release_ret = client.ExecuteAction(action_map.get("release arm"))
print(f"Release arm return: {release_ret}")

print("DONE")
