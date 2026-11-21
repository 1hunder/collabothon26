"""Personal quest jobs: one job per company, each on its own thread with its own agent graph.

- ``daily_quest`` runs on login: today's quest exists -> return it; demo mode -> assign the
  pre-created scenario at once; otherwise pick the next company from the player's spending and
  start generating it.
- ``generate_extra`` starts another company on request ("Generate another quest").
- At most ``generation_concurrency`` jobs run at the same time; the rest wait in ``queued``.

Only the category label, status, a player-safe step label and (when ready) the scenario id ever
leave this module through ``public_view``. Company and ticker are server-only.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from financequest.api.errors import ApiError
from financequest.config import get_settings
from financequest.db.models import Scenario, ScenarioSecret
from financequest.db.models_personal import GenerationJob
from financequest.db.session import get_engine
from financequest.personal import transactions as tx

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
_slots_lock = threading.Lock()
_slots: threading.BoundedSemaphore | None = None


def _semaphore() -> threading.BoundedSemaphore:
    global _slots
    with _slots_lock:
        if _slots is None:
            _slots = threading.BoundedSemaphore(max(1, get_settings().generation_concurrency))
        return _slots


def public_view(job: GenerationJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "quest_date": job.quest_date.isoformat(),
        "category": job.category,
        "category_label": job.category_label,
        "status": job.status,
        "step": job.step,
        "scenario_id": str(job.scenario_id) if job.status == "ready" and job.scenario_id else None,
        "created_at": job.created_at.isoformat(),
    }


def _update(job_id: uuid.UUID, **fields: Any) -> None:
    with Session(get_engine()) as s:
        job = s.get(GenerationJob, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = datetime.now(UTC)
        s.add(job)
        s.commit()


def _merge_detail(job_id: uuid.UUID, extra: dict[str, Any]) -> None:
    with Session(get_engine()) as s:
        job = s.get(GenerationJob, job_id)
        if job is None:
            return
        job.detail = {**(job.detail or {}), **extra}
        s.add(job)
        s.commit()


# ---- running ------------------------------------------------------------------------------------


def run_job(job_id: uuid.UUID) -> None:
    """Blocking: runs one company's agent graph. Called on its own thread by ``start_job``."""
    from financequest.personal.agent import QuestFailed, build_quest_graph

    with Session(get_engine()) as s:
        job = s.get(GenerationJob, job_id)
        if job is None:
            return
        cat = tx.CATEGORIES.get(job.category)
        company = next((c for c in cat.companies if c.ticker == job.ticker), None) if cat else None
        pack_dir = Path(job.pack_dir or "")
    if cat is None or company is None:
        _update(job_id, status="failed", step="Failed", error="unknown company")
        return
    with _semaphore():
        _update(job_id, status="running", step="Starting")

        def progress(label: str, _extra: dict[str, Any]) -> None:
            _update(job_id, step=label)

        graph = build_quest_graph(company, cat, pack_dir, f"PQ-{str(job_id)[:8]}", progress)
        try:
            final = graph.invoke({}, {"recursion_limit": 60})
        except QuestFailed as exc:
            _update(job_id, status="failed", step="Failed", error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - a job failure must never kill the API
            log.exception("quest job %s crashed", job_id)
            _update(job_id, status="failed", step="Failed",
                    error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")  # fmt: skip  # noqa: E501
            return
        _merge_detail(job_id, {"log": final.get("log", []), "window": final.get("window")})
        sid = final.get("scenario_id")
        if final.get("outcome") == "approved" and sid:
            _update(job_id, status="ready", step="Ready", attempts=final.get("attempt", 1),
                    scenario_id=uuid.UUID(str(sid)))  # fmt: skip
        else:
            _update(job_id, status="rejected", step="Too recognisable, skipped",
                    attempts=final.get("attempt", 1))  # fmt: skip


def start_job(job_id: uuid.UUID) -> None:
    threading.Thread(target=run_job, args=(job_id,), name=f"quest-{job_id}", daemon=True).start()


def recover_interrupted() -> int:
    """Jobs left queued or running by a restart can never finish: mark them failed."""
    try:
        with Session(get_engine()) as s:
            jobs = list(s.exec(select(GenerationJob).where(GenerationJob.status.in_(ACTIVE))))  # type: ignore[attr-defined]
            for j in jobs:
                j.status, j.step, j.error = "failed", "Failed", "interrupted by a restart"
                s.add(j)
            s.commit()
            return len(jobs)
    except Exception:  # noqa: BLE001 - never block startup (e.g. table not migrated yet)
        log.warning("could not recover quest jobs", exc_info=True)
        return 0


# ---- creating jobs ------------------------------------------------------------------------------


def _jobs(db: Session, sid: uuid.UUID) -> list[GenerationJob]:
    stmt = select(GenerationJob).where(GenerationJob.session_id == sid)
    return sorted(db.exec(stmt), key=lambda j: j.created_at, reverse=True)


def _new_job(db: Session, sid: uuid.UUID, kind: str, today: date) -> GenerationJob:
    jobs = _jobs(db, sid)
    used = {j.ticker for j in jobs if j.status != "failed"}
    queue = tx.candidate_queue(tx.transactions_for(sid), used, today.toordinal() + len(jobs))
    if not queue:
        raise ApiError(409, "no_companies_left", "No more companies to build quests from")
    cat, comp = queue[0]
    job = GenerationJob(
        session_id=sid, kind=kind, quest_date=today, category=cat.key,
        category_label=cat.label, company=comp.name, ticker=comp.ticker,
    )  # fmt: skip
    db.add(job)
    db.flush()
    job.pack_dir = str((Path(get_settings().data_dir) / "quests" / str(job.id)).resolve())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _demo_scenario(db: Session) -> Scenario | None:
    s = get_settings()
    if s.demo_scenario_id:
        try:
            sc = db.get(Scenario, uuid.UUID(s.demo_scenario_id))
        except ValueError:
            sc = None
        if sc is not None and sc.status == "playable":
            return sc
    ready = db.exec(
        select(GenerationJob).where(GenerationJob.status == "ready")
    ).all()  # newest generated quest of anyone
    for j in sorted(ready, key=lambda j: j.created_at, reverse=True):
        sc = db.get(Scenario, j.scenario_id) if j.scenario_id else None
        if sc is not None and sc.status == "playable":
            return sc
    packs = db.exec(
        select(Scenario).where(Scenario.status == "playable", Scenario.source == "reference_pack")
    ).all()
    return next(iter(packs), None)


def _category_for(ticker: str | None) -> tx.Category | None:
    for cat in tx.CATEGORIES.values():
        if any(c.ticker == ticker for c in cat.companies):
            return cat
    return None


def daily_quest(db: Session, sid: uuid.UUID, today: date | None = None) -> GenerationJob:
    today = today or date.today()
    for j in _jobs(db, sid):
        if j.kind == "daily" and j.quest_date == today and j.status not in ("failed", "rejected"):
            return j
    if get_settings().demo_mode:
        sc = _demo_scenario(db)
        if sc is not None:
            sec = db.get(ScenarioSecret, sc.id)
            cat = _category_for(sec.ticker if sec else None)
            top = tx.spending_by_category(tx.transactions_for(sid))
            cat = cat or (tx.CATEGORIES[top[0][0]] if top else None)
            job = GenerationJob(
                session_id=sid, kind="daily", quest_date=today,
                category=cat.key if cat else "pick", category_label=cat.label if cat
                else "Today's pick", company=sec.real_name if sec else "", ticker=(sec.ticker or "")
                if sec else "", status="ready", step="Ready", scenario_id=sc.id,
                detail={"demo": True},
            )  # fmt: skip
            db.add(job)
            db.commit()
            db.refresh(job)
            return job
    job = _new_job(db, sid, "daily", today)
    start_job(job.id)
    return job


def generate_extra(db: Session, sid: uuid.UUID, today: date | None = None) -> GenerationJob:
    job = _new_job(db, sid, "extra", today or date.today())
    start_job(job.id)
    return job


def list_jobs(db: Session, sid: uuid.UUID) -> list[GenerationJob]:
    return _jobs(db, sid)


def owns_scenario(db: Session, sid: uuid.UUID, scenario_id: uuid.UUID) -> bool:
    """Generated quests are personal: a player may start one only from their own job list."""
    stmt = select(GenerationJob).where(GenerationJob.scenario_id == scenario_id)
    owners = list(db.exec(stmt))
    return not owners or any(j.session_id == sid for j in owners)
