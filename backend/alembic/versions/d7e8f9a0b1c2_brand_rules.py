"""brand rules (claims + visual rules used by the image planner)

Revision ID: d7e8f9a0b1c2
Revises: c5d3e6f7a8b9
Create Date: 2026-11-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c5d3e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('brands') as batch:
        batch.add_column(sa.Column('rules', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('brands') as batch:
        batch.drop_column('rules')
