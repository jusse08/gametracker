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
    settings = session.get(Settings, 1)
    if not settings:
        settings = Settings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)

    if current_user.steam_api_key:
        settings.steam_api_key = current_user.steam_api_key
    if current_user.steam_profile_url:
        settings.steam_profile_url = current_user.steam_profile_url

    return settings


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

    settings = session.get(Settings, 1)
    if not settings:
        settings = Settings(id=1)

    settings.steam_api_key = current_user.steam_api_key
    settings.steam_profile_url = current_user.steam_profile_url
    settings.steam_user_id = current_user.steam_user_id

    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings
