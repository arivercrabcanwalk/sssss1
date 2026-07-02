from __future__ import annotations

import bcrypt
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings

security = HTTPBearer()
settings = get_settings()
USER_DB_PATH = settings.data_dir / "users.json"
_user_cache: dict[str, UserInDB] | None = None


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------
class User(BaseModel):
    """Public user info — safe for JWT embedding and API responses."""
    username: str
    role: Literal["普通用户", "管理员"]


class UserInDB(User):
    """Internal user record with hashed password."""
    hashed_password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: Literal["普通用户", "管理员"]


# ---------------------------------------------------------------------------
# password helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expiration_minutes)
    to_encode: dict[str, Any] = {
        "sub": user.username,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的访问令牌",
        )


# ---------------------------------------------------------------------------
# user persistence
# ---------------------------------------------------------------------------
def _load_users() -> dict[str, UserInDB]:
    global _user_cache
    if _user_cache is not None:
        return _user_cache
    if not USER_DB_PATH.exists():
        _seed_users()
    data = json.loads(USER_DB_PATH.read_text(encoding="utf-8"))
    _user_cache = {k: UserInDB(**v) for k, v in data.items()}
    return _user_cache


def _seed_users() -> None:
    """Write pre-seeded accounts to users.json. Idempotent — checks file existence first."""
    USER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    users: dict[str, dict[str, str]] = {
        "user": {
            "username": "user",
            "hashed_password": hash_password("user123"),
            "role": "普通用户",
        },
        "admin": {
            "username": "admin",
            "hashed_password": hash_password("admin123"),
            "role": "管理员",
        },
    }
    USER_DB_PATH.write_text(
        json.dumps(users, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def authenticate_user(username: str, password: str) -> User | None:
    users = _load_users()
    db_user = users.get(username)
    if not db_user or not verify_password(password, db_user.hashed_password):
        return None
    return User(username=db_user.username, role=db_user.role)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Extract and validate Bearer token from Authorization header."""
    payload = decode_access_token(credentials.credentials)
    username: str | None = payload.get("sub")
    role: str | None = payload.get("role")
    if username is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少用户信息",
        )
    return User(username=username, role=role)


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require admin role — chains on get_current_user."""
    if current_user.role != "管理员":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def verify_ws_token(token: str) -> User:
    """Verify JWT from WebSocket query parameter. Returns User or raises HTTPException."""
    payload = decode_access_token(token)
    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return User(username=username, role=role)
