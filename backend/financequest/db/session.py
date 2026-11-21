from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from financequest.config import get_settings


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    return create_engine(
        s.database_url,
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        pool_pre_ping=True,
    )


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
