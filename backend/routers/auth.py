"""
认证路由 — 登录 / 登出 / 获取当前用户
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import bcrypt

from models.database import get_db, User
from models.schemas import LoginRequest, TokenResponse, UserInfo
from config import settings

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_token(data: dict) -> str:
    """生成 JWT Token"""
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """依赖注入：从Token解析当前用户（用于需要登录的接口）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭据，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


def require_supervisor(current_user: User = Depends(get_current_user)) -> User:
    """依赖注入：只允许 supervisor 角色访问"""
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation needs authority of supervisor"
        )
    return current_user


# ── 路由 ──

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    用户登录
    - 验证用户名、密码、角色
    - 返回 JWT Token
    """
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="username or password error")
    if not bcrypt.checkpw(req.password.encode('utf-8'), user.hashed_password.encode('utf-8')):
        raise HTTPException(status_code=401, detail="username or password error")
    if user.role != req.role:
        raise HTTPException(status_code=401, detail=f"The role of this account is  {user.role}，please select correct role")

    token = create_token({"sub": user.username, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserInfo(username=user.username, display_name=user.display_name, role=user.role)
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserInfo(
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role
    )


@router.post("/logout")
async def logout():
    """
    登出（前端删除Token即可）
    此接口主要用于记录审计日志
    """
    return {"message": "已登出"}
