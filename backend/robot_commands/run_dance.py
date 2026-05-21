"""
Sidecar for voice-triggered scripted arm-only routines (currently "slow dance").

Init the SDK once, walk through a sequence of (action, hold_sec) steps,
always release_arm on the way out. Killable mid-routine by the parent — the
final `release arm` in the except/finally guard is best-effort.

Usage:
  python3 run_dance.py <iface> <routine>

Routines:
  slow_dance — gentle 4-gesture sequence, kid-friendly, ~10 s total.
"""
import sys
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map


ROUTINES = {
    # (action_name, hold_seconds). hold_seconds is the wait AFTER firing the
    # action, before the next one. Tuned for "slow" — kids should be able to
    # follow along and copy.
    "slow_dance": [
        ("high wave",   1.8),
        ("clap",        1.2),
        ("hands up",    1.5),
        ("heart",       1.8),
    ],
    # Slow dance with "shake hand" interleaved between the slow gestures —
    # more energetic, more shake-feel, still arm-only. Password-gated at the
    # voice router level because it's the flashier crowd-pleaser.
    "shake_dance": [
        ("high wave",   1.2),
        ("shake hand",  0.9),
        ("clap",        0.9),
        ("shake hand",  0.9),
        ("hands up",    1.0),
        ("shake hand",  0.9),
        ("heart",       1.5),
    ],
}


if len(sys.argv) < 3:
    print("Usage: python3 run_dance.py <interface> <routine>", file=sys.stderr)
    sys.exit(1)

iface = sys.argv[1]
routine = sys.argv[2]

if routine not in ROUTINES:
    print(f"Unknown routine: {routine!r}. Known: {list(ROUTINES)}", file=sys.stderr)
    sys.exit(1)

sequence = ROUTINES[routine]

ChannelFactoryInitialize(0, iface)

client = G1ArmActionClient()
client.SetTimeout(10.0)
client.Init()

print(f"START: {routine} ({len(sequence)} steps)")

try:
    for action_name, hold_s in sequence:
        action_id = action_map.get(action_name)
        if action_id is None:
            print(f"SKIP: unknown action {action_name!r}", file=sys.stderr)
            continue
        ret = client.ExecuteAction(action_id)
        print(f"STEP: {action_name} -> rc={ret}")
        if ret is not None and ret != 0:
            # An action failure mid-routine still attempts the rest — one bad
            # gesture shouldn't strand the arms in a weird pose.
            print(f"WARN: {action_name} returned {ret}", file=sys.stderr)
        time.sleep(hold_s)
finally:
    # Always try to return arms to neutral, even on KeyboardInterrupt / SIGTERM
    # from the parent. Wrapped in try so we still exit cleanly if release fails.
    try:
        client.ExecuteAction(action_map.get("release arm"))
    except Exception as exc:
        print(f"WARN: final release arm failed: {exc}", file=sys.stderr)

print(f"DONE: {routine}")
