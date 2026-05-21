"""
Sidecar for voice-triggered walking with a finite duration + auto-stop.

Differs from run_loco_command.py in that this fires Move(v, ...), sleeps for
the requested duration, then explicitly fires Move(0, 0, 0) before exiting —
the caller (routers/voice.py) can also kill us mid-sleep to interrupt the
walk on a "stop" utterance. In that case the watchdog (1 s) is the backstop
that catches the missing follow-up STOP.

Usage:
  python3 run_voice_walk.py <iface> <command> <duration_s>

Where <command> is one of MOVE_FWD/MOVE_BACK/TURN_LEFT/TURN_RIGHT.
"""
import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient


if len(sys.argv) < 4:
    print("Usage: python3 run_voice_walk.py <interface> <command> <duration_s>",
          file=sys.stderr)
    sys.exit(1)

iface = sys.argv[1]
command = sys.argv[2]
try:
    duration_s = float(sys.argv[3])
except ValueError:
    print(f"Invalid duration: {sys.argv[3]!r}", file=sys.stderr)
    sys.exit(1)

if duration_s <= 0 or duration_s > 10.0:
    # Hard cap as a defence-in-depth: even if the voice intent parser
    # produces nonsense, a single voice utterance can't walk for >10 s.
    print(f"Duration out of range (0, 10]: {duration_s}", file=sys.stderr)
    sys.exit(1)

VX = 0.3
VYAW = 0.5

velocity_by_command = {
    "MOVE_FWD":   (VX, 0.0, 0.0),
    "MOVE_BACK":  (-VX, 0.0, 0.0),
    "TURN_LEFT":  (0.0, 0.0, VYAW),
    "TURN_RIGHT": (0.0, 0.0, -VYAW),
}

if command not in velocity_by_command:
    print(f"Invalid voice walk command: {command}", file=sys.stderr)
    sys.exit(1)

ChannelFactoryInitialize(0, iface)

client = LocoClient()
client.SetTimeout(10.0)
client.Init()

vx, vy, vyaw = velocity_by_command[command]

# Send the velocity setpoint. If sport_mode isn't engaged this returns
# non-zero; same surfaced-error pattern as run_loco_command.py.
ret = client.Move(vx, vy, vyaw)
if ret is not None and ret != 0:
    print(
        f"FAIL: {command} returned {ret}. "
        f"Robot likely not in sport_mode - operator press R2+A on the handheld controller.",
        file=sys.stderr,
    )
    sys.exit(2)

# Walk for the requested duration. If the parent kills us during this sleep,
# the velocity setpoint persists on the robot — the parent is responsible for
# firing its own STOP after the kill (and the 1 s watchdog catches drops).
try:
    time.sleep(duration_s)
finally:
    # Always try to bring the velocity back to zero on the way out, even on
    # exception. This is the auto-stop that makes the "N-step" semantics work.
    try:
        client.Move(0.0, 0.0, 0.0)
    except Exception as exc:
        print(f"WARN: auto-stop Move(0) failed: {exc}", file=sys.stderr)
        # Don't exit 2 here — we already walked the full duration; the
        # operator-facing failure is "didn't stop", but the watchdog
        # will catch it within 1 s anyway.

print(f"DONE: {command} {duration_s}s")
