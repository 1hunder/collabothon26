"""Personal quest jobs: one job per company, each on its own thread with its own agent graph.

Nothing is generated automatically. A job starts only when the player asks for one
(``generate_personal``, from the Quest Board): with a theme they typed (matched to a category
and company by ``board.match_theme``) or, with none, the category they spend the most on.
- At most ``generation_concurrency`` jobs run at the same time; the rest wait in ``queued``.

Only the category label, status, a player-safe step label and (when ready) the scenario id ever
leave this module through ``public_view``. Company and ticker are server-only.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import traceback
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from financequest.api.errors import ApiError
from financequest.config import get_settings
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


def quest_prefix(job_id: uuid.UUID) -> str:
    """Storage key prefix of a quest's documents (case.md, prices.csv, manifest.json)."""
    return f"quests/{job_id}"


def run_job(job_id: uuid.UUID) -> None:
    """Blocking: runs one company's agent graph. Called on its own thread by ``start_job``."""
    from financequest.personal.agent import QuestFailed, build_quest_graph

    with Session(get_engine()) as s:
        job = s.get(GenerationJob, job_id)
        if job is None:
            return
        cat = tx.CATEGORIES.get(job.category)
        company = next((c for c in cat.companies if c.ticker == job.ticker), None) if cat else None
        prefix = job.pack_dir or quest_prefix(job_id)
    if cat is None or company is None:
        _update(job_id, status="failed", step="Failed", error="unknown company")
        return
    journal: list[dict[str, Any]] = []
    work = Path(tempfile.mkdtemp(prefix="fq-quest-"))
    window: Any = None
    with _semaphore():
        _update(job_id, status="running", step="Starting")
        log.info("quest job %s: generating %s", job_id, company.ticker)

        def progress(label: str, _extra: dict[str, Any]) -> None:
            log.info("quest job %s: %s", job_id, label)
            _update(job_id, step=label)

        graph = build_quest_graph(company, cat, work, f"PQ-{str(job_id)[:8]}", progress,
                                  journal=journal, storage_prefix=prefix)  # fmt: skip
        try:
            final = graph.invoke({}, {"recursion_limit": 60})
            window = final.get("window")
            sid = final.get("scenario_id")
            if final.get("outcome") == "approved" and sid:
                _merge_detail(job_id, {"log": journal, "window": window})
                _update(job_id, status="ready", step="Ready", attempts=final.get("attempt", 1),
                        scenario_id=uuid.UUID(str(sid)))  # fmt: skip
                log.info("quest job %s: ready", job_id)
            else:
                raise QuestFailed("the quest was not approved")
        except QuestFailed as exc:
            log.warning("quest job %s failed: %s", job_id, exc)
            _merge_detail(job_id, {"log": journal, "window": window})
            _update(job_id, status="failed", step="Failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - a job failure must never kill the API
            log.exception("quest job %s crashed", job_id)
            _merge_detail(job_id, {"log": journal, "window": window})
            _update(job_id, status="failed", step="Failed",
                    error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")  # fmt: skip  # noqa: E501
        finally:
            shutil.rmtree(work, ignore_errors=True)


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


def _create_job(db: Session, sid: uuid.UUID, kind: str, today: date, cat: tx.Category,
                comp: tx.Company, **fields: Any) -> GenerationJob:
    job = GenerationJob(
        session_id=sid, kind=kind, quest_date=today, category=cat.key,
        category_label=cat.label, company=comp.name, ticker=comp.ticker, **fields,
    )  # fmt: skip
    db.add(job)
    db.flush()
    job.pack_dir = quest_prefix(job.id) if not job.pack_dir else job.pack_dir
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _new_job(db: Session, sid: uuid.UUID, kind: str, today: date) -> GenerationJob:
    """A queued job for the next company in the player's spending order (no thread started)."""
    cat, comp = _pick(db, sid, today)
    return _create_job(db, sid, kind, today, cat, comp)


def _pick(db: Session, sid: uuid.UUID, today: date) -> tuple[tx.Category, tx.Company]:
    jobs = _jobs(db, sid)
    used = {j.ticker for j in jobs if j.status != "failed"}
    queue = tx.candidate_queue(tx.transactions_for(sid), used, today.toordinal() + len(jobs))
    if not queue:
        raise ApiError(409, "no_companies_left", "No more companies to build quests from")
    return queue[0]


def generate_personal(
    db: Session, sid: uuid.UUID, theme: str | None = None, today: date | None = None
) -> GenerationJob:
    """Start a personal quest. The theme (if any) is recorded on the job; it steers the choice of
    category and company, never the real name shown to the player."""
    from financequest.personal import board

    today = today or date.today()
    theme = (theme or "").strip()[:120]
    used = {j.ticker for j in _jobs(db, sid) if j.status != "failed"}
    matched = board.match_theme(theme) if theme else None
    cat = matched[0] if matched else board.suggestion_category(sid)
    comp = matched[1] if matched and matched[1] and matched[1].ticker not in used else None
    if comp is None:
        comp = next((c for c in cat.companies if c.ticker not in used), None)
    if comp is None:  # the category is used up: fall back to any unused company
        cat, comp = _pick(db, sid, today)
    job = _create_job(db, sid, "personal", today, cat, comp,
                      detail={"theme": theme or None, "matched": bool(matched)})  # fmt: skip
    start_job(job.id)
    return job


def list_jobs(db: Session, sid: uuid.UUID) -> list[GenerationJob]:
    return _jobs(db, sid)


def owns_scenario(db: Session, sid: uuid.UUID, scenario_id: uuid.UUID) -> bool:
    """Generated quests are personal: a player may start one only from their own job list."""
    stmt = select(GenerationJob).where(GenerationJob.scenario_id == scenario_id)
    owners = list(db.exec(stmt))
    return not owners or any(j.session_id == sid for j in owners)
