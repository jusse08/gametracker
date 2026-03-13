"""add users table and user_id to games

Revision ID: add_users
Revises: initial
Create Date: 2024-01-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'add_users'
down_revision: Union[str, None] = 'initial'
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


def _has_foreign_key(table_name: str, constrained_columns: list[str], referred_table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys(table_name)
    return any(
        foreign_key.get("referred_table") == referred_table
        and foreign_key.get("constrained_columns") == constrained_columns
        for foreign_key in foreign_keys
    )


def upgrade() -> None:
    # Create users table
    if not _has_table('users'):
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('username', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
            sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('steam_api_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('steam_profile_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('steam_user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('username')
        )

    needs_user_id = not _has_column('games', 'user_id')
    needs_user_id_index = not _has_index('games', 'ix_games_user_id')
    needs_user_fk = _has_column('games', 'user_id') and not _has_foreign_key('games', ['user_id'], 'users')
    if needs_user_id or needs_user_id_index or needs_user_fk:
        with op.batch_alter_table('games', schema=None) as batch_op:
            if needs_user_id:
                batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            if not _has_index('games', 'ix_games_user_id'):
                batch_op.create_index('ix_games_user_id', ['user_id'])
            if not _has_foreign_key('games', ['user_id'], 'users'):
                batch_op.create_foreign_key('fk_games_user_id_users', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    # Use batch mode for SQLite
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_constraint('fk_games_user_id_users', type_='foreignkey')
        batch_op.drop_index('ix_games_user_id')
        batch_op.drop_column('user_id')
    
    op.drop_table('users')
