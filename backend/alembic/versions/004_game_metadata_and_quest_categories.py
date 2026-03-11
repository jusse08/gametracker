"""add game metadata fields and quest categories

Revision ID: game_meta_quest_categories
Revises: agent_auth_launch
Create Date: 2026-03-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'game_meta_quest_categories'
down_revision: Union[str, None] = 'agent_auth_launch'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('personal_rating', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('genres', sa.JSON(), nullable=False, server_default='[]'))

    op.create_table(
        'quest_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_id', 'name', name='uq_quest_categories_game_id_name'),
    )


def downgrade() -> None:
    op.drop_table('quest_categories')

    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_column('genres')
        batch_op.drop_column('personal_rating')
