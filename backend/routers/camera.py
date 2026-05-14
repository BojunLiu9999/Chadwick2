"""
Camera configuration and frame routes.

Why a background worker
-----------------------
The previous design ran ``run_camera_frame.py`` via ``subprocess.run()`` on
every ``GET /api/camera/frame.jpg``. Each invocation paid for a fresh Python
interpreter, ``ChannelFactoryInitialize``, ``VideoClient.Init()`` and the first
``GetImageSample()`` round-trip (1–3 s) before returning one JPEG. That capped
the effective stream at a few FPS and added huge per-frame latency.

This module now runs a single daemon thread (``_camera_worker_loop``) that:

* initialises CycloneDDS / the ``VideoClient`` once,
* polls ``GetImageSample()`` at ``CAMERA_FPS``,
* writes the newest JPEG into ``_FRAME_CACHE`` under ``_FRAME_LOCK``.

HTTP handlers just snapshot the cache — no subprocesses, no SDK calls. If the
worker fails to grab a frame we keep serving the last good one and surface the
error through ``/api/camera/status``.

``ChannelFactoryInitialize`` is a per-process singleton (see CLAUDE.md). The
worker tolerates the case where ``robot_bridge`` already initialised the
factory and reuses the same DDS participant.
"""
import importlib
import os
import sys
import threading
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
# Helper script retained for ad-hoc debugging (`python run_camera_frame.py eth0`);
# the HTTP path no longer shells out to it.
CAMERA_HELPER_PATH = BACKEND_ROOT / "robot_commands" / "run_camera_frame.py"

# Shared cache — all reads/writes happen under _FRAME_LOCK.
#   bytes        : most recent JPEG payload, or None until first frame arrives
#   captured_at  : wall-clock seconds of last good frame (time.time())
#   last_error   : most recent capture error message, cleared on success
#   running      : worker should keep looping (False = please exit)
#   thread       : handle to the worker thread (daemon, joined on process exit)
_FRAME_CACHE = {
    "bytes": None,
    "captured_at": 0.0,
    "last_error": "",
    "running": False,
    "thread": None,
}
_FRAME_LOCK = threading.Lock()
# Distinct lock for the start_worker critical section so we never hold the
# frame-cache lock across thread creation or SDK init.
_WORKER_START_LOCK = threading.Lock()


def resolve_camera_mode() -> str:
    mode = (settings.CAMERA_MODE or "browser").strip().lower()
    return mode if mode in SUPPORTED_CAMERA_MODES else "browser"


def resolve_camera_iface() -> str:
    return (settings.CAMERA_INTERFACE or settings.ROBOT_IFACE or "eth0").strip()


def resolve_camera_python_bin() -> str:
    # Kept for any external tooling that still wants to launch the helper script.
    return (settings.CAMERA_PYTHON_BIN or settings.ROBOT_PYTHON_BIN or "python3").strip()


def resolve_unitree_fps() -> int:
    # Target capture rate for the worker loop. Clamped to a sane upper bound
    # so a stray CAMERA_FPS=1000 doesn't pin a core; lower bound 1 fps.
    configured_fps = max(1, int(settings.CAMERA_FPS or 1))
    return min(configured_fps, 60)


def resolve_unitree_stream_url() -> str:
    return "/api/camera/frame.jpg"


def _load_symbol(import_spec: str):
    module_name, separator, attr_name = import_spec.partition(":")
    if not module_name or not separator or not attr_name:
        raise ValueError(
            "CAMERA_SDK_CLIENT_IMPORT must look like 'package.module:ClassName'"
        )
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _apply_camera_pythonpath() -> None:
    # The old subprocess flow passed PYTHONPATH via env; running in-process we
    # have to mutate sys.path ourselves so the SDK checkout is importable.
    configured_pythonpath = (
        settings.CAMERA_PYTHONPATH or settings.ROBOT_SDK_PYTHONPATH or ""
    ).strip()
    if not configured_pythonpath:
        return
    for entry in configured_pythonpath.split(os.pathsep):
        entry = entry.strip()
        if entry and entry not in sys.path:
            sys.path.insert(0, entry)


def _camera_worker_loop() -> None:
    """Long-running capture loop.

    Initialises the SDK once, then polls ``GetImageSample()`` at the configured
    FPS. Failures update ``last_error`` but never tear down the loop — if a
    previous frame is cached, the endpoint keeps serving it.
    """
    iface = resolve_camera_iface()
    domain_id = int(settings.ROBOT_DOMAIN_ID)
    timeout_s = float(settings.CAMERA_COMMAND_TIMEOUT or 5.0)
    client_import = (
        settings.CAMERA_SDK_CLIENT_IMPORT
        or "unitree_sdk2py.go2.video.video_client:VideoClient"
    )

    try:
        _apply_camera_pythonpath()
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize

        # robot_bridge may have already initialised the factory in this process.
        # Mirror its tolerance: swallow the "already initialised" case, surface
        # anything else.
        try:
            ChannelFactoryInitialize(domain_id, iface)
        except Exception as init_exc:
            if "already" not in str(init_exc).lower():
                raise

        VideoClient = _load_symbol(client_import)
        client = VideoClient()
        if hasattr(client, "SetTimeout"):
            client.SetTimeout(timeout_s)
        client.Init()
    except Exception as exc:
        with _FRAME_LOCK:
            _FRAME_CACHE["last_error"] = f"camera worker init failed: {exc}"
            _FRAME_CACHE["running"] = False
        return

    while True:
        # Re-read fps each tick so a config change takes effect on the next loop.
        with _FRAME_LOCK:
            if not _FRAME_CACHE["running"]:
                return
        period = 1.0 / max(1, resolve_unitree_fps())
        loop_start = time.time()

        try:
            code, data = client.GetImageSample()
            if code == 0 and data:
                payload = bytes(data)
                if len(payload) >= 16:
                    with _FRAME_LOCK:
                        _FRAME_CACHE["bytes"] = payload
                        _FRAME_CACHE["captured_at"] = time.time()
                        _FRAME_CACHE["last_error"] = ""
                else:
                    with _FRAME_LOCK:
                        _FRAME_CACHE["last_error"] = "empty frame from VideoClient"
            else:
                with _FRAME_LOCK:
                    _FRAME_CACHE["last_error"] = f"GetImageSample failed code={code}"
        except Exception as exc:
            with _FRAME_LOCK:
                _FRAME_CACHE["last_error"] = f"GetImageSample raised: {exc}"

        elapsed = time.time() - loop_start
        remaining = period - elapsed
        if remaining > 0:
            time.sleep(remaining)


def start_camera_worker_if_needed() -> None:
    """Idempotently boot the worker thread on first use.

    Called lazily from the status / frame endpoints so mock-mode dev never
    pays for the SDK import. Safe to call concurrently.
    """
    if resolve_camera_mode() != "unitree_sdk":
        return

    with _WORKER_START_LOCK:
        thread = _FRAME_CACHE["thread"]
        if thread is not None and thread.is_alive():
            return
        _FRAME_CACHE["running"] = True
        thread = threading.Thread(
            target=_camera_worker_loop,
            name="unitree-camera-worker",
            daemon=True,
        )
        _FRAME_CACHE["thread"] = thread
        thread.start()


def _snapshot_frame_cache() -> dict:
    """Atomically copy the fields we need so the handler does its own work
    outside the lock."""
    with _FRAME_LOCK:
        return {
            "bytes": _FRAME_CACHE["bytes"],
            "captured_at": _FRAME_CACHE["captured_at"],
            "last_error": _FRAME_CACHE["last_error"],
            "running": _FRAME_CACHE["running"],
        }


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
        start_camera_worker_if_needed()
        snapshot = _snapshot_frame_cache()

        enabled = True
        connected = snapshot["bytes"] is not None
        stream_url = resolve_unitree_stream_url()
        fps = resolve_unitree_fps()

        if snapshot["last_error"] and not connected:
            status_message = f"Unitree SDK camera worker error: {snapshot['last_error']}"
        elif settings.ROBOT_MODE != "real":
            status_message = "Unitree SDK camera mode is configured, but ROBOT_MODE is not set to real."
        elif connected:
            age_ms = int(max(0.0, time.time() - snapshot["captured_at"]) * 1000)
            tail = ""
            if snapshot["last_error"]:
                # Transient hiccup but we still have a usable frame — surface it.
                tail = f" Last error: {snapshot['last_error']}."
            status_message = (
                f"Unitree SDK camera streaming on iface={resolve_camera_iface()} "
                f"(last frame {age_ms} ms ago, target {fps} fps).{tail}"
            )
        else:
            status_message = (
                f"Unitree SDK camera worker started on iface={resolve_camera_iface()}. "
                "Waiting for the first frame."
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
        raise HTTPException(
            status_code=409,
            detail="Camera frame endpoint is only available in unitree_sdk mode",
        )

    start_camera_worker_if_needed()
    snapshot = _snapshot_frame_cache()
    payload = snapshot["bytes"]

    if payload is None:
        detail = snapshot["last_error"] or "camera worker has not produced a frame yet"
        raise HTTPException(
            status_code=502,
            detail=f"No camera frame available: {detail}",
        )

    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
