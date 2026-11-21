"""Campaign use-cases over the database. Short transactions; no LLM call under a lock."""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from financequest.api.errors import ApiError
from financequest.campaign import clock, dice, focus, ledger, portfolio, rules, xp
from financequest.campaign import reasoning as reasoning_mod
from financequest.campaign.events import append_event, campaign_events, find_by_msg_id
from financequest.campaign.journal import backlog, journal
from financequest.campaign.narration import Narration
from financequest.campaign.pack import Pack, load_pack
from financequest.campaign.view import board_out, gated_content, gated_view, reveal_chart
from financequest.db.models import Decision, Event, Scenario
from financequest.db.models_campaign import (
    CampaignRun,
    Challenge,
    ClueState,
    Debrief,
    Hero,
    HeroItem,
    Location,
    Outcome,
    Player,
    Trade,
    XpAward,
)

PHASES = [
    "setup",
    "play",
    "commit",
    "timeskip",
    "reveal",
    "debrief",
    "reflect",
    "company",
    "xp",
    "done",
]
CONF = {"low": 1, "medium": 2, "high": 3}
BONUS_CLUE = "BONUS-LEAD"
BONUS_TEXT = "A quiet source adds a bonus clue: compare what the ledgers call earnings with the coin that actually moved."


def num(v: Any) -> float | None:
    """A Decimal-computed display value (stored as text) as a JSON number."""
    return None if v is None else float(v)


def _now() -> datetime:
    return datetime.now(UTC)


def phase_at_least(run: CampaignRun, phase: str) -> bool:
    return PHASES.index(run.phase) >= PHASES.index(phase)


def touch(run: CampaignRun) -> None:
    run.version += 1
    run.updated_at = _now()


# ---- hero ---------------------------------------------------------------------------------
def ensure_player(db: Session, sid: uuid.UUID) -> Player:
    p = db.get(Player, sid)
    if p is None:
        p = Player(id=sid)
        db.add(p)
        db.flush()
    return p


def get_hero(db: Session, sid: uuid.UUID) -> Hero | None:
    return db.exec(select(Hero).where(Hero.player_id == sid)).first()


def hero_items(db: Session, hero: Hero) -> set[str]:
    return {i.item_key for i in db.exec(select(HeroItem).where(HeroItem.hero_id == hero.id))}


def hero_history(db: Session, hero: Hero) -> list[dict[str, Any]]:
    out = []
    runs = db.exec(
        select(CampaignRun)
        .where(CampaignRun.hero_id == hero.id, CampaignRun.status == "finished")
        .order_by(CampaignRun.created_at)  # type: ignore[arg-type]
    )
    for r in runs:
        dec = db.exec(select(Decision).where(Decision.campaign_id == r.id)).first()
        oc = db.get(Outcome, r.id)
        award = db.get(XpAward, r.id)
        out.append({
            "campaign_id": str(r.id),
            "interests": r.interests or [],
            "total_xp": award.total if award else 0,
            "decision": dec.action if dec else None,
            "result_pct": num(oc.pnl_pct) if oc else None,
            "finished_at": (award.finished_at if award and award.finished_at else r.created_at)
            .date().isoformat(),
        })  # fmt: skip
    return out


def hero_out(db: Session, hero: Hero, player: Player) -> dict[str, Any]:
    items = hero_items(db, hero)
    return {
        "name": hero.name,
        "class": hero.hero_class,
        "total_xp": hero.total_xp,
        "items": [focus.item_out(k) for k in focus.ITEM_ORDER if k in items],
        "history": hero_history(db, hero),
        "active_campaign_id": str(player.active_campaign_id) if player.active_campaign_id else None,
    }


# ---- loading ------------------------------------------------------------------------------
def owned_run(db: Session, cid: uuid.UUID, sid: uuid.UUID, *, write: bool) -> CampaignRun:
    stmt = select(CampaignRun).where(CampaignRun.id == cid, CampaignRun.player_id == sid)
    run = db.exec(stmt.with_for_update() if write else stmt).first()
    if run is None:
        raise ApiError(404, "not_found", "Campaign not found")
    return run


def pack_of(db: Session, run: CampaignRun) -> Pack:
    return load_pack(db, run.scenario_id)


def load(
    db: Session, cid: uuid.UUID, sid: uuid.UUID, write: bool = True
) -> tuple[CampaignRun, Pack, Hero]:
    """The campaign of this session (row-locked when ``write``), its pack and its hero."""
    run = owned_run(db, cid, sid, write=write)
    if run.status == "abandoned":
        raise ApiError(404, "not_found", "Campaign not found")
    hero = db.get(Hero, run.hero_id)
    assert hero is not None
    return run, pack_of(db, run), hero


def found_ids(db: Session, cid: uuid.UUID) -> set[str]:
    return {c.clue_id for c in db.exec(select(ClueState).where(ClueState.campaign_id == cid))}


def locations(db: Session, cid: uuid.UUID) -> list[Location]:
    return list(db.exec(select(Location).where(Location.campaign_id == cid)))


def challenges(db: Session, cid: uuid.UUID) -> list[Challenge]:
    return list(db.exec(select(Challenge).where(Challenge.campaign_id == cid)))


def location_by_key(db: Session, cid: uuid.UUID, key: str) -> Location | None:
    return db.exec(select(Location).where(Location.campaign_id == cid, Location.key == key)).first()


def decision_of(db: Session, cid: uuid.UUID) -> Decision | None:
    return db.exec(select(Decision).where(Decision.campaign_id == cid)).first()


# ---- clues, arrival, news -------------------------------------------------------------------
def grant_clue(db: Session, run: CampaignRun, pack: Pack, clue_id: str, source: str) -> bool:
    exists = db.exec(
        select(ClueState).where(ClueState.campaign_id == run.id, ClueState.clue_id == clue_id)
    ).first()
    if exists:
        return False
    ev = append_event(db, run, "clue_found", _clue_payload(pack, clue_id, source))
    db.add(ClueState(campaign_id=run.id, clue_id=clue_id, found_at_seq=ev.seq, source=source))
    db.flush()
    return True


def _clue_payload(pack: Pack, clue_id: str, source: str) -> dict[str, Any]:
    e = pack.evidence_by_id(clue_id)
    if e is None:
        return {"clue_id": clue_id, "title": "A bonus lead", "text": BONUS_TEXT, "source": source}
    return {"clue_id": clue_id, "title": e.title, "text": e.text, "source": source}


def grant_free_at(db: Session, run: CampaignRun, pack: Pack, loc_key: str) -> list[str]:
    gv = gated_view(run)
    gated = rules.gated_clue_ids(pack)
    got = []
    for e in pack.evidence:
        if (
            gv.at_checkpoint(e.checkpoint)
            and e.id not in gated
            and rules.normalize_location(e.location) == loc_key
            and grant_clue(db, run, pack, e.id, "location")
        ):
            got.append(e.id)
    return got


def arrive(db: Session, run: CampaignRun, pack: Pack, loc: Location) -> tuple[list[str], bool]:
    first = not loc.visited
    run.current_location_id = loc.id
    loc.visited = True
    db.add(loc)
    return grant_free_at(db, run, pack, loc.key), first


def fire_news(db: Session, run: CampaignRun, pack: Pack) -> dict[str, Any]:
    assert pack.news is not None
    run.news_shown = True
    before = run.clock_day
    run.checkpoint, run.clock_day = clock.after_news(pack, run.clock_day)
    card = {
        "kind": "news",
        "headline": pack.news["headline"],
        "summary": pack.news["summary"],
        "time_skip_label": clock.time_skip_label(pack, before, run.clock_day),
        "story_day": run.clock_day,
    }
    append_event(db, run, "news", card)
    for eid in pack.news.get("evidence_ids", []):
        if pack.evidence_by_id(eid):
            grant_clue(db, run, pack, eid, "news")
    cur = db.get(Location, run.current_location_id) if run.current_location_id else None
    if cur:
        grant_free_at(db, run, pack, cur.key)
    return card


def count_turn(
    db: Session, run: CampaignRun, pack: Pack, kind: str, arrived_at: str | None = None
) -> dict[str, Any] | None:
    if rules.counts_as_turn(kind):
        run.turn_count += 1
    if rules.should_fire_news(run.news_shown, run.turn_count, arrived_at):
        return fire_news(db, run, pack)
    return None


def investigation_done(db: Session, run: CampaignRun, pack: Pack) -> bool:
    """Enough evidence for the day of decision (the rule before decisions ran all game long)."""
    gv = gated_view(run)
    return rules.can_decide(
        pack, gv.at_checkpoint, found_ids(db, run.id), run.opening_done, run.pending, run.news_shown
    )


def decide_ready(db: Session, run: CampaignRun, pack: Pack) -> bool:
    """Ready to seal the forecast: the investigation is done and the player has answered the
    decision-day scene in their own words."""
    if run.market_scene:
        return False
    return investigation_done(db, run, pack) and any(t.beat == "decision" for t in trades_of(db, run.id))


# ---- decisions throughout the campaign ----------------------------------------------------------
OPENING_TURNS = 2  # the opening offer comes after the hero has looked around a little
STORY_SCENES_MAX = 2  # scenes the Campaign Master may open on its own


def trades_of(db: Session, cid: uuid.UUID) -> list[Trade]:
    return list(db.exec(select(Trade).where(Trade.campaign_id == cid).order_by(Trade.seq)))  # type: ignore[arg-type]


def position_of(run: CampaignRun, trades: list[Trade]) -> ledger.Position:
    lost = Decimal(run.loss_unapplied_cents) / 100  # damage taken since the last decision
    if not trades:
        return ledger.Position(Decimal(run.hp_start * 10) - lost)
    last = trades[-1]
    return ledger.Position(Decimal(last.cash_after_cents) / 100 - lost, Decimal(last.shares_after))


# ---- damage: HP is the budget bar (1 HP = 10 euros) -------------------------------------------
HP_EUR = 10
LOAN_TEXT = "Loan from "
MAX_HP_LOSS_TURN = 10  # a schema bound only: one model reply cannot take more than this


def hp_now(run: CampaignRun) -> int:
    return run.hp_start - run.hp_lost


def budget_now(run: CampaignRun) -> Decimal:
    """The investable budget: starting purse minus the damage taken (what lock and the result
    maths use)."""
    return Decimal(hp_now(run) * HP_EUR)


def hp_change_out(delta: int, reason: str, run: CampaignRun) -> dict[str, Any]:
    hp = hp_now(run)
    return {"delta": delta, "reason": reason, "hp": hp, "hp_eur": hp * HP_EUR}


def apply_hp_loss(
    db: Session, run: CampaignRun, pack: Pack, loss: int, reason: str
) -> dict[str, Any] | None:
    """Applies what the Campaign Master asked for: at most 10 HP a turn, never below 0 HP, never
    more than the hero owns, never once the decision is locked. No other floor or total cap.

    Cash in the purse pays first. What cash cannot cover comes out of the drafted position: a
    ``loss`` trade removes those coins at the board price (the money is gone, not paid into the
    purse), so the budget really drops. Persists the run fields and an ``hp_change`` event."""
    if run.phase not in ("play", "commit"):
        return None
    trades = trades_of(db, run.id)
    pos = position_of(run, trades)
    row = ledger.fill_row(pack.rows, run.clock_day)
    cash = max(pos.cash, portfolio.ZERO)
    owned = cash + pos.value(row.close)
    n = max(0, min(int(loss), MAX_HP_LOSS_TURN, hp_now(run), int(owned // HP_EUR)))
    if n <= 0:
        return None
    loss_eur = Decimal(n * HP_EUR)
    short = loss_eur - min(loss_eur, cash)
    run.hp_lost += n
    if short > 0:  # cash is gone: the rest is taken from the invested coins
        sold = min(short / row.close, pos.shares)
        db.add(Trade(
            campaign_id=run.id, seq=len(trades) + 1, beat="damage", story_day=run.clock_day,
            fill_day=row.day, text=reason.strip()[:200], action="loss",
            amount_cents=int(portfolio.q_cents(short) * 100), shares=str(-sold),
            price=str(row.close), cash_after_cents=0, shares_after=str(pos.shares - sold),
        ))  # fmt: skip
        run.loss_unapplied_cents = 0  # folded into the loss trade's cash_after
        db.flush()
    else:
        run.loss_unapplied_cents += n * HP_EUR * 100
    out = hp_change_out(-n, reason.strip(), run)
    append_event(db, run, "hp_change", out)
    return out


def _eur(x: Decimal) -> float:
    return float(portfolio.q_cents(x))


def purse(db: Session, run: CampaignRun, pack: Pack) -> dict[str, Any]:
    """Cash and the value of the coins in the company at today's board price (euros only)."""
    pos = position_of(run, trades_of(db, run.id))
    price = ledger.fill_row(pack.rows, run.clock_day).close
    held = pos.value(price)
    out: dict[str, Any] = {
        "cash_eur": _eur(pos.cash), "position_eur": _eur(held), "total_eur": _eur(pos.cash + held),
        "loan": None,
    }
    loan = loan_of(trades_of(db, run.id))
    if loan is not None:
        out["loan"] = loan_out(loan)
        out["net_eur"] = _eur(pos.cash + held - loan.repay)  # what they own once the loan is repaid
    return out


# ---- the loan of an all-in plot (a Trade row with action "loan") ----------------------------------
@dataclass(frozen=True)
class Loan:
    lender: str
    principal: Decimal
    repay: Decimal  # principal plus the flat interest, due at the end of the horizon


def loan_of(trades: list[Trade]) -> Loan | None:
    row = next((t for t in trades if t.action == "loan"), None)
    if row is None:
        return None
    return Loan(row.text.removeprefix(LOAN_TEXT), Decimal(row.amount_cents) / 100, Decimal(row.price or 0))


def loan_out(loan: Loan) -> dict[str, Any]:
    return {
        "lender": loan.lender, "principal_eur": _eur(loan.principal), "repay_eur": _eur(loan.repay),
        "interest_eur": _eur(loan.repay - loan.principal),
        "label": f"Loan from {loan.lender}: +€{_eur(loan.principal):g} now, repay €{_eur(loan.repay):g} at the end",
    }


def loan_terms(run: CampaignRun) -> dict[str, Any]:
    """What a moneylender may offer: up to half the starting budget, flat interest, repaid at the
    end of the horizon. Pure engine figures."""
    principal = Decimal(run.hp_start * HP_EUR * rules.LOAN_PRINCIPAL_PCT // 100)
    repay = portfolio.q_cents(principal * (100 + rules.LOAN_INTEREST_PCT) / 100)
    return {"principal_eur": float(principal), "interest_pct": rules.LOAN_INTEREST_PCT,
            "repay_eur": float(repay), "due": "at the end of the horizon"}  # fmt: skip


def scenes_opened(db: Session, cid: uuid.UUID) -> list[str]:
    """Beats of the scenes opened so far. A decision scene the player passed (they went elsewhere)
    does not count as held: it is owed again, so the forecast can still be sealed."""
    held: list[str] = []
    for e in campaign_events(db, cid):
        beat = str((e.payload or {}).get("beat"))
        if e.type == "market_scene":
            held.append(beat)
        elif e.type == "scene_passed" and beat == "decision" and "decision" in held:
            held.remove("decision")
    return held


def due_beat(db: Session, run: CampaignRun, pack: Pack, *, news_now: bool, asked: bool,
             story_call: bool) -> str | None:  # fmt: skip
    """The decision scene the story calls for now, if any. One scene at a time; each story beat
    once; never in the same turn as the news (the news gets its own moment first)."""
    if run.phase != "play" or run.market_scene or run.pending or news_now:
        return None
    held = scenes_opened(db, run.id)
    passed = any(e.type == "scene_passed" and (e.payload or {}).get("beat") == "decision"
                 for e in campaign_events(db, run.id))  # fmt: skip
    if "decision" not in held and investigation_done(db, run, pack) and (
        asked or (run.news_shown and not passed)  # a passed decision comes back only when asked
    ):
        return "decision"
    if "decision" in held:
        return None
    if run.news_shown and "news" not in held:
        return "news"
    if not run.news_shown and "opening" not in held and run.opening_done \
            and run.turn_count >= OPENING_TURNS:
        return "opening"
    if story_call and held.count("story") < STORY_SCENES_MAX:
        return "story"
    return None


def open_scene(db: Session, run: CampaignRun, pack: Pack, beat: str) -> dict[str, Any]:
    scene = {"beat": beat, "story_day": run.clock_day}
    run.market_scene = scene
    append_event(db, run, "market_scene", {**scene, "purse": purse(db, run, pack)})
    return scene


DECISION_HOW_MUCH = ["A quarter of my coins", "Half of my coins", "All of my coins"]


def decision_problem(
    db: Session, run: CampaignRun, action: str, amount_eur: int | None, portion: str | None
) -> str | None:
    """Why a written decision cannot be executed as it stands (engine text), else None."""
    if action == "hold":
        return None
    pos = position_of(run, trades_of(db, run.id))
    if action == "sell" and pos.shares <= 0:
        return "You have no coins in the company to take out. Do you put some in, or wait?"
    if action == "buy" and pos.cash <= 0:
        return "Your purse is empty: every coin is already in the company. Do you hold, or take some out?"
    if amount_eur is None and portion is None:
        verb = "put in" if action == "buy" else "take out"
        return f"How much do you {verb}: a sum of coins, or a share such as half?"
    return None


def scene_out(run: CampaignRun) -> dict[str, Any] | None:
    """The open decision scene for the screen: its beat and, once framed, the narration."""
    s = run.market_scene if isinstance(run.market_scene, dict) else None
    if s is None:
        return None
    return {"beat": s.get("beat"), "story_day": s.get("story_day"), "text": s.get("text"),
            "suggestions": s.get("suggestions") or []}  # fmt: skip


# ---- the all-in plot: nothing left at stake -------------------------------------------------------
def last_reasoning(trades: list[Trade]) -> str | None:
    """The player's latest stated reasons for a trade of theirs (never an engine row)."""
    return next((t.reasoning for t in reversed(trades)
                 if t.reasoning and t.action in ("buy", "sell", "hold")), None)  # fmt: skip


def is_all_in(db: Session, run: CampaignRun, pack: Pack) -> bool:
    """Everything is in the company: free cash is at most 2% of the starting budget."""
    if run.phase not in ("play", "commit"):
        return False
    p = purse(db, run, pack)
    return p["position_eur"] > 0 and p["cash_eur"] <= run.hp_start * HP_EUR * rules.ALL_IN_CASH_PCT / 100


def offers_made(db: Session, cid: uuid.UUID) -> int:
    return sum(1 for e in campaign_events(db, cid) if e.type == "all_in_offer")


def story_ahead(run: CampaignRun) -> bool:
    """There are unrevealed checkpoints ahead: the news has not broken yet."""
    return not run.news_shown


def nothing_at_stake(db: Session, run: CampaignRun, pack: Pack, trade: Trade, text: str) -> str | None:
    """What the player's latest decision did to the plot: ``"offer"`` (all in, the story still has
    ahead of it, no offer made yet), ``"fast_forward"`` (all in or all out with nothing left to
    play for, or an offer was already made), or None."""
    if run.phase != "play":
        return None
    trades = trades_of(db, run.id)
    out_for_good = (
        trade.action == "sell" and Decimal(trade.shares_after) <= 0 and rules.says_done(text)
        and any(t.action == "buy" for t in trades)
    )  # fmt: skip
    if out_for_good:
        return "fast_forward"
    if not is_all_in(db, run, pack):
        return None
    if offers_made(db, run.id) == 0:
        return "offer" if story_ahead(run) else "fast_forward"
    if any(t.beat == "offer" for t in trades):
        return None  # they took the offer: the plot goes on as before
    return "fast_forward"


def offer_facts(db: Session, run: CampaignRun, pack: Pack) -> dict[str, Any]:
    """The engine's figures for the two offers the Master may make (euros only)."""
    p = purse(db, run, pack)
    return {
        "buyback": {"max_eur": p["position_eur"], "price": "today's board price",
                    "default_portion": "half"},
        "loan": loan_terms(run),
    }  # fmt: skip


def open_offer(
    db: Session, run: CampaignRun, pack: Pack, kind: str, by: dict[str, str], text: str,
) -> dict[str, Any]:
    """The Master's offer becomes the open scene: terms from the engine, never from the model."""
    terms = offer_facts(db, run, pack)[kind]
    offer = {"kind": kind, "by": by, "terms": terms}
    run.market_scene = {"beat": "offer", "story_day": run.clock_day, "text": text, "offer": offer,
                        "ignored": 0}  # fmt: skip
    append_event(db, run, "all_in_offer", {"beat": "offer", "kind": kind, "by": by, "terms": terms})
    return offer


def offer_out(run: CampaignRun) -> dict[str, Any] | None:
    s = run.market_scene if isinstance(run.market_scene, dict) else None
    return dict(s["offer"]) if s and s.get("beat") == "offer" and s.get("offer") else None


def note_offer_ignored(db: Session, run: CampaignRun, text: str) -> int:
    """The player did something else in front of the open offer; returns how often so far."""
    s = dict(run.market_scene or {})
    s["ignored"] = int(s.get("ignored", 0)) + 1
    run.market_scene = s
    append_event(db, run, "offer_ignored", {"text": text, "count": s["ignored"]})
    return int(s["ignored"])


def accept_loan(db: Session, run: CampaignRun, pack: Pack, text: str) -> Trade:
    """The player takes the moneylender's loan: the principal joins the purse now, the repayment
    comes off the final result. Stored as a ``loan`` trade (price holds the repayment in euros)."""
    offer = offer_out(run)
    assert offer is not None and offer["kind"] == "loan"
    terms = offer["terms"]
    amount = Decimal(rules.loan_amount(text, int(terms["principal_eur"])))
    repay = portfolio.q_cents(amount * (100 + rules.LOAN_INTEREST_PCT) / 100)
    trades = trades_of(db, run.id)
    pos = position_of(run, trades)
    trade = Trade(
        campaign_id=run.id, seq=len(trades) + 1, beat="offer", story_day=run.clock_day,
        fill_day=None, text=f"{LOAN_TEXT}{offer['by']['name']}", action="loan",
        amount_cents=int(amount * 100), shares="0", price=str(repay),
        cash_after_cents=int(portfolio.q_cents(pos.cash + amount) * 100),
        shares_after=str(pos.shares),
    )  # fmt: skip
    db.add(trade)
    run.market_scene = None
    run.loss_unapplied_cents = 0  # folded into cash_after, as for any trade
    db.flush()
    append_event(db, run, "trade", {
        "seq": trade.seq, "beat": trade.beat, "action": trade.action,
        "amount_eur": trade.amount_cents / 100, "story_day": trade.story_day,
        "purse": purse(db, run, pack),
    })  # fmt: skip
    return trade


def record_decision(
    db: Session, run: CampaignRun, pack: Pack, text: str, action: str,
    amount_eur: int | None, portion: str | None,
    reasoning: str | None = None, reasoning_sufficient: bool = False,
) -> Trade:  # fmt: skip
    """Executes the player's written decision at once and closes the scene. A sufficient reason is
    stored as ``inline``; a missing or thin one leaves the trade ``awaiting`` the one follow-up."""
    scene = run.market_scene if isinstance(run.market_scene, dict) else {"beat": "story"}
    trades = trades_of(db, run.id)
    pos = position_of(run, trades)
    row = ledger.fill_row(pack.rows, run.clock_day)
    amount = ledger.resolve_amount(action, pos, row.close, amount_eur, portion)
    fill = ledger.execute(pos, action, amount, row)
    trade = Trade(
        campaign_id=run.id, seq=len(trades) + 1, beat=str(scene.get("beat", "story")),
        story_day=run.clock_day, fill_day=fill.fill_day, text=text, action=fill.action,
        amount_cents=int(portfolio.q_cents(fill.amount) * 100), shares=str(fill.shares),
        price=str(fill.price), cash_after_cents=int(portfolio.q_cents(fill.after.cash) * 100),
        shares_after=str(fill.after.shares),
    )  # fmt: skip
    reasoning = (reasoning or "").strip()[:1000] or None
    trade.reasoning = reasoning
    trade.reasoning_source = "inline" if reasoning and reasoning_sufficient else reasoning_mod.AWAITING
    db.add(trade)
    run.market_scene = None
    run.loss_unapplied_cents = 0  # the damage is now part of this trade's cash_after
    db.flush()
    append_event(db, run, "trade", {
        "seq": trade.seq, "beat": trade.beat, "action": trade.action,
        "amount_eur": trade.amount_cents / 100, "story_day": trade.story_day,
        "purse": purse(db, run, pack),
    })  # fmt: skip
    if trade.reasoning_source == "inline":
        append_event(db, run, "decision_reasoning", {
            "seq": trade.seq, "reasoning": trade.reasoning, "source": "inline", "skipped": False,
        })  # fmt: skip
    return trade


def awaiting_trade(db: Session, run: CampaignRun) -> Trade | None:
    """The decision whose one follow-up question is open (only while the campaign is in play)."""
    if run.phase != "play":
        return None
    return db.exec(
        select(Trade).where(
            Trade.campaign_id == run.id, Trade.reasoning_source == reasoning_mod.AWAITING
        ).order_by(Trade.seq.desc())  # type: ignore[attr-defined]
    ).first()


def resolve_reasoning(
    db: Session, run: CampaignRun, trade: Trade, text: str | None, *, skipped: bool
) -> Trade:
    """Closes the follow-up: the player's next words verbatim (appended to a thin first reason),
    or skipped. Asked once per decision, never again."""
    thin = trade.reasoning
    if skipped or not (text or "").strip():
        trade.reasoning_source = "skipped"  # a thin reason already given is kept
    else:
        said = text.strip()[:1000]  # type: ignore[union-attr]
        trade.reasoning = f"{thin}. {said}" if thin else said
        trade.reasoning_source = "asked"
    db.add(trade)
    append_event(db, run, "decision_reasoning", {
        "seq": trade.seq, "reasoning": trade.reasoning, "source": trade.reasoning_source,
        "skipped": trade.reasoning_source == "skipped",
    })  # fmt: skip
    return trade


def reasoning_fields(source: str | None, reasoning: str | None) -> dict[str, Any]:
    return {"reasoning": reasoning, "reasoning_source": None if source == reasoning_mod.AWAITING else source}


def decisions_out(db: Session, run: CampaignRun, pack: Pack) -> list[dict[str, Any]]:
    """The player's decisions in euros; once the decision is locked, each one's effect too."""
    locked = phase_at_least(run, "timeskip")
    out = []
    for t in trades_of(db, run.id):
        row: dict[str, Any] = {
            "seq": t.seq, "beat": t.beat, "story_day": t.story_day,
            "day_label": clock.day_label(t.story_day), "text": t.text, "action": t.action,
            "amount_eur": t.amount_cents / 100,
            "cash_after_eur": t.cash_after_cents / 100,
            **reasoning_fields(t.reasoning_source, t.reasoning),
        }  # fmt: skip
        if locked:
            eff = ledger.effect(t.action, Decimal(t.amount_cents) / 100, Decimal(t.shares), pack.end_close)
            row["effect_eur"] = _eur(eff)
        out.append(row)
    return out


def require_phase(run: CampaignRun, *phases: str) -> None:
    if run.phase not in phases:
        raise ApiError(409, "wrong_phase", f"Not allowed in phase {run.phase}")


# ---- creating a campaign ----------------------------------------------------------------------
def pick_scenario(
    db: Session, scenario_id: uuid.UUID | None = None, sid: uuid.UUID | None = None
) -> tuple[Scenario, Pack]:
    from financequest.db.models import ScenarioSecret

    if scenario_id is not None:  # a personal quest chosen by the player
        from financequest.campaign.pack import build_pack
        from financequest.personal.jobs import owns_scenario

        sc = db.get(Scenario, scenario_id)
        sec = db.get(ScenarioSecret, scenario_id)
        if sc is None or sec is None or sc.status != "playable":
            raise ApiError(404, "no_scenario", "This quest is not available")
        if sid is not None and not owns_scenario(db, sid, scenario_id):
            raise ApiError(404, "no_scenario", "This quest is not available")
        return sc, build_pack(sc, sec)

    rows = list(db.exec(select(Scenario).where(Scenario.status == "playable")))
    rows.sort(key=lambda s: (
        s.source != "reference_pack",
        not (isinstance(s.manifest, dict) and s.manifest.get("pack_id") == "FQ-AV-001"),
    ))  # fmt: skip
    for sc in rows:
        sec = db.get(ScenarioSecret, sc.id)
        if sec is None:
            continue
        try:
            from financequest.campaign.pack import build_pack

            return sc, build_pack(sc, sec)
        except Exception:  # noqa: BLE001 - skip scenarios that cannot be adapted
            continue
    raise ApiError(404, "no_scenario", "No playable scenario")


def create_campaign(
    db: Session, sid: uuid.UUID, interests: list[str], scenario_id: uuid.UUID | None = None
) -> CampaignRun:
    hero = get_hero(db, sid)
    if hero is None:
        raise ApiError(409, "hero_required", "Create your hero first")
    player = db.exec(select(Player).where(Player.id == sid).with_for_update()).one()
    if player.active_campaign_id:
        active = db.get(CampaignRun, player.active_campaign_id)
        if active and active.status == "active":
            raise ApiError(
                409, "campaign_in_progress", "A quest is already in progress",
                campaign_id=str(active.id),
            )  # fmt: skip
    sc, pack = pick_scenario(db, scenario_id, sid)
    cls = rules.CLASSES[hero.hero_class]
    cp, day = clock.initial_state(pack)
    run = CampaignRun(
        player_id=sid, hero_id=hero.id, scenario_id=sc.id, interests=interests, checkpoint=cp,
        clock_day=day, focus_left=focus.starting_focus(hero_items(db, hero)),
        rerolls_left=cls["rerolls"], keen_eye_left=cls["keen_eye"], hp_start=cls["hp"],
        rng_seed=random.SystemRandom().randrange(1, 2**31 - 1),
    )  # fmt: skip
    db.add(run)
    db.flush()
    fixed = [
        ("tavern", "Tavern", f"Where every journey starts in {pack.setting}."),
        (
            "market_square",
            "Market Square",
            f"The {pack.market_name}: the price board and the crowd.",
        ),
        ("library", "Library", "The archive: ledgers, announcements and the company card."),
    ]
    for key, name, desc in fixed:
        db.add(Location(campaign_id=run.id, key=key, fixed=True, name=name, description=desc))
    for seed in pack.seeds:
        db.add(Location(
            campaign_id=run.id, key=seed["key"], fixed=False, name=seed["name"],
            description=seed["description"], art_subject=seed.get("art_subject"),
        ))  # fmt: skip
    for enc in pack.encounters:
        db.add(Challenge(
            campaign_id=run.id, key=enc.id, title=enc.title, kind=enc.kind or "encounter",
            dc=rules.encounter_dc(enc), checkpoint=enc.checkpoint,
            location_key=rules.normalize_location(enc.location), clue_id=enc.clue_id,
            alt_source=enc.failure_forward,
        ))  # fmt: skip
    db.flush()
    tavern = location_by_key(db, run.id, "tavern")
    assert tavern is not None
    arrive(db, run, pack, tavern)
    player.active_campaign_id = run.id
    db.add(player)
    db.commit()
    return run


def abandon_campaign(db: Session, cid: uuid.UUID, sid: uuid.UUID) -> None:
    run = owned_run(db, cid, sid, write=True)
    if run.status != "active":
        return
    player = db.exec(select(Player).where(Player.id == sid).with_for_update()).one()
    if player.active_campaign_id == run.id:
        player.active_campaign_id = None
        db.add(player)
    run.status = "abandoned"
    touch(run)
    db.add(run)
    db.commit()


# ---- rolls ------------------------------------------------------------------------------------
def challenge_of(db: Session, run: CampaignRun, rid: uuid.UUID) -> Challenge:
    ch = db.get(Challenge, rid)
    if ch is None or ch.campaign_id != run.id:
        raise ApiError(404, "not_found", "Challenge not found")
    return ch


def adhoc_clue(
    db: Session, run: CampaignRun, pack: Pack, loc_key: str, target: str, skill: str
) -> str | None:
    """The one real, unlocked, not-yet-found clue an ad-hoc success may reveal, or None (then the
    Master tells a useful non-evidence detail). Never a dice-gated clue (those have their own
    challenge), never a locked one, never one found or already promised to another check. A
    person's own clues come first when the check is aimed at them."""
    gv = gated_view(run)
    gated = rules.gated_clue_ids(pack)
    taken = found_ids(db, run.id) | {
        c.clue_id for c in challenges(db, run.id)
        if rules.is_adhoc(c.kind) and c.clue_id and c.result != "setback"
    }
    chars = [
        c for c in pack.characters
        if rules.normalize_location(c.location) == loc_key
    ]
    def held(c: Any) -> list[str]:
        return [i for cp, ids in c.may_reveal.items() if gv.at_checkpoint(cp) for i in ids]
    named = [c for c in chars if c.name.lower() in target.lower()]
    pools: list[list[str]] = [held(c) for c in named]
    pools.append([
        e.id for e in pack.evidence
        if rules.normalize_location(e.location) == loc_key and gv.at_checkpoint(e.checkpoint)
    ])
    if not named:
        pools += [held(c) for c in chars]
    for pool in pools:
        for cid in pool:
            e = pack.evidence_by_id(cid)
            if e is not None and cid not in taken and cid not in gated \
                    and gv.at_checkpoint(e.checkpoint):
                return cid
    return None


def create_adhoc_challenge(
    db: Session, run: CampaignRun, pack: Pack, check: dict[str, Any], loc_key: str
) -> Challenge | None:
    """Opens the dice check for an ad-hoc skill attempt. None when the same skill + target was
    already attempted at this place (campaign + key is unique), or the check is malformed."""
    skill = str(check.get("skill") or "")
    target = " ".join(str(check.get("target") or "").split())[:80]
    if skill not in rules.SKILLS or not target or not loc_key:
        return None
    key = rules.adhoc_key(skill, target, loc_key)
    if db.exec(select(Challenge).where(Challenge.campaign_id == run.id, Challenge.key == key)).first():
        return None
    ch = Challenge(
        campaign_id=run.id, key=key, title=target[:1].upper() + target[1:],
        kind=f"{rules.ADHOC_KIND}{skill}", dc=rules.adhoc_dc(str(check.get("difficulty"))),
        checkpoint=run.checkpoint, location_key=loc_key, optional=True,
        clue_id=adhoc_clue(db, run, pack, loc_key, target, skill),
        alt_source=" ".join(str(check.get("stakes") or "").split())[:120] or None,
    )  # fmt: skip
    db.add(ch)
    db.flush()
    return ch


def _roll_payload(
    ch: Challenge, run: CampaignRun, final: bool, options: tuple[str, ...]
) -> dict[str, Any]:
    dice_ = ch.dice or []
    return {
        "roll_id": str(ch.id), "challenge_id": str(ch.id), "title": ch.title, "dice": dice_,
        "used": max(dice_) if dice_ else None, "bonus": dice.BONUS, "total": ch.total, "dc": ch.dc,
        "result": ch.result, "final": final, "options": list(options), "rerolled": ch.rerolled,
        "rerolls_left": run.rerolls_left, "keen_eye_left": run.keen_eye_left,
        "alt_source": ch.alt_source if ch.result == "setback" and not rules.is_adhoc(ch.kind) else None,
        "skill": rules.adhoc_skill(ch.kind),
    }  # fmt: skip


def _finalize(db: Session, run: CampaignRun, pack: Pack, ch: Challenge) -> None:
    ch.state = "final"
    run.pending = None
    if ch.result == "success":
        if ch.clue_id:
            grant_clue(db, run, pack, ch.clue_id, "dice")
    elif not rules.is_adhoc(ch.kind):  # an ad-hoc check never guards key evidence
        e = pack.evidence_by_id(ch.clue_id or "")
        if e is not None and e.key:  # failure-forward: key evidence is never behind luck
            grant_clue(db, run, pack, e.id, "failure_forward")
    db.add(ch)


def offer_roll(run: CampaignRun, ch: Challenge, hero: Hero) -> dict[str, Any]:
    run.pending = {"type": "roll", "challenge_id": str(ch.id), "state": "offered"}
    return {
        "kind": "dice", "roll_id": str(ch.id), "challenge_id": str(ch.id), "title": ch.title,
        "dc": ch.dc, "bonus": dice.BONUS,
        "keen_eye_available": hero.hero_class == "investigator" and run.keen_eye_left > 0,
        "keen_eye_left": run.keen_eye_left,
        "skill": rules.adhoc_skill(ch.kind),
    }  # fmt: skip


def do_roll(
    db: Session, run: CampaignRun, pack: Pack, hero: Hero, ch: Challenge, mode: str
) -> dict[str, Any]:
    require_phase(run, "play")
    if ch.state == "final":
        raise ApiError(409, "already_resolved", "The information must come from another source.",
                       alt_source=ch.alt_source)  # fmt: skip
    if ch.state == "rolling":
        raise ApiError(409, "roll_open", "Reroll or accept the setback first")
    if not gated_view(run).at_checkpoint(ch.checkpoint):
        raise ApiError(409, "not_available", "That challenge is not available yet")
    pend = run.pending
    if pend and pend.get("challenge_id") != str(ch.id):
        raise ApiError(409, "roll_open", "Another dice check is open")
    advantage = mode == "advantage"
    if advantage:
        if hero.hero_class != "investigator" or run.keen_eye_left < 1:
            raise ApiError(409, "no_keen_eye", "Keen Eye is not available")
        run.keen_eye_left -= 1
        append_event(db, run, "keen_eye", {"challenge_id": str(ch.id)})
    r = dice.roll(run.rng_seed, ch.key, 0, ch.dc, advantage)
    ch.dice, ch.total, ch.result, ch.roll_index = list(r.dice), r.total, r.result, 0
    opts = rules.roll_options(r.success, hero.hero_class, run.rerolls_left, False)
    if opts.final:
        _finalize(db, run, pack, ch)
    else:
        ch.state = "rolling"
        run.pending = {"type": "roll", "challenge_id": str(ch.id), "state": "rolling"}
    db.add(ch)
    out = _roll_payload(ch, run, opts.final, opts.options)
    append_event(db, run, "dice_roll", out)
    return out


def do_reroll(
    db: Session, run: CampaignRun, pack: Pack, hero: Hero, ch: Challenge
) -> dict[str, Any]:
    if ch.state != "rolling" or hero.hero_class != "analyst" or run.rerolls_left < 1:
        raise ApiError(409, "no_reroll", "Second Look is not available")
    run.rerolls_left -= 1
    r = dice.roll(run.rng_seed, ch.key, 1, ch.dc, False)
    ch.dice, ch.total, ch.result, ch.roll_index, ch.rerolled = (
        list(r.dice),
        r.total,
        r.result,
        1,
        True,
    )
    append_event(db, run, "reroll", {"challenge_id": str(ch.id)})
    _finalize(db, run, pack, ch)
    out = _roll_payload(ch, run, True, ("continue",))
    append_event(db, run, "dice_roll", out)
    return out


def do_accept(db: Session, run: CampaignRun, pack: Pack, ch: Challenge) -> dict[str, Any]:
    if ch.state != "rolling":
        raise ApiError(409, "no_open_roll", "No setback to accept")
    _finalize(db, run, pack, ch)
    out = _roll_payload(ch, run, True, ("continue",))
    append_event(db, run, "dice_roll", out)
    return out


# ---- commit and lock --------------------------------------------------------------------------
def validate_commit(
    body: dict[str, Any], run: CampaignRun, pack: Pack
) -> tuple[dict[str, Any], dict[str, str]]:
    """The seal asks only for the forecast and the confidence: what the player did with their coins
    comes from the decisions they wrote during the campaign. An optional closing note may add to
    their reasoning; ``action`` and ``amount_eur`` from older clients are ignored."""
    errs: dict[str, str] = {}
    text = str(body.get("evidence") or "").strip()
    fp = body.get("forecast_pct")
    if isinstance(fp, bool) or not isinstance(fp, int | float) or fp % 5 or not 0 <= fp <= 100:
        errs["forecast_pct"] = "Pick a forecast from 0% to 100% in steps of 5%."
    conf = body.get("confidence")
    if conf not in CONF:
        errs["confidence"] = "Choose Low, Medium or High."
    return {"evidence": text, "forecast_pct": fp, "confidence": conf}, errs


def ledger_result(run: CampaignRun, pack: Pack, trades: list[Trade]) -> ledger.LedgerResult:
    """The final result of every decision together, valued at the horizon close."""
    loan = loan_of(trades)
    return ledger.result(
        budget_now(run), position_of(run, trades), pack.end_close,
        loan.principal if loan else portfolio.ZERO, loan.repay if loan else portfolio.ZERO,
    )


def evidence_text(trades: list[Trade], note: str) -> str:
    """The player's own words across the campaign: every decision, then the closing note."""
    lines = [t.text for t in trades if t.beat != "damage" and t.action != "loan"]  # not the player's words
    return "\n".join([*lines, note] if note else lines)


def reveal_payload(
    db: Session, run: CampaignRun, pack: Pack, dec: Decision, oc: Outcome
) -> dict[str, Any]:
    """Outcome of a locked decision (POST lock and GET reveal): story labels and numbers only;
    ``locked_at`` is the story moment, never the wall-clock time."""
    r = portfolio.investment_return(pack.buy_open, pack.end_close)
    loan = loan_of(trades_of(db, run.id))
    return {
        "locked_at": f"{clock.day_label(pack.decision_day)}, evening",
        "horizon_days": pack.horizon_days,
        "horizon_label": clock.horizon_label(pack),
        "time_skip_label": clock.horizon_skip_label(pack),
        "decision_day": pack.decision_day,
        "series": reveal_chart(pack),
        "action": dec.action,
        "amount_eur": (dec.amount_cents or 0) // 100,
        "breakdown": {
            "starting_budget": float(budget_now(run).quantize(portfolio.CENTS)),
            "cash_kept": num(oc.cash), "invested": num(oc.invested), "value_now": num(oc.value_now),
            "fees": num(oc.fees), "final_value": num(oc.final), "pl_eur": num(oc.pnl),
            "pl_pct": num(oc.pnl_pct),
            "loan_repay_eur": float(loan.repay) if loan else 0.0,
            "loan": loan_out(loan) if loan else None,
        },
        "hp_before": oc.hp_before,
        "hp_after": oc.hp_after,
        "investment_return_pct": num(portfolio.q_pct(r * 100)),
        "currency_note": portfolio.CURRENCY_NOTE,
        "phase": run.phase,
        "decisions": decisions_out(db, run, pack),
        "final_reasoning": reasoning_fields(dec.reasoning_source, dec.reasoning),
    }  # fmt: skip


AUTO_LOCK: dict[str, Any] = {"evidence": "", "forecast_pct": 50, "confidence": "low"}  # a fast-forward seals neutrally


def lock_decision(
    db: Session, run: CampaignRun, pack: Pack, body: dict[str, Any], *, auto: bool = False
) -> tuple[Decision, Outcome]:
    """Seals the position. ``auto`` is the all-in plot's fast-forward: the position as it stands is
    sealed without the form (neutral forecast), keeping the player's own reasoning."""
    existing = decision_of(db, run.id)
    if existing is not None:  # idempotent
        oc = db.get(Outcome, run.id)
        assert oc is not None
        return existing, oc
    require_phase(run, "play", "commit")
    over = body.get("amount_cents")
    if isinstance(over, int | float) and not isinstance(over, bool) \
            and over > hp_now(run) * HP_EUR * 100:
        raise ApiError(422, "amount_over_budget", "That is more than your budget now")
    if auto:
        clean: dict[str, Any] = dict(AUTO_LOCK)
    else:
        if not decide_ready(db, run, pack):
            raise ApiError(409, "not_ready", "Keep investigating first")
        clean, errs = validate_commit(body, run, pack)
        if errs:
            raise ApiError(422, "invalid_commit", "Check your answers", fields=errs)
    trades = trades_of(db, run.id)
    for t in trades:  # a follow-up still open is closed unanswered: never asked twice
        if t.reasoning_source == reasoning_mod.AWAITING:
            resolve_reasoning(db, run, t, None, skipped=True)
    b = ledger_result(run, pack, trades)
    holds = position_of(run, trades).shares > 0
    dec = Decision(
        session_id=run.player_id, scenario_id=run.scenario_id, campaign_id=run.id,
        action="invest" if holds else "dont_invest",
        amount_cents=max(0, int(b.invested * 100)) if holds else 0,
        evidence=evidence_text(trades, clean["evidence"]),
        reasoning=clean["evidence"] or (last_reasoning(trades) if auto else None),
        reasoning_source="commit" if clean["evidence"] else (
            "skipped" if not auto or not last_reasoning(trades) else "auto"),
        forecast_pct=float(clean["forecast_pct"]), confidence=CONF[clean["confidence"]],
    )  # fmt: skip
    db.add(dec)
    oc = Outcome(
        campaign_id=run.id,
        prices={"end_close": str(pack.end_close), "trades": len(trades)},
        cash=str(b.cash), invested=str(b.invested), value_now=str(b.value_now), fees="0.00",
        final=str(b.final), pnl=str(b.pnl), pnl_pct=str(b.pnl_pct), hp_before=b.hp_before,
        hp_after=b.hp_after,
    )  # fmt: skip
    db.add(oc)
    run.checkpoint = pack.cp_by_role("decision").id
    run.clock_day = max(run.clock_day, pack.decision_day)
    run.phase = "timeskip"
    run.commit_draft = None
    run.market_scene = None  # an open offer is over with the lock
    db.flush()
    run.locked_at = dec.locked_at
    append_event(db, run, "lock", {"action": dec.action, "amount_cents": dec.amount_cents,
                                   **({"auto": True} if auto else {})})  # fmt: skip
    if dec.reasoning:
        append_event(db, run, "decision_reasoning", {
            "seq": None, "reasoning": dec.reasoning, "source": dec.reasoning_source, "skipped": False,
        })  # fmt: skip
    append_event(db, run, "time_skip", {"label": clock.horizon_skip_label(pack)})
    return dec, oc


def debrief_facts(
    db: Session, run: CampaignRun, pack: Pack, dec: Decision, oc: Outcome
) -> dict[str, Any]:
    """Engine-computed part of the debrief: what-if, forecast line, unfound clues, question."""
    r = portfolio.investment_return(pack.buy_open, pack.end_close)
    trades = trades_of(db, run.id)
    final_scene = next((t for t in trades if t.beat == "decision" and t.price), None)
    decision_price = (
        Decimal(final_scene.price) if final_scene and final_scene.price
        else ledger.fill_row(pack.rows, pack.decision_day).close
    )  # fmt: skip
    rows = ledger.whatif_rows(
        budget_now(run), ledger_result(run, pack, trades),
        Decimal(first.price) if (first := next((t for t in trades if t.action in ("buy", "sell")), None))
        and first.price else None, decision_price,
        pack.end_close,
    )  # fmt: skip
    found = found_ids(db, run.id)
    missed = [e.title for e in pack.evidence if e.id not in found]
    pct = int(dec.forecast_pct or 0)
    verdict = "higher" if r > 0 else "lower" if r < 0 else "unchanged"
    return {
        "rows": rows,
        "missed": missed,
        "line": f"You said {pct}% likely higher — it ended {verdict}.",
        "question": pack.questions[0] if pack.questions else None,
    }


def debrief_text(parts: dict[str, Any], line: str) -> str:
    """The spoken debrief: stored on the event so TTS can synthesize guarded text only."""
    return "\n\n".join(
        str(x)
        for x in (parts.get("sound"), parts.get("reasoning"), parts.get("overlooked"), parts.get("luck"), line,
                  parts.get("question"))
        if x
    )  # fmt: skip


def store_debrief(
    db: Session, run: CampaignRun, facts: dict[str, Any], parts: dict[str, Any]
) -> Debrief:
    deb = Debrief(
        campaign_id=run.id, narrative=parts, overlooked=facts["missed"],
        forecast_line=facts["line"], whatif=facts["rows"],
    )  # fmt: skip
    db.add(deb)
    append_event(
        db, run, "debrief",
        {"forecast_line": facts["line"], "text": debrief_text(parts, facts["line"])},
    )  # fmt: skip
    return deb


def debrief_payload(
    db: Session, run: CampaignRun, pack: Pack, dec: Decision, oc: Outcome, nar: Narration
) -> Debrief:
    """Synchronous path (the reflection endpoint when the debrief was never streamed)."""
    deb = db.get(Debrief, run.id)
    if deb is not None:
        return deb
    from financequest.agents.campaign.context import build_agent_context

    facts = debrief_facts(db, run, pack, dec, oc)
    hero = db.get(Hero, run.hero_id)
    assert hero is not None
    ctx = build_agent_context(
        db, run, pack, hero, whatif=facts["rows"], overlooked=facts["missed"],
        question=facts["question"],
    )  # fmt: skip
    return store_debrief(db, run, facts, nar.debrief(ctx))


_WHATIF_KEYS = {"dont": "dont_invest", "choice": "yours"}


def whatif_out(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wire shape of the what-if rows (the engine and the agents keep their own)."""
    return [
        {
            "key": _WHATIF_KEYS.get(r["key"], r["key"]), "label": r["label"],
            "final_value": num(r["final"]), "pct": num(r["pnl_pct"]), "hp_after": r["hp_after"],
            "is_yours": bool(r["is_choice"]),
        }
        for r in rows
    ]  # fmt: skip


def debrief_out(deb: Debrief) -> dict[str, Any]:
    n = deb.narrative or {}
    return {
        "sound_reasoning": n.get("sound") or "", "how_you_reasoned": n.get("reasoning") or "",
        "overlooked": n.get("overlooked") or "",
        "luck": n.get("luck") or "", "forecast_line": deb.forecast_line or "",
        "reflection_question": n.get("question") or "", "whatif": whatif_out(deb.whatif or []),
    }  # fmt: skip


def has_event(db: Session, cid: uuid.UUID, type_: str) -> bool:
    return (
        db.exec(select(Event.id).where(Event.campaign_id == cid, Event.type == type_)).first()
        is not None
    )


def player_text(
    db: Session, run: CampaignRun, dec: Decision, deb: Debrief | None
) -> dict[str, str]:
    given = [
        f"Decision {t.seq} ({t.action}): {t.reasoning}"
        for t in trades_of(db, run.id) if t.beat != "damage" and t.reasoning
    ]
    if dec.reasoning:
        given.append(f"At the seal: {dec.reasoning}")
    return {
        "evidence": str(dec.evidence or ""),
        "reflection": (deb.reflection_text or "") if deb else "",
        "reasoning": "\n".join(given),
    }


def make_xp(db: Session, run: CampaignRun, pack: Pack, nar: Narration) -> XpAward:
    award = db.get(XpAward, run.id)
    if award is not None:
        return award
    dec = decision_of(db, run.id)
    deb = db.get(Debrief, run.id)
    if dec is None or deb is None or not deb.reflection_text:
        raise ApiError(409, "wrong_phase", "Finish the reflection first")
    texts = player_text(db, run, dec, deb)
    rubric = xp.rubric_for(pack.rubric)
    conf = {v: k for k, v in CONF.items()}.get(dec.confidence or 0)
    raw = nar.xp(rubric, texts, {
        "action": dec.action, "amount_eur": (dec.amount_cents or 0) // 100,
        "forecast_pct": int(dec.forecast_pct) if dec.forecast_pct is not None else None,
        "confidence": conf,
    })  # fmt: skip
    all_text = "\n".join(texts.values())
    cats, total = xp.validate_scores(rubric, raw, all_text)
    award = XpAward(campaign_id=run.id, categories=cats, total=total)
    db.add(award)
    run.phase = "xp"
    append_event(db, run, "xp", {"total": total})
    return award


def finish(db: Session, run: CampaignRun) -> dict[str, Any]:
    award = db.get(XpAward, run.id)
    hero = db.get(Hero, run.hero_id)
    assert hero is not None
    if award is None:
        raise ApiError(409, "wrong_phase", "Get your XP first")
    if award.finished_at is None:
        hero.total_xp += award.total
        if award.total >= focus.ITEM_XP_THRESHOLD:
            item = focus.next_item(hero_items(db, hero))
            if item:
                db.add(HeroItem(hero_id=hero.id, item_key=item, earned_campaign_id=run.id))
        award.finished_at = _now()
        run.status, run.phase = "finished", "done"
        player = db.get(Player, run.player_id)
        if player and player.active_campaign_id == run.id:
            player.active_campaign_id = None
            db.add(player)
        append_event(db, run, "finish", {"total_xp": hero.total_xp})
        db.add_all([hero, award])
        _remember(db, run)
    got = db.exec(select(HeroItem).where(HeroItem.earned_campaign_id == run.id)).first()
    return {"total_xp": hero.total_xp, "new_item": focus.item_out(got.item_key) if got else None}


def _remember(db: Session, run: CampaignRun) -> None:
    """The Veteran's memory of this campaign. In a savepoint: a failure here never blocks the
    finish; the memory is rebuilt from the same rows the next time the Veteran is opened."""
    from financequest.veteran import memory

    try:
        with db.begin_nested():
            memory.remember(db, run)
    except Exception:  # noqa: BLE001
        log = logging.getLogger("financequest.veteran")
        log.exception("could not remember campaign %s", run.id)


def latest_suggestions(events: list[Event]) -> list[str]:
    """Suggestions of the latest Campaign Master reply, so a resumed screen can offer them again.
    Stored with the reply in the event log; nothing else is kept."""
    for e in reversed(events):
        p = e.payload or {}
        if e.type == "dm_reply" and p.get("suggestions") and not p.get("news_framing"):
            return [str(x) for x in p["suggestions"]]
    return []


# ---- Master-created places ----------------------------------------------------------------------
def npc_out(loc: Location) -> dict[str, str] | None:
    n = loc.npc if isinstance(loc.npc, dict) else None
    return {"id": n["id"], "name": n["name"], "role": n["role"]} if n else None


def generated_count(db: Session, cid: uuid.UUID) -> int:
    return sum(1 for x in locations(db, cid) if x.generated)


def create_generated_location(
    db: Session, run: CampaignRun, spec: dict[str, Any]
) -> Location:
    """Adds the validated place and its NPC to the campaign; there is no cap on created places."""
    have = locations(db, run.id)
    taken = {x.key for x in have}
    slug = "".join(c if c.isalnum() else "_" for c in spec["name"].lower()).strip("_")[:40] or "place"
    key, n = f"gen_{slug}", 2
    while key in taken:
        key, n = f"gen_{slug}_{n}", n + 1
    npc = {**spec["npc"], "id": f"npc-{uuid.uuid4().hex[:8]}"}
    row = Location(
        campaign_id=run.id, key=key, fixed=False, generated=True, name=spec["name"],
        description=spec["description"], art_subject=spec["art_subject"], npc=npc,
    )  # fmt: skip
    db.add(row)
    db.flush()
    return row


# ---- state ------------------------------------------------------------------------------------
def build_state(db: Session, run: CampaignRun, pack: Pack) -> dict[str, Any]:
    hero = db.get(Hero, run.hero_id)
    assert hero is not None
    items = hero_items(db, hero)
    gv = gated_view(run)
    content = gated_content(pack, gv)
    events = campaign_events(db, run.id)
    revealed = phase_at_least(run, "reveal")
    oc = db.get(Outcome, run.id) if revealed else None
    hp = oc.hp_after if oc else hp_now(run)
    docs = []
    by_id = {
        e["id"]: {k: e[k] for k in ("id", "title", "text")} for e in content["evidence"]
    }
    for d in content["documents"]:
        docs.append(
            {
                "id": d["id"],
                "title": d["title"],
                "entries": [by_id[i] for i in d["evidence_ids"] if i in by_id],
            }
        )
    card = content["company_card"]
    if "ratio_lens" not in items:
        card = {
            **card,
            "key_figures": [
                {k: v for k, v in f.items() if k != "explain"} for f in card["key_figures"]
            ],
        }
    state: dict[str, Any] = {
        "id": str(run.id), "phase": run.phase, "status": run.status, "version": run.version,
        "scenario_id": str(run.scenario_id),
        "scenario": {
            "title": pack.title, "company_name": pack.company_name, "trade": pack.trade,
            "horizon_label": clock.horizon_label(pack), "budget_eur": run.hp_start * 10,
            "currency": pack.currency, "spread_available": pack.has_fund,
        },
        "hero": {"name": hero.name, "class": hero.hero_class, "total_xp": hero.total_xp,
                 "items": sorted(items)},
        "hp": hp, "hp_eur": hp * HP_EUR, "hp_start": run.hp_start, "focus_left": run.focus_left, "rerolls_left": run.rerolls_left,
        "keen_eye_left": run.keen_eye_left, "bonus_lead_available": not run.bonus_lead_used,
        "turn_count": run.turn_count, "checkpoint": run.checkpoint, "story_day": run.clock_day,
        "story_day_label": clock.day_label(run.clock_day), "news_shown": run.news_shown,
        "news": content["news"], "current_location_id": str(run.current_location_id) if run.current_location_id else None,
        "locations": [
            {"id": str(loc.id), "key": loc.key, "name": loc.name, "description": loc.description,
             "fixed": loc.fixed, "art_status": loc.art_status, "visited": loc.visited,
             "generated": loc.generated, "npc": npc_out(loc)}
            for loc in locations(db, run.id)
        ],
        "backlog": backlog(events),
        "clues": [{"clue_id": c.clue_id, "source": c.source, **_clue_payload(pack, c.clue_id, c.source)}
                  for c in db.exec(select(ClueState).where(ClueState.campaign_id == run.id).order_by(ClueState.found_at_seq))],  # type: ignore[arg-type]
        "library": {"documents": docs, "company_card": card},
        "price_board": board_out(content["chart"]),
        "characters": [{k: v for k, v in c.items() if k not in ("never", "may_reveal")} for c in content["characters"]],
        "challenges": [
            {"id": str(c.id), "title": c.title, "dc": c.dc, "state": c.state, "optional": c.optional,
             "result": c.result, "location": c.location_key, "skill": rules.adhoc_skill(c.kind)}
            for c in challenges(db, run.id) if gv.at_checkpoint(c.checkpoint)
        ],
        "pending": run.pending,
        "can_decide": decide_ready(db, run, pack) if run.phase in ("play", "commit") else False,
        "opening_done": run.opening_done,
        "commit_draft": run.commit_draft,
        "suggestions": latest_suggestions(events),
        "budget_eur": run.hp_start * 10, "horizon_days": pack.horizon_days,
        "offers_spread": pack.has_fund,
        "purse": purse(db, run, pack),
        "market_scene": scene_out(run),
        "all_in": is_all_in(db, run, pack), "offer": offer_out(run),
        "awaiting_reasoning": awaiting_trade(db, run) is not None,
        "decisions": decisions_out(db, run, pack),
    }  # fmt: skip
    if "rumour_ledger" in items:
        state["rumours"] = [
            c["title"]
            for c in state["clues"]
            if (ev := pack.evidence_by_id(c["clue_id"])) is not None and ev.kind == "opinion"
        ]
    dec = decision_of(db, run.id)
    if dec and oc and revealed:
        state["outcome"] = reveal_payload(db, run, pack, dec, oc)
    deb = db.get(Debrief, run.id)
    if deb and phase_at_least(run, "debrief"):
        state["debrief"] = debrief_out(deb)
    award = db.get(XpAward, run.id)
    if award and phase_at_least(run, "xp"):
        state["xp"] = {"categories": award.categories, "total": award.total}
    return state


__all__ = ["find_by_msg_id", "journal"]


def db_outcome(db: Session, cid: uuid.UUID) -> Outcome | None:
    return db.get(Outcome, cid)
