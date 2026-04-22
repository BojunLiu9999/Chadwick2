"""
Chadwick II command center backend entrypoint.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.database import init_db
from routers import auth, robot, session, telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("[startup] database initialization completed")
    print(f"[startup] robot mode: {settings.ROBOT_MODE}")
    yield
    print("[shutdown] service closed")


app = FastAPI(
    title="Chadwick II Command Center API",
    description="Humanoid Robotics Command Center - University of Sydney Techlab",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(robot.router, prefix="/api/robot", tags=["Robot Control"])
app.include_router(session.router, prefix="/api/session", tags=["Session Management"])
app.include_router(telemetry.router, prefix="/api", tags=["Telemetry"])


@app.get("/")
async def root():
    return {"message": "Chadwick II API is running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "robot_mode": settings.ROBOT_MODE}
