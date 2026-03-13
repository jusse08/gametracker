"""drop legacy users.agent_token

Revision ID: drop_legacy_agent_token
Revises: agent_pairing_devices
Create Date: 2026-03-13 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "drop_legacy_agent_token"
down_revision: Union[str, None] = "agent_pairing_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        if _has_index("users", "ix_users_agent_token"):
            batch_op.drop_index("ix_users_agent_token")
        if _has_column("users", "agent_token"):
            batch_op.drop_column("agent_token")


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        if not _has_column("users", "agent_token"):
            batch_op.add_column(sa.Column("agent_token", sa.String(), nullable=True))
        if not _has_index("users", "ix_users_agent_token"):
            batch_op.create_index("ix_users_agent_token", ["agent_token"], unique=True)
