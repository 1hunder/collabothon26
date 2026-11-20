"""Everything a client or agent sees before the lock is built here, through ``GatedView``."""

from __future__ import annotations

from typing import Any

from financequest.campaign.pack import Pack
from financequest.campaign.rules import normalize_location
from financequest.engine.gate import GatedView


def gated_view(run: Any) -> GatedView:
    return GatedView(run.checkpoint, run.clock_day, bool(run.news_shown))


def visible_evidence(pack: Pack, gv: GatedView) -> list[Any]:
    return gv.by_checkpoint(list(pack.evidence), lambda e: e.checkpoint)


def price_board(pack: Pack, gv: GatedView) -> list[dict[str, Any]]:
    # rows after decision day belong to /reveal only, whatever the clock says
    rows = gv.chart([r for r in pack.rows if r.day <= pack.decision_day], lambda r: r.day)
    return [
        {"day": r.day, "open": pack.display(r.open), "high": pack.display(r.high),
         "low": pack.display(r.low), "close": pack.display(r.close)}
        for r in rows
    ]  # fmt: skip


def board_out(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wire shape of the price board: numbers, not strings (the agents keep the strings)."""
    return [{k: (float(v) if k != "day" else v) for k, v in r.items()} for r in rows]


def reveal_chart(pack: Pack) -> list[dict[str, Any]]:
    """Only /reveal, after a decision exists, may extend to the horizon."""
    return [
        {"story_day": r.day, "price": pack.display_num(r.close)}
        for r in pack.rows
        if r.day <= pack.horizon_day
    ]


def gated_content(pack: Pack, gv: GatedView) -> dict[str, Any]:
    ev = visible_evidence(pack, gv)
    vis_ids = {e.id for e in ev}
    docs = gv.by_checkpoint(list(pack.documents), lambda d: d["checkpoint"])
    news = None
    if pack.news:
        news = gv.news_item({"headline": pack.news["headline"], "summary": pack.news["summary"]})
    return {
        "checkpoint": gv.checkpoint,
        "story_day": gv.clock_day,
        "evidence": [
            {
                "id": e.id,
                "checkpoint": e.checkpoint,
                "location": normalize_location(e.location),
                "title": e.title,
                "text": e.text,
                "key": e.key,
            }
            for e in ev
        ],  # fmt: skip
        "documents": [
            {
                "id": d["id"],
                "title": d["title"],
                "evidence_ids": [i for i in d["evidence_ids"] if i in vis_ids],
            }
            for d in docs
        ],  # fmt: skip
        "encounters": [
            {
                "id": e.id,
                "title": e.title,
                "location": normalize_location(e.location),
                "checkpoint": e.checkpoint,
            }
            for e in gv.by_checkpoint(list(pack.encounters), lambda x: x.checkpoint)
        ],  # fmt: skip
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "role": c.role,
                "location": normalize_location(c.location),
                "may_reveal": [
                    i for cp, ids in c.may_reveal.items() if gv.at_checkpoint(cp) for i in ids
                ],
                "never": c.never,
            }
            for c in pack.characters
        ],  # fmt: skip
        "chart": price_board(pack, gv),
        "news": news,
        "company_card": {
            "name": pack.company_name,
            "trade": pack.trade,
            "size": pack.size,
            "key_figures": [
                {k: v for k, v in f.items() if k != "checkpoint"}
                for f in pack.key_figures
                if gv.at_checkpoint(f["checkpoint"])
            ],
        },  # fmt: skip
    }
