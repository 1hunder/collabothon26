"""Builds the engine facts of one narrated reply and runs the educational-moment detector.

Called from ``turns._streamed`` (the commit phase of every narrated reply: actions, NPC turns,
moves, dice narration, decision scenes, offers, Buddy). Reads the event log and the gated board;
writes only ``edu_*`` events. Never calls a model and never fails the reply.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlmodel import Session

from financequest.campaign import edu, service
from financequest.campaign.events import campaign_events
from financequest.campaign.pack import Pack
from financequest.campaign.view import gated_content, gated_view
from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun, Location

log = logging.getLogger("financequest.edu")
_BOUNDARY = ("dm_reply", "buddy_a")


def _whole(v: Any) -> int:
    return int(Decimal(str(v)).quantize(Decimal(1), ROUND_HALF_UP))


def board(content: dict[str, Any]) -> dict[str, int] | None:
    rows = content["chart"]
    if len(rows) < 2:
        return None
    first, last = Decimal(rows[0]["close"]), Decimal(rows[-1]["close"])
    change = (last / first - 1) * 100 if first else Decimal(0)
    return {"first": _whole(first), "last": _whole(last), "change_pct": _whole(change)}


def _window(events: list[Event], ev: Event) -> list[Event]:
    """Events of this reply's turn: after the previous reply, up to and including this one. A Buddy
    answer only looks at the question right before it."""
    at = ev.seq or 0
    before = [e for e in events if (e.seq or 0) <= at]
    if ev.type == "buddy_a":
        q = next((e for e in reversed(before) if e.type == "buddy_q"), None)
        return [q] if q is not None else []
    start = next((i for i in range(len(before) - 2, -1, -1) if before[i].type in _BOUNDARY), -1)
    return before[start + 1 :]


def _screen_texts(content: dict[str, Any], screen: str | None) -> list[str]:
    if not screen:
        return []
    if screen == "library":
        card = content["company_card"]
        return [f"{f['label']} {f.get('value', '')}" for f in card["key_figures"]]
    if screen.startswith("document:"):
        doc = next((d for d in content["documents"] if d["id"] == screen.split(":", 1)[1]), None)
        by_id = {e["id"]: e for e in content["evidence"]}
        return [f"{by_id[i]['title']} {by_id[i]['text']}" for i in (doc["evidence_ids"] if doc else [])
                if i in by_id]
    return []


def build_facts(db: Session, run: CampaignRun, pack: Pack, ev: Event, events: list[Event]) -> edu.EduFacts:
    win = _window(events, ev)
    p = ev.payload or {}
    content = gated_content(pack, gated_view(run))
    f = edu.EduFacts()
    texts = [str((e.payload or {}).get("text", "")) for e in win if e.type in ("action", "buddy_q")]
    f.text = " ".join(t for t in texts if t)
    q = next((e for e in win if e.type == "buddy_q"), None)
    f.screen = (q.payload or {}).get("screen") if q is not None else None
    f.screen_texts = _screen_texts(content, f.screen)
    f.news = any(e.type == "news" for e in win) or bool(p.get("news"))
    news = next((e.payload for e in win if e.type == "news"), None) or p.get("news") or {}
    f.news_headline = str(news.get("headline", ""))
    f.clue_texts = [f"{(e.payload or {}).get('title', '')} {(e.payload or {}).get('text', '')}"
                    for e in win if e.type == "clue_found"]
    trades = [e for e in win if e.type == "trade"]
    inline = any(e.type == "decision_reasoning" and (e.payload or {}).get("source") == "inline" for e in win)
    skipped = any(e.type == "decision_reasoning" and (e.payload or {}).get("skipped") for e in win)
    f.thin_reasoning = (bool(trades) and not inline) or skipped
    made = next((e.payload for e in trades if (e.payload or {}).get("action") in ("buy", "sell")), None)
    if made:
        f.trade = {"action": made["action"], "amount": _whole(made.get("amount_eur") or 0)}
    offer = p.get("offer") or {}
    card = p.get("card") or {}
    f.loan_offered = (offer.get("kind") == "loan") or bool(card.get("loan")) or any(
        e.type == "all_in_offer" and (e.payload or {}).get("kind") == "loan" for e in win)
    loan = card.get("loan") or ((offer.get("terms") or {}) if offer.get("kind") == "loan" else None)
    if loan:
        f.loan = {"principal": _whole(loan.get("principal_eur", 0)), "repay": _whole(loan.get("repay_eur", 0)),
                  "interest": _whole(loan.get("interest_eur", 0) or (loan.get("repay_eur", 0) - loan.get("principal_eur", 0)))}
    if offer.get("reason"):  # a supporting hand: the lesson may quote what the engine offered
        t = offer.get("terms") or {}
        f.support = {"kind": str(offer.get("kind")), "reason": str(offer["reason"]),
                     "amount": _whole(t.get("gift_eur") or t.get("principal_eur") or t.get("max_eur") or 0)}  # fmt: skip
    rid = p.get("roll_id")
    roll = next((e.payload for e in reversed(events) if e.type == "dice_roll" and (e.seq or 0) <= (ev.seq or 0)
                 and (e.payload or {}).get("final") and (e.payload or {}).get("roll_id") == rid), None) if rid else None
    if roll:
        f.roll = {"title": str(roll.get("title", "")), "result": str(roll.get("result", "")),
                  "used": roll.get("used")}
    hp = p.get("hp_change") or {}
    f.hp_loss = -int(hp.get("delta", 0)) if hp else 0
    f.chart = board(content)
    cur = db.get(Location, run.current_location_id) if run.current_location_id else None
    f.at_market = bool(cur and cur.key == "market_square")
    purse = service.purse(db, run, pack)
    f.gp = {"cash": _whole(purse["cash_eur"]), "position": _whole(purse["position_eur"]),
            "total": _whole(purse["total_eur"])}
    f.hp, f.hp_start = service.hp_now(run), run.hp_start
    f.day = _day(run)
    f.all_in = bool(p.get("all_in"))
    return f


def _day(run: CampaignRun) -> str:
    from financequest.campaign import clock

    return clock.day_label(run.clock_day)


def detect_for_reply(db: Session, run: CampaignRun, pack: Pack, ev: Event) -> list[dict[str, str]]:
    """Detect, store and return the moments new with this reply. Idempotent per reply: what an
    earlier call for the same reply found is kept in its payload (``edu_new``) and merged. Never
    raises: a failure here must not fail a guarded reply."""
    p = dict(ev.payload or {})
    earlier = list(p.get("edu_new") or [])
    try:
        db.refresh(run, with_for_update=True)  # race-free seq, one detector at a time
        events = campaign_events(db, run.id)
        new = edu.record(db, run, events, build_facts(db, run, pack, ev, events), ev.seq or 0)
        if new:
            ev.payload = {**p, "edu_new": [*earlier, *new]}
            db.add(ev)
        db.commit()
        return [*earlier, *new]
    except Exception as exc:  # noqa: BLE001
        log.warning("educational detector failed: %s", exc)
        db.rollback()
        return earlier
