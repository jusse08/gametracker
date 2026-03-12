from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
import sqlalchemy as sa

class UserBase(SQLModel):
    username: str = Field(..., min_length=3, max_length=50, unique=True)
    steam_api_key: Optional[str] = None
    steam_profile_url: Optional[str] = None
    steam_user_id: Optional[str] = None
    agent_token: Optional[str] = Field(default=None, index=True, unique=True)

class User(UserBase, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str

    games: List["Game"] = Relationship(back_populates="user", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class UserCreate(SQLModel):
    username: str
    password: str

class UserPasswordUpdate(SQLModel):
    password: str = Field(min_length=6, max_length=255)

class UserRead(SQLModel):
    id: int
    username: str
    steam_api_key: Optional[str] = None
    steam_profile_url: Optional[str] = None
    is_superadmin: bool = False

class GameBase(SQLModel):
    title: str = Field(..., min_length=1, max_length=200)
    status: str = Field(default="backlog", description="playing | backlog | completed | deferred | wishlist")
    cover_url: Optional[str] = None
    description: Optional[str] = None
    sync_type: str = Field(default="steam", description="steam | non_steam")
    steam_app_id: Optional[int] = None
    exe_name: Optional[str] = None
    launch_path: Optional[str] = None
    personal_rating: Optional[int] = Field(default=None, ge=1, le=5)
    genres: List[str] = Field(
        default_factory=list,
        sa_column=sa.Column(sa.JSON(), nullable=False, server_default="[]"),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Game(GameBase, table=True):
    __tablename__ = "games"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    user: User = Relationship(back_populates="games")
    sessions: List["Session"] = Relationship(back_populates="game", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    achievements: List["Achievement"] = Relationship(back_populates="game", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    checklist_items: List["ChecklistItem"] = Relationship(back_populates="game", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    notes: List["Note"] = Relationship(back_populates="game", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    agent_config: Optional["AgentConfig"] = Relationship(back_populates="game", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    quest_categories: List["QuestCategory"] = Relationship(back_populates="game", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class GameCreate(GameBase):
    pass

class GameRead(GameBase):
    id: int
    total_playtime_minutes: int = 0

class SessionBase(SQLModel):
    game_id: int = Field(foreign_key="games.id")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    duration_minutes: Optional[int] = 0
    source: str = Field(default="manual", description="agent | manual")

class Session(SessionBase, table=True):
    __tablename__ = "sessions"
    id: Optional[int] = Field(default=None, primary_key=True)
    
    game: Game = Relationship(back_populates="sessions")

class SessionRead(SessionBase):
    id: int

class AchievementBase(SQLModel):
    game_id: int = Field(foreign_key="games.id")
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    completed: bool = Field(default=False)
    completed_at: Optional[datetime] = None
    steam_api_name: Optional[str] = None

class Achievement(AchievementBase, table=True):
    __tablename__ = "achievements"
    id: Optional[int] = Field(default=None, primary_key=True)
    
    game: Game = Relationship(back_populates="achievements")

class AchievementRead(AchievementBase):
    id: int

class ChecklistItemBase(SQLModel):
    game_id: int = Field(foreign_key="games.id")
    title: str
    category: str = Field(default="General", description="Главная миссия | Побочка | Цель | кастомная")
    completed: bool = Field(default=False)
    sort_order: int = Field(default=0)
    imported_from_url: Optional[str] = None

class ChecklistItem(ChecklistItemBase, table=True):
    __tablename__ = "checklist_items"
    id: Optional[int] = Field(default=None, primary_key=True)
    
    game: Game = Relationship(back_populates="checklist_items")

class ChecklistItemCreate(SQLModel):
    title: str
    category: str = "General"
    completed: bool = False
    sort_order: int = 0

class ChecklistItemRead(ChecklistItemBase):
    id: int

class QuestCategoryBase(SQLModel):
    game_id: int = Field(foreign_key="games.id")
    name: str = Field(min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class QuestCategory(QuestCategoryBase, table=True):
    __tablename__ = "quest_categories"
    id: Optional[int] = Field(default=None, primary_key=True)

    game: Game = Relationship(back_populates="quest_categories")

class QuestCategoryRead(QuestCategoryBase):
    id: int

class QuestCategoryCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)

class QuestCategoryRename(SQLModel):
    new_name: str = Field(min_length=1, max_length=100)

class NoteBase(SQLModel):
    game_id: int = Field(foreign_key="games.id")
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    session_id: Optional[int] = Field(default=None, foreign_key="sessions.id")

class Note(NoteBase, table=True):
    __tablename__ = "notes"
    id: Optional[int] = Field(default=None, primary_key=True)
    
    game: Game = Relationship(back_populates="notes")

class NoteCreate(SQLModel):
    text: str
    session_id: Optional[int] = None

class NoteRead(NoteBase):
    id: int

class AgentConfigBase(SQLModel):
    game_id: int = Field(foreign_key="games.id")
    exe_name: str
    launch_path: Optional[str] = None
    enabled: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    pending_launch_id: Optional[str] = None
    pending_launch_path: Optional[str] = None
    pending_launch_requested_at: Optional[datetime] = None
    last_launch_status: Optional[str] = None
    last_launch_error: Optional[str] = None
    last_launch_at: Optional[datetime] = None

class AgentConfig(AgentConfigBase, table=True):
    __tablename__ = "agent_config"
    id: Optional[int] = Field(default=None, primary_key=True)

    game: Game = Relationship(back_populates="agent_config")

class AgentConfigCreate(SQLModel):
    launch_path: str
    enabled: bool = True

class AgentConfigRead(SQLModel):
    id: int
    game_id: int
    exe_name: str
    launch_path: Optional[str]
    enabled: bool
    updated_at: datetime

class DashboardWidgetBase(SQLModel):
    widget_type: str
    position_x: int
    position_y: int
    width: int
    height: int
    config_json: Optional[str] = None

class DashboardWidget(DashboardWidgetBase, table=True):
    __tablename__ = "dashboard_widgets"
    id: Optional[int] = Field(default=None, primary_key=True)

class SettingsBase(SQLModel):
    steam_api_key: Optional[str] = None
    steam_profile_url: Optional[str] = None
    steam_user_id: Optional[str] = None

class Settings(SettingsBase, table=True):
    __tablename__ = "settings"
    id: int = Field(default=1, primary_key=True)

class SettingsUpdate(SQLModel):
    steam_api_key: Optional[str] = None
    steam_profile_url: Optional[str] = None

class GameUpdate(SQLModel):
    title: Optional[str] = None
    status: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    sync_type: Optional[str] = None
    exe_name: Optional[str] = None
    launch_path: Optional[str] = None
    personal_rating: Optional[int] = Field(default=None, ge=1, le=5)
    genres: Optional[List[str]] = None
