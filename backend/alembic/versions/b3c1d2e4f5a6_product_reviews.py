"""product reviews

Revision ID: b3c1d2e4f5a6
Revises: 7ea08bc13557
Create Date: 2026-11-17 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, Sequence[str], None] = '7ea08bc13557'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('product_reviews',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('product_id', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('external_id', sa.String(length=80), nullable=True),
    sa.Column('rating', sa.Float(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('author', sa.String(length=120), nullable=True),
    sa.Column('review_date', sa.String(length=10), nullable=True),
    sa.Column('verified', sa.Boolean(), nullable=True),
    sa.Column('variant', sa.String(length=200), nullable=True),
    sa.Column('helpful_votes', sa.Integer(), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('product_reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_reviews_product_id'), ['product_id'], unique=False)
        batch_op.create_index('ux_product_reviews_hash', ['product_id', 'content_hash'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('product_reviews', schema=None) as batch_op:
        batch_op.drop_index('ux_product_reviews_hash')
        batch_op.drop_index(batch_op.f('ix_product_reviews_product_id'))
    op.drop_table('product_reviews')
