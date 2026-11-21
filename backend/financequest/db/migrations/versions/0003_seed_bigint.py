"""scenario_secret.seed to BIGINT (crc32 + salt exceeds int4)

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('scenario_secret', 'seed', existing_type=sa.Integer(),
                    type_=sa.BigInteger(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column('scenario_secret', 'seed', existing_type=sa.BigInteger(),
                    type_=sa.Integer(), existing_nullable=True)
