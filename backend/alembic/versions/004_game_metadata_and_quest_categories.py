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


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    with op.batch_alter_table('games', schema=None) as batch_op:
        if not _has_column('games', 'personal_rating'):
            batch_op.add_column(sa.Column('personal_rating', sa.Integer(), nullable=True))
        if not _has_column('games', 'genres'):
            batch_op.add_column(sa.Column('genres', sa.JSON(), nullable=False, server_default='[]'))

    if not _has_table('quest_categories'):
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
    elif not _has_index('quest_categories', 'uq_quest_categories_game_id_name'):
        op.create_index(
            'uq_quest_categories_game_id_name',
            'quest_categories',
            ['game_id', 'name'],
            unique=True,
        )


def downgrade() -> None:
    op.drop_table('quest_categories')

    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_column('genres')
        batch_op.drop_column('personal_rating')
