from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.core.database import get_session
from app.domain.models import User, UserCreate, UserPasswordUpdate, UserRead
from app.services.common import enrich_user_read, is_superadmin

router = APIRouter()


@router.get("/api/users", response_model=List[UserRead])
def read_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Superadmin only")
    users = session.exec(select(User)).all()
    return [enrich_user_read(u) for u in users]


@router.post("/api/users", response_model=UserRead)
def create_user(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    user_data: UserCreate,
):
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Superadmin only")
    existing = session.exec(select(User).where(User.username == user_data.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return enrich_user_read(user)


@router.put("/api/users/{user_id}/password")
def update_user_password(
    user_id: int,
    password_data: UserPasswordUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Superadmin only")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if is_superadmin(user):
        raise HTTPException(status_code=400, detail="Cannot change superadmin password here")

    user.hashed_password = get_password_hash(password_data.password)
    session.add(user)
    session.commit()
    return {"ok": True}


@router.post("/api/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {"access_token": access_token, "token_type": "bearer", "user": enrich_user_read(user)}


@router.get("/api/auth/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return enrich_user_read(current_user)


@router.put("/api/auth/me", response_model=UserRead)
def update_me(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    steam_api_key: Optional[str] = None,
    steam_profile_url: Optional[str] = None,
):
    if steam_api_key is not None:
        current_user.steam_api_key = steam_api_key
    if steam_profile_url is not None:
        current_user.steam_profile_url = steam_profile_url
        from app.integrations.steam import resolve_steam_id

        current_user.steam_user_id = resolve_steam_id(
            current_user.steam_profile_url,
            api_key=current_user.steam_api_key,
        )

    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user
