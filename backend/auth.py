from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from sqlmodel import Session, select
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt

from database import get_session
from models import User

# JWT settings
SECRET_KEY = "your-secret-key-change-in-production"  # TODO: Move to env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

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
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    print(f"[DEBUG] Token received: {token[:50] if token else 'None'}...")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        user_id = int(user_id_str) if user_id_str else None
        print(f"[DEBUG] Token decoded, user_id: {user_id}")
        if user_id is None:
            print("[DEBUG] user_id is None")
            raise credentials_exception
    except JWTError as e:
        print(f"[DEBUG] JWTError: {e}")
        raise credentials_exception

    user = session.get(User, user_id)
    if user is None:
        print(f"[DEBUG] User {user_id} not found in database")
        raise credentials_exception

    return user
