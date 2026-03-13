from pathlib import Path
from typing import Tuple

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

MIGRATION_COMMAND = "python scripts/manage_db.py upgrade"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(_backend_root() / "alembic.ini"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def get_schema_heads(engine: Engine) -> Tuple[tuple[str, ...], tuple[str, ...]]:
    alembic_config = build_alembic_config(str(engine.url))
    directory = ScriptDirectory.from_config(alembic_config)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        current_heads = tuple(context.get_current_heads())
    return current_heads, tuple(directory.get_heads())


def ensure_database_schema_current(engine: Engine) -> None:
    current_heads, expected_heads = get_schema_heads(engine)
    if set(current_heads) == set(expected_heads):
        return

    current_display = ", ".join(current_heads) if current_heads else "base"
    expected_display = ", ".join(expected_heads) if expected_heads else "head"
    raise RuntimeError(
        "Database schema is not up to date. "
        f"Current revision(s): {current_display}. "
        f"Expected revision(s): {expected_display}. "
        f"Run '{MIGRATION_COMMAND}' before starting the app."
    )
