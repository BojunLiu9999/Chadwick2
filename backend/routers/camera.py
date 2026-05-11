"""
Camera configuration and availability routes.
"""
import asyncio
import os
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from config import settings
from models.database import User
from models.schemas import CameraStatus
from routers.auth import get_current_user

router = APIRouter()

SUPPORTED_CAMERA_MODES = {"browser", "mjpeg", "video", "unitree_sdk"}
BACKEND_ROOT = Path(__file__).resolve().parents[1]
CAMERA_HELPER_PATH = BACKEND_ROOT / "robot_commands" / "run_camera_frame.py"

_FRAME_CACHE = {
    "bytes": None,
    "captured_at": 0.0,
    "last_error": "",
}
_FRAME_LOCK = asyncio.Lock()


def resolve_camera_mode() -> str:
    mode = (settings.CAMERA_MODE or "browser").strip().lower()
    return mode if mode in SUPPORTED_CAMERA_MODES else "browser"


def resolve_camera_iface() -> str:
    return (settings.CAMERA_INTERFACE or settings.ROBOT_IFACE or "eth0").strip()


def resolve_camera_python_bin() -> str:
    return (settings.CAMERA_PYTHON_BIN or settings.ROBOT_PYTHON_BIN or "python3").strip()


def resolve_unitree_fps() -> int:
    configured_fps = max(1, int(settings.CAMERA_FPS or 1))
    return min(configured_fps, 4)


def resolve_unitree_stream_url() -> str:
    return "/api/camera/frame.jpg"


def build_camera_env() -> dict:
    env = os.environ.copy()
    configured_pythonpath = (settings.CAMERA_PYTHONPATH or settings.ROBOT_SDK_PYTHONPATH or "").strip()

    if configured_pythonpath:
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            configured_pythonpath
            if not existing_pythonpath
            else f"{configured_pythonpath}{os.pathsep}{existing_pythonpath}"
        )

    env["UNITREE_CAMERA_DOMAIN_ID"] = str(settings.ROBOT_DOMAIN_ID)
    env["UNITREE_CAMERA_TIMEOUT"] = str(settings.CAMERA_COMMAND_TIMEOUT)
    env["UNITREE_CAMERA_CLIENT_IMPORT"] = settings.CAMERA_SDK_CLIENT_IMPORT
    return env


def capture_unitree_frame() -> bytes:
    if not CAMERA_HELPER_PATH.exists():
        raise RuntimeError(f"Camera helper script missing: {CAMERA_HELPER_PATH}")

    result = subprocess.run(
        [
            resolve_camera_python_bin(),
            str(CAMERA_HELPER_PATH),
            resolve_camera_iface(),
        ],
        capture_output=True,
        timeout=max(3, int(settings.CAMERA_COMMAND_TIMEOUT or 8)),
        env=build_camera_env(),
    )

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        stdout = result.stdout.decode("utf-8", errors="ignore").strip()
        detail = stderr or stdout or "unknown camera helper failure"
        raise RuntimeError(detail)

    payload = bytes(result.stdout)
    if len(payload) < 16:
        raise RuntimeError("camera helper returned an empty frame")

    return payload


async def get_unitree_frame_bytes(force_refresh: bool = False) -> bytes:
    cache_ttl = 1.0 / resolve_unitree_fps()
    now = time.time()

    if (
        not force_refresh
        and _FRAME_CACHE["bytes"] is not None
        and now - _FRAME_CACHE["captured_at"] < cache_ttl
    ):
        return _FRAME_CACHE["bytes"]

    async with _FRAME_LOCK:
        now = time.time()
        if (
            not force_refresh
            and _FRAME_CACHE["bytes"] is not None
            and now - _FRAME_CACHE["captured_at"] < cache_ttl
        ):
            return _FRAME_CACHE["bytes"]

        try:
            payload = await asyncio.to_thread(capture_unitree_frame)
        except Exception as exc:
            _FRAME_CACHE["last_error"] = str(exc)
            if _FRAME_CACHE["bytes"] is not None:
                return _FRAME_CACHE["bytes"]
            raise

        _FRAME_CACHE["bytes"] = payload
        _FRAME_CACHE["captured_at"] = time.time()
        _FRAME_CACHE["last_error"] = ""
        return payload


@router.get("/status", response_model=CameraStatus)
async def get_camera_status(current_user: User = Depends(get_current_user)):
    mode = resolve_camera_mode()
    stream_url = (settings.CAMERA_STREAM_URL or "").strip() or None
    fps = settings.CAMERA_FPS

    if mode == "browser":
        enabled = True
        connected = True
        stream_url = None
        status_message = "Browser camera capture will be requested from this workstation."
    elif mode == "unitree_sdk":
        enabled = True
        connected = _FRAME_CACHE["bytes"] is not None
        stream_url = resolve_unitree_stream_url()
        fps = resolve_unitree_fps()

        if _FRAME_CACHE["last_error"]:
            status_message = f"Unitree SDK camera helper error: {_FRAME_CACHE['last_error']}"
        elif settings.ROBOT_MODE != "real":
            status_message = "Unitree SDK camera mode is configured, but ROBOT_MODE is not set to real."
        else:
            status_message = (
                f"Unitree SDK camera bridge configured on iface={resolve_camera_iface()}. "
                "The first frame will be fetched when the page requests it."
            )
    elif stream_url:
        enabled = True
        connected = True
        status_message = f"{mode.upper()} camera stream configured."
    else:
        enabled = False
        connected = False
        status_message = "Camera stream URL is not configured."

    return CameraStatus(
        enabled=enabled,
        connected=connected,
        mode=mode,
        label=settings.CAMERA_LABEL,
        resolution=settings.CAMERA_RESOLUTION,
        fps=fps,
        stream_url=stream_url,
        status_message=status_message,
    )


@router.get("/frame.jpg")
async def get_camera_frame(current_user: User = Depends(get_current_user)):
    if resolve_camera_mode() != "unitree_sdk":
        raise HTTPException(status_code=409, detail="Camera frame endpoint is only available in unitree_sdk mode")

    try:
        payload = await get_unitree_frame_bytes()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to capture Unitree camera frame: {exc}") from exc

    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
