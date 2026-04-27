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
    FRONTEND_URL: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()