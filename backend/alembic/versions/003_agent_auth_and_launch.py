"""add agent auth token and launch command fields

Revision ID: agent_auth_launch
Revises: add_users
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'agent_auth_launch'
down_revision: Union[str, None] = 'add_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_token', sa.String(), nullable=True))
        batch_op.create_index('ix_users_agent_token', ['agent_token'], unique=True)

    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('launch_path', sa.String(), nullable=True))

    with op.batch_alter_table('agent_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('launch_path', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('pending_launch_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('pending_launch_path', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('pending_launch_requested_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_launch_status', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('last_launch_error', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('last_launch_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('agent_config', schema=None) as batch_op:
        batch_op.drop_column('last_launch_at')
        batch_op.drop_column('last_launch_error')
        batch_op.drop_column('last_launch_status')
        batch_op.drop_column('pending_launch_requested_at')
        batch_op.drop_column('pending_launch_path')
        batch_op.drop_column('pending_launch_id')
        batch_op.drop_column('launch_path')

    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_column('launch_path')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_agent_token')
        batch_op.drop_column('agent_token')
