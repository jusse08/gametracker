from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.domain.models import (
    AgentConfig,
    ChecklistItem,
    Game,
    GameRead,
    Note,
    Session as DbSession,
    User,
    UserRead,
)


def is_superadmin(user: User) -> bool:
    import os

    return user.username == os.getenv("SUPERADMIN_USERNAME")


def enrich_user_read(user: User) -> UserRead:
    user_read = UserRead.model_validate(user)
    user_read.is_superadmin = is_superadmin(user)
    return user_read


def ensure_owned_game(session: Session, current_user: User, game_id: int) -> Game:
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


def ensure_owned_game_with_detail(
    session: Session,
    current_user: User,
    game_id: int,
    detail: str,
) -> Game:
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail=detail)
    return game


def ensure_owned_checklist_item_with_detail(
    session: Session,
    current_user: User,
    item_id: int,
    detail: str,
) -> ChecklistItem:
    db_item = session.get(ChecklistItem, item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail=detail)
    ensure_owned_game_with_detail(session, current_user, db_item.game_id, detail)
    return db_item


def ensure_owned_note_with_detail(
    session: Session,
    current_user: User,
    note_id: int,
    detail: str,
) -> Note:
    db_note = session.get(Note, note_id)
    if not db_note:
        raise HTTPException(status_code=404, detail=detail)
    ensure_owned_game_with_detail(session, current_user, db_note.game_id, detail)
    return db_note


def get_agent_config_by_game_id(session: Session, game_id: int) -> Optional[AgentConfig]:
    return session.exec(select(AgentConfig).where(AgentConfig.game_id == game_id)).first()


def get_total_playtime_minutes(session: Session, game_id: int) -> int:
    playtime_query = select(DbSession.duration_minutes).where(DbSession.game_id == game_id)
    return sum(session.exec(playtime_query) or [0])


def build_game_read(session: Session, game: Game) -> GameRead:
    game_read = GameRead.model_validate(game)
    game_read.total_playtime_minutes = get_total_playtime_minutes(session, game.id)
    return game_read


def validate_sync_type(sync_type: str) -> str:
    if sync_type not in {"steam", "non_steam"}:
        raise HTTPException(status_code=400, detail="sync_type must be 'steam' or 'non_steam'")
    return sync_type


def validate_game_status(status: str) -> str:
    allowed = {"playing", "backlog", "completed", "deferred", "wishlist"}
    if status not in allowed:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: playing, backlog, completed, deferred, wishlist",
        )
    return status


def upsert_agent_session(
    session: Session,
    game_id: int,
    now: datetime,
    active_source: str,
    new_source: str,
):
    query = (
        select(DbSession)
        .where(DbSession.game_id == game_id, DbSession.source == active_source)
        .order_by(DbSession.started_at.desc())
    )
    active_session_obj = session.exec(query).first()

    if not active_session_obj:
        new_session = DbSession(
            game_id=game_id,
            started_at=now,
            ended_at=now,
            source=new_source,
            duration_minutes=0,
        )
        session.add(new_session)
        return new_session, "new_session"

    last_ended_at = active_session_obj.ended_at or active_session_obj.started_at
    diff_minutes = (now - last_ended_at).total_seconds() / 60.0

    if diff_minutes > 5:
        new_session = DbSession(
            game_id=game_id,
            started_at=now,
            ended_at=now,
            source=new_source,
            duration_minutes=0,
        )
        session.add(new_session)
        return new_session, "new_session"

    active_session_obj.ended_at = now
    duration_delta = now - active_session_obj.started_at
    active_session_obj.duration_minutes = int(duration_delta.total_seconds() / 60)
    session.add(active_session_obj)
    return active_session_obj, "session_updated"
