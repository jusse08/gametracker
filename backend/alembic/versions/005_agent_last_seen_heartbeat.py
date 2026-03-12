"""add users.agent_last_seen_at for live agent heartbeat checks

Revision ID: agent_last_seen_heartbeat
Revises: game_meta_quest_categories
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "agent_last_seen_heartbeat"
down_revision: Union[str, None] = "game_meta_quest_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("agent_last_seen_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("agent_last_seen_at")
