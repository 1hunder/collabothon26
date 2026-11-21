"""generation_job: personal quests generated per company from the player's transactions

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'generation_job',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('quest_date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('category_label', sa.String(), nullable=False),
        sa.Column('company', sa.String(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('step', sa.String(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.Uuid(), nullable=True),
        sa.Column('pack_dir', sa.String(), nullable=True),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.ForeignKeyConstraint(['scenario_id'], ['scenario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_generation_job_session_id', 'generation_job', ['session_id'])


def downgrade() -> None:
    op.drop_index('ix_generation_job_session_id', table_name='generation_job')
    op.drop_table('generation_job')
