"""Personal quests: mock transactions, the daily quest and extra generated quests.

Responses carry the spending category only, never the company behind a quest.
"""

from datetime import date
from functools import partial
from typing import Any

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from financequest.api.deps import DbSession, SessionId
from financequest.personal import jobs
from financequest.personal import transactions as tx

router = APIRouter(tags=["personal"])


@router.get("/me/transactions")
def my_transactions(sid: SessionId) -> list[dict[str, str]]:
    today = date.today()
    return [t.as_dict(today) for t in tx.transactions_for(sid)]


@router.post("/quests/daily")
async def daily_quest(
    db: DbSession, sid: SessionId, regenerate: bool = False
) -> dict[str, Any]:
    """Called on login. Idempotent per day: returns today's quest (no generation when one is
    ready, even one built for another player). ``?regenerate=true`` forces a fresh generation
    that replaces today's quest for this player."""
    job = await run_in_threadpool(partial(jobs.daily_quest, db, sid, regenerate=regenerate))
    return jobs.public_view(job)


@router.post("/quests/generate", status_code=201)
async def generate_quest(db: DbSession, sid: SessionId) -> dict[str, Any]:
    job = await run_in_threadpool(jobs.generate_extra, db, sid)
    return jobs.public_view(job)


@router.get("/quests")
def list_quests(db: DbSession, sid: SessionId) -> list[dict[str, Any]]:
    return [jobs.public_view(j) for j in jobs.list_jobs(db, sid)]
