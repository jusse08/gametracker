"""add agent pairing codes and device sessions

Revision ID: agent_pairing_devices
Revises: agent_last_seen_heartbeat
Create Date: 2026-03-12 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "agent_pairing_devices"
down_revision: Union[str, None] = "agent_last_seen_heartbeat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    if not _has_table("agent_pair_codes"):
        op.create_table(
            "agent_pair_codes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("code_hash", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code_hash", name="uq_agent_pair_codes_code_hash"),
        )
    if not _has_index("agent_pair_codes", "ix_agent_pair_codes_user_id"):
        op.create_index("ix_agent_pair_codes_user_id", "agent_pair_codes", ["user_id"], unique=False)
    if not _has_index("agent_pair_codes", "ix_agent_pair_codes_expires_at"):
        op.create_index("ix_agent_pair_codes_expires_at", "agent_pair_codes", ["expires_at"], unique=False)

    if not _has_table("agent_devices"):
        op.create_table(
            "agent_devices",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("device_name", sa.String(length=120), nullable=False),
            sa.Column("refresh_token_hash", sa.String(), nullable=False),
            sa.Column("refresh_expires_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("device_id", name="uq_agent_devices_device_id"),
        )
    if not _has_index("agent_devices", "ix_agent_devices_user_id"):
        op.create_index("ix_agent_devices_user_id", "agent_devices", ["user_id"], unique=False)
    if not _has_index("agent_devices", "ix_agent_devices_refresh_token_hash"):
        op.create_index("ix_agent_devices_refresh_token_hash", "agent_devices", ["refresh_token_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_devices_refresh_token_hash", table_name="agent_devices")
    op.drop_index("ix_agent_devices_user_id", table_name="agent_devices")
    op.drop_table("agent_devices")

    op.drop_index("ix_agent_pair_codes_expires_at", table_name="agent_pair_codes")
    op.drop_index("ix_agent_pair_codes_user_id", table_name="agent_pair_codes")
    op.drop_table("agent_pair_codes")
