"""add performance indexes

Revision ID: add_performance_indexes
Revises: drop_legacy_agent_token
Create Date: 2026-03-24 07:43:00.000000

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_performance_indexes"
down_revision: Union[str, None] = "drop_legacy_agent_token"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _has_index(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def upgrade() -> None:
    # Add index on sessions.started_at for ORDER BY performance
    if not _has_index("sessions", "ix_sessions_started_at"):
        op.create_index("ix_sessions_started_at", "sessions", ["started_at"], unique=False)

    # Add index on checklist_items.sort_order for ORDER BY performance
    if not _has_index("checklist_items", "ix_checklist_items_sort_order"):
        op.create_index(
            "ix_checklist_items_sort_order", "checklist_items", ["sort_order"], unique=False
        )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_checklist_items_sort_order", table_name="checklist_items")
    op.drop_index("ix_sessions_started_at", table_name="sessions")
