"""competitor listings

Revision ID: c5d3e6f7a8b9
Revises: b3c1d2e4f5a6
Create Date: 2026-11-18 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d3e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c1d2e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('competitor_listings',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('product_id', sa.String(length=32), nullable=False),
    sa.Column('market', sa.String(length=20), nullable=False),
    sa.Column('market_id', sa.String(length=64), nullable=False),
    sa.Column('url', sa.String(length=1000), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('brand', sa.String(length=200), nullable=True),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=True),
    sa.Column('rating', sa.Float(), nullable=True),
    sa.Column('review_count', sa.Integer(), nullable=True),
    sa.Column('rank', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=True),
    sa.Column('bsr_rank', sa.Integer(), nullable=True),
    sa.Column('bsr', sa.String(length=300), nullable=True),
    sa.Column('category', sa.String(length=200), nullable=True),
    sa.Column('monthly_bought', sa.Integer(), nullable=True),
    sa.Column('sponsored', sa.Boolean(), nullable=True),
    sa.Column('badges', sa.JSON(), nullable=False),
    sa.Column('bullets', sa.JSON(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('specifications', sa.JSON(), nullable=False),
    sa.Column('image_count', sa.Integer(), nullable=True),
    sa.Column('has_video', sa.Boolean(), nullable=True),
    sa.Column('has_aplus', sa.Boolean(), nullable=True),
    sa.Column('image_url', sa.String(length=1000), nullable=True),
    sa.Column('reviews', sa.JSON(), nullable=False),
    sa.Column('sources', sa.JSON(), nullable=False),
    sa.Column('included', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('competitor_listings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competitor_listings_product_id'), ['product_id'], unique=False)
        batch_op.create_index('ux_competitor_item', ['product_id', 'market', 'market_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('competitor_listings', schema=None) as batch_op:
        batch_op.drop_index('ux_competitor_item')
        batch_op.drop_index(batch_op.f('ix_competitor_listings_product_id'))
    op.drop_table('competitor_listings')
