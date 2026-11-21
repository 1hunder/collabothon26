"""HP damage on campaign_run; generated locations with an NPC on location

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('campaign_run', sa.Column('hp_lost', sa.Integer(), nullable=False, server_default='0'))
    op.add_column(
        'campaign_run',
        sa.Column('loss_unapplied_cents', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'location', sa.Column('generated', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column('location', sa.Column('npc', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('location', 'npc')
    op.drop_column('location', 'generated')
    op.drop_column('campaign_run', 'loss_unapplied_cents')
    op.drop_column('campaign_run', 'hp_lost')
