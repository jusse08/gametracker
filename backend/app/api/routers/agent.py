import os
import secrets
from datetime import datetime, timedelta
from uuid import uuid4
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.auth import get_current_user
from app.core.database import get_session
from app.domain.models import AgentConfig, AgentConfigRead, Game, GameRead, Session as DbSession, User
from app.domain.schemas import (
    AgentConfigRequest,
    AgentLaunchAckRequest,
    AgentLaunchRequest,
    AgentTestPingRequest,
    PingRequest,
)
from app.services.common import (
    build_game_read,
    ensure_owned_game_with_detail,
    get_agent_config_by_game_id,
    upsert_agent_session,
)

router = APIRouter()
AGENT_HEARTBEAT_TIMEOUT_SECONDS = 120


def get_agent_user(
    *,
    session: Session = Depends(get_session),
    x_agent_token: Optional[str] = Header(default=None, alias="X-Agent-Token"),
) -> User:
    if not x_agent_token:
        raise HTTPException(status_code=401, detail="Missing agent token")

    agent_user = session.exec(select(User).where(User.agent_token == x_agent_token)).first()
    if not agent_user:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    return agent_user


def extract_exe_name(launch_path: str) -> str:
    normalized = launch_path.replace("\\", "/").strip()
    exe_name = os.path.basename(normalized)
    if not exe_name:
        raise HTTPException(status_code=400, detail="Не удалось определить exe из launch_path")
    return exe_name


@router.get("/api/agent/token")
def get_agent_token(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not current_user.agent_token:
        current_user.agent_token = secrets.token_urlsafe(32)
        session.add(current_user)
        session.commit()
        session.refresh(current_user)

    return {"ok": True, "agent_token": current_user.agent_token}


@router.post("/api/agent/token/rotate")
def rotate_agent_token(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    current_user.agent_token = secrets.token_urlsafe(32)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return {"ok": True, "agent_token": current_user.agent_token}


@router.get("/api/agent/config")
def get_agent_config(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
):
    query = (
        select(AgentConfig)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(AgentConfig.enabled == True, Game.user_id == agent_user.id)
    )
    configs = session.exec(query).all()
    return {
        "items": [
            {
                "game_id": cfg.game_id,
                "exe_name": cfg.exe_name,
            }
            for cfg in configs
            if cfg.exe_name
        ]
    }


@router.get("/api/agent/commands")
def get_agent_commands(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
):
    query = (
        select(AgentConfig)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(
            AgentConfig.enabled == True,
            AgentConfig.pending_launch_id != None,
            AgentConfig.pending_launch_path != None,
            Game.user_id == agent_user.id,
        )
    )
    configs = session.exec(query).all()
    return {
        "items": [
            {
                "game_id": cfg.game_id,
                "request_id": cfg.pending_launch_id,
                "launch_path": cfg.pending_launch_path,
            }
            for cfg in configs
        ]
    }


@router.post("/api/agent/commands/ack")
def ack_agent_command(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    req: AgentLaunchAckRequest,
):
    config = session.exec(
        select(AgentConfig)
        .join(Game, AgentConfig.game_id == Game.id)
        .where(AgentConfig.game_id == req.game_id, Game.user_id == agent_user.id)
    ).first()
    if not config or not config.pending_launch_id:
        return {"ok": True, "status": "ignored"}

    if config.pending_launch_id != req.request_id:
        return {"ok": True, "status": "ignored"}

    config.last_launch_status = "ok" if req.success else "error"
    config.last_launch_error = None if req.success else (req.error or "Unknown launch error")
    config.last_launch_at = datetime.utcnow()
    config.pending_launch_id = None
    config.pending_launch_path = None
    config.pending_launch_requested_at = None
    config.updated_at = datetime.utcnow()
    session.add(config)
    session.commit()
    return {"ok": True, "status": "acknowledged"}


@router.get("/api/agent/download")
def download_agent():
    base_dir = os.path.dirname(__file__)
    candidates = [
        os.path.abspath(os.path.join(base_dir, "..", "data", "agent", "GameTrackerAgent.exe")),
        os.path.abspath(os.path.join(base_dir, "..", "..", "agent", "dist", "GameTrackerAgent.exe")),
        os.path.abspath(os.path.join(base_dir, "..", "agent", "dist", "GameTrackerAgent.exe")),
    ]
    agent_path = next((path for path in candidates if os.path.exists(path)), None)

    if not agent_path:
        raise HTTPException(
            status_code=404,
            detail="Агент не найден. Убедитесь, что сервис agent-builder в docker-compose успешно собрал GameTrackerAgent.exe.",
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
    active_since = now - timedelta(seconds=AGENT_HEARTBEAT_TIMEOUT_SECONDS)
    last_agent_session = session.exec(
        select(DbSession)
        .where(DbSession.game_id == game_id, DbSession.source == "agent")
        .order_by(DbSession.ended_at.desc(), DbSession.started_at.desc())
    ).first()

    if not last_agent_session:
        return {
            "ok": False,
            "message": "Агент не найден в сети: ещё не было ни одного ping от установленного агента.",
            "exe_name": game.exe_name,
            "status": "agent_inactive",
        }

    last_seen = last_agent_session.ended_at or last_agent_session.started_at
    if last_seen < active_since:
        return {
            "ok": False,
            "message": "Агент сейчас не активен. Запустите агент и игру, затем попробуйте снова.",
            "exe_name": game.exe_name,
            "status": "agent_inactive",
            "duration_minutes": last_agent_session.duration_minutes,
        }

    return {
        "ok": True,
        "message": "Агент активен: получен недавний ping от запущенного агента.",
        "exe_name": game.exe_name,
        "status": "agent_active",
        "duration_minutes": last_agent_session.duration_minutes,
    }


@router.post("/api/sessions/ping")
def ping_session(
    *,
    session: Session = Depends(get_session),
    agent_user: User = Depends(get_agent_user),
    req: PingRequest,
):
    game = session.get(Game, req.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.user_id != agent_user.id:
        raise HTTPException(status_code=403, detail="Game does not belong to this agent user")

    config = get_agent_config_by_game_id(session, req.game_id)
    if not config or not config.enabled:
        raise HTTPException(status_code=400, detail="Agent config is missing or disabled")

    if req.exe_name.strip().lower() != config.exe_name.strip().lower():
        raise HTTPException(status_code=400, detail="Ping exe_name does not match game config")

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
    query = select(Game).where(Game.user_id == current_user.id, Game.sync_type == "non_steam")
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
    launch_path = req.launch_path.strip()
    enabled = req.enabled

    if not launch_path:
        raise HTTPException(status_code=400, detail="launch_path is required")

    exe_name = extract_exe_name(launch_path)

    game = ensure_owned_game_with_detail(session, current_user, game_id, "Игра не найдена")

    game.exe_name = exe_name
    game.launch_path = launch_path
    session.add(game)

    existing = get_agent_config_by_game_id(session, game_id)
    if existing:
        existing.exe_name = exe_name
        existing.launch_path = launch_path
        existing.enabled = enabled
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    new_config = AgentConfig(
        game_id=game_id,
        exe_name=exe_name,
        launch_path=launch_path,
        enabled=enabled,
    )
    session.add(new_config)
    session.commit()
    session.refresh(new_config)
    return new_config


@router.post("/api/agent/launch")
def request_agent_launch(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentLaunchRequest,
):
    game = ensure_owned_game_with_detail(session, current_user, req.game_id, "Игра не найдена")

    config = get_agent_config_by_game_id(session, req.game_id)
    if not config or not config.enabled:
        raise HTTPException(status_code=400, detail="Агент не настроен или отключен для этой игры")

    launch_path = (config.launch_path or game.launch_path or "").strip()
    if not launch_path:
        raise HTTPException(status_code=400, detail="Сначала сохраните путь к исполняемому файлу игры")

    config.pending_launch_id = str(uuid4())
    config.pending_launch_path = launch_path
    config.pending_launch_requested_at = datetime.utcnow()
    config.updated_at = datetime.utcnow()
    session.add(config)
    session.commit()

    return {
        "ok": True,
        "message": "Команда запуска отправлена агенту. Убедитесь, что агент запущен.",
        "request_id": config.pending_launch_id,
    }


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
