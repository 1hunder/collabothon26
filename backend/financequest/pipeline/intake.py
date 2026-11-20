"""Intake: Markdown case collection -> validated, tagged ``source_case`` rows + spot-check CSV.

The extraction itself is ``reid.graph.run_intake`` (LLM, validation, skip rules). This module reads
the files, tokenises amounts (code owns every number), tags size and fame and persists.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dateutil import parser as dateparser
from pydantic import BaseModel
from sqlmodel import Session, select

from financequest.db.models import SourceBeat, SourceCase
from financequest.llm import DefaultFakeNodeLLM, LLMResult, NodeLLM
from financequest.pipeline.fx import to_eur
from financequest.pipeline.sources import MetadataSource
from financequest.reid import rules, schemas
from financequest.reid.graph import run_intake
from financequest.reid.schemas import IntakeResult

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_MONEY = re.compile(
    r"(?:[$€£¥]|USD\s|EUR\s|GBP\s)\s?(\d[\d,]*(?:\.\d+)?)\s?(trillion|billion|million|bn|m|k|thousand)?\b",
    re.I,
)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)(?=\s?(?:%|percent))")
_MULT = {
    "trillion": Decimal("1e12"), "billion": Decimal("1e9"), "bn": Decimal("1e9"),
    "million": Decimal("1e6"), "m": Decimal("1e6"), "thousand": Decimal("1e3"), "k": Decimal("1e3"),
}  # fmt: skip


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "case"


def parse_real_date(text: str) -> date | None:
    """ISO dates, 'March 11, 2019', 'Mar 2019'. A year alone is too vague and returns None."""
    if not text or not _YEAR.search(text):
        return None
    try:
        parsed: datetime = dateparser.parse(text, default=datetime(2000, 1, 1))
    except (ValueError, OverflowError):
        return None
    if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", text):
        return None
    return parsed.date()


def tokenise_facts(
    facts_by_beat: list[list[str]],
) -> tuple[list[list[str]], list[dict[str, Any]]]:
    """Replace each money amount and percentage with ``{An}``. Money keeps full-unit value."""
    amounts: list[dict[str, Any]] = []

    def token(family: str, value: Decimal, ratio: bool) -> str:
        tok = f"{{A{len(amounts) + 1}}}"
        amounts.append(
            {"token": tok, "family": family, "value": format(value, "f"), "is_ratio": ratio}
        )
        return tok

    def money(m: re.Match[str]) -> str:
        value = Decimal(m.group(1).replace(",", ""))
        value *= _MULT.get((m.group(2) or "").lower(), Decimal(1))
        return token("money", value, False)

    out = []
    for facts in facts_by_beat:
        row = []
        for f in facts:
            f = _MONEY.sub(money, f)
            f = _PERCENT.sub(lambda m: token("percent", Decimal(m.group(1)), True), f)
            row.append(f)
        out.append(row)
    return out, amounts


class FixtureIntakeLLM:
    """``--dry-run-fake-llm`` intake: drafts come from a sidecar JSON (title -> SourceCaseDraft)
    next to the Markdown file; any other node falls through to the default fake."""

    def __init__(self, drafts: dict[str, Any]) -> None:
        self._drafts = drafts
        self._default = DefaultFakeNodeLLM()

    @classmethod
    def for_md(cls, md: Path) -> FixtureIntakeLLM:
        side = md.with_suffix(".drafts.json")
        return cls(json.loads(side.read_text(encoding="utf-8")) if side.exists() else {})

    def run(self, node: str, messages: Any, **kw: Any) -> LLMResult:
        title = (kw.get("context") or {}).get("title")
        if node == "extract_case" and title in self._drafts:
            parsed: BaseModel = schemas.SourceCaseDraft.model_validate(self._drafts[title])
            return LLMResult(
                parsed=parsed,
                content=[{"type": "text", "text": parsed.model_dump_json()}],
                usage={"input_tokens": 1, "output_tokens": 1},
            )
        return self._default.run(node, messages, **kw)


@dataclass
class IntakeSummary:
    ok: int = 0
    untagged: int = 0
    skipped: int = 0
    errors: int = 0


def read_results(md: Path, llm: NodeLLM | None = None) -> list[IntakeResult]:
    return run_intake(md.read_text(encoding="utf-8"), llm=llm)


def persist_results(
    session: Session,
    results: list[IntakeResult],
    origin: str = "md61",
    metadata: MetadataSource | None = None,
) -> IntakeSummary:
    summary = IntakeSummary()
    for res in results:
        if res.status == "error" or res.draft is None:
            summary.errors += 1
            continue
        d = res.draft
        case_id = slugify(res.title)
        market_cap, fx_note = d.market_cap_eur, None
        meta = metadata.get(d.ticker) if metadata and d.ticker else None
        if market_cap is None and meta and meta.market_cap_local and meta.currency and d.story_year:
            fx = to_eur(meta.market_cap_local, meta.currency, d.story_year)
            market_cap = float(fx.eur)
            fx_note = {"rate_per_eur": str(fx.rate), "currency": fx.currency, "year": fx.year_used}
        facts = rules.CaseFacts(
            lesson=d.lesson or "",
            identifying_terms=tuple(d.identifying_terms),
            beat_prices=tuple(0.0 for _ in d.beats),
            market_cap_eur=market_cap,
            is_us_listed=d.is_us_listed,
            country=d.country or "",
            story_year=d.story_year,
        )
        tagged = res.status == "ok"
        band = rules.size_band(market_cap) if market_cap is not None else None
        fame = rules.case_fame(facts) if tagged else None
        existing = session.get(SourceCase, case_id)
        case = existing or SourceCase(id=case_id, company=d.company or res.title)
        case.company = d.company or res.title
        case.ticker, case.exchange, case.country = d.ticker, d.exchange, d.country
        case.currency, case.lesson, case.story_year = d.currency, d.lesson, d.story_year
        case.market_cap_eur, case.size_band, case.fame = market_cap, band, fame
        case.identifying_terms = list(d.identifying_terms)
        case.known_names = {
            "parent": d.parent or "",
            "subsidiaries": d.subsidiaries,
            "former_names": d.former_names,
            "executives": d.executives,
            "industry": d.industry or "",
            "is_us_listed": d.is_us_listed,
            "fx": fx_note,
        }
        case.status = res.status if res.status in ("skipped", "untagged") else "ok"
        case.skip_reason = res.skip_reason
        case.origin = origin
        session.add(case)
        session.flush()
        for old in session.exec(select(SourceBeat).where(SourceBeat.case_id == case_id)).all():
            session.delete(old)
        tokenised, amounts = tokenise_facts([b.facts for b in d.beats])
        for i, b in enumerate(d.beats):
            session.add(
                SourceBeat(
                    case_id=case_id,
                    idx=i,
                    real_date=b.real_date,
                    headline=b.headline,
                    facts={
                        "facts": tokenised[i],
                        "amounts": [
                            a for a in amounts if any(a["token"] in f for f in tokenised[i])
                        ],
                    },
                )
            )
        session.commit()
        if res.status == "skipped":
            summary.skipped += 1
        elif res.status == "untagged":
            summary.untagged += 1
        else:
            summary.ok += 1
    return summary


SPOTCHECK_COLUMNS = [
    "case_id", "company", "ticker", "status", "skip_reason", "size_band", "fame",
    "market_cap_eur", "story_year", "country", "n_beats", "identifying_terms", "spot_checked",
]  # fmt: skip


def write_spotcheck(session: Session, path: Path) -> int:
    cases = session.exec(select(SourceCase).order_by(SourceCase.id)).all()
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(SPOTCHECK_COLUMNS)
        for c in cases:
            n = len(session.exec(select(SourceBeat).where(SourceBeat.case_id == c.id)).all())
            w.writerow(
                [
                    c.id, c.company, c.ticker or "", c.status, c.skip_reason or "",
                    c.size_band or "", c.fame or "", c.market_cap_eur or "", c.story_year or "",
                    c.country or "", n, "; ".join(c.identifying_terms or []),
                    "yes" if c.spot_checked else "no",
                ]
            )  # fmt: skip
    return len(cases)
