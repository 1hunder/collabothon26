"""veteran_memory, veteran_profile, veteran_message, veteran_lesson: the Tavern's Veteran

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _ts() -> sa.Column:
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        'veteran_memory',
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('hero_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('verdicts', JSONB, nullable=False),
        sa.Column('built_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign_run.id']),
        sa.ForeignKeyConstraint(['hero_id'], ['hero.id']),
        sa.PrimaryKeyConstraint('campaign_id'),
    )
    op.create_index('ix_veteran_memory_hero_id', 'veteran_memory', ['hero_id'])
    op.create_table(
        'veteran_profile',
        sa.Column('hero_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', JSONB, nullable=False),
        sa.Column('campaign_ids', JSONB, nullable=False),
        sa.Column('built_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['hero_id'], ['hero.id']),
        sa.PrimaryKeyConstraint('hero_id'),
    )
    op.create_table(
        'veteran_message',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hero_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('topic', sa.String(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('payload', JSONB, nullable=True),
        sa.Column('client_msg_id', sa.String(), nullable=True),
        _ts(),
        sa.ForeignKeyConstraint(['hero_id'], ['hero.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_msg_id'),
    )
    op.create_index('ix_veteran_message_hero_id', 'veteran_message', ['hero_id'])
    op.create_table(
        'veteran_lesson',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hero_id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        _ts(),
        sa.ForeignKeyConstraint(['hero_id'], ['hero.id']),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign_run.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_veteran_lesson_hero_id', 'veteran_lesson', ['hero_id'])


def downgrade() -> None:
    op.drop_index('ix_veteran_lesson_hero_id', table_name='veteran_lesson')
    op.drop_table('veteran_lesson')
    op.drop_index('ix_veteran_message_hero_id', table_name='veteran_message')
    op.drop_table('veteran_message')
    op.drop_table('veteran_profile')
    op.drop_index('ix_veteran_memory_hero_id', table_name='veteran_memory')
    op.drop_table('veteran_memory')
