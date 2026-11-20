import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from financequest.config import get_settings

ADMIN_DEFAULT = "postgresql+psycopg://fq:fq@localhost:5432/financequest"


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    """Throwaway database on the configured Postgres, migrated with Alembic."""
    base = make_url(os.environ.get("DATABASE_URL", ADMIN_DEFAULT))
    name = f"fq_test_{uuid.uuid4().hex[:12]}"
    admin_dsn = base.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = base.set(database=name).render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    from financequest.db.session import get_engine

    get_engine.cache_clear()
    from financequest.cli import db_upgrade

    db_upgrade("head")
    try:
        yield url
    finally:
        get_engine().dispose()
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        os.environ["DATABASE_URL"] = str(base.render_as_string(hide_password=False))
        get_settings.cache_clear()
        get_engine.cache_clear()


@pytest.fixture
def client(test_db_url: str) -> Iterator[TestClient]:
    from financequest.api.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _isolated_db(request: pytest.FixtureRequest) -> Iterator[None]:
    """The throwaway database lives for the whole run; empty every table after each test that
    used it, so rows (scenarios, events, decisions...) never leak into the next test."""
    yield
    if "test_db_url" not in request.fixturenames:
        return
    from sqlalchemy import inspect, text

    from financequest.db.session import get_engine

    engine = get_engine()
    tables = [t for t in inspect(engine).get_table_names() if t != "alembic_version"]
    if tables:
        # a test may leave a session open mid-transaction (its read locks would block TRUNCATE)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE "
                    "datname = current_database() AND pid <> pg_backend_pid() "
                    "AND state LIKE 'idle in transaction%'"
                )
            )
        engine.dispose()
        names = ", ".join(f'"{t}"' for t in tables)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {names} CASCADE"))
