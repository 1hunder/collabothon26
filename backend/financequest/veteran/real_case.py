"""The real case behind a finished quest, for the Veteran's teaching sessions.

During a quest everything is disguised: a fantasy company, story days, gold pieces, scaled prices.
Once the quest is finished the Veteran may teach with history itself: the real company and ticker,
the real dates, the real share price in US dollars on the day of each decision, the real headlines
and how the price really moved. All of it comes from the server-only secret and the engine's real
price rows; nothing is computed by a model.

Every figure is a whole number, like everything the player reads: whole dollars from $1 up, cents
below ("26 cents"), so a collapse to pennies stays visible.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from financequest.campaign.pack import Pack, Row
from financequest.db.models import Scenario, ScenarioSecret
from financequest.db.models_campaign import Trade
from financequest.refpack import real_events

log = logging.getLogger("financequest.veteran")
MAX_EVENTS = 8
_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip


def usd(price: Decimal | str | float) -> str:
    """A real share price as the player reads it: "$43", "$1,250", or "26 cents" below a dollar."""
    p = Decimal(str(price))
    if p >= 1:
        return f"${int(p.quantize(Decimal(1), ROUND_HALF_UP)):,}"
    cents = int((p * 100).quantize(Decimal(1), ROUND_HALF_UP))
    return "1 cent" if cents == 1 else f"{cents} cents"


def long_date(iso: str) -> str:
    """2001-08-14 -> 14 August 2001 (an ISO date only; anything else is returned as it is)."""
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
        return f"{d} {_MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def _pct(a: Decimal, b: Decimal) -> int | None:
    if a == 0:
        return None
    return int(((b / a - 1) * 100).quantize(Decimal(1), ROUND_HALF_UP))


def _row_on(rows: tuple[Row, ...], day: int) -> Row | None:
    """The real trading day a story day falls on: the last real row on or before it."""
    before = [r for r in rows if r.day <= day]
    if before:
        return before[-1]
    return rows[0] if rows else None


def _is_real_date(iso: str) -> bool:
    return len(iso) >= 10 and iso[4] == "-" and iso[:4].isdigit()


def _events(sc: Scenario, sec: ScenarioSecret) -> list[dict[str, Any]]:
    """The real headlines, oldest first; beats with only disguised prose are left out."""
    rb: dict[str, Any] = sec.real_beats if isinstance(sec.real_beats, dict) else {}
    manifest = sc.manifest if isinstance(sc.manifest, dict) else {}
    pack_id = manifest.get("pack_id") or manifest.get("meta", {}).get("case_id")
    bundled = real_events.bundled(str(pack_id)) if pack_id else {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in rb.get("beats") or []:
        head = b.get("headline")
        if not head and b.get("evidence_id") in bundled:
            head = bundled[b["evidence_id"]][0]
        if not head or head in seen or not _is_real_date(str(b.get("date", ""))):
            continue
        seen.add(head)
        ev = {"date": long_date(str(b["date"])), "headline": str(head)}
        if b.get("price") not in (None, ""):
            ev["price"] = usd(b["price"])
        out.append(ev)
    return out[:MAX_EVENTS]


def build(
    sc: Scenario | None, sec: ScenarioSecret | None, pack: Pack, trades: list[Trade]
) -> dict[str, Any] | None:
    """The real case of one finished quest, or None when the quest has no real price history
    (an adapted scenario without real dates cannot be taught as history)."""
    if sec is None or sc is None:
        return None
    rows = pack.rows
    if not rows or not _is_real_date(rows[0].iso):
        return None
    start = _row_on(rows, pack.intro.story_day) or rows[0]
    today = _row_on(rows, pack.decision_day) or start
    end = _row_on(rows, pack.horizon_day) or rows[-1]
    decisions = []
    for t in trades:
        r = _row_on(rows, t.story_day)
        if r is None:
            continue
        decisions.append(
            {"seq": t.seq, "action": t.action, "date": long_date(r.iso), "price": usd(r.close)}
        )
    return {
        "company": sec.real_name,
        "ticker": sec.ticker,
        "start": {"date": long_date(start.iso), "price": usd(start.close)},
        "decision_day": {"date": long_date(today.iso), "price": usd(today.close)},
        "end": {"date": long_date(end.iso), "price": usd(end.close)},
        "move_pct": _pct(start.close, end.close),
        "move_after_decision_pct": _pct(today.close, end.close),
        "high": usd(max(r.close for r in rows)),
        "low": usd(min(r.close for r in rows)),
        "decisions": decisions,
        "events": _events(sc, sec),
    }
