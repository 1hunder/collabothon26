"""campaign_trade + campaign_run.market_scene: investment decisions throughout the campaign

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'campaign_run',
        sa.Column('market_scene', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        'campaign_trade',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('beat', sa.String(), nullable=False),
        sa.Column('story_day', sa.Integer(), nullable=False),
        sa.Column('fill_day', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('shares', sa.String(), nullable=False),
        sa.Column('price', sa.String(), nullable=True),
        sa.Column('cash_after_cents', sa.Integer(), nullable=False),
        sa.Column('shares_after', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign_run.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_campaign_trade_campaign_id', 'campaign_trade', ['campaign_id'])


def downgrade() -> None:
    op.drop_index('ix_campaign_trade_campaign_id', table_name='campaign_trade')
    op.drop_table('campaign_trade')
    op.drop_column('campaign_run', 'market_scene')
