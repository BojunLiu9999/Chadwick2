"""
Chadwick II — Command Center Backend
FastAPI 主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from routers import auth, robot, session, telemetry
from models.database import init_db
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库"""
    await init_db()
    print("✅ Initiating database completed")
    print(f"🤖 Robot mode: {settings.ROBOT_MODE}")
    yield
    print("👋 Service close")


app = FastAPI(
    title="Chadwick II Command Center API",
    description="Humanoid Robotics Command Center — University of Sydney Techlab",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS 配置（允许前端跨域请求）──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(auth.router,      prefix="/api/auth",     tags=["认证"])
app.include_router(robot.router,     prefix="/api/robot",    tags=["机器人控制"])
app.include_router(session.router,   prefix="/api/session",  tags=["会话管理"])
app.include_router(telemetry.router, prefix="/api",          tags=["遥测"])


@app.get("/")
async def root():
    return {"message": "Chadwick II API is running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "robot_mode": settings.ROBOT_MODE}
