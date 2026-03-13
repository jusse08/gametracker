from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.auth import get_current_user
from app.core.database import get_session
from app.domain.models import (
    Achievement,
    AchievementRead,
    AgentConfig,
    ChecklistItem,
    ChecklistItemCreate,
    ChecklistItemRead,
    Game,
    GameCreate,
    GameRead,
    GameUpdate,
    Note,
    NoteCreate,
    NoteRead,
    QuestCategory,
    QuestCategoryCreate,
    QuestCategoryRead,
    QuestCategoryRename,
    Session as DbSession,
    SessionRead,
    User,
)
from app.domain.schemas import WikiImportRequest
from app.integrations.scraper import parse_wiki_missions
from app.integrations.steam import (
    build_steam_store_image_urls,
    fetch_steam_genres,
    fetch_steam_playtime,
    search_steam_games,
    sync_steam_achievements,
)
from app.services.common import (
    build_game_read,
    ensure_owned_checklist_item_with_detail,
    ensure_owned_game,
    ensure_owned_note_with_detail,
    get_total_playtime_map,
    get_agent_config_by_game_id,
    validate_game_status,
    validate_sync_type,
)

router = APIRouter()


def normalize_category_name(category_name: str) -> str:
    normalized = category_name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Category name is required")
    return normalized


def ensure_quest_category_exists(session: Session, game_id: int, category_name: str) -> QuestCategory:
    normalized = normalize_category_name(category_name)
    existing = session.exec(
        select(QuestCategory).where(
            QuestCategory.game_id == game_id,
            func.lower(QuestCategory.name) == normalized.lower(),
        )
    ).first()
    if existing:
        return existing

    new_category = QuestCategory(game_id=game_id, name=normalized)
    session.add(new_category)
    return new_category


@router.post("/api/games", response_model=GameRead)
def create_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game: GameCreate,
):
    validate_sync_type(game.sync_type)
    validate_game_status(game.status)

    existing = session.exec(
        select(Game).where(Game.title == game.title, Game.user_id == current_user.id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Game with this title already exists")

    game_data = game.model_dump()
    if game_data.get("sync_type") == "steam" and game_data.get("steam_app_id"):
        steam_images = build_steam_store_image_urls(game_data["steam_app_id"])
        current_cover = (game_data.get("cover_url") or "").strip()
        if not current_cover or current_cover.endswith("/header.jpg"):
            game_data["cover_url"] = steam_images["poster2x"]

    if game_data.get("steam_app_id") and not game_data.get("genres"):
        game_data["genres"] = fetch_steam_genres(game_data["steam_app_id"])

    db_game = Game.model_validate(game_data, update={"user_id": current_user.id})
    session.add(db_game)
    session.commit()
    session.refresh(db_game)
    return build_game_read(session, db_game)


@router.get("/api/games", response_model=List[GameRead])
def read_games(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
):
    query = select(Game).where(Game.user_id == current_user.id)
    if status is not None:
        validate_game_status(status)
        query = query.where(Game.status == status)

    games = session.exec(query).all()
    playtime_map = get_total_playtime_map(session, [game.id for game in games if game.id is not None])
    return [build_game_read(session, game, playtime_map=playtime_map) for game in games]


@router.get("/api/games/{game_id}", response_model=GameRead)
def read_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    game = ensure_owned_game(session, current_user, game_id)
    return build_game_read(session, game)


@router.put("/api/games/{game_id}", response_model=GameRead)
def update_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    game_data: GameUpdate,
):
    db_game = ensure_owned_game(session, current_user, game_id)

    data = game_data.model_dump(exclude_unset=True)
    if "sync_type" in data:
        validate_sync_type(data["sync_type"])
    if "status" in data:
        validate_game_status(data["status"])

    for key, value in data.items():
        setattr(db_game, key, value)

    if db_game.sync_type == "steam" and db_game.steam_app_id:
        steam_images = build_steam_store_image_urls(db_game.steam_app_id)
        current_cover = (db_game.cover_url or "").strip()
        if not current_cover or current_cover.endswith("/header.jpg"):
            db_game.cover_url = steam_images["poster2x"]

    if db_game.sync_type == "steam":
        db_game.exe_name = None
        existing_config = get_agent_config_by_game_id(session, game_id)
        if existing_config:
            session.delete(existing_config)

    session.add(db_game)
    session.commit()
    session.refresh(db_game)
    return build_game_read(session, db_game)


@router.delete("/api/games/{game_id}")
def delete_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    game = ensure_owned_game(session, current_user, game_id)
    session.delete(game)
    session.commit()
    return {"ok": True}


@router.get("/api/games/{game_id}/checklist", response_model=List[ChecklistItemRead])
def read_checklist_items(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game(session, current_user, game_id)
    query = select(ChecklistItem).where(ChecklistItem.game_id == game_id).order_by(ChecklistItem.sort_order)
    return session.exec(query).all()


@router.post("/api/games/{game_id}/checklist", response_model=ChecklistItemRead)
def create_checklist_item(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    item: ChecklistItemCreate,
):
    ensure_owned_game(session, current_user, game_id)
    category_name = normalize_category_name(item.category)
    ensure_quest_category_exists(session, game_id, category_name)

    db_item = ChecklistItem.model_validate(item, update={"game_id": game_id, "category": category_name})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@router.get("/api/games/{game_id}/checklist/categories", response_model=List[QuestCategoryRead])
def read_checklist_categories(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game(session, current_user, game_id)

    categories = session.exec(
        select(QuestCategory).where(QuestCategory.game_id == game_id).order_by(QuestCategory.name.asc())
    ).all()

    # Backfill categories from checklist items for pre-existing DB rows.
    existing_lc = {c.name.lower() for c in categories}
    item_categories = session.exec(
        select(ChecklistItem.category).where(ChecklistItem.game_id == game_id)
    ).all()
    for category_name in item_categories:
        normalized = normalize_category_name(category_name)
        if normalized.lower() not in existing_lc:
            new_category = QuestCategory(game_id=game_id, name=normalized)
            session.add(new_category)
            categories.append(new_category)
            existing_lc.add(normalized.lower())

    session.commit()
    for category in categories:
        session.refresh(category)
    return sorted(categories, key=lambda c: c.name.lower())


@router.post("/api/games/{game_id}/checklist/categories", response_model=QuestCategoryRead)
def create_checklist_category(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    payload: QuestCategoryCreate,
):
    ensure_owned_game(session, current_user, game_id)
    category = ensure_quest_category_exists(session, game_id, payload.name)
    session.commit()
    session.refresh(category)
    return category


@router.put("/api/games/{game_id}/checklist/categories/{category_name}")
def rename_checklist_category(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    category_name: str,
    payload: QuestCategoryRename,
):
    ensure_owned_game(session, current_user, game_id)
    old_name = normalize_category_name(category_name)
    new_name = normalize_category_name(payload.new_name)

    if old_name.lower() == new_name.lower():
        return {"ok": True, "category": new_name, "updated_items": 0}

    # Ensure old category exists at least by its items.
    old_category = session.exec(
        select(QuestCategory).where(
            QuestCategory.game_id == game_id,
            func.lower(QuestCategory.name) == old_name.lower(),
        )
    ).first()

    existing_target = session.exec(
        select(QuestCategory).where(
            QuestCategory.game_id == game_id,
            func.lower(QuestCategory.name) == new_name.lower(),
        )
    ).first()

    if not old_category:
        has_old_items = session.exec(
            select(ChecklistItem.id).where(
                ChecklistItem.game_id == game_id,
                func.lower(ChecklistItem.category) == old_name.lower(),
            )
        ).first()
        if not has_old_items:
            raise HTTPException(status_code=404, detail="Category not found")
        old_category = ensure_quest_category_exists(session, game_id, old_name)

    items_to_move = session.exec(
        select(ChecklistItem).where(
            ChecklistItem.game_id == game_id,
            func.lower(ChecklistItem.category) == old_name.lower(),
        )
    ).all()
    for item in items_to_move:
        item.category = new_name
        session.add(item)

    if existing_target:
        session.delete(old_category)
    else:
        old_category.name = new_name
        session.add(old_category)

    session.commit()
    return {"ok": True, "category": new_name, "updated_items": len(items_to_move)}


@router.put("/api/checklist/{item_id}", response_model=ChecklistItemRead)
def update_checklist_item(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    item_id: int,
    completed: bool,
):
    db_item = ensure_owned_checklist_item_with_detail(session, current_user, item_id, "Item not found")
    db_item.completed = completed
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@router.delete("/api/checklist/{item_id}")
def delete_checklist_item(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    item_id: int,
):
    db_item = ensure_owned_checklist_item_with_detail(session, current_user, item_id, "Item not found")
    session.delete(db_item)
    session.commit()
    return {"ok": True}


@router.delete("/api/games/{game_id}/checklist/category/{category_name}")
def delete_checklist_category(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    category_name: str,
):
    ensure_owned_game(session, current_user, game_id)
    normalized = normalize_category_name(category_name)

    query = select(ChecklistItem).where(
        ChecklistItem.game_id == game_id,
        ChecklistItem.category == normalized,
    )
    items = session.exec(query).all()

    for item in items:
        session.delete(item)

    category = session.exec(
        select(QuestCategory).where(
            QuestCategory.game_id == game_id,
            func.lower(QuestCategory.name) == normalized.lower(),
        )
    ).first()
    if category:
        session.delete(category)

    session.commit()
    return {"ok": True, "deleted_count": len(items)}


@router.post("/api/games/{game_id}/import/wiki", response_model=List[ChecklistItemRead])
def import_wiki_checklist(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    req: WikiImportRequest,
):
    ensure_owned_game(session, current_user, game_id)

    items = parse_wiki_missions(req.url)

    query = select(ChecklistItem).where(ChecklistItem.game_id == game_id)
    existing_items = session.exec(query).all()
    max_order = max([item.sort_order for item in existing_items] + [-1])

    new_db_items = []
    for item_data in items:
        category_name = normalize_category_name(item_data["category"])
        ensure_quest_category_exists(session, game_id, category_name)
        max_order += 1
        db_item = ChecklistItem(
            game_id=game_id,
            title=item_data["title"],
            category=category_name,
            sort_order=max_order,
            imported_from_url=req.url,
        )
        session.add(db_item)
        new_db_items.append(db_item)

    session.commit()
    for item in new_db_items:
        session.refresh(item)

    return new_db_items


@router.get("/api/games/{game_id}/notes", response_model=List[NoteRead])
def read_notes(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game(session, current_user, game_id)
    query = select(Note).where(Note.game_id == game_id).order_by(Note.created_at.desc())
    return session.exec(query).all()


@router.post("/api/games/{game_id}/notes", response_model=NoteRead)
def create_note(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    note: NoteCreate,
):
    ensure_owned_game(session, current_user, game_id)

    db_note = Note.model_validate(note, update={"game_id": game_id})
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note


@router.put("/api/notes/{note_id}", response_model=NoteRead)
def update_note(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    note_id: int,
    text: str,
):
    db_note = ensure_owned_note_with_detail(session, current_user, note_id, "Note not found")
    db_note.text = text
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note


@router.delete("/api/notes/{note_id}")
def delete_note(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    note_id: int,
):
    db_note = ensure_owned_note_with_detail(session, current_user, note_id, "Note not found")
    session.delete(db_note)
    session.commit()
    return {"ok": True}


@router.get("/api/games/{game_id}/sessions", response_model=List[SessionRead])
def read_game_sessions(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game(session, current_user, game_id)
    query = select(DbSession).where(DbSession.game_id == game_id).order_by(DbSession.started_at.desc()).limit(10)
    return session.exec(query).all()


def _sync_steam_playtime_manual(
    session: Session,
    game_id: int,
    steam_app_id: int,
    steam_api_key: Optional[str],
    steam_user_id: Optional[str],
) -> int:
    steam_playtime = fetch_steam_playtime(steam_app_id, steam_api_key, steam_user_id)
    current_playtime_query = select(DbSession.duration_minutes).where(DbSession.game_id == game_id)
    current_total = sum(session.exec(current_playtime_query) or [0])

    if steam_playtime <= current_total:
        return 0

    diff = steam_playtime - current_total
    sync_session = DbSession(
        game_id=game_id,
        started_at=datetime.utcnow(),
        ended_at=datetime.utcnow(),
        duration_minutes=diff,
        source="steam_manual_sync",
    )
    session.add(sync_session)
    return diff


def _sync_steam_achievements_for_game(
    session: Session,
    game_id: int,
    steam_app_id: int,
    steam_api_key: Optional[str],
    steam_user_id: Optional[str],
) -> List[Achievement]:
    achievements_data = sync_steam_achievements(steam_app_id, steam_api_key, steam_user_id)
    existing_query = select(Achievement).where(Achievement.game_id == game_id)
    existing_achievements = session.exec(existing_query).all()
    existing_map = {a.steam_api_name: a for a in existing_achievements if a.steam_api_name}

    db_items: List[Achievement] = []
    for item in achievements_data:
        api_name = item["steam_api_name"]
        if api_name in existing_map:
            db_ach = existing_map[api_name]
            db_ach.completed = item["completed"]
            if db_ach.completed and not db_ach.completed_at:
                db_ach.completed_at = datetime.utcnow()
            session.add(db_ach)
            db_items.append(db_ach)
        else:
            db_ach = Achievement(
                game_id=game_id,
                name=item["name"],
                description=item["description"],
                icon_url=item["icon_url"],
                completed=item["completed"],
                completed_at=datetime.utcnow() if item["completed"] else None,
                steam_api_name=api_name,
            )
            session.add(db_ach)
            db_items.append(db_ach)
    return db_items


@router.post("/api/games/{game_id}/sync/steam/manual")
def sync_steam_manual_playtime(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    game = ensure_owned_game(session, current_user, game_id)

    if game.sync_type != "steam":
        raise HTTPException(status_code=400, detail="Ручной Steam-синк доступен только для steam-игр")

    if not game.steam_app_id:
        raise HTTPException(status_code=400, detail="У игры не задан steam_app_id")

    added_minutes = _sync_steam_playtime_manual(
        session,
        game_id,
        game.steam_app_id,
        current_user.steam_api_key,
        current_user.steam_user_id,
    )
    session.commit()
    return {"ok": True, "added_minutes": added_minutes}

@router.post("/api/games/{game_id}/sync/steam/achievements", response_model=List[AchievementRead])
def sync_steam_achievements_only(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    game = ensure_owned_game(session, current_user, game_id)

    if game.sync_type != "steam":
        raise HTTPException(status_code=400, detail="Синхронизация достижений Steam доступна только для steam-игр")

    if not game.steam_app_id:
        raise HTTPException(status_code=400, detail="У игры не задан steam_app_id")

    new_db_items = _sync_steam_achievements_for_game(
        session,
        game_id,
        game.steam_app_id,
        current_user.steam_api_key,
        current_user.steam_user_id,
    )
    session.commit()
    for db_item in new_db_items:
        session.refresh(db_item)
    return new_db_items


@router.get("/api/games/{game_id}/achievements", response_model=List[AchievementRead])
def read_achievements(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
):
    ensure_owned_game(session, current_user, game_id)
    query = select(Achievement).where(Achievement.game_id == game_id)
    return session.exec(query).all()


@router.get("/api/games/search/steam")
def search_steam(query: str):
    return search_steam_games(query)
