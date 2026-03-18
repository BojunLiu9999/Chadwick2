"""
数据库模型定义 + 初始化
使用 SQLAlchemy async + SQLite
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from datetime import datetime

from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    """用户表"""
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True)
    username     = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100))
    hashed_password = Column(String(200), nullable=False)
    role         = Column(String(20), nullable=False)   # "operator" | "supervisor"
    created_at   = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    """机器人操作会话表"""
    __tablename__ = "sessions"
    id           = Column(Integer, primary_key=True)
    session_id   = Column(String(20), unique=True)     # e.g. SES-0042
    operator_id  = Column(Integer)
    mode         = Column(String(50))
    started_at   = Column(DateTime, default=datetime.utcnow)
    ended_at     = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)


class LogEntry(Base):
    """会话日志表"""
    __tablename__ = "log_entries"
    id           = Column(Integer, primary_key=True)
    session_id   = Column(String(20))
    timestamp    = Column(DateTime, default=datetime.utcnow)
    operator     = Column(String(50))
    entry_type   = Column(String(10))   # CMD / INFO / WARN / ERR / TAG
    event        = Column(String(100))
    detail       = Column(Text, nullable=True)


class SafetyConfig(Base):
    """安全参数配置表（Supervisor设置）"""
    __tablename__ = "safety_config"
    id             = Column(Integer, primary_key=True)
    max_speed      = Column(Float, default=0.4)
    turn_rate      = Column(Float, default=30.0)
    max_torque_pct = Column(Float, default=40.0)
    temp_warn      = Column(Float, default=60.0)
    temp_stop      = Column(Float, default=70.0)
    active_zone    = Column(String(50), default="LAB G12")
    updated_by     = Column(String(50))
    updated_at     = Column(DateTime, default=datetime.utcnow)


async def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()


async def init_db():
    """创建所有表 + 插入默认用户"""
    import bcrypt
    def hash_pw(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 插入默认用户（如果不存在）
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.username == "student_01"))
        if not result.scalar_one_or_none():
            default_users = [
                User(username="student_01", display_name="Student 01",
                     hashed_password=hash_pw("pass123"), role="operator"),
                User(username="student_02", display_name="Student 02",
                     hashed_password=hash_pw("pass123"), role="operator"),
                User(username="staff_jim",  display_name="Jim Cook",
                     hashed_password=hash_pw("admin456"), role="supervisor"),
                User(username="staff_baden", display_name="Baden Spargo",
                     hashed_password=hash_pw("admin456"), role="supervisor"),
            ]
            db.add_all(default_users)
            await db.commit()
            print("✅ 默认用户已创建")
