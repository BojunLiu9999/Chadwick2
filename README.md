# Chadwick II — Command Center (前后端分离版)

## 项目结构

```
chadwick-fullstack/
├── frontend/          ← React 前端 (组员A负责)
│   ├── src/
│   │   ├── components/    ← 可复用UI组件
│   │   ├── pages/         ← 页面组件
│   │   ├── hooks/         ← 自定义Hook（WebSocket等）
│   │   ├── services/      ← API请求函数
│   │   └── context/       ← 全局状态（登录用户等）
│   ├── package.json
│   └── index.html
│
├── backend/           ← Python FastAPI 后端 (组员B/C负责)
│   ├── main.py            ← 程序入口
│   ├── routers/           ← API路由
│   │   ├── auth.py        ← 登录/登出
│   │   ├── robot.py       ← 机器人控制指令
│   │   ├── session.py     ← 会话管理
│   │   └── telemetry.py   ← 遥测数据
│   ├── models/            ← 数据结构定义
│   ├── services/          ← 业务逻辑
│   │   ├── robot_bridge.py  ← 连接真实机器人/ROS2
│   │   └── mock_robot.py    ← 模拟机器人（开发用）
│   ├── requirements.txt
│   └── .env
│
└── README.md
```

## 快速启动

### 后端
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev        # 访问 http://localhost:5173
```

## 团队分工建议

| 组员 | 负责模块 | 主要文件 |
|------|----------|----------|
| 组员A | 前端页面+组件 | frontend/src/pages/, components/ |
| 组员B | 后端API+登录 | backend/routers/auth.py, session.py |
| 组员C | 机器人通信 | backend/services/robot_bridge.py, routers/robot.py |
| 组员D | 遥测+数据库 | backend/routers/telemetry.py, models/ |

## API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录 |
| POST | /api/auth/logout | 登出 |
| GET  | /api/robot/status | 获取机器人状态 |
| POST | /api/robot/command | 发送控制指令 |
| POST | /api/robot/estop | 紧急停止 |
| GET  | /api/session/current | 当前会话信息 |
| POST | /api/session/start | 开始会话 |
| POST | /api/session/stop | 结束会话 |
| POST | /api/session/tag | 添加事件标签 |
| GET  | /api/session/{id}/export | 导出日志 |
| WS   | /ws/telemetry | WebSocket实时遥测 |
