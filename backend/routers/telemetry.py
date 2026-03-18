"""
遥测路由 — WebSocket 实时推送遥测数据
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from jose import jwt, JWTError
import asyncio, json, random
from datetime import datetime

from config import settings
from services.mock_robot import mock_robot

router = APIRouter()

# 连接管理器：管理所有 WebSocket 连接
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    """
    WebSocket 端点：每秒推送一次遥测数据
    前端通过 ws://localhost:8000/ws/telemetry 连接

    连接后发送 Token 验证:
      { "token": "<jwt_token>" }
    """
    await manager.connect(websocket)
    authenticated = False

    try:
        # 第一条消息必须是 Token
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        token = auth_msg.get("token", "")
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            authenticated = True
            username = payload.get("sub", "unknown")
        except JWTError:
            await websocket.send_json({"error": "Invalid token"})
            await websocket.close()
            return

        await websocket.send_json({"type": "connected", "message": f"Welcome {username}"})

        # 循环推送遥测数据
        while True:
            telemetry = await mock_robot.get_telemetry()
            await websocket.send_json({
                "type": "telemetry",
                "data": telemetry,
            })
            await asyncio.sleep(1.0)   # 每秒推一次，可调整

    except asyncio.TimeoutError:
        await websocket.send_json({"error": "Auth timeout"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
