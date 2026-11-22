"""The Quest Board: player-safe quest cards, the detail view, the spending-based suggestion and
the theme -> category matcher.

Everything that leaves this module is disguised text from the scenario's rendered manifest, run
through the scenario's leak terms. Company, ticker and real names never appear here.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlmodel import Session, select

from financequest.db.models import Scenario, ScenarioSecret
from financequest.db.models_campaign import CampaignRun, Hero
from financequest.db.models_personal import GenerationJob
from financequest.personal import transactions as tx
from financequest.refpack.board import DEFAULT_ORDER, WHAT_YOU_DO, derive_board
from financequest.refpack.validate import _leak_hits

GP_PER_HP = 10  # mirrors campaign.service.HP_EUR (1 HP = 10 gold pieces)
DEFAULT_HP = 100

# what the player spent on, as a phrase for "You spent the most on ..."
WHY_PHRASE = {
    "music": "music and streaming", "sportswear": "sportswear and sneakers",
    "fashion": "online fashion", "mobility": "rides", "food_delivery": "food delivery",
    "gaming": "games",
}  # fmt: skip
# extra words that point at a category (the catalog's labels and company names are matched too)
KEYWORDS = {
    "music": ("music", "song", "songs", "streaming", "podcast", "concert", "playlist", "radio"),
    "sportswear": ("sport", "sports", "sneaker", "sneakers", "shoe", "shoes", "running", "gym",
                   "fitness", "football", "soccer", "workout"),
    "fashion": ("fashion", "clothes", "clothing", "dress", "outfit", "style", "shopping",
                "online shop"),
    "mobility": ("car", "cars", "electric", "ev", "taxi", "ride", "rides", "bike", "scooter",
                 "transport", "travel", "mobility", "driving"),
    "food_delivery": ("food", "delivery", "pizza", "burger", "restaurant", "meal", "dinner",
                      "takeaway", "eat", "groceries"),
    "gaming": ("game", "games", "gaming", "console", "consoles", "playstation", "xbox", "esports",
               "video game", "nintendo", "steam"),
}  # fmt: skip


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9&.+-]+", text.lower()))


def suggestion(sid: uuid.UUID) -> dict[str, str]:
    """The category the player spent the most on (mock transactions)."""
    ranked = tx.spending_by_category(tx.transactions_for(sid))
    cat = tx.CATEGORIES[ranked[0][0]] if ranked else next(iter(tx.CATEGORIES.values()))
    return {
        "theme": cat.label, "category_label": cat.label,
        "why": f"You spent the most on {WHY_PHRASE.get(cat.key, cat.label.lower())} this month",
    }  # fmt: skip


def suggestion_category(sid: uuid.UUID) -> tx.Category:
    ranked = tx.spending_by_category(tx.transactions_for(sid))
    return tx.CATEGORIES[ranked[0][0]] if ranked else next(iter(tx.CATEGORIES.values()))


def match_theme(theme: str) -> tuple[tx.Category, tx.Company | None] | None:
    """Fuzzy, deterministic: keywords, category label words, company names and aliases.
    A company hit wins; otherwise the category with the most hits. None when nothing matches."""
    low = theme.lower().strip()
    if not low:
        return None
    words = _words(low)
    best: tuple[int, tx.Category, tx.Company | None] | None = None
    for cat in tx.CATEGORIES.values():
        score, company = 0, None
        score += 2 * len(words & {w.lower() for w in KEYWORDS.get(cat.key, ())})
        score += len(words & (_words(cat.label) - {"&"}))
        score += int(cat.interest.lower() in words)
        for comp in cat.companies:
            names = (comp.name, *comp.aliases)
            if any(len(n) > 2 and n.lower() in low for n in names):
                score += 5
                company = comp
        if score and (best is None or score > best[0]):
            best = (score, cat, company)
    return (best[1], best[2]) if best else None


# ---- cards --------------------------------------------------------------------------------------


def _safe(text: str, terms: list[str], fallback: str) -> str:
    return fallback if text and _leak_hits(text, terms) else text


def _manifest(sc: Scenario) -> dict[str, Any]:
    return sc.manifest if isinstance(sc.manifest, dict) else {}


def _board_of(sc: Scenario) -> dict[str, Any]:
    m = _manifest(sc)
    if m.get("world") and m.get("meta"):
        return {**derive_board(m), **(m.get("board") or {})}
    return {  # a gate scenario without a campaign manifest
        "title": sc.invented_name,
        "teaser": f"{sc.invented_name} is a house of the {sc.industry_shown} trade. "
        "Read what the market says and decide where your gold belongs.",
        "difficulty": "medium", "learn": list(derive_board({})["learn"]), "order": DEFAULT_ORDER,
        "briefing": "",
    }  # fmt: skip


def _horizon_days(sc: Scenario) -> int:
    p = _manifest(sc).get("prices") or {}
    d, h = p.get("decision_story_day"), p.get("horizon_story_day")
    return max(0, int(h) - int(d)) if isinstance(d, int) and isinstance(h, int) else 0


def budget_gp(db: Session, sid: uuid.UUID) -> int:
    from financequest.campaign import rules

    hero = db.exec(select(Hero).where(Hero.player_id == sid)).first()
    hp = rules.CLASSES.get(hero.hero_class, {}).get("hp", DEFAULT_HP) if hero else DEFAULT_HP
    return int(hp) * GP_PER_HP


def _runs(db: Session, sid: uuid.UUID) -> dict[uuid.UUID, tuple[bool, bool]]:
    out: dict[uuid.UUID, tuple[bool, bool]] = {}
    for r in db.exec(select(CampaignRun).where(CampaignRun.player_id == sid)):
        _, fin = out.get(r.scenario_id, (False, False))
        out[r.scenario_id] = (True, fin or r.status == "finished")
    return out


def card_for_scenario(
    db: Session, sc: Scenario, *, kind: str, budget: int, runs: dict[uuid.UUID, tuple[bool, bool]],
    card_id: str | None = None,
) -> dict[str, Any]:
    sec = db.get(ScenarioSecret, sc.id)
    terms = [t for t in [sec.real_name if sec else "", *((sec.leak_terms or []) if sec else [])]
             if t]  # fmt: skip
    b = _board_of(sc)
    played, finished = runs.get(sc.id, (False, False))
    name = _safe(sc.invented_name, terms, "A hidden house")
    return {
        "id": card_id or str(sc.id), "kind": kind, "status": "ready", "step": None,
        "title": _safe(b["title"], terms, "A New Quest"),
        "company_name": name,
        "trade": _safe(sc.industry_shown, terms, "Trade"),
        "teaser": _safe(b["teaser"], terms, f"{name} is at the heart of a market mystery."),
        "difficulty": b["difficulty"], "horizon_days": _horizon_days(sc), "budget_gp": budget,
        "learn": [_safe(x, terms, "Reading the market") for x in b["learn"][:3]],
        "scenario_id": str(sc.id), "played": played, "finished": finished,
    }  # fmt: skip


def card_for_job(
    db: Session, job: GenerationJob, *, budget: int, runs: dict[uuid.UUID, tuple[bool, bool]]
) -> dict[str, Any]:
    sc = db.get(Scenario, job.scenario_id) if job.status == "ready" and job.scenario_id else None
    if sc is not None and sc.status == "playable":
        return card_for_scenario(db, sc, kind="personal", budget=budget, runs=runs,
                                 card_id=str(job.id))  # fmt: skip
    failed = job.status in ("failed", "rejected")
    return {
        "id": str(job.id), "kind": "personal", "status": "failed" if failed else "generating",
        "step": job.step, "title": f"Your {job.category_label} quest",
        "company_name": "A house still hidden", "trade": job.category_label,
        "teaser": "The Master is writing this tale for you." if not failed
        else "This tale could not be finished. You can ask for a new one.",
        "difficulty": "medium", "horizon_days": 0, "budget_gp": budget,
        "learn": [], "scenario_id": None, "played": False, "finished": False,
    }  # fmt: skip


def _personal_ids(db: Session) -> set[uuid.UUID]:
    """Scenarios a player actually generated. Old demo-mode daily jobs only *pointed at* a
    curated scenario (detail.demo) and must not hide it from everyone's board."""
    jobs = db.exec(
        select(GenerationJob).where(GenerationJob.scenario_id.is_not(None))  # type: ignore[union-attr]
    ).all()
    return {j.scenario_id for j in jobs if j.scenario_id and not (j.detail or {}).get("demo")}


def board(db: Session, sid: uuid.UUID) -> dict[str, Any]:
    from financequest.personal.jobs import list_jobs

    budget, runs, personal = budget_gp(db, sid), _runs(db, sid), _personal_ids(db)
    scenarios = [
        sc for sc in db.exec(select(Scenario).where(Scenario.status == "playable"))
        if sc.id not in personal and _board_of(sc).get("listed", True) is not False
    ]  # fmt: skip
    cards = sorted(
        ((_board_of(sc), sc) for sc in scenarios), key=lambda t: (t[0]["order"], t[0]["title"])
    )
    curated = [
        card_for_scenario(db, sc, kind="curated", budget=budget, runs=runs) for _, sc in cards
    ]
    mine = [card_for_job(db, j, budget=budget, runs=runs) for j in list_jobs(db, sid)]
    return {"curated": curated, "mine": mine, "suggestion": suggestion(sid)}


def detail(db: Session, sid: uuid.UUID, quest_id: uuid.UUID) -> dict[str, Any] | None:
    """The card plus the detail-view text. ``quest_id`` is a scenario id (curated, or a ready
    quest) or one of this player's job ids."""
    budget, runs = budget_gp(db, sid), _runs(db, sid)
    job = db.get(GenerationJob, quest_id)
    if job is not None:
        if job.session_id != sid:
            return None
        card = card_for_job(db, job, budget=budget, runs=runs)
        sc = db.get(Scenario, job.scenario_id) if card["scenario_id"] else None
    else:
        sc = db.get(Scenario, quest_id)
        if sc is None or sc.status != "playable" or quest_id in _personal_ids(db):
            return None
        card = card_for_scenario(db, sc, kind="curated", budget=budget, runs=runs)
    return {**card, "details": _details(db, sc, card)}


def _details(db: Session, sc: Scenario | None, card: dict[str, Any]) -> dict[str, Any]:
    if sc is None:
        return {"briefing": card["teaser"], "characters": [], "places": [],
                "what_you_do": list(WHAT_YOU_DO)}  # fmt: skip
    sec = db.get(ScenarioSecret, sc.id)
    terms = [t for t in [sec.real_name if sec else "", *((sec.leak_terms or []) if sec else [])]
             if t]  # fmt: skip
    m, b = _manifest(sc), _board_of(sc)
    briefing = _safe(b.get("briefing") or card["teaser"], terms, card["teaser"])
    chars = [
        {"name": _safe(c["name"], terms, "A stranger"), "role": _safe(c["role"], terms, "Local")}
        for c in m.get("characters", [])
    ]
    places = ["Tavern", "Market Square", "Library"] + [
        _safe(s["name"], terms, "") for s in m.get("campaign_location_seeds", [])
    ]
    return {
        "briefing": briefing, "characters": chars, "places": [p for p in places if p],
        "what_you_do": list(WHAT_YOU_DO),
    }  # fmt: skip


__all__ = ["board", "detail", "suggestion", "match_theme"]
