import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from sqlmodel import Session
from fastapi import Depends, HTTPException, Request, status
import bcrypt

from app.core.database import get_session
from app.domain.models import User

# JWT settings
SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is required")
ALGORITHM = "HS256"
_expire_minutes_raw = (os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "").strip()
if _expire_minutes_raw:
    try:
        ACCESS_TOKEN_EXPIRE_MINUTES = max(1, int(_expire_minutes_raw))
    except ValueError as exc:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer") from exc
else:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

AUTH_COOKIE_NAME = (os.getenv("AUTH_COOKIE_NAME") or "access_token").strip() or "access_token"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt имеет ограничение в 72 байта на пароль
    if len(plain_password) > 72:
        plain_password = plain_password[:72]
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    # bcrypt имеет ограничение в 72 байта на пароль
    if len(password) > 72:
        password = password[:72]
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def extract_token_from_request(request: Request) -> Optional[str]:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    cookie_token = (request.cookies.get(AUTH_COOKIE_NAME) or "").strip()
    return cookie_token or None

def get_current_user(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = extract_token_from_request(request)
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        user_id = int(user_id_str) if user_id_str else None
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = session.get(User, user_id)
    if user is None:
        raise credentials_exception

    return user
