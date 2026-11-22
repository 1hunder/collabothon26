import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from financequest.api import errors
from financequest.api.routers import (
    campaigns,
    health,
    hero,
    media,
    personal,
    scenarios,
    session,
    veteran,
)
from financequest.api.sse import VoiceHeaderMiddleware
from financequest.config import get_settings


def configure_logging(level: str) -> None:
    """Uvicorn only wires its own loggers: without this, info logs from ``financequest.*`` (quest
    job progress, scan verdicts) never reach the output."""
    lvl = getattr(logging, level.upper(), logging.INFO)
    pkg = logging.getLogger("financequest")
    pkg.setLevel(lvl)
    if not any(getattr(h, "_fq", False) for h in pkg.handlers):
        h = logging.StreamHandler()
        h._fq = True  # type: ignore[attr-defined]
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        pkg.addHandler(h)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from financequest.media.art import start_rescan
    from financequest.personal.jobs import recover_interrupted

    start_rescan()  # pending art jobs left by a restart; never blocks or fails startup
    recover_interrupted()  # quest jobs cut off by a restart can never finish
    yield


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level)
    app = FastAPI(title="FinanceQuest API", lifespan=lifespan)
    app.add_middleware(VoiceHeaderMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in s.cors_origin_list if "*" not in o],
        allow_origin_regex=s.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(session.router)
    app.include_router(health.router)
    app.include_router(media.router)
    app.include_router(hero.router)
    app.include_router(campaigns.router)
    app.include_router(scenarios.router)
    app.include_router(personal.router)
    app.include_router(veteran.router)
    errors.install(app)
    return app


app = create_app()
