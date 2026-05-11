# Chadwick II

Web-based teleoperation and monitoring platform for a Unitree G1 EDU bipedal humanoid robot, built for the University of Sydney TechLab capstone project.

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688) ![React 18](https://img.shields.io/badge/React-18-61DAFB) ![Vite](https://img.shields.io/badge/Vite-5-646CFF)

## Project overview

Chadwick II is a browser-based command-and-control surface for a Unitree G1 EDU bipedal humanoid robot. It gives a lab operator a single page to start/stop sessions, connect to the robot, arm motion, drive the robot with directional buttons or scripted "quick action" gestures, and watch IMU / motor / temperature telemetry stream live — all while every operator action is recorded to an audit log. A supervisor role can adjust the safety envelope (max speed, turn rate) but not drive the robot directly.

It is intended for use in a teaching and research lab where the robot, the human operator, and a spotter (who handles physical mode switching on the handheld controller) share the same room. There is no remote-internet deployment.

## Architecture

### Layered view

```
┌──────────────────────────────────────────────────────────────────┐
│                       React + Vite frontend                      │
│  Operator / Supervisor pages, telemetry hook, axios API client   │
└──────────────────────────────────────────────────────────────────┘
                              │  HTTP /api/*   WS /api/ws/telemetry
┌──────────────────────────────────────────────────────────────────┐
│                          FastAPI backend                         │
│   routers/{auth,robot,session,telemetry,camera}.py + JWT auth    │
└──────────────────────────────────────────────────────────────────┘
                              │
                  ┌───────────┴────────────┐
                  │                        │
        ┌─────────────────┐      ┌──────────────────────┐
        │ services/       │      │ robot_commands/*.py  │
        │   __init__.py   │      │  (subprocess sidecars)│
        │  ROBOT_MODE     │      └──────────┬───────────┘
        │   factory       │                 │
        └────────┬────────┘                 │
                 │                          │
    ┌────────────┴───────────┐              │
    │                        │              │
┌────────────┐      ┌──────────────────┐    │
│ mock_robot │      │ real_robot       │    │
│  (asyncio  │      │  RealRobotBridge │    │
│   pure     │      │  in-process,     │    │
│   Python)  │      │  long-lived DDS  │    │
└────────────┘      └─────────┬────────┘    │
                              │              │
                              ▼              ▼
                    ┌─────────────────────────────────┐
                    │       unitree_sdk2py            │
                    │  ChannelFactory, LowState_,     │
                    │  LocoClient, G1ArmActionClient  │
                    └────────────┬────────────────────┘
                                 │ CycloneDDS
                                 ▼
                         ┌───────────────┐
                         │   Unitree G1  │
                         └───────────────┘
```

### Two parallel control paths

The backend uses **two different mechanisms** to drive the robot, and it's important to know which is which:

- **In-process bridge** ([backend/services/robot_bridge.py](backend/services/robot_bridge.py)) — owns one long-lived `LocoClient` and one `ChannelSubscriber("rt/lowstate", ...)` per backend process. Used by `/api/robot/{status,connect,disconnect,arm,estop,estop/release,safety-config}`. The subscription is what makes the telemetry WebSocket return real values: `_on_low_state` populates an internal `_low_state` cache, and `get_telemetry()` translates that into the IMU / motor / temperature fields the frontend renders.

- **Subprocess sidecars** ([backend/robot_commands/run_loco_command.py](backend/robot_commands/run_loco_command.py) and [backend/robot_commands/run_arm_action.py](backend/robot_commands/run_arm_action.py)) — each invocation spawns a fresh Python process that calls `ChannelFactoryInitialize`, creates its own client, sends one command, and exits. Used by `/api/robot/loco/{cmd}` (F/B/L/R/STOP) and `/api/robot/high-level/{cmd}` (Shake, Wave, Clap, …).

The reason for the split: a single CycloneDDS participant per process is a common SDK assumption, and `ChannelFactoryInitialize` is effectively a module-level singleton. Spawning sidecars sidesteps the "factory already initialised" issue and lets the long-lived telemetry subscription stay untouched when an operator clicks a teleop button. The cost is ~1-3 s of SDK init overhead per click, which is acceptable for the use case.

### Factory pattern

[backend/services/__init__.py](backend/services/__init__.py) selects which bridge implementation routes import at startup based on the `ROBOT_MODE` env var. Callers write `from services import robot as ...` and get the right object without conditionals at the call site:

```python
if settings.ROBOT_MODE == "real":
    from .robot_bridge import real_robot as robot
else:
    from .mock_robot import mock_robot as robot
```

## Features

### Robot control
- Connect / Disconnect to the G1 (in-process SDK bridge initialisation)
- Arm / Disarm motion (software gate; the SDK has no "arm" call on G1)
- E-Stop / Release E-Stop (calls `LocoClient.Damp()` — soft stop)
- Quick Actions: Shake Hand, Wave Hand, Clap, High Five, Hands Up, Home Pose, Stand Still
- Teleop directional pad: F / B / L / R / STOP (click-to-toggle; not press-and-hold)
- Supervisor-only safety config: max speed (m/s), turn rate (deg/s), max torque %, temperature thresholds, active zone label

### Telemetry
- 1 Hz WebSocket push at `/api/ws/telemetry`, JWT-authenticated
- IMU tilt (deg, derived from `imu_state.rpy[1]`)
- Per-leg motor load percentages (L/R × HIP/KNEE/ANKLE)
- Core temperature (max of motor temperatures)
- Round-trip latency (placeholder constant; SDK does not expose this directly)
- Signal strength placeholder
- Battery percentage (placeholder — see "Known limitations")
- System status pill (disconnected / connecting / connected / ready)

### Session management
- JWT-based login with two roles: `operator` and `supervisor`
- Default users seeded in [backend/models/database.py](backend/models/database.py): `student_01` / `pass123` (op), `staff_jim` / `admin456` (sup), plus `student_02` and `staff_baden`
- Start / Pause / Stop sessions, tag with operator-supplied notes
- Audit log of operator actions persisted to SQLite (`backend/chadwick.db`, `log_entries` table)
- CSV / JSON export of session logs via `/api/session/{id}/export?format=...`

### Camera feed
- Browser-based and SDK-streamed paths are scaffolded under [backend/routers/camera.py](backend/routers/camera.py) (teammate's in-progress work)

### Mock mode
- `ROBOT_MODE=mock` swaps in [backend/services/mock_robot.py](backend/services/mock_robot.py), a pure-Python state machine that simulates connect/arm/estop/telemetry without any SDK dependency
- Lets frontend development and UI testing happen without the robot or the unitree_sdk2py install

## Project structure

```
chadwick2/
├── backend/
│   ├── main.py                      FastAPI app, lifespan hook, router registration
│   ├── config.py                    pydantic-settings env loader
│   ├── chadwick.db                  local SQLite DB (gitignored)
│   ├── audio/                       audio playback sidecars (test.wav, g1_audio_*)
│   ├── high_level/                  Unitree SDK reference examples (read-only)
│   ├── models/
│   │   ├── database.py              SQLAlchemy models: User, Session, LogEntry, SafetyConfig
│   │   └── schemas.py               pydantic request/response shapes
│   ├── robot_commands/
│   │   ├── run_loco_command.py      sidecar: LocoClient.Move() per F/B/L/R/STOP
│   │   └── run_arm_action.py        sidecar: G1ArmActionClient for Quick Actions
│   ├── routers/
│   │   ├── auth.py                  JWT login / current-user / require_supervisor
│   │   ├── camera.py                camera feed endpoints (WIP)
│   │   ├── robot.py                 connect/disconnect/arm/estop/command/loco/high-level
│   │   ├── session.py               start/pause/stop/tag/logs/export
│   │   └── telemetry.py             WebSocket telemetry stream
│   └── services/
│       ├── __init__.py              ROBOT_MODE factory (real ↔ mock)
│       ├── robot_bridge.py          RealRobotBridge — in-process SDK bridge
│       └── mock_robot.py            MockRobot — asyncio fake for dev mode
├── frontend/
│   └── src/
│       ├── components/SharedComponents.jsx  Panel, EStop, TelemetryPanel, etc.
│       ├── context/AuthContext.jsx          JWT/token store
│       ├── hooks/
│       │   ├── useTelemetry.js              WS connection + reconnect loop
│       │   ├── useRobotConnection.js        polls /api/robot/status
│       │   └── useCameraFeed.js
│       ├── pages/
│       │   ├── LoginPage.jsx
│       │   ├── OperatorPage.jsx             main teleop UI
│       │   └── SupervisorPage.jsx
│       ├── services/api.js                  axios client + endpoint wrappers
│       └── utils/sessionLogs.js             log-entry normaliser for the UI
├── README.md
└── .gitignore
```

## Quickstart

### Development mode (mock, no hardware needed)

```bash
# 1. Clone
git clone <repo-url> chadwick2
cd chadwick2

# 2. Backend
cd backend
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt

# minimal env file
cat > .env << 'EOF'
ROBOT_MODE=mock
SECRET_KEY=dev-only-change-me
DATABASE_URL=sqlite+aiosqlite:///./chadwick.db
FRONTEND_URL=http://localhost:5173
EOF

uvicorn main:app --reload --port 8000

# 3. Frontend (in a second terminal)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

Default test credentials (seeded into `chadwick.db` on first run):

| Role | Username | Password |
|---|---|---|
| operator | `student_01` | `pass123` |
| operator | `student_02` | `pass123` |
| supervisor | `staff_jim` | `admin456` |
| supervisor | `staff_baden` | `admin456` |

### Real-robot mode

Additional prerequisites:

- Linux host (Ubuntu 20.04+ tested) wired to the G1 EDU's onboard Ethernet
- `unitree_sdk2py` and `CycloneDDS` installed in the backend venv (see Unitree's docs; you'll need `CYCLONEDDS_HOME` and a built `cyclonedds`)
- A handheld operator (Chris in our setup) standing by the robot

Network configuration:

```bash
# host interface: eno3 (adjust to your NIC)
sudo ip addr add 192.168.123.222/24 dev eno3
sudo ip link set eno3 up
ping 192.168.123.164    # robot
```

Backend `.env` (template at [backend/.env.lab.example](backend/.env.lab.example)):

```bash
ROBOT_MODE=real
ROBOT_IFACE=eno3
ROBOT_DOMAIN_ID=0
ROBOT_PYTHON_BIN=python3
ROBOT_SDK_PYTHONPATH=/home/<user>/unitree_sdk2_python
```

Robot-side prerequisite:

> **Before any locomotion command** (F/B/L/R or `Move`), the operator at the handheld controller must press **R2 + A** to enter **sport_mode**. Without it, `LocoClient.Move()` returns a non-zero result code and the UI alerts "Robot not in sport_mode — operator press R2+A". Arm actions (Shake/Wave/Clap/…) do **not** require sport_mode.

Then start the backend and frontend as in mock mode.

### Simulator (unitree_mujoco)

```
ROBOT_MODE=real
ROBOT_IFACE=lo
ROBOT_DOMAIN_ID=1
```

LowState telemetry works in sim, but `LocoClient` high-level commands (`Move`, `WaveHand`, etc.) do **not** — see Known limitations.

## Configuration

Environment variables are loaded by [backend/config.py](backend/config.py) from `.env` (or the alternate `env` file). The most important keys:

| Key | Default | Purpose |
|---|---|---|
| `ROBOT_MODE` | `mock` | `mock` ↔ `real`. Switches the services factory. |
| `ROBOT_IFACE` | `lo` | NIC name for the DDS participant. `eno3` for lab G1, `lo` for sim. |
| `ROBOT_DOMAIN_ID` | `0` | DDS domain. `0` for real G1, `1` for unitree_mujoco. |
| `ROBOT_PYTHON_BIN` | `python3` | Interpreter used by the subprocess sidecars. |
| `ROBOT_SDK_PYTHONPATH` | `""` | Prepended to `PYTHONPATH` when spawning sidecars; point to your `unitree_sdk2_python` checkout. |
| `ROBOT_AUDIO_WAV` | `""` | Default WAV file for the `/api/robot/audio` endpoint. |
| `SECRET_KEY` | `change-me` | JWT signing key. **Set this in any non-mock deployment.** |
| `ALGORITHM` | `HS256` | JWT algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Token lifetime. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./chadwick.db` | SQLAlchemy URL. |
| `FRONTEND_URL` | `http://localhost:5173` | CORS allow-origin. |
| `CAMERA_*` | various | Camera router config. See `.env.lab.example`. |

The file [backend/.env.lab.example](backend/.env.lab.example) is the canonical lab-rig template; copy it to `backend/.env` and adjust paths.

## Operating the UI

The operator-side flow, in order:

1. **Log in** at `http://localhost:5173` as an operator (e.g. `student_01` / `pass123`).
2. **Click Start Session** in the right panel. From this point, every action you take is logged with the active `session_id`. *Actions taken without an active session are recorded under `NO_SESSION` and surfaced via the "no session" fallback in `/api/session/logs`.*
3. **Click Connect**. The status pill cycles `DISCONNECTED → CONNECTING → ROBOT CONNECTED → ROBOT READY`. Behind the scenes this calls `real_robot.connect()`, which runs `ChannelFactoryInitialize` and waits up to 3 s for the first `LowState` frame before reporting READY.
4. **Toggle Motion Arm**. This is a software gate only — the G1 has no SDK arm call. Required before non-STOP teleop commands will fire.
5. **(For locomotion only)** Spotter presses **R2 + A** on the handheld to put the G1 in sport_mode.
6. Drive the robot:
   - **Quick Actions**: single-fire arm gestures. Click and wait for completion.
   - **Teleop pad**: click-to-toggle. F starts walking forward at the configured max speed; STOP halts. Clicking a different direction transitions to the new velocity without needing to STOP first.
7. **E-Stop** (red button) when you need to halt motion fast. *Read the next section before relying on this for safety.*
8. **Disconnect** when done. Releases the long-lived bridge state.
9. **Click Stop Session** to close the audit window and write the `SESSION_STOPPED` log entry. You can export the log as CSV or JSON.

### Emergency stop — what to use

| Situation | Use |
|---|---|
| Robot misbehaving, you can reach the handheld | **Handheld L2 + B** — physical damp, always works |
| You can't reach the handheld, robot is connected | **UI E-Stop** — calls `LocoClient.Damp()`, soft stop |
| Pre-Connect or post-Disconnect | UI E-Stop is **state-only**, does not reach the robot — see Known limitations |

The handheld is the authoritative emergency stop. Treat the UI E-Stop as a convenience, not as a safety device.

## Known limitations & gotchas

These are real footguns, kept current with the codebase audit:

- **E-Stop before Connect or after Disconnect is a software flag only.** `RealRobotBridge.estop()` only calls `_loco_client.Damp()` if `_loco_client` is not `None`. In any state where the SDK client hasn't been initialised, e-stop updates `self.estop_active` and `self.motion_armed` but no DDS message goes out. **For real emergency stops, use handheld L2 + B.**
- **`release_estop()` does not auto-stand the robot.** After `Damp()`, the robot is limp. Releasing the e-stop clears the software flag but doesn't issue a stand command — operator must follow up with Home Pose / Stand Still.
- **Telemetry stream behaviour during sport_mode is under investigation.** Operators have observed the IMU / motor values freezing when sport_mode is engaged via R2+A. The current hypothesis is that the G1 throttles or reroutes `rt/lowstate` publishes when the sport service takes over. A diagnostic endpoint (`/api/robot/_debug/dds`) returning the `_on_low_state` callback count and last-receive timestamp is planned to confirm; not yet implemented.
- **Disconnect → Connect within the same backend process** now succeeds thanks to a try/except guard around `ChannelFactoryInitialize` in [robot_bridge.py](backend/services/robot_bridge.py) that tolerates "already initialised" errors. The underlying CycloneDDS subscriber handle still leaks one per cycle — functionally harmless (the new subscriber overwrites `_low_state`), but not a clean teardown.
- **Battery percentage is a placeholder.** `_read_battery()` returns `float(getattr(s, "power_v", 0)) * 100 / 60`, a rough voltage-to-percent guess. Real BMS state is on `rt/bmsstate` with a separate IDL; the bridge does not subscribe to it yet.
- **`backend/routers/robotttt.py` is a known dead duplicate.** It is not registered in [backend/main.py](backend/main.py) and is scheduled for removal.
- **unitree_mujoco simulator does not implement the `ai_sport` service.** This means `LocoClient` high-level methods (`Move`, `WaveHand`, `ShakeHand`, …) all fail in sim. LowState telemetry still works, so the bridge connects and telemetry streams; just don't expect the Quick Actions or teleop to do anything visible.
- **Subprocess sidecar latency.** Each F / B / L / R / STOP click spawns a new Python process that runs `ChannelFactoryInitialize` and `LocoClient().Init()`, typically 1-3 s of overhead before the `Move()` call reaches the robot. Acceptable for click-to-toggle, would not work for press-and-hold.
- **Speed slider / safety config is supervisor-only and partially enforced.** `max_speed` and `turn_rate` are read by `_execute_sync` in the in-process bridge, but the loco subprocess script reads its own constants. Edits to safety config don't propagate to subprocess teleop.
- **No tests yet.** No `tests/` directory exists in either backend or frontend. Verification today is manual via the UI plus `python -m py_compile` for syntax.

## Development notes

### Adding a new robot command

Suppose you want a new Quick Action `Bow`.

1. Confirm `LocoClient` or `G1ArmActionClient` exposes the action you need (consult [backend/high_level/g1_loco_client_example.py](backend/high_level/g1_loco_client_example.py)).
2. Add the dispatch to the appropriate sidecar:
   - Arm actions → extend `action_map` consumed by [run_arm_action.py](backend/robot_commands/run_arm_action.py).
   - Locomotion → extend `velocity_by_command` or the dispatch in [run_loco_command.py](backend/robot_commands/run_loco_command.py).
3. The route is already generic — `POST /api/robot/high-level/{command}` and `POST /api/robot/loco/{command}` accept any whitelisted string.
4. Add the button in [frontend/src/pages/OperatorPage.jsx](frontend/src/pages/OperatorPage.jsx), wiring `onClick={() => handleHighLevelCommand('bow')}`.
5. (Optional) Add an alias / friendly label to the API client in [frontend/src/services/api.js](frontend/src/services/api.js).
6. Audit log entries are emitted automatically by the route — no extra work needed.

### Why the subprocess split, again

If you're tempted to "just call `LocoClient.Move()` from the in-process bridge instead of spawning a subprocess" — that *does* work, but it forces the in-process bridge to also hold the `LocoClient` (it does), and any second `ChannelFactoryInitialize` call from a future feature will collide with the long-lived participant. The sidecar pattern keeps the telemetry subscription isolated from command churn. Don't change this unless you also rethink the participant model.

### Factory and import discipline

Always go through the factory:

```python
from services import robot as mock_robot      # ← right
```

Not:

```python
from services import mock_robot                # ← wrong: bypasses the factory, always mock
```

The second form imports the `mock_robot.py` submodule directly, which is a Python footgun caused by giving a module and a variable the same name. The committed code went through a 10-day period where [backend/routers/robot.py](backend/routers/robot.py) accidentally used the second form, severing all of `/api/robot/{connect,arm,estop,…}` from the real bridge until it was caught.

### Logging an action from a new route

Mirror the pattern in [robot.py](backend/routers/robot.py):

```python
db.add(LogEntry(
    session_id=mock_robot.current_session_id or "NO_SESSION",
    operator=current_user.username,
    entry_type="CMD",            # or "INFO" / "WARN" / "ERR" / "TAG"
    event="YOUR_EVENT_NAME",
    detail=encode_detail({...}),
))
await db.commit()
```

Wrap in `try/except` and print to `stderr` on failure so a broken audit log doesn't take out the route.

## Testing

There is no automated test suite at the moment. Verification today is:

- **Syntax**: `python -m py_compile <files>` for the backend before any commit
- **Mock-mode smoke test**: `ROBOT_MODE=mock`, full UI clickthrough (login → start session → connect → arm → quick actions → teleop → stop)
- **Real-robot smoke test**: same flow against the lab G1 with a spotter present and the handheld armed for L2+B emergency damp

Mock-mode reproduction of the full flow without hardware:

```bash
# backend
cd backend
ROBOT_MODE=mock uvicorn main:app --reload --port 8000

# frontend
cd frontend
npm run dev
```

Then drive the UI at `http://localhost:5173`. Telemetry will show plausible random values, not real motion.

Suggested future work (not done): pytest + httpx-based route tests in mock mode, Playwright for the operator clickthrough.

## Tech stack

**Backend** (Python 3.10+):
- [FastAPI](https://fastapi.tiangolo.com/) 0.111 — HTTP + WebSocket framework
- [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 async + [aiosqlite](https://github.com/omnilib/aiosqlite) — DB layer
- [pydantic](https://docs.pydantic.dev/) 2.7 + pydantic-settings — schemas + env config
- [python-jose](https://github.com/mpdavis/python-jose) + [passlib (bcrypt)](https://passlib.readthedocs.io/) — JWT + password hashing
- [uvicorn](https://www.uvicorn.org/) — ASGI server
- [unitree_sdk2py](https://github.com/unitreerobotics/unitree_sdk2_python) — Unitree's Python SDK (real-mode only)
- [CycloneDDS](https://github.com/eclipse-cyclonedds/cyclonedds) — DDS transport under the SDK

**Frontend**:
- [React](https://react.dev/) 18 + [React Router](https://reactrouter.com/) 6
- [Vite](https://vitejs.dev/) 5 — dev server + bundler
- [axios](https://axios-http.com/) — HTTP client

**Robot**:
- Unitree G1 EDU, 23-DoF, on-board IMU + per-motor temperature/torque telemetry
- High-level control via `ai_sport` service (`LocoClient`, `G1ArmActionClient`)
- Low-level state via `rt/lowstate` topic, `unitree_hg` IDL

## Team & acknowledgements

University of Sydney TechLab capstone, 2026.

| Area | Member | Status |
|---|---|---|
| Robot connection state machine, top status bar, audit log | Member 1 | ✅ |
| Operator UI, teleop, Quick Actions wiring | Member 2 | TODO — add name |
| Telemetry stream + safety panels | Member 3 | TODO — add name |
| Camera feed + sensing | Member 4 | TODO — add name |
| Supervisor view + safety config | Member 5 | TODO — add name |

Project supervisor: TODO. Lab handheld operator: Chris.

Robot platform courtesy of the University of Sydney Faculty of Engineering TechLab.
