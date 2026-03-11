from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from typing import List, Optional
from datetime import timedelta, datetime
import os
from dotenv import load_dotenv

load_dotenv()

from database import create_db_and_tables, get_session
from scraper import parse_wiki_missions
from steam import sync_steam_achievements, search_steam_games
from models import (
    User, UserCreate, UserRead,
    Game, GameCreate, GameRead, GameUpdate,
    Note, NoteCreate, NoteRead,
    ChecklistItem, ChecklistItemCreate, ChecklistItemRead,
    Achievement, AchievementRead,
    AgentConfig, AgentConfigRead, Session as DbSession, SessionRead,
    Settings, SettingsUpdate,
)
from schemas import PingRequest, WikiImportRequest, AgentConfigRequest, AgentTestPingRequest
from auth import (
    get_current_user, get_password_hash, create_access_token,
    verify_password, ACCESS_TOKEN_EXPIRE_MINUTES
)

app = FastAPI(title="GameTracker API")

@app.get("/health")
def healthcheck():
    return {"ok": True}

# CORS configuration from environment
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    from database import engine
    with Session(engine) as session:
        if not session.get(Settings, 1):
            session.add(Settings(id=1))
            session.commit()
            
        superadmin_username = os.getenv("SUPERADMIN_USERNAME")
        superadmin_password = os.getenv("SUPERADMIN_PASSWORD")
        if superadmin_username and superadmin_password:
            existing_superadmin = session.exec(select(User).where(User.username == superadmin_username)).first()
            if not existing_superadmin:
                superadmin = User(
                    username=superadmin_username,
                    hashed_password=get_password_hash(superadmin_password)
                )
                session.add(superadmin)
                session.commit()

# --- Auth ---

def is_superadmin(user: User) -> bool:
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

def get_total_playtime_minutes(session: Session, game_id: int) -> int:
    playtime_query = select(DbSession.duration_minutes).where(DbSession.game_id == game_id)
    return sum(session.exec(playtime_query) or [0])

def build_game_read(session: Session, game: Game) -> GameRead:
    game_read = GameRead.model_validate(game)
    game_read.total_playtime_minutes = get_total_playtime_minutes(session, game.id)
    return game_read

def validate_sync_type(sync_type: str) -> str:
    if sync_type not in {"steam", "agent"}:
        raise HTTPException(status_code=400, detail="sync_type must be 'steam' or 'agent'")
    return sync_type

def upsert_agent_session(
    session: Session,
    game_id: int,
    now: datetime,
    active_source: str,
    new_source: str
):
    query = select(DbSession).where(
        DbSession.game_id == game_id,
        DbSession.source == active_source
    ).order_by(DbSession.started_at.desc())
    active_session_obj = session.exec(query).first()

    if not active_session_obj:
        new_session = DbSession(
            game_id=game_id,
            started_at=now,
            ended_at=now,
            source=new_source,
            duration_minutes=0
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
            duration_minutes=0
        )
        session.add(new_session)
        return new_session, "new_session"

    active_session_obj.ended_at = now
    duration_delta = now - active_session_obj.started_at
    active_session_obj.duration_minutes = int(duration_delta.total_seconds() / 60)
    session.add(active_session_obj)
    return active_session_obj, "session_updated"

@app.get("/api/users", response_model=List[UserRead])
def read_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Superadmin only")
    users = session.exec(select(User)).all()
    return [enrich_user_read(u) for u in users]

@app.post("/api/users", response_model=UserRead)
def create_user(
    *, session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    user_data: UserCreate
):
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Superadmin only")
    existing = session.exec(select(User).where(User.username == user_data.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password)
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return enrich_user_read(user)

@app.post("/api/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
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
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user": enrich_user_read(user)}

@app.get("/api/auth/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return enrich_user_read(current_user)

@app.put("/api/auth/me", response_model=UserRead)
def update_me(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    steam_api_key: Optional[str] = None,
    steam_profile_url: Optional[str] = None
):
    if steam_api_key is not None:
        current_user.steam_api_key = steam_api_key
    if steam_profile_url is not None:
        current_user.steam_profile_url = steam_profile_url
        from steam import resolve_steam_id
        current_user.steam_user_id = resolve_steam_id(
            current_user.steam_profile_url,
            api_key=current_user.steam_api_key
        )
    
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user

# --- Games ---

@app.post("/api/games", response_model=GameRead)
def create_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game: GameCreate
):
    validate_sync_type(game.sync_type)

    # Check for duplicate title for this user
    existing = session.exec(
        select(Game).where(Game.title == game.title, Game.user_id == current_user.id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Game with this title already exists")

    if game.sync_type == "steam":
        game.exe_name = None

    db_game = Game.model_validate(game, update={"user_id": current_user.id})
    session.add(db_game)
    session.commit()
    session.refresh(db_game)
    return build_game_read(session, db_game)

@app.get("/api/games", response_model=List[GameRead])
def read_games(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None
):
    query = select(Game).where(Game.user_id == current_user.id)
    if status is not None:
        query = query.where(Game.status == status)
    
    games = session.exec(query).all()
    return [build_game_read(session, game) for game in games]

@app.get("/api/games/{game_id}", response_model=GameRead)
def read_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    playtime_query = select(DbSession.duration_minutes).where(DbSession.game_id == game_id)
    total_minutes = sum(session.exec(playtime_query) or [0])
    
    game_read = GameRead.model_validate(game)
    game_read.total_playtime_minutes = total_minutes
    return game_read

@app.put("/api/games/{game_id}", response_model=GameRead)
def update_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    game_data: GameUpdate
):
    db_game = session.get(Game, game_id)
    if not db_game or db_game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")

    data = game_data.model_dump(exclude_unset=True)
    if "sync_type" in data:
        validate_sync_type(data["sync_type"])

    for key, value in data.items():
        setattr(db_game, key, value)

    if db_game.sync_type == "steam":
        db_game.exe_name = None
        existing_config = session.exec(select(AgentConfig).where(AgentConfig.game_id == game_id)).first()
        if existing_config:
            session.delete(existing_config)

    session.add(db_game)
    session.commit()
    session.refresh(db_game)
    return build_game_read(session, db_game)

@app.delete("/api/games/{game_id}")
def delete_game(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    session.delete(game)
    session.commit()
    return {"ok": True}

# --- Checklist ---

@app.get("/api/games/{game_id}/checklist", response_model=List[ChecklistItemRead])
def read_checklist_items(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    query = select(ChecklistItem).where(ChecklistItem.game_id == game_id).order_by(ChecklistItem.sort_order)
    return session.exec(query).all()

@app.post("/api/games/{game_id}/checklist", response_model=ChecklistItemRead)
def create_checklist_item(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    item: ChecklistItemCreate
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    db_item = ChecklistItem.model_validate(item, update={"game_id": game_id})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item

@app.put("/api/checklist/{item_id}", response_model=ChecklistItemRead)
def update_checklist_item(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    item_id: int,
    completed: bool
):
    db_item = session.get(ChecklistItem, item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Verify ownership through game
    game = session.get(Game, db_item.game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Item not found")
    
    db_item.completed = completed
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item

@app.delete("/api/checklist/{item_id}")
def delete_checklist_item(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    item_id: int
):
    db_item = session.get(ChecklistItem, item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    game = session.get(Game, db_item.game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Item not found")
    
    session.delete(db_item)
    session.commit()
    return {"ok": True}

@app.delete("/api/games/{game_id}/checklist/category/{category_name}")
def delete_checklist_category(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    category_name: str
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    query = select(ChecklistItem).where(
        ChecklistItem.game_id == game_id,
        ChecklistItem.category == category_name
    )
    items = session.exec(query).all()
    
    for item in items:
        session.delete(item)
    
    session.commit()
    return {"ok": True, "deleted_count": len(items)}

@app.post("/api/games/{game_id}/import/wiki", response_model=List[ChecklistItemRead])
def import_wiki_checklist(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    req: WikiImportRequest
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    items = parse_wiki_missions(req.url)
    
    query = select(ChecklistItem).where(ChecklistItem.game_id == game_id)
    existing_items = session.exec(query).all()
    max_order = max([item.sort_order for item in existing_items] + [-1])
    
    new_db_items = []
    for item_data in items:
        max_order += 1
        db_item = ChecklistItem(
            game_id=game_id,
            title=item_data["title"],
            category=item_data["category"],
            sort_order=max_order,
            imported_from_url=req.url
        )
        session.add(db_item)
        new_db_items.append(db_item)
    
    session.commit()
    for item in new_db_items:
        session.refresh(item)
    
    return new_db_items

# --- Notes ---

@app.get("/api/games/{game_id}/notes", response_model=List[NoteRead])
def read_notes(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    query = select(Note).where(Note.game_id == game_id).order_by(Note.created_at.desc())
    return session.exec(query).all()

@app.post("/api/games/{game_id}/notes", response_model=NoteRead)
def create_note(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int,
    note: NoteCreate
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    db_note = Note.model_validate(note, update={"game_id": game_id})
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note

@app.put("/api/notes/{note_id}", response_model=NoteRead)
def update_note(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    note_id: int,
    text: str
):
    db_note = session.get(Note, note_id)
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    game = session.get(Game, db_note.game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    
    db_note.text = text
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note

@app.delete("/api/notes/{note_id}")
def delete_note(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    note_id: int
):
    db_note = session.get(Note, note_id)
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")
    
    game = session.get(Game, db_note.game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    
    session.delete(db_note)
    session.commit()
    return {"ok": True}

# --- Agent & Sessions ---

@app.get("/api/agent/config")
def get_agent_config(
    *,
    session: Session = Depends(get_session),
    user_id: Optional[int] = None
):
    # For agent authentication, we use user_id from query param
    # In production, use API key authentication
    query = select(AgentConfig).where(AgentConfig.enabled == True)
    if user_id:
        query = query.join(Game).where(Game.user_id == user_id)

    configs = session.exec(query).all()
    return {cfg.exe_name: cfg.game_id for cfg in configs}

@app.get("/api/agent/download")
def download_agent():
    """Скачать исполняемый файл агента для Windows."""
    agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "dist", "GameTrackerAgent.exe")
    
    if not os.path.exists(agent_path):
        raise HTTPException(
            status_code=404,
            detail="Агент не найден. Сначала соберите .exe файл через PyInstaller."
        )
    
    from fastapi.responses import FileResponse
    return FileResponse(
        agent_path,
        media_type="application/octet-stream",
        filename="GameTrackerAgent.exe"
    )

@app.post("/api/agent/test-ping")
def test_agent_ping(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentTestPingRequest
):
    """Проверить связь с агентом для указанной игры."""
    game_id = req.game_id
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Игра не найдена")

    if game.sync_type != "agent":
        raise HTTPException(status_code=400, detail="Проверка агента доступна только для agent-игр")

    if not game.exe_name:
        raise HTTPException(
            status_code=400,
            detail="Для игры не указан исполняемый файл. Укажите его в карточке игры."
        )

    # Проверяем, есть ли конфиг для этого exe
    config_query = select(AgentConfig).where(
        AgentConfig.game_id == game_id,
        AgentConfig.enabled == True
    )
    config = session.exec(config_query).first()
    
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Агент не настроен для этой игры. Сохраните исполняемый файл в карточке игры."
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

@app.post("/api/sessions/ping")
def ping_session(
    *,
    session: Session = Depends(get_session),
    req: PingRequest
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

@app.get("/api/games/{game_id}/sessions", response_model=List[SessionRead])
def read_game_sessions(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    query = select(DbSession).where(DbSession.game_id == game_id).order_by(DbSession.started_at.desc()).limit(10)
    return session.exec(query).all()

# --- Achievements ---

@app.post("/api/games/{game_id}/sync/steam", response_model=List[AchievementRead])
def sync_steam(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    from steam import fetch_steam_playtime

    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.sync_type != "steam":
        raise HTTPException(status_code=400, detail="Steam sync доступен только для steam-игр")

    if not game.steam_app_id:
        game.steam_app_id = 400
        session.add(game)
        session.commit()
    
    # Use user's Steam API key
    steam_playtime = fetch_steam_playtime(game.steam_app_id)
    
    current_playtime_query = select(DbSession.duration_minutes).where(DbSession.game_id == game_id)
    current_total = sum(session.exec(current_playtime_query) or [0])
    
    if steam_playtime > current_total:
        diff = steam_playtime - current_total
        sync_session = DbSession(
            game_id=game_id,
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
            duration_minutes=diff,
            source="steam_sync"
        )
        session.add(sync_session)
    
    achievements_data = sync_steam_achievements(game.steam_app_id)
    
    existing_query = select(Achievement).where(Achievement.game_id == game_id)
    existing_achievements = session.exec(existing_query).all()
    existing_map = {a.steam_api_name: a for a in existing_achievements if a.steam_api_name}
    
    new_db_items = []
    for item in achievements_data:
        api_name = item["steam_api_name"]
        if api_name in existing_map:
            db_ach = existing_map[api_name]
            db_ach.completed = item["completed"]
            if db_ach.completed and not db_ach.completed_at:
                db_ach.completed_at = datetime.utcnow()
            session.add(db_ach)
            new_db_items.append(db_ach)
        else:
            db_ach = Achievement(
                game_id=game_id,
                name=item["name"],
                description=item["description"],
                icon_url=item["icon_url"],
                completed=item["completed"],
                completed_at=datetime.utcnow() if item["completed"] else None,
                steam_api_name=api_name
            )
            session.add(db_ach)
            new_db_items.append(db_ach)
    
    session.commit()
    for db_item in new_db_items:
        session.refresh(db_item)
    
    return new_db_items

@app.get("/api/games/{game_id}/achievements", response_model=List[AchievementRead])
def read_achievements(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Game not found")
    
    query = select(Achievement).where(Achievement.game_id == game_id)
    return session.exec(query).all()

# --- Search ---

@app.get("/api/games/search/steam")
def search_steam(query: str):
    return search_steam_games(query)

# --- Agent Management ---

@app.get("/api/agent/games", response_model=List[GameRead])
def get_agent_games(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Получить список игр пользователя с настройками агента."""
    query = select(Game).where(Game.user_id == current_user.id, Game.sync_type == "agent")
    games = session.exec(query).all()
    return [build_game_read(session, game) for game in games]

@app.post("/api/agent/configure", response_model=AgentConfigRead)
def configure_agent(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    req: AgentConfigRequest
):
    """Настроить отслеживание для игры."""
    game_id = req.game_id
    exe_name = req.exe_name.strip()
    enabled = req.enabled

    if not exe_name:
        raise HTTPException(status_code=400, detail="exe_name is required")

    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Игра не найдена")

    if game.sync_type != "agent":
        raise HTTPException(status_code=400, detail="Агент можно настроить только для agent-игр")

    # Обновляем exe_name в игре
    game.exe_name = exe_name
    session.add(game)
    
    # Проверяем существующий конфиг
    existing_query = select(AgentConfig).where(AgentConfig.game_id == game_id)
    existing = session.exec(existing_query).first()
    
    if existing:
        existing.exe_name = exe_name
        existing.enabled = enabled
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    else:
        new_config = AgentConfig(
            game_id=game_id,
            exe_name=exe_name,
            enabled=enabled
        )
        session.add(new_config)
        session.commit()
        session.refresh(new_config)
        return new_config

@app.delete("/api/agent/config/{game_id}")
def delete_agent_config(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    game_id: int
):
    """Удалить настройку агента для игры."""
    game = session.get(Game, game_id)
    if not game or game.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    
    config_query = select(AgentConfig).where(AgentConfig.game_id == game_id)
    config = session.exec(config_query).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    session.delete(config)
    session.commit()
    return {"ok": True}

# --- Settings ---

@app.get("/api/settings", response_model=Settings)
def get_settings(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    settings = session.get(Settings, 1)
    if not settings:
        settings = Settings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    
    # Merge with user settings
    if current_user.steam_api_key:
        settings.steam_api_key = current_user.steam_api_key
    if current_user.steam_profile_url:
        settings.steam_profile_url = current_user.steam_profile_url
    
    return settings

@app.put("/api/settings", response_model=Settings)
def update_settings(
    *,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    settings_data: SettingsUpdate
):
    # Update user's Steam settings
    if settings_data.steam_api_key is not None:
        current_user.steam_api_key = settings_data.steam_api_key
    if settings_data.steam_profile_url is not None:
        current_user.steam_profile_url = settings_data.steam_profile_url
        from steam import resolve_steam_id
        current_user.steam_user_id = resolve_steam_id(
            current_user.steam_profile_url,
            api_key=current_user.steam_api_key
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









