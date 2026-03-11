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


def upgrade() -> None:
    # Create users table
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
    
    # Use batch mode for SQLite
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_games_user_id', ['user_id'])
        batch_op.create_foreign_key('fk_games_user_id_users', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    # Use batch mode for SQLite
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_constraint('fk_games_user_id_users', type_='foreignkey')
        batch_op.drop_index('ix_games_user_id')
        batch_op.drop_column('user_id')
    
    op.drop_table('users')
