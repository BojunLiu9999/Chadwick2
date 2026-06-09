from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    DATABASE_URL: str = "sqlite+aiosqlite:///./chadwick.db"
    ROBOT_MODE: str = "mock"          # "mock" or "real"
    ROBOT_IFACE: str = "lo"           # ★ 新增：网卡名 (lo=仿真器, eth0/enp2s0=真机)
    ROBOT_DOMAIN_ID: int = 0          # ★ 新增：DDS domain ID, G1 用 0
    ROBOT_PYTHON_BIN: str = ""
    ROBOT_SDK_PYTHONPATH: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    CAMERA_MODE: str = "browser"      # browser | mjpeg | video | unitree_sdk
    CAMERA_STREAM_URL: str = ""
    CAMERA_LABEL: str = "HEAD_CAM_01"
    CAMERA_RESOLUTION: str = "1280x720"
    CAMERA_FPS: int = 30
    CAMERA_INTERFACE: str = ""
    CAMERA_PYTHON_BIN: str = ""
    CAMERA_PYTHONPATH: str = ""
    CAMERA_SDK_CLIENT_IMPORT: str = "unitree_sdk2py.go2.video.video_client:VideoClient"
    CAMERA_COMMAND_TIMEOUT: float = 8.0
    ROBOT_AUDIO_WAV: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_TTS_MODEL: str = "tts-1"
    OPENAI_TTS_VOICE: str = "alloy"

    # Azure VoiceLive (real-time speech-in / speech-out gateway). Endpoint is the
    # wss:// URL from the tutor; the API key goes in .env (gitignored) only.
    AZURE_VOICE_LIVE_ENDPOINT: str = ""
    AZURE_VOICE_LIVE_API_KEY: str = ""
    AZURE_VOICE_LIVE_MODEL: str = "gpt-4o-realtime-preview"
    AZURE_VOICE_LIVE_VOICE: str = "alloy"
    AZURE_VOICE_LIVE_WAKE_WORD: str = "Chadwick"

    # Voice-triggered movement: password gate + unlock timeout + per-step duration.
    # Empty password disables the feature entirely.
    VOICE_MOVE_PASSWORD: str = ""
    VOICE_UNLOCK_TIMEOUT_S: float = 60.0
    VOICE_STEP_SEC: float = 1.0

    class Config:
        env_file = ("env", ".env")


settings = Settings()
