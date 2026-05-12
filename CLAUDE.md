# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Chadwick II — FastAPI + React teleoperation console for a Unitree G1 EDU bipedal humanoid robot (USYD TechLab capstone). One web page lets an operator start sessions, connect to the robot, arm motion, teleop F/B/L/R, fire scripted arm gestures, and watch IMU/motor/temp telemetry. A supervisor role edits the safety envelope but does not drive. No remote deployment — operator, robot, and spotter share a room.

## Common commands

### Backend (Python 3.10+, from `backend/`)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000          # dev server
python -m py_compile <file>                    # only syntax check available (no test suite)
```

Env loaded by `config.py` from `env` or `.env`. Minimal mock config: `ROBOT_MODE=mock`, `SECRET_KEY=...`, `DATABASE_URL=sqlite+aiosqlite:///./chadwick.db`, `FRONTEND_URL=http://localhost:5173`. Lab template: `backend/.env.lab.example`.

### Frontend (from `frontend/`)

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api and /ws to :8000
npm run build
npm run preview
```

### Real robot prerequisites

- `unitree_sdk2py` + CycloneDDS installed in the backend venv; set `ROBOT_SDK_PYTHONPATH` to the `unitree_sdk2_python` checkout.
- Host NIC configured: `sudo ip addr add 192.168.123.222/24 dev eno3 && sudo ip link set eno3 up`; ping `192.168.123.164`.
- `.env`: `ROBOT_MODE=real`, `ROBOT_IFACE=eno3`, `ROBOT_DOMAIN_ID=0`.
- **Before any locomotion command, the handheld operator must press R2 + A to enter sport_mode.** Arm actions (Shake/Wave/Clap/…) do not require it.
- `unitree_mujoco` sim works for LowState telemetry only; `LocoClient` high-level methods all fail in sim because it lacks the `ai_sport` service.

### No automated tests

There is no test suite. Verification = `python -m py_compile` + manual UI clickthrough in mock mode (and real mode with a spotter at the handheld for L2+B emergency damp).

## Architecture you need to know before editing

### Two parallel control paths — do not collapse them

The backend talks to the robot via **two distinct mechanisms** and you must respect the split:

- **In-process bridge** — `backend/services/robot_bridge.py`. Owns one long-lived `LocoClient` and one `ChannelSubscriber("rt/lowstate")` per backend process. Used by `/api/robot/{status,connect,disconnect,arm,estop,estop/release,safety-config}`. The subscription is what makes the telemetry WebSocket return real values: `_on_low_state` populates `_low_state`, and `get_telemetry()` reads from it.
- **Subprocess sidecars** — `backend/robot_commands/run_loco_command.py` and `run_arm_action.py`. Each invocation spawns a fresh Python process that runs `ChannelFactoryInitialize`, creates its own client, fires one command, exits. Used by `/api/robot/loco/{cmd}` (F/B/L/R/STOP) and `/api/robot/high-level/{cmd}` (Shake, Wave, Clap, …).

The split exists because `ChannelFactoryInitialize` is effectively a per-process singleton — running it twice in one process collides with the long-lived telemetry participant. Sidecars cost ~1-3 s of SDK init per click; that's the deliberate trade. Don't "simplify" by calling `LocoClient.Move()` from the in-process bridge unless you also rethink the participant model.

### Factory import discipline (a real footgun)

`backend/services/__init__.py` picks the bridge from `ROBOT_MODE` at startup. Always go through the factory:

```python
from services import robot          # ← right (gets real or mock)
from services import mock_robot     # ← wrong: imports the submodule directly, bypasses the factory, always mock
```

The wrong form once severed `/api/robot/{connect,arm,estop,…}` from the real bridge for 10 days. Same name collision between the module `mock_robot.py` and the variable `mock_robot` inside it.

### Mock mode

`ROBOT_MODE=mock` swaps in `backend/services/mock_robot.py`, a pure-Python asyncio state machine with no SDK dependency. Telemetry returns plausible random values. Use this for all frontend dev.

### Auth, sessions, audit log

- JWT-based auth, two roles (`operator`, `supervisor`). `routers/auth.py` exposes `require_supervisor` for the safety-config endpoint.
- Seed users live in `backend/models/database.py`: `student_01`/`pass123` (op), `staff_jim`/`admin456` (sup), plus `student_02`/`staff_baden`.
- Every operator action is logged to SQLite (`chadwick.db`, `log_entries`). Actions performed without an active session are logged under `session_id="NO_SESSION"`.
- Export: `/api/session/{id}/export?format=csv|json`.
- New routes should emit a `LogEntry` mirroring the pattern in `routers/robot.py`; wrap in try/except + stderr so a broken audit doesn't kill the route.

### Telemetry stream

`routers/telemetry.py` pushes at 1 Hz over `/api/ws/telemetry` (JWT-auth). Values come from the in-process bridge's `_low_state` cache. Fields: IMU tilt (from `imu_state.rpy[1]`), per-leg motor load %, max motor temp, battery (placeholder voltage-to-percent), plus placeholder latency/signal/status pill.

## Critical operational gotchas

These are real footguns kept current with the codebase. Re-read before changing anything in the bridge or robot routes:

- **UI E-Stop is a soft stop** (`LocoClient.Damp()`), and it only reaches the robot if `_loco_client is not None`. Pre-Connect or post-Disconnect, E-Stop is a software flag only — no DDS message goes out. Handheld **L2 + B** is the authoritative emergency stop.
- **`release_estop()` does not stand the robot up.** After `Damp()` the robot is limp; releasing the e-stop only clears the flag. Operator must follow up with Home Pose / Stand Still.
- **`Disconnect → Connect` in the same process works** thanks to a try/except around `ChannelFactoryInitialize` for "already initialised". The CycloneDDS subscriber handle still leaks one per cycle — harmless but not a clean teardown.
- **Telemetry may freeze when sport_mode engages.** Working hypothesis: the G1 throttles/reroutes `rt/lowstate` once the sport service takes over. A planned debug endpoint to expose `_on_low_state` callback count + last-receive timestamp is not yet implemented.
- **Battery % is a placeholder** — `power_v * 100 / 60`. Real BMS state is on `rt/bmsstate` (separate IDL); not subscribed yet.
- **Safety config is partially enforced.** `max_speed`/`turn_rate` are read by `_execute_sync` in the in-process bridge, but the loco subprocess script reads its own constants — supervisor edits don't propagate to subprocess teleop.
- **`backend/routers/robotttt.py` is dead.** Not registered in `main.py`; scheduled for removal — don't add to it.

## Adding a new robot command

1. Confirm `LocoClient` or `G1ArmActionClient` exposes the action (see `backend/high_level/g1_loco_client_example.py`).
2. Extend the appropriate sidecar's dispatch map:
   - Arm gesture → `action_map` in `backend/robot_commands/run_arm_action.py`
   - Locomotion → `velocity_by_command` in `backend/robot_commands/run_loco_command.py`
3. Routes are already generic — `POST /api/robot/high-level/{command}` and `POST /api/robot/loco/{command}` accept whitelisted strings; no router edits needed.
4. Wire the button in `frontend/src/pages/OperatorPage.jsx` via `handleHighLevelCommand('bow')` (or the loco equivalent).
5. Optional friendly label in `frontend/src/services/api.js`. Audit logging is automatic.
