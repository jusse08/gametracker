import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import AgentConfig, AgentConfigRead, Game, GameRead, User
from schemas import AgentConfigRequest, AgentTestPingRequest, PingRequest
from services.common import (
    build_game_read,
    ensure_owned_game_with_detail,
    get_agent_config_by_game_id,
    upsert_agent_session,
)

router = APIRouter()


@router.get("/api/agent/config")
def get_agent_config(
    *,
    session: Session = Depends(get_session),
    user_id: Optional[int] = None,
):
    query = select(AgentConfig).where(AgentConfig.enabled == True)
    if user_id:
        query = query.join(Game).where(Game.user_id == user_id)

    configs = session.exec(query).all()
    return {cfg.exe_name: cfg.game_id for cfg in configs}


@router.get("/api/agent/download")
def download_agent():
    base_dir = os.path.dirname(__file__)
    candidates = [
        os.path.abspath(os.path.join(base_dir, "..", "..", "agent", "dist", "GameTrackerAgent.exe")),
        os.path.abspath(os.path.join(base_dir, "..", "agent", "dist", "GameTrackerAgent.exe")),
    ]
    agent_path = next((path for path in candidates if os.path.exists(path)), None)

    if not agent_path:
        raise HTTPException(
            status_code=404,
            detail="Агент не найден. Сначала соберите .exe файл через PyInstaller.",
        )

    return FileResponse(
        agent_path,
        media_type="application/octet-stream",
        filename="GameTrackerAgent.exe",
    )


@router.post("/api/agent/test-ping")
def test_agent_ping(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentTestPingRequest,
):
    game_id = req.game_id
    game = ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")

    if game.sync_type != "agent":
        raise HTTPException(status_code=400, detail="Проверка агента доступна только для agent-игр")

    if not game.exe_name:
        raise HTTPException(
            status_code=400,
            detail="Для игры не указан исполняемый файл. Укажите его в карточке игры.",
        )

    config = session.exec(
        select(AgentConfig).where(
            AgentConfig.game_id == game_id,
            AgentConfig.enabled == True,
        )
    ).first()

    if not config:
        raise HTTPException(
            status_code=400,
            detail="Агент не настроен для этой игры. Сохраните исполняемый файл в карточке игры.",
        )

    now = datetime.utcnow()
    session_obj, status_name = upsert_agent_session(
        session=session,
        game_id=game_id,
        now=now,
        active_source="agent",
        new_source="agent_test",
    )
    session.commit()
    return {
        "ok": True,
        "message": "Агент активен! Сессия обновлена." if status_name == "session_updated" else "Агент активен! Создана новая сессия.",
        "exe_name": game.exe_name,
        "status": status_name,
        "duration_minutes": session_obj.duration_minutes,
    }


@router.post("/api/sessions/ping")
def ping_session(
    *,
    session: Session = Depends(get_session),
    req: PingRequest,
):
    game = session.get(Game, req.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.sync_type != "agent":
        raise HTTPException(status_code=400, detail="Agent ping is only available for agent games")

    now = datetime.utcnow()
    upsert_agent_session(
        session=session,
        game_id=req.game_id,
        now=now,
        active_source="agent",
        new_source="agent",
    )
    session.commit()
    return {"ok": True}


@router.get("/api/agent/games", response_model=List[GameRead])
def get_agent_games(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    query = select(Game).where(Game.user_id == current_user.id, Game.sync_type == "agent")
    games = session.exec(query).all()
    return [build_game_read(session, game) for game in games]


@router.post("/api/agent/configure", response_model=AgentConfigRead)
def configure_agent(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentConfigRequest,
):
    game_id = req.game_id
    exe_name = req.exe_name.strip()
    enabled = req.enabled

    if not exe_name:
        raise HTTPException(status_code=400, detail="exe_name is required")

    game = ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")

    if game.sync_type != "agent":
        raise HTTPException(status_code=400, detail="Агент можно настроить только для agent-игр")

    game.exe_name = exe_name
    session.add(game)

    existing = get_agent_config_by_game_id(session, game_id)
    if existing:
        existing.exe_name = exe_name
        existing.enabled = enabled
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_config = AgentConfig(
        game_id=game_id,
        exe_name=exe_name,
        enabled=enabled,
    )
    session.add(new_config)
    session.commit()
    session.refresh(new_config)
    return new_config


@router.delete("/api/agent/config/{game_id}")
def delete_agent_config(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")
    config = get_agent_config_by_game_id(session, game_id)

    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")

    session.delete(config)
    session.commit()
    return {"ok": True}
