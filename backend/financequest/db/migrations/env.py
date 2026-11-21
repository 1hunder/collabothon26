from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

from financequest.config import get_settings
from financequest.db import models, models_campaign, models_personal  # noqa: F401  (register tables)

target_metadata = SQLModel.metadata


def _url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
