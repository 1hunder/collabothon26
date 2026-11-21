"""reasoning and reasoning_source on campaign_trade and decision

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ('campaign_trade', 'decision'):
        op.add_column(table, sa.Column('reasoning', sa.Text(), nullable=True))
        op.add_column(table, sa.Column('reasoning_source', sa.String(), nullable=True))


def downgrade() -> None:
    for table in ('decision', 'campaign_trade'):
        op.drop_column(table, 'reasoning_source')
        op.drop_column(table, 'reasoning')
