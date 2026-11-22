"""Personal quests: mock transactions and the Quest Board (curated + personal quests).

Responses carry disguised text only: never the company, ticker or a real year.
"""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from financequest.api.deps import DbSession, SessionId
from financequest.api.errors import ApiError
from financequest.personal import board, jobs
from financequest.personal import transactions as tx

router = APIRouter(tags=["personal"])


class GenerateIn(BaseModel):
    theme: str | None = Field(default=None, max_length=200)


@router.get("/me/transactions")
def my_transactions(sid: SessionId) -> list[dict[str, str]]:
    today = date.today()
    return [t.as_dict(today) for t in tx.transactions_for(sid)]


@router.get("/quests/board")
def quest_board(db: DbSession, sid: SessionId) -> dict[str, Any]:
    return board.board(db, sid)


@router.get("/quests/board/{quest_id}")
def quest_detail(quest_id: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    out = board.detail(db, sid, quest_id)
    if out is None:
        raise ApiError(404, "quest_not_found", "Quest not found")
    return out


@router.post("/quests/generate", status_code=201)
async def generate_quest(
    db: DbSession, sid: SessionId, body: GenerateIn | None = None
) -> dict[str, Any]:
    job = await run_in_threadpool(jobs.generate_personal, db, sid, body.theme if body else None)
    return await run_in_threadpool(
        lambda: board.card_for_job(db, job, budget=board.budget_gp(db, sid), runs={})
    )


@router.post("/quests/daily", deprecated=True)
def daily_quest() -> None:
    """Deprecated: there is no daily quest. Nothing is generated; use the Quest Board."""
    raise ApiError(410, "daily_quests_removed", "Daily quests are gone: use GET /quests/board")


@router.get("/quests")
def list_quests(db: DbSession, sid: SessionId) -> list[dict[str, Any]]:
    return [jobs.public_view(j) for j in jobs.list_jobs(db, sid)]
