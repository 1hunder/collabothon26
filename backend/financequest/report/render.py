"""Check report: one run rendered as HTML (Jinja, no external assets) and JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session, select

from financequest.db.models import (
    Attempt,
    CaseResult,
    CheckRun,
    Guess,
    Scenario,
    SourceCase,
)
from financequest.reid import rules
from financequest.report.stats import CaseOutcome, FinalStatus, compute_stats

CAVEAT = "Claude-only guessers are a weaker test than mixed providers"
TEMPLATES = Path(__file__).parent / "templates"
FAME_ORDER = ("low", "medium", "high")
SIZE_ORDER = ("small", "mid", "large")


def _guess_dict(g: Guess) -> dict[str, Any]:
    return {
        "guesser": g.guesser,
        "round": g.round,
        "top3": g.top3 or [],
        "start_guess": (
            f"{g.start_year}-{g.start_month:02d}" if g.start_year and g.start_month else None
        ),
        "start_conf": g.start_conf,
        "clues": g.clues or [],
        "readability": g.readability,
        "recognised": g.recognised,
        "searches_used": g.searches_used,
    }


def build_report_data(session: Session, run_id: int) -> dict[str, Any]:
    run = session.get(CheckRun, run_id)
    if run is None:
        raise KeyError(f"no check run {run_id}")
    results = session.exec(select(CaseResult).where(CaseResult.run_id == run_id)).all()
    cases: list[dict[str, Any]] = []
    outcomes: list[CaseOutcome] = []
    for res in sorted(results, key=lambda r: r.case_id):
        case = session.get(SourceCase, res.case_id)
        if case is None:
            continue
        attempts = session.exec(
            select(Attempt).where(Attempt.run_id == run_id, Attempt.case_id == res.case_id)
        ).all()
        rows = []
        invented = None
        for a in sorted(attempts, key=lambda x: x.n):
            guesses = session.exec(select(Guess).where(Guess.attempt_id == a.id)).all()
            if a.scenario_json:
                invented = a.scenario_json.get("invented_name", invented)
            rows.append(
                {
                    "n": a.n,
                    "verdict": a.verdict,
                    "fail_reason": a.fail_reason,
                    "avg_readability": a.avg_readability,
                    "scan_reasons": (a.scan_result or {}).get("reasons", []),
                    "guesses": [_guess_dict(g) for g in guesses],
                }
            )
        status: FinalStatus = res.final_status  # type: ignore[assignment]
        outcomes.append(
            CaseOutcome(
                case_id=case.id,
                status=status,
                recognised_first_attempt=bool(res.recognised_first_attempt),
                fame=case.fame,
                size=case.size_band,
            )
        )
        cases.append(
            {
                "case_id": case.id,
                "company": case.company,
                "ticker": case.ticker,
                "invented_name": invented,
                "size": case.size_band,
                "fame": case.fame,
                "country": case.country,
                "story_year": case.story_year,
                "untagged": case.fame is None,
                "status": res.final_status,
                "status_label": STATUS_LABELS.get(res.final_status, res.final_status),
                "skip_reason": case.skip_reason if res.final_status == "skipped" else None,
                "attempts": rows,
            }
        )
    stats = compute_stats(outcomes)

    def shares(table: dict[str, Any], order: tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            {"label": k, "count": table[k].count, "total": table[k].total, "pct": table[k].pct}
            for k in order
            if k in table
        ]

    playable = [
        {"id": str(s.id), "invented_name": s.invented_name, "industry": s.industry_shown,
         "case_id": s.case_id}
        for s in session.exec(
            select(Scenario).where(Scenario.source == "gate", Scenario.status == "playable")
        ).all()
    ]  # fmt: skip
    return {
        "run": {"id": run.id, "label": run.label, "config": run.config or {}},
        "header": stats.summary_line,
        "skipped_count": stats.skipped,
        "approval_by_fame": shares(stats.approval_by_fame, FAME_ORDER),
        "approval_by_size": shares(stats.approval_by_size, SIZE_ORDER),
        "playable": playable,
        "skipped": [
            {"case_id": c["case_id"], "company": c["company"], "reason": c["skip_reason"]}
            for c in cases
            if c["status"] == "skipped"
        ],
        "caveat": CAVEAT,
        "cases": cases,
        "telemetry": (run.config or {}).get("telemetry", {}),
    }


STATUS_LABELS = {
    "approved": "Approved",
    "rejected": "Rejected: too recognisable",
    "skipped": rules.SKIP_INCOMPLETE,
    "error": "Error",
}


def render_html(data: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    return env.get_template("report.html.j2").render(**data)


def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def write_report(session: Session, run_id: int, out: Path) -> tuple[Path, Path]:
    data = build_report_data(session, run_id)
    out.write_text(render_html(data), encoding="utf-8")
    json_path = out.with_suffix(".json")
    json_path.write_text(render_json(data), encoding="utf-8")
    return out, json_path
