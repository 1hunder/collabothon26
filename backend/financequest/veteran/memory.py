"""The Veteran's long-term memory, derived from the campaign tables and rebuildable at any time.

Three layers:

* ``summarize`` -> one ``veteran_memory`` row per finished campaign: verdicts and tags only
  (judgement and luck per decision, forecast band, missed clue ids, campaign tags). It never copies
  the player's words, figures or clue titles.
* ``build_profile`` -> one ``veteran_profile`` row per hero: recurring strengths, weaknesses and
  habits, milestones and counts, aggregated from the summaries.
* ``campaign_detail`` -> the full picture of one campaign for a conversation or the timeline card:
  the summary's verdicts joined with the source rows (the player's words, amounts, result, XP).

Judgement is graded only on what the player knew and wrote at the time; luck only on what the
price did afterwards (direction, never a figure). A loss never makes reasoning look bad, a gain
never makes it look good.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlmodel import Session, col, delete, select

from financequest.campaign import clock, ledger, portfolio
from financequest.campaign import service as cs
from financequest.campaign.pack import Pack
from financequest.db.models import Decision, ScenarioSecret
from financequest.db.models_campaign import CampaignRun, Debrief, Hero, Outcome, Trade, XpAward
from financequest.db.models_veteran import VeteranMemory, VeteranProfile

log = logging.getLogger("financequest.veteran")
VERSION = 1

# ---- judgement of one decision (the player's words and what they knew; never the outcome) -------
_REASON = re.compile(
    r"\b(because|since|so\b|given|due to|as the|evidence|ledger|ledgers|report|reports|figures?|"
    r"cash|debt|earnings|revenue|profit|margin|clue|notice|read|seen|saw|books|accounts|"
    r"statement|record|records|flow|risk|value|cheap|expensive|price board|trend)\b",
    re.I,
)
_PANIC = re.compile(
    r"(panic|scared|afraid|fear|get out|before it sinks|sinks?\b|quick(ly)?\b|hurry|"
    r"everyone (is|was) selling|crash|run for|all out|now!|!!)",
    re.I,
)
POSITIVE = ("cited_evidence", "thorough", "reflective", "well_matched")
NEGATIVE = ("panic_sell", "thin_reasons", "missed_clues", "overconfident")
NEUTRAL = ("stayed_out", "all_in", "sold_on_news", "bought_on_news", "held_through_news", "hedged")
TAG_LABELS = {
    "cited_evidence": "gives reasons from the evidence",
    "thorough": "finds the key clues before deciding",
    "reflective": "writes honest reflections",
    "well_matched": "forecasts with confidence that matches the result",
    "panic_sell": "sells in a hurry when bad news breaks",
    "thin_reasons": "decides without writing down why",
    "missed_clues": "decides before the key clues are found",
    "overconfident": "is more confident than the evidence allows",
    "stayed_out": "keeps the coins out of the market",
    "all_in": "puts nearly everything in at once",
    "sold_on_news": "sells when the news breaks",
    "bought_on_news": "buys when the news breaks",
    "held_through_news": "holds steady through the news",
    "hedged": "keeps forecasts close to even odds",
}
MILESTONES = {
    "first_quest": "First quest finished",
    "first_gain": "First quest that ended in gain",
    "first_sound_loss": "First loss with sound reasoning: the luck went against you",
    "first_well_matched": "First forecast whose confidence matched the result",
    "first_thorough": "First quest with every key clue found",
    "third_quest": "Three quests finished",
}


def judge(trade: Trade) -> tuple[str, list[str]]:
    """``sound`` / ``hasty`` / ``thin`` from the words alone, plus decision tags."""
    text = trade.text or ""
    tags: list[str] = []
    if trade.beat == "news":
        tags.append(
            {"sell": "sold_on_news", "buy": "bought_on_news"}.get(trade.action, "held_through_news")
        )
    panic = bool(_PANIC.search(text)) and trade.action == "sell"
    reasons = bool(_REASON.search(text)) and len(text.split()) >= 8
    if panic:
        tags.append("panic")
        return "hasty", tags
    if reasons:
        tags.append("cited_evidence")
        return "sound", tags
    tags.append("no_reason")
    return "thin", tags


def luck_of(trade: Trade, end_close: Decimal, budget: Decimal) -> str:
    """``kind`` / ``cruel`` / ``neutral``: the price after the decision, direction only."""
    if trade.action == "hold" or trade.amount_cents <= 0:
        return "neutral"
    fx = ledger.effect(
        trade.action, Decimal(trade.amount_cents) / 100, Decimal(trade.shares), end_close
    )
    if budget and abs(fx) < budget * Decimal("0.01"):
        return "neutral"
    return "kind" if fx > 0 else "cruel"


def forecast_band(dec: Decision, went_up: bool | None) -> str:
    pct = dec.forecast_pct if dec.forecast_pct is not None else 50.0
    conf = dec.confidence or 2
    if went_up is None or 35 < pct < 65:
        return "hedged"
    said_up = pct >= 65
    if said_up != went_up:
        return "overconfident" if conf >= 3 or pct >= 80 or pct <= 20 else "missed"
    return "underconfident" if conf <= 1 else "well_matched"


# ---- one campaign ----------------
def _finished_runs(db: Session, hero_id: uuid.UUID) -> list[CampaignRun]:
    return list(
        db.exec(
            select(CampaignRun)
            .where(CampaignRun.hero_id == hero_id, CampaignRun.status == "finished")
            .order_by(col(CampaignRun.created_at))
        )
    )


def summarize(db: Session, run: CampaignRun, pack: Pack | None = None) -> dict[str, Any]:
    """The derived verdicts of one finished campaign. Deterministic: same rows, same summary."""
    pack = pack or cs.pack_of(db, run)
    trades = cs.trades_of(db, run.id)
    dec = cs.decision_of(db, run.id)
    oc = db.get(Outcome, run.id)
    deb = db.get(Debrief, run.id)
    budget = Decimal(run.hp_start * 10)
    went_up = portfolio.investment_return(pack.buy_open, pack.end_close) > 0
    rows: list[dict[str, Any]] = []
    for t in trades:
        j, t_tags = judge(t)
        luck = luck_of(t, pack.end_close, budget)
        rows.append({"seq": t.seq, "judgement": j, "luck": luck, "tags": t_tags})
    found = cs.found_ids(db, run.id)
    key = [e for e in pack.evidence if e.key]
    missed_key = [e.id for e in key if e.id not in found]
    missed_all = [e.id for e in pack.evidence if e.id not in found]
    band = forecast_band(dec, went_up) if dec else "hedged"
    pnl = cs.num(oc.pnl_pct) if oc else 0.0
    result = "gain" if (pnl or 0) > 0.5 else "loss" if (pnl or 0) < -0.5 else "flat"

    tags: list[str] = []
    n = len(rows)
    if any("panic" in r["tags"] for r in rows):
        tags.append("panic_sell")
    if n and sum(r["judgement"] == "sound" for r in rows) * 2 >= n:
        tags.append("cited_evidence")
    if n and sum(r["judgement"] == "thin" for r in rows) * 2 > n:
        tags.append("thin_reasons")
    if len(missed_key) >= 2 or (key and len(missed_key) * 2 >= len(key) and missed_key):
        tags.append("missed_clues")
    if key and not missed_key:
        tags.append("thorough")
    if deb and deb.reflection_text and len(deb.reflection_text.split()) >= 25:
        tags.append("reflective")
    if band in ("well_matched", "overconfident", "hedged"):
        tags.append(band)
    if not any(t.action == "buy" and t.amount_cents > 0 for t in trades):
        tags.append("stayed_out")
    if any(
        t.action == "buy" and Decimal(t.amount_cents) / 100 >= budget * Decimal("0.9")
        for t in trades
    ):
        tags.append("all_in")
    for r in rows:
        for tg in r["tags"]:
            if tg in ("sold_on_news", "bought_on_news", "held_through_news") and tg not in tags:
                tags.append(tg)
    judgements = {r["judgement"] for r in rows}
    sound_overall = bool(rows) and "hasty" not in judgements and "sound" in judgements
    return {
        "decisions": rows,
        "forecast": band,
        "market": "up" if went_up else "down",
        "missed_key_clues": missed_key,
        "missed_clues": missed_all,
        "result": result,
        "sound_overall": sound_overall,
        "tags": tags,
    }


def remember(db: Session, run: CampaignRun) -> VeteranMemory:
    """Write (or rewrite) the memory of one finished campaign and refresh the hero's profile."""
    runs = _finished_runs(db, run.hero_id)
    number = next((i + 1 for i, r in enumerate(runs) if r.id == run.id), len(runs) + 1)
    mem = db.get(VeteranMemory, run.id)
    verdicts = summarize(db, run)
    if mem is None:
        mem = VeteranMemory(
            campaign_id=run.id,
            hero_id=run.hero_id,
            number=number,
            version=VERSION,
            verdicts=verdicts,
        )
    else:
        mem.number, mem.version, mem.verdicts = number, VERSION, verdicts
    db.add(mem)
    db.flush()
    refresh_profile(db, run.hero_id)
    return mem


def ensure_memory(db: Session, hero_id: uuid.UUID) -> list[VeteranMemory]:
    """Every finished campaign has a current memory row (fills gaps from before the Veteran, or
    after a schema bump); returns them oldest first."""
    runs = _finished_runs(db, hero_id)
    have = {
        m.campaign_id: m
        for m in db.exec(select(VeteranMemory).where(VeteranMemory.hero_id == hero_id))
    }
    changed = False
    for i, r in enumerate(runs):
        m = have.get(r.id)
        if m is None or m.version != VERSION or m.number != i + 1:
            try:
                have[r.id] = remember(db, r)
                changed = True
            except Exception:  # noqa: BLE001 - a broken old campaign must not hide the others
                log.exception("could not remember campaign %s", r.id)
    prof = db.get(VeteranProfile, hero_id)
    if (
        changed
        or prof is None
        or prof.version != VERSION
        or len(prof.campaign_ids or []) != len(runs)
    ):
        refresh_profile(db, hero_id)
    return [have[r.id] for r in runs if r.id in have]


def rebuild(db: Session, hero_id: uuid.UUID) -> list[VeteranMemory]:
    """Throw the derived memory away and build it again from the campaign tables."""
    db.exec(delete(VeteranMemory).where(col(VeteranMemory.hero_id) == hero_id))  # type: ignore[call-overload]
    db.exec(delete(VeteranProfile).where(col(VeteranProfile.hero_id) == hero_id))  # type: ignore[call-overload]
    db.flush()
    return ensure_memory(db, hero_id)


# ---- profile ----------------
def build_profile(
    mems: list[VeteranMemory], xp_by_campaign: dict[uuid.UUID, int]
) -> dict[str, Any]:
    """Aggregate the summaries, oldest first. A tag seen in two or more campaigns is recurring."""
    counts: dict[str, int] = {}
    milestones: list[dict[str, Any]] = []

    def mark(key: str, number: int) -> None:
        if not any(m["key"] == key for m in milestones):
            milestones.append({"key": key, "label": MILESTONES[key], "quest": number})

    gains = losses = 0
    for m in mems:
        v = m.verdicts or {}
        for t in set(v.get("tags") or []):
            counts[t] = counts.get(t, 0) + 1
        if m.number == 1:
            mark("first_quest", 1)
        if m.number == 3:
            mark("third_quest", 3)
        if v.get("result") == "gain":
            gains += 1
            mark("first_gain", m.number)
        if v.get("result") == "loss":
            losses += 1
            if v.get("sound_overall"):
                mark("first_sound_loss", m.number)
        if v.get("forecast") == "well_matched":
            mark("first_well_matched", m.number)
        if "thorough" in (v.get("tags") or []):
            mark("first_thorough", m.number)

    def recurring(group: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = [
            {"tag": t, "label": TAG_LABELS[t], "count": counts[t]}
            for t in group
            if counts.get(t, 0) >= 2
        ]
        return sorted(rows, key=lambda r: -r["count"])

    latest = set((mems[-1].verdicts or {}).get("tags") or []) if mems else set()
    emerging = [
        {"tag": t, "label": TAG_LABELS[t]}
        for t in (*POSITIVE, *NEGATIVE, *NEUTRAL)
        if t in latest and counts.get(t, 0) == 1
    ]
    return {
        "quests": len(mems),
        "gains": gains,
        "losses": losses,
        "xp": sum(xp_by_campaign.get(m.campaign_id, 0) for m in mems),
        "strengths": recurring(POSITIVE),
        "weaknesses": recurring(NEGATIVE),
        "habits": recurring(NEUTRAL),
        "emerging": emerging,
        "milestones": sorted(milestones, key=lambda m: m["quest"]),
    }


def refresh_profile(db: Session, hero_id: uuid.UUID) -> VeteranProfile:
    mems = sorted(
        db.exec(select(VeteranMemory).where(VeteranMemory.hero_id == hero_id)),
        key=lambda m: m.number,
    )
    xp = (
        {
            a.campaign_id: a.total
            for a in db.exec(
                select(XpAward).where(col(XpAward.campaign_id).in_([m.campaign_id for m in mems]))
            )
        }
        if mems
        else {}
    )
    data = build_profile(mems, xp)
    prof = db.get(VeteranProfile, hero_id)
    ids = [str(m.campaign_id) for m in mems]
    if prof is None:
        prof = VeteranProfile(hero_id=hero_id, version=VERSION, data=data, campaign_ids=ids)
    else:
        prof.version, prof.data, prof.campaign_ids = VERSION, data, ids
    db.add(prof)
    db.flush()
    return prof


# ---- hydration: the summary joined with the source rows ----------------
BEAT_LABELS = {
    "opening": "At the start",
    "news": "When the news broke",
    "decision": "On decision day",
    "story": "Along the way",
}
CONF_LABELS = {1: "low", 2: "medium", 3: "high"}


@dataclass
class Sealed:
    """What the Veteran must not touch while a campaign is running."""

    scenario_id: uuid.UUID | None = None
    real_name: str | None = None
    leak_terms: tuple[str, ...] = ()

    def covers(self, db: Session, run: CampaignRun) -> bool:
        if self.scenario_id is None:
            return False
        if run.scenario_id == self.scenario_id:
            return True
        if not self.real_name:
            return False
        sec = db.get(ScenarioSecret, run.scenario_id)
        return bool(sec and _squash(sec.real_name) == _squash(self.real_name))


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sealed_for(db: Session, hero: Hero) -> Sealed:
    """The hero's running campaign (if any): its scenario, company and leak terms."""
    run = db.exec(
        select(CampaignRun).where(CampaignRun.hero_id == hero.id, CampaignRun.status == "active")
    ).first()
    if run is None:
        return Sealed()
    sec = db.get(ScenarioSecret, run.scenario_id)
    terms: tuple[str, ...] = ()
    try:
        terms = cs.pack_of(db, run).leak_terms
    except Exception:  # noqa: BLE001 - a pack that cannot load still seals its scenario
        log.exception("could not load the running campaign's pack")
    names = tuple(x for x in ((sec.real_name, sec.ticker or "") if sec else ()) if x)
    return Sealed(
        run.scenario_id, sec.real_name if sec else None, tuple(dict.fromkeys((*terms, *names)))
    )


def campaign_detail(db: Session, run: CampaignRun, mem: VeteranMemory) -> dict[str, Any]:
    """Everything the Veteran may say about one finished (and revealed) campaign."""
    pack = cs.pack_of(db, run)
    v = mem.verdicts or {}
    by_seq = {d["seq"]: d for d in v.get("decisions") or []}
    trades = cs.trades_of(db, run.id)
    dec = cs.decision_of(db, run.id)
    oc = db.get(Outcome, run.id)
    deb = db.get(Debrief, run.id)
    award = db.get(XpAward, run.id)
    sec = db.get(ScenarioSecret, run.scenario_id)
    titles = {e.id: e.title for e in pack.evidence}
    decisions = []
    for t in trades:
        d = by_seq.get(t.seq, {})
        decisions.append(
            {
                "seq": t.seq,
                "beat": t.beat,
                "when": BEAT_LABELS.get(t.beat, "Along the way"),
                "day": clock.day_label(t.story_day),
                "action": t.action,
                "amount_eur": t.amount_cents // 100,
                "text": t.text,
                "judgement": d.get("judgement", "thin"),
                "luck": d.get("luck", "neutral"),
                "tags": d.get("tags", []),
            }
        )
    narrative = (deb.narrative or {}) if deb else {}
    return {
        "campaign_id": str(run.id),
        "number": mem.number,
        "title": pack.title,
        "company": pack.company_name,
        "real_name": sec.real_name if sec else None,
        "decisions": decisions,
        "closing_note": _closing_note(dec, trades),
        "forecast": {
            "pct": int(dec.forecast_pct) if dec and dec.forecast_pct is not None else None,
            "confidence": CONF_LABELS.get(dec.confidence or 0) if dec else None,
            "band": v.get("forecast", "hedged"),
            "market": v.get("market"),
        },
        "result": {
            "kind": v.get("result"),
            "pnl_pct": cs.num(oc.pnl_pct) if oc else None,
            "pnl_eur": cs.num(oc.pnl) if oc else None,
            "final_eur": cs.num(oc.final) if oc else None,
            "budget_eur": run.hp_start * 10,
        },
        "missed": [titles[c] for c in v.get("missed_key_clues") or [] if c in titles],
        "debrief": {
            "sound": narrative.get("sound"),
            "luck": narrative.get("luck"),
            "overlooked": narrative.get("overlooked"),
        },
        "reflection": deb.reflection_text if deb else None,
        "xp": award.total if award else 0,
        "tags": v.get("tags", []),
        "sound_overall": bool(v.get("sound_overall")),
    }


def _closing_note(dec: Decision | None, trades: list[Trade]) -> str | None:
    """The note written at the seal: the decision's evidence minus the per-decision lines."""
    if dec is None or not dec.evidence:
        return None
    lines = str(dec.evidence).split("\n")
    rest = lines[len(trades) :] if len(lines) > len(trades) else []
    note = "\n".join(rest).strip()
    return note or None


def short(mem: VeteranMemory, run: CampaignRun, db: Session) -> dict[str, Any]:
    """A one-line memory for the "recent campaigns" block and the topic list."""
    pack = cs.pack_of(db, run)
    v = mem.verdicts or {}
    oc = db.get(Outcome, run.id)
    sec = db.get(ScenarioSecret, run.scenario_id)
    award = db.get(XpAward, run.id)
    return {
        "campaign_id": str(run.id),
        "number": mem.number,
        "title": pack.title,
        "company": pack.company_name,
        "real_name": sec.real_name if sec else None,
        "result": v.get("result"),
        "pnl_pct": cs.num(oc.pnl_pct) if oc else None,
        "forecast": v.get("forecast"),
        "tags": v.get("tags", []),
        "xp": award.total if award else 0,
        "finished_at": (
            award.finished_at.date().isoformat() if award and award.finished_at else None
        ),
    }
