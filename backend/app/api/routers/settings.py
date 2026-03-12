from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.auth import get_current_user
from app.core.database import get_session
from app.domain.models import Settings, SettingsUpdate, User

router = APIRouter()


@router.get("/api/settings", response_model=Settings)
def get_settings(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return Settings(
        id=1,
        steam_api_key=current_user.steam_api_key,
        steam_profile_url=current_user.steam_profile_url,
        steam_user_id=current_user.steam_user_id,
    )


@router.put("/api/settings", response_model=Settings)
def update_settings(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    settings_data: SettingsUpdate,
):
    if settings_data.steam_api_key is not None:
        current_user.steam_api_key = settings_data.steam_api_key
    if settings_data.steam_profile_url is not None:
        current_user.steam_profile_url = settings_data.steam_profile_url
        from app.integrations.steam import resolve_steam_id

        current_user.steam_user_id = resolve_steam_id(
            current_user.steam_profile_url,
            api_key=current_user.steam_api_key,
        )

    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return Settings(
        id=1,
        steam_api_key=current_user.steam_api_key,
        steam_profile_url=current_user.steam_profile_url,
        steam_user_id=current_user.steam_user_id,
    )
