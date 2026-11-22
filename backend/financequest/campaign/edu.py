"""Educational moments: a generous, rule-based detector over the engine facts of one turn.

A moment is a small "you could learn something here" flag tied to a concept of a fixed catalog.
Detection reads only engine facts (the event log of the turn, the gated board, the purse, the
player's own words); it never calls a model and never produces a figure. Moments are stored as
events (``edu_moment``, then ``edu_viewed`` / ``edu_dismissed``); ``edu_skipped`` notes a detection
dropped because three moments were already waiting. Each concept fires at most once per campaign
(``concept_question`` once per term). See ``edu_turn.py`` for building the facts.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from financequest.campaign.events import append_event
from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun

MAX_PENDING = 3  # up to 3 moments are recorded; the UI shows one bubble
PRICE_MOVE_PCT = 8
CONCENTRATION_PCT = 80

# concept_key -> player-safe title (concept_question's title is "<Term> in plain words")
CATALOG: dict[str, str] = {
    "news_reaction": "Reacting to news",
    "first_trade": "Your first trade: what you actually own",
    "cash_vs_profit": "Profit isn't cash",
    "debt_and_equity": "Debt vs what owners own",
    "price_move": "Why prices move",
    "concentration": "All eggs in one basket",
    "loan_cost": "Borrowing costs",
    "thin_reasoning": "Deciding with evidence",
    "luck_vs_skill": "Luck vs judgement",
    "concept_question": "Terms in plain words",
}
# detection priority when several fire in one turn (the cap then keeps the first three)
ORDER = ("concept_question", "luck_vs_skill", "news_reaction", "first_trade", "loan_cost",
         "concentration", "thin_reasoning", "debt_and_equity", "cash_vs_profit", "price_move")  # fmt: skip

# canonical term -> pattern in the player's words
TERMS: dict[str, str] = {
    "cash flow": r"cash[- ]?flows?", "revenue": r"revenues?|sales|turnover", "profit": r"profits?|profitable",
    "earnings": r"earnings", "debt": r"debts?|liabilit\w+", "equity": r"equity", "dividend": r"dividends?",
    "share": r"shares?|stocks?", "price": r"prices?", "risk": r"risks?|risky",
    "diversification": r"diversif\w+", "margin": r"margins?", "ledger": r"ledgers?",
}  # fmt: skip
_ASKS = re.compile(
    r"\b(what\s+(is|are|does|do|'s)|what's|whats|meaning|means?|mean by|explain|define|"
    r"how does .{0,30} work|why does .{0,30} matter|tell me about)\b", re.I,
)
_CHART_RE = re.compile(r"\b(chart|price board|board|graph|trend|price (?:move|change|drop|rise|fall))\b", re.I)
# the story says "ready coin" and "treasury movement" for cash, "owed" and "net owners' claim" for debt
_CASH_RE = re.compile(r"cash[- ]?flow|operating cash|cash (?:statement|ledger)|ready coin|treasury movement|coin through", re.I)
_EARN_RE = re.compile(r"earnings|profit|net income|income statement|revenue|\bsales\b", re.I)
_DEBT_RE = re.compile(
    r"\bdebts?\b|liabilit|equity|owners'? claim|\bowed?\b|due (?:soon|later)|borrow|\bloans?\b|leverage|balance sheet", re.I,
)
_LEDGER_RE = re.compile(r"ledger|statement|balance sheet|cash flow|earnings", re.I)


@dataclass
class EduFacts:
    """Engine facts of one narrated turn. Everything a lesson may state is in ``snapshot``."""

    text: str = ""  # the player's own words this turn (action or question to Buddy)
    screen: str | None = None
    news: bool = False
    news_headline: str = ""
    trade: dict[str, Any] | None = None  # buy / sell made this turn
    thin_reasoning: bool = False
    clue_texts: list[str] = field(default_factory=list)  # evidence found this turn (title + text)
    screen_texts: list[str] = field(default_factory=list)  # what the open Library page shows
    loan_offered: bool = False
    loan: dict[str, int] | None = None
    roll: dict[str, Any] | None = None  # final dice check: title, result, used
    hp_loss: int = 0
    chart: dict[str, int] | None = None  # first, last, change_pct of the shown board
    at_market: bool = False
    gp: dict[str, int] = field(default_factory=dict)
    hp: int = 0
    hp_start: int = 0
    day: str = ""
    all_in: bool = False


@dataclass(frozen=True)
class Candidate:
    concept_key: str
    title: str
    term: str | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.concept_key}:{self.term}" if self.term else self.concept_key


def term_title(term: str) -> str:
    return f"{term[:1].upper()}{term[1:]} in plain words"


def _asked_terms(text: str) -> list[str]:
    if not text or not (_ASKS.search(text) or "?" in text):
        return []
    return [t for t, pat in TERMS.items() if re.search(rf"\b(?:{pat})\b", text, re.I)][:1]


def detect(f: EduFacts) -> list[Candidate]:
    """Every concept this turn's facts touch, in priority order. Generous on purpose."""
    hits: dict[str, Candidate] = {}

    def add(key: str, term: str | None = None) -> None:
        title = term_title(term) if term else CATALOG[key]
        hits.setdefault(f"{key}:{term}" if term else key, Candidate(key, title, term))

    for term in _asked_terms(f.text):
        add("concept_question", term)
    if f.roll and (f.roll.get("result") != "success" or f.roll.get("used") in (1, 20)) or f.hp_loss > 0:
        add("luck_vs_skill")
    if f.news:
        add("news_reaction")
    if f.trade:
        add("first_trade")
    if f.loan_offered:
        add("loan_cost")
    total = f.gp.get("total", 0)
    if f.all_in or (total > 0 and f.gp.get("position", 0) * 100 >= CONCENTRATION_PCT * total):
        add("concentration")
    if f.thin_reasoning:
        add("thin_reasoning")
    seen = " ".join([*f.clue_texts, *f.screen_texts])
    if f.loan_offered or _DEBT_RE.search(seen) or _DEBT_RE.search(f.text):
        add("debt_and_equity")
    both = bool(_CASH_RE.search(seen)) and bool(_EARN_RE.search(seen))
    if both or _CASH_RE.search(f.text) or _CASH_RE.search(" ".join(f.clue_texts)) \
            or (_EARN_RE.search(f.text) and _LEDGER_RE.search(f.text)):
        add("cash_vs_profit")
    moved = f.chart is not None and abs(f.chart.get("change_pct", 0)) >= PRICE_MOVE_PCT
    if (moved and (f.at_market or (f.screen or "") in ("market_square", "price_board"))) \
            or _CHART_RE.search(f.text):
        add("price_move")
    order = {k: i for i, k in enumerate(ORDER)}
    return sorted(hits.values(), key=lambda c: order[c.concept_key])


def snapshot(f: EduFacts, cand: Candidate) -> dict[str, Any]:
    """What the lesson for this moment may quote: whole numbers, gold pieces, the player's words."""
    snap: dict[str, Any] = {"gp": dict(f.gp), "hp": f.hp, "hp_start": f.hp_start, "day": f.day}
    key = cand.concept_key
    if f.text and key in ("concept_question", "thin_reasoning", "cash_vs_profit", "debt_and_equity",
                          "price_move"):
        snap["quote"] = f.text.strip()[:140]
    if cand.term:
        snap["term"] = cand.term
    if key == "news_reaction":
        snap["news"] = f.news_headline
    if key == "first_trade" and f.trade:
        snap["trade"] = dict(f.trade)
    if key in ("loan_cost", "debt_and_equity") and f.loan:
        snap["loan"] = dict(f.loan)
    if key == "luck_vs_skill":
        if f.roll:
            snap["roll"] = dict(f.roll)
        if f.hp_loss:
            snap["hp_loss"] = f.hp_loss
            snap["hp_loss_gp"] = f.hp_loss * 10
    if key == "price_move" and f.chart:
        snap["price"] = dict(f.chart)
    if key == "concentration":
        total = f.gp.get("total", 0)
        snap["share_pct"] = round(100 * f.gp.get("position", 0) / total) if total else 100
    return snap


# ---- the event log: pending / viewed / dismissed ---------------------------------------------------
EDU_TYPES = ("edu_moment", "edu_viewed", "edu_dismissed", "edu_skipped", "edu_lesson")


@dataclass
class Moment:
    id: str
    concept_key: str
    title: str
    seq: int
    facts: dict[str, Any]
    term: str | None
    status: str = "pending"  # pending / viewed / dismissed


def moments(events: list[Event]) -> list[Moment]:
    """Every moment with its current status, in detection order (a projection of the log)."""
    out: dict[str, Moment] = {}
    for e in events:
        p = e.payload or {}
        if e.type == "edu_moment":
            out[p["id"]] = Moment(p["id"], p["concept_key"], p["title"], int(p.get("seq", 0)),
                                  dict(p.get("facts") or {}), p.get("term"))
        elif e.type in ("edu_viewed", "edu_dismissed") and p.get("id") in out:
            if out[p["id"]].status == "pending":
                out[p["id"]].status = e.type.removeprefix("edu_")
    return list(out.values())


def public(m: Moment) -> dict[str, str]:
    return {"id": m.id, "concept_key": m.concept_key, "title": m.title}


def edu_out(events: list[Event]) -> dict[str, Any]:
    pending = [public(m) for m in moments(events) if m.status == "pending"]
    return {"pending": pending, "pending_count": len(pending)}


def cached_lesson(events: list[Event], moment_id: str) -> dict[str, Any] | None:
    for e in reversed(events):
        if e.type == "edu_lesson" and (e.payload or {}).get("id") == moment_id:
            return dict(e.payload["lesson"])
    return None


def record(
    db: Any, run: CampaignRun, events: list[Event], facts: EduFacts, seq: int
) -> list[dict[str, str]]:
    """Detect and store. Caller holds the run row lock. Returns the new moments (public view)."""
    mine = moments(events)
    have = {f"{m.concept_key}:{m.term}" if m.term else m.concept_key for m in mine}
    pending = sum(1 for m in mine if m.status == "pending")
    new: list[dict[str, str]] = []
    for cand in detect(facts):
        if cand.dedupe_key in have:
            continue
        if pending >= MAX_PENDING:
            append_event(db, run, "edu_skipped", {"concept_key": cand.concept_key,
                                                  "title": cand.title, "reason": "cap", "seq": seq})
            continue
        mid = uuid.uuid4().hex[:12]
        append_event(db, run, "edu_moment", {
            "id": mid, "concept_key": cand.concept_key, "title": cand.title, "seq": seq,
            "term": cand.term, "facts": snapshot(facts, cand),
        })
        have.add(cand.dedupe_key)
        pending += 1
        new.append({"id": mid, "concept_key": cand.concept_key, "title": cand.title})
    return new
