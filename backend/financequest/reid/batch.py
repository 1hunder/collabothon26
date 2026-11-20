"""Batch runner: the gate over many cases with plain asyncio.

- A semaphore of ``CHECK_CONCURRENCY`` caps the cases running at once.
- Each finished case is committed immediately (attempts, guesses, case_result, scenario), so a
  re-run with the same run id skips every case that already has a result (resumable).
- LangGraph checkpoints are never the source of truth; the database is.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from financequest.config import Settings, get_settings
from financequest.db.models import (
    Attempt,
    CaseResult,
    CheckRun,
    Guess,
    PriceSeries,
    Scenario,
    ScenarioSecret,
    SourceBeat,
    SourceCase,
)
from financequest.engine.disguise import AmountFact, NumberPlan
from financequest.llm import DefaultFakeNodeLLM, LLMResult, NodeLLM, get_node_llm
from financequest.pipeline.intake import parse_real_date
from financequest.pipeline.prices import load_frame, price_on_or_before
from financequest.reid import rules
from financequest.reid.graph import _real_terms, run_gate
from financequest.reid.schemas import AttemptRecord, CaseAmount, CaseBeat, GateCase, GuessRecord

log = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
GateRunner = Callable[[GateCase, int, NodeLLM], dict[str, Any]]
LLMFactory = Callable[[SourceCase], NodeLLM]
CaseDone = Callable[[str, str], None]  # case_id, final_status


def default_gate_runner(case: GateCase, salt: int, llm: NodeLLM) -> dict[str, Any]:
    return dict(run_gate(case, run_salt=salt, llm=llm))


# ---- dry-run fake --------------------------------------------------------
class DryRunFakeLLM:
    """``--dry-run-fake-llm`` gate model: deterministic text, and guessers that name the real
    company when ``recognise`` is set (used for high-fame cases, so they end Rejected)."""

    def __init__(self, recognise: str | None = None) -> None:
        self._recognise = recognise
        self._default = DefaultFakeNodeLLM()

    def run(self, node: str, messages: Any, **kw: Any) -> LLMResult:
        if self._recognise and node in ("guess_memory", "guess_web"):
            from financequest.reid.schemas import CompanyGuess, GuesserReport

            parsed = GuesserReport(
                top3=[CompanyGuess(company=self._recognise, confidence=90)],
                start_confidence=5,
                readability=4,
            )
            return LLMResult(
                parsed=parsed,
                content=[{"type": "text", "text": parsed.model_dump_json()}],
                usage={"input_tokens": 1, "output_tokens": 1},
            )
        return self._default.run(node, messages, **kw)


def dry_run_llm_factory(case: SourceCase) -> NodeLLM:
    return DryRunFakeLLM(case.company if case.fame == "high" else None)


def live_llm_factory(case: SourceCase) -> NodeLLM:
    return get_node_llm()


# ---- case -> GateCase ------------------------------------------------------
def build_gate_case(session: Session, case: SourceCase) -> GateCase | str:
    """The server-only gate input, or the skip reason when the case lacks usable prices."""
    beats = sorted(
        session.exec(select(SourceBeat).where(SourceBeat.case_id == case.id)).all(),
        key=lambda b: b.idx,
    )
    ps = session.exec(select(PriceSeries).where(PriceSeries.case_id == case.id)).first()
    if not ps or not ps.cache_ref or not Path(ps.cache_ref).exists():
        return rules.SKIP_INCOMPLETE
    frame = load_frame(Path(ps.cache_ref))
    series = [(date.fromisoformat(d).toordinal(), float(c)) for d, c in zip(
        frame["date"], frame["close"], strict=True)]  # fmt: skip
    gate_beats: list[CaseBeat] = []
    amounts: list[CaseAmount] = []
    dates: list[date] = []
    for b in beats:
        day = parse_real_date(b.real_date or "")
        hit = price_on_or_before(frame, day) if day else None
        if hit is None:
            return rules.SKIP_INCOMPLETE
        snapped = date.fromisoformat(hit[0])
        payload = b.facts or {}
        gate_beats.append(
            CaseBeat(
                real_day=snapped.toordinal(),
                headline=b.headline or "",
                facts=list(payload.get("facts", [])),
            )
        )
        amounts += [
            CaseAmount(
                token=a["token"],
                family=a["family"],
                value=Decimal(a["value"]),
                is_ratio=a["is_ratio"],
            )
            for a in payload.get("amounts", [])
        ]
        dates.append(snapped)
    days = [b.real_day for b in gate_beats]
    if any(y <= x for x, y in zip(days, days[1:], strict=False)):
        return rules.SKIP_INCOMPLETE
    names = case.known_names or {}
    return GateCase(
        case_id=case.id,
        company=case.company,
        ticker=case.ticker or "",
        parent=names.get("parent", ""),
        subsidiaries=list(names.get("subsidiaries", [])),
        former_names=list(names.get("former_names", [])),
        aliases=list(names.get("aliases", [])),
        identifying_terms=list(case.identifying_terms or []),
        executives=list(names.get("executives", [])),
        industry=names.get("industry", ""),
        lesson=case.lesson or "",
        real_start=(dates[0].year, dates[0].month),
        beats=gate_beats,
        series=series,
        amounts=amounts,
    )


def reevaluate_skip(session: Session, case: SourceCase) -> str | None:
    """Recompute the skip rules from current data (lesson, terms, beat count, prices) and update
    ``status`` / ``skip_reason`` so a stale ``skipped`` never outlives the missing data.
    Returns the current skip reason, or None when the case is checkable. Does not commit."""
    n_beats = len(session.exec(select(SourceBeat).where(SourceBeat.case_id == case.id)).all())
    facts = rules.CaseFacts(
        lesson=case.lesson or "",
        identifying_terms=tuple(case.identifying_terms or []),
        beat_prices=tuple(0.0 for _ in range(n_beats)),
        market_cap_eur=case.market_cap_eur,
        is_us_listed=(case.known_names or {}).get("is_us_listed"),
        country=case.country or "",
        story_year=case.story_year,
    )
    reason = rules.skip_reason(facts)
    if reason is None:
        built = build_gate_case(session, case)
        reason = built if isinstance(built, str) else None
    if reason is not None:
        case.status, case.skip_reason = "skipped", reason
    else:
        case.status = "untagged" if rules.is_untagged(facts) else "ok"
        case.skip_reason = None
    session.add(case)
    return reason


# ---- telemetry -----------------------------------------------------------
TELEMETRY_KEYS = (
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
    "web_searches", "retries",
)  # fmt: skip


def add_telemetry(total: dict[str, Any] | None, calls: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out = dict(total or {})
    out["calls"] = out.get("calls", 0) + len(calls)
    out["errors"] = out.get("errors", 0) + sum(c.get("outcome") != "ok" for c in calls)
    out["latency_s"] = round(
        out.get("latency_s", 0.0) + sum(c.get("latency_s", 0) for c in calls), 3
    )
    for k in TELEMETRY_KEYS:
        out[k] = out.get(k, 0) + sum(int(c.get(k) or 0) for c in calls)
    return out


# ---- persistence ---------------------------------------------------------
def _guess_row(attempt_id: int, g: GuessRecord) -> Guess:
    r = g.report
    return Guess(
        attempt_id=attempt_id,
        guesser=g.persona,
        round=g.round,
        top3=[x.model_dump() for x in r.top3] if r else None,
        start_month=r.start_month if r else None,
        start_year=r.start_year if r else None,
        start_conf=r.start_confidence if r else None,
        clues=[c.model_dump() for c in r.clues] if r else None,
        readability=r.readability if r else None,
        readability_issues=r.readability_issues if r else None,
        searches_used=g.searches_used,
        queries=g.queries,
        citations=g.citations,
        recognised=g.recognised,
    )


def _store_attempt(session: Session, run_id: int, case_id: str, a: AttemptRecord) -> int:
    row = Attempt(
        run_id=run_id,
        case_id=case_id,
        n=a.n,
        number_plan=a.number_plan,
        scenario_json=a.scenario.model_dump(mode="json") if a.scenario else None,
        scan_result=a.scan_result,
        avg_readability=a.avg_readability,
        verdict=a.verdict,
        fail_reason=a.fail_reason,
    )
    session.add(row)
    session.flush()
    assert row.id is not None
    for g in a.guesses:
        session.add(_guess_row(row.id, g))
    return row.id


def _what_changed(plan: NumberPlan, company: str, invented: str) -> list[str]:
    money = plan.amount_factors.get("money")
    return [
        f"Company name {company} became {invented}; ticker hidden.",
        "All dates were replaced by story days; gaps between news items were stretched or "
        "squeezed by up to 30 percent, in whole weeks.",
        f"Prices were multiplied by {plan.price_factor} (percentage moves unchanged).",
        f"All money amounts share one factor ({money}), rounded to 2 significant figures.",
        "The news was rewritten in our own words. The ups and downs are real.",
    ]


def create_scenario(
    session: Session,
    case: SourceCase,
    gate_case: GateCase,
    attempt: AttemptRecord,
    attempt_id: int,
    salt: int,
) -> Scenario:
    assert attempt.scenario is not None
    scn = attempt.scenario
    facts = [AmountFact(a.token, a.family, a.value, a.is_ratio) for a in gate_case.amounts]
    plan = NumberPlan.build(
        gate_case.case_id, salt, gate_case.series, [b.real_day for b in gate_case.beats], facts
    )
    today = plan.story_days[-1]
    chart = [
        {"day": p.day, "close": str(p.price)} for p in plan.transform_series(gate_case.series)
        if p.day <= today
    ]  # fmt: skip
    for old in session.exec(
        select(Scenario).where(Scenario.case_id == case.id, Scenario.status == "playable")
    ).all():
        old.status = "retired"
        session.add(old)
    scenario = Scenario(
        case_id=case.id,
        attempt_id=attempt_id,
        source="gate",
        invented_name=scn.invented_name,
        industry_shown=scn.industry,
        story_days=list(plan.story_days),
        beats=[b.model_dump() for b in scn.beats],
        chart_series=chart,
        company_card={"name": scn.invented_name, "sector": scn.sector, "industry": scn.industry},
        status="playable",
    )
    session.add(scenario)
    session.flush()
    series_dates = {d.toordinal(): d for d in (date.fromordinal(x) for x, _ in gate_case.series)}
    real_beats = {
        "beats": [
            {
                "date": date.fromordinal(b.real_day).isoformat(),
                "day": plan.story_days[i],
                "price": str(dict(gate_case.series)[b.real_day]),
                "headline": b.headline,
            }
            for i, b in enumerate(gate_case.beats)
        ],
        "series": [
            {"date": series_dates[d].isoformat(), "price": str(p)} for d, p in gate_case.series
        ],
    }
    guessers = {g.persona for g in attempt.guesses if g.report is not None}
    session.add(
        ScenarioSecret(
            scenario_id=scenario.id,
            real_name=case.company,
            ticker=case.ticker,
            real_beats=real_beats,
            price_series_ref=None,
            price_factor=float(plan.price_factor),
            amount_factors={k: str(v) for k, v in sorted(plan.amount_factors.items())},
            seed=plan.seed,
            what_changed=_what_changed(plan, case.company, scn.invented_name),
            n_guessers=len(guessers),
            leak_terms=_real_terms(gate_case),
        )
    )
    return scenario


def retire_playable(session: Session, case_id: str) -> None:
    for old in session.exec(
        select(Scenario).where(Scenario.case_id == case_id, Scenario.status == "playable")
    ).all():
        old.status = "retired"
        session.add(old)


def record_case(
    session: Session,
    run_id: int,
    case: SourceCase,
    gate_case: GateCase | None,
    state: dict[str, Any] | None,
    status_override: str | None = None,
    error: str | None = None,
    salt: int = 0,
) -> str:
    """Write one case's attempts, guesses, case_result (and scenario) in a single commit."""
    final = status_override or "error"
    approved_id: int | None = None
    first_recognised: bool | None = None
    if state is not None and status_override is None:
        attempts: list[AttemptRecord] = list(state.get("attempts", []))
        ids = [_store_attempt(session, run_id, case.id, a) for a in attempts]
        gate_status = state.get("status", "error")
        final = gate_status if gate_status in ("approved", "rejected") else "error"
        if attempts:
            first_recognised = any(g.recognised for g in attempts[0].guesses)
        if final == "approved" and gate_case is not None:
            i = max(i for i, a in enumerate(attempts) if a.verdict == "passed")
            approved_id = ids[i]
            create_scenario(session, case, gate_case, attempts[i], ids[i], salt)
        elif final == "rejected":
            retire_playable(session, case.id)
        run = session.get(CheckRun, run_id)
        if run is not None:
            cfg = dict(run.config or {})
            cfg["telemetry"] = add_telemetry(cfg.get("telemetry"), state.get("telemetry", []))
            run.config = cfg
            session.add(run)
    elif error is not None:
        session.add(
            Attempt(
                run_id=run_id,
                case_id=case.id,
                n=1,
                scan_result={"error": error},
                verdict="error",
                fail_reason="error",
            )
        )
    session.add(
        CaseResult(
            case_id=case.id,
            run_id=run_id,
            final_status=final,
            approved_attempt_id=approved_id,
            recognised_first_attempt=first_recognised,
        )
    )
    session.commit()
    return final


# ---- the run ---------------------------------------------------------------
def start_run(session: Session, label: str, settings: Settings, resume: bool = True) -> CheckRun:
    """Open a run; an unfinished run with the same label is resumed."""
    if resume:
        open_run = session.exec(
            select(CheckRun)
            .where(CheckRun.label == label, CheckRun.finished_at.is_(None))  # type: ignore[union-attr]
            .order_by(CheckRun.id.desc())  # type: ignore[union-attr]
        ).first()
        if open_run is not None:
            return open_run
    run = CheckRun(
        label=label,
        config={"model": settings.model_id, "thresholds": settings.thresholds(), "run_salt": 0},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@dataclass
class BatchSummary:
    run_id: int
    done: dict[str, str] = field(default_factory=dict)  # case_id -> final status
    already_done: list[str] = field(default_factory=list)


async def run_batch(
    session_factory: SessionFactory,
    run_id: int,
    case_ids: Sequence[str] | None = None,
    *,
    llm_factory: LLMFactory = live_llm_factory,
    gate_runner: GateRunner = default_gate_runner,
    concurrency: int | None = None,
    on_case_done: CaseDone | None = None,
) -> BatchSummary:
    cfg = get_settings()
    sem = asyncio.Semaphore(concurrency or cfg.check_concurrency)
    summary = BatchSummary(run_id)
    with session_factory() as s:
        run = s.get(CheckRun, run_id)
        assert run is not None
        salt = int((run.config or {}).get("run_salt", 0))
        wanted = list(case_ids) if case_ids else [c.id for c in s.exec(select(SourceCase)).all()]
        finished = set(s.exec(select(CaseResult.case_id).where(CaseResult.run_id == run_id)).all())
        todo = sorted(c for c in wanted if c not in finished)
        summary.already_done = sorted(c for c in wanted if c in finished)
        run.n_cases = len(wanted)
        s.add(run)
        s.commit()

    async def one(case_id: str) -> None:
        async with sem:  # take a slot before checking out a connection
            final = await _run_case(case_id)
        if final and on_case_done:
            on_case_done(case_id, final)

    async def _run_case(case_id: str) -> str | None:
        # Short sessions: read inputs, release the connection, run the gate, then write.
        with session_factory() as s:
            case = s.get(SourceCase, case_id)
            if case is None:
                return None
            gate_case: GateCase | None = None
            override: str | None = None
            if reevaluate_skip(s, case) is not None:
                override = "skipped"
            else:
                built = build_gate_case(s, case)
                if isinstance(built, str):  # pragma: no cover - reevaluate_skip checked it
                    override = "skipped"
                else:
                    gate_case = built
            s.commit()  # persist the skip re-evaluation and free the connection
            llm = llm_factory(case) if gate_case is not None else None
        state: dict[str, Any] | None = None
        error: str | None = None
        if gate_case is not None and llm is not None:
            try:
                state = await asyncio.to_thread(gate_runner, gate_case, salt, llm)
            except Exception as exc:  # noqa: BLE001 - one bad case must not stop the run
                log.exception("gate failed for %s", case_id)
                error = f"{type(exc).__name__}: {exc}"
        with session_factory() as s:
            case = s.get(SourceCase, case_id)
            assert case is not None
            final = record_case(s, run_id, case, gate_case, state, override, error, salt)
        summary.done[case_id] = final
        return final

    await asyncio.gather(*(one(c) for c in todo))
    with session_factory() as s:
        run = s.get(CheckRun, run_id)
        if run is not None:
            run.finished_at = datetime.now(UTC)
            s.add(run)
            s.commit()
    return summary
