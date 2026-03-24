from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from alembic import command
from app import main as main_module
from app.core.migrations import ensure_database_schema_current
from app.domain.models import Settings, User


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _sqlite_engine(database_path: Path):
    return create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )


def test_alembic_upgrade_head_smoke(monkeypatch, tmp_path):
    database_path = tmp_path / "smoke.sqlite3"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(_alembic_config(database_url), "head")

    inspector = inspect(_sqlite_engine(database_path))
    table_names = set(inspector.get_table_names())

    assert {"users", "games", "sessions", "settings", "agent_devices"} <= table_names


def test_bootstrap_runtime_state_requires_migrations(monkeypatch, tmp_path):
    database_path = tmp_path / "missing-schema.sqlite3"
    engine = _sqlite_engine(database_path)
    monkeypatch.setattr(main_module, "engine", engine)

    with pytest.raises(RuntimeError, match="python scripts/manage_db.py upgrade"):
        main_module.bootstrap_runtime_state()


def test_schema_current_check_rejects_outdated_revision(monkeypatch, tmp_path):
    database_path = tmp_path / "outdated.sqlite3"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(_alembic_config(database_url), "add_users")

    with pytest.raises(RuntimeError, match="not up to date"):
        ensure_database_schema_current(_sqlite_engine(database_path))


def test_bootstrap_runtime_state_initializes_runtime_records(monkeypatch, tmp_path):
    database_path = tmp_path / "runtime.sqlite3"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(_alembic_config(database_url), "head")
    engine = _sqlite_engine(database_path)

    monkeypatch.setattr(main_module, "engine", engine)
    monkeypatch.setenv("SUPERADMIN_USERNAME", "runtime_admin")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "runtime_password_123")

    main_module.bootstrap_runtime_state()

    with Session(engine) as session:
        assert session.get(Settings, 1) is not None
        usernames = session.exec(select(User.username)).all()
        assert "runtime_admin" in usernames


def test_alembic_upgrade_recovers_from_existing_schema_with_empty_version(monkeypatch, tmp_path):
    database_path = tmp_path / "existing-schema.sqlite3"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(_alembic_config(database_url), "head")
    engine = _sqlite_engine(database_path)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))

    command.upgrade(_alembic_config(database_url), "head")

    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    inspector = inspect(engine)

    assert revision == "add_performance_indexes"
    assert "agent_pair_codes" in inspector.get_table_names()
    quest_indexes = {index["name"] for index in inspector.get_indexes("quest_categories")}
    session_indexes = {index["name"] for index in inspector.get_indexes("sessions")}
    checklist_indexes = {index["name"] for index in inspector.get_indexes("checklist_items")}
    assert "uq_quest_categories_game_id_name" in quest_indexes
    assert "ix_sessions_started_at" in session_indexes
    assert "ix_checklist_items_sort_order" in checklist_indexes
