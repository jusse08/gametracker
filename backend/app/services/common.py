from datetime import datetime
from typing import Dict, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlmodel import Session, select

from app.domain.models import (
    Achievement,
    AgentConfig,
    ChecklistItem,
    Game,
    GameRead,
    Note,
    User,
    UserRead,
)
from app.domain.models import (
    Session as DbSession,
)
from app.domain.schemas import GameProgressSummaryItem


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


def get_total_playtime_map(session: Session, game_ids: Sequence[int]) -> Dict[int, int]:
    ids = [gid for gid in game_ids if gid is not None]
    if not ids:
        return {}

    rows = session.exec(
        select(DbSession.game_id, func.coalesce(func.sum(DbSession.duration_minutes), 0))
        .where(DbSession.game_id.in_(ids))
        .group_by(DbSession.game_id)
    ).all()
    return {int(game_id): int(total or 0) for game_id, total in rows}


def _calc_progress_percent(
    *,
    sync_type: str,
    checklist_total: int,
    checklist_completed: int,
    achievement_total: int,
    achievement_completed: int,
) -> int:
    checklist_percent = (
        round((checklist_completed / checklist_total) * 100) if checklist_total > 0 else None
    )
    achievement_percent = (
        round((achievement_completed / achievement_total) * 100) if achievement_total > 0 else None
    )

    if sync_type == "steam":
        if checklist_percent is None and achievement_percent is None:
            return 0
        if checklist_percent is None:
            return achievement_percent or 0
        if achievement_percent is None:
            return checklist_percent
        return round((checklist_percent + achievement_percent) / 2)

    return checklist_percent or 0


def get_game_progress_summary_map(
    session: Session,
    games: Sequence[Game],
) -> Dict[int, GameProgressSummaryItem]:
    game_map = {game.id: game for game in games if game.id is not None}
    game_ids = list(game_map.keys())
    if not game_ids:
        return {}

    checklist_rows = session.exec(
        select(
            ChecklistItem.game_id,
            func.count(ChecklistItem.id),
            func.coalesce(
                func.sum(case((ChecklistItem.completed, 1), else_=0)),
                0,
            ),
        )
        .where(ChecklistItem.game_id.in_(game_ids))
        .group_by(ChecklistItem.game_id)
    ).all()
    checklist_map = {
        int(game_id): (int(total or 0), int(completed or 0))
        for game_id, total, completed in checklist_rows
    }

    achievement_rows = session.exec(
        select(
            Achievement.game_id,
            func.count(Achievement.id),
            func.coalesce(
                func.sum(case((Achievement.completed, 1), else_=0)),
                0,
            ),
        )
        .where(Achievement.game_id.in_(game_ids))
        .group_by(Achievement.game_id)
    ).all()
    achievement_map = {
        int(game_id): (int(total or 0), int(completed or 0))
        for game_id, total, completed in achievement_rows
    }

    result: Dict[int, GameProgressSummaryItem] = {}
    for game_id, game in game_map.items():
        checklist_total, checklist_completed = checklist_map.get(game_id, (0, 0))
        achievement_total, achievement_completed = achievement_map.get(game_id, (0, 0))
        result[game_id] = GameProgressSummaryItem(
            game_id=game_id,
            progress_percent=_calc_progress_percent(
                sync_type=game.sync_type,
                checklist_total=checklist_total,
                checklist_completed=checklist_completed,
                achievement_total=achievement_total,
                achievement_completed=achievement_completed,
            ),
            checklist_total=checklist_total,
            checklist_completed=checklist_completed,
            achievement_total=achievement_total,
            achievement_completed=achievement_completed,
        )
    return result


def build_game_read(session: Session, game: Game, playtime_map: Optional[Dict[int, int]] = None) -> GameRead:
    game_read = GameRead.model_validate(game)
    if playtime_map is not None and game.id in playtime_map:
        game_read.total_playtime_minutes = playtime_map[game.id]
    else:
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
    max_gap_seconds: int = 300,
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
    diff_seconds = (now - last_ended_at).total_seconds()

    if diff_seconds > max(int(max_gap_seconds or 0), 1):
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
