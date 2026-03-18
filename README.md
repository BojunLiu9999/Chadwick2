# Chadwick II — Command Center 

## Project structure

```
chadwick-fullstack/
├── frontend/          ← React Frontend 
│   ├── src/
│   │   ├── components/    ← Reusable UI components
│   │   ├── pages/         ← Page components
│   │   ├── hooks/         ← Custom hooks (WebSocket etc.)
│   │   ├── services/      ← API request functions
│   │   └── context/       ← Global state (auth user etc.)
│   ├── package.json
│   └── index.html
│
├── backend/           ← Python FastAPI Backend 
│   ├── main.py            ← App entry point
│   ├── routers/           ← API routes
│   │   ├── auth.py        ← Login / Logout
│   │   ├── robot.py       ← Robot control commands
│   │   ├── session.py     ← Session management
│   │   └── telemetry.py   ← Telemetry data
│   ├── models/            ← Data structure definitions
│   ├── services/          ← Business logic
│   │   ├── robot_bridge.py  ← Real robot / ROS2 connection
│   │   └── mock_robot.py    ← Simulated robot (for development)
│   ├── requirements.txt
│   └── .env
│
└── README.md
```

## fast start

### backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### frontend
```bash
cd frontend
npm install
npm run dev        # visit http://localhost:5173
```


## API Endpoints

| method | path | Description |
|------|------|------|
| POST | /api/auth/login | Login |
| POST | /api/auth/logout | Logout |
| GET  | /api/robot/status | Get robot status |
| POST | /api/robot/command | Send control command |
| POST | /api/robot/estop | Emergency stop |
| GET  | /api/session/current | Get current session info |
| POST | /api/session/start | Start session |
| POST | /api/session/stop | End session |
| POST | /api/session/tag | Add event tag |
| GET  | /api/session/{id}/export | Export session log |
| WS   | /ws/telemetry | WebSocket real-time telemetry |
