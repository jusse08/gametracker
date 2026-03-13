import argparse
import sys
from pathlib import Path
from typing import Sequence

from alembic import command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import engine
from app.core.migrations import build_alembic_config, ensure_database_schema_current


def upgrade() -> None:
    command.upgrade(build_alembic_config(str(engine.url)), "head")


def check_current() -> None:
    ensure_database_schema_current(engine)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GameTracker database management")
    parser.add_argument(
        "command",
        choices=["upgrade", "check-current"],
        help="Database operation to run",
    )
    args = parser.parse_args(argv)

    if args.command == "upgrade":
        upgrade()
        print("Database migrated to Alembic head.")
        return 0

    check_current()
    print("Database schema is at Alembic head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
