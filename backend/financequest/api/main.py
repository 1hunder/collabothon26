from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from financequest.api import errors
from financequest.api.routers import campaigns, health, hero, media, scenarios, session
from financequest.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from financequest.media.art import start_rescan

    start_rescan()  # pending art jobs left by a restart; never blocks or fails startup
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="FinanceQuest API", lifespan=lifespan)
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
    errors.install(app)
    return app


app = create_app()
