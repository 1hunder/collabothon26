"""Campaign use-cases over the database. Short transactions; no LLM call under a lock."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from financequest.api.errors import ApiError
from financequest.campaign import clock, dice, focus, portfolio, rules, whatif, xp
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
def lock_run(db: Session, cid: uuid.UUID, sid: uuid.UUID) -> CampaignRun:
    run = db.exec(select(CampaignRun).where(CampaignRun.id == cid).with_for_update()).first()
    if run is None or run.player_id != sid:
        raise ApiError(404, "not_found", "Campaign not found")
    return run


def pack_of(db: Session, run: CampaignRun) -> Pack:
    return load_pack(db, run.scenario_id)


def load(
    db: Session, cid: uuid.UUID, sid: uuid.UUID, write: bool = True
) -> tuple[CampaignRun, Pack, Hero]:
    """The campaign of this session (row-locked when ``write``), its pack and its hero."""
    if write:
        run = lock_run(db, cid, sid)
    else:
        found = db.get(CampaignRun, cid)
        if found is None or found.player_id != sid:
            raise ApiError(404, "not_found", "Campaign not found")
        run = found
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
    run.checkpoint, run.clock_day = clock.after_news(pack, run.clock_day)
    card = {
        "kind": "news",
        "headline": pack.news["headline"],
        "summary": pack.news["summary"],
        "time_skip_label": clock.time_skip_label(pack),
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


def decide_ready(db: Session, run: CampaignRun, pack: Pack) -> bool:
    gv = gated_view(run)
    return rules.can_decide(
        pack, gv.at_checkpoint, found_ids(db, run.id), run.opening_done, run.pending, run.news_shown
    )


def require_phase(run: CampaignRun, *phases: str) -> None:
    if run.phase not in phases:
        raise ApiError(409, "wrong_phase", f"Not allowed in phase {run.phase}")


# ---- creating a campaign ----------------------------------------------------------------------
def pick_scenario(db: Session) -> tuple[Scenario, Pack]:
    from financequest.db.models import ScenarioSecret

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


def create_campaign(db: Session, sid: uuid.UUID, interests: list[str]) -> CampaignRun:
    player = ensure_player(db, sid)
    hero = get_hero(db, sid)
    if hero is None:
        raise ApiError(409, "hero_required", "Create your hero first")
    if player.active_campaign_id:
        active = db.get(CampaignRun, player.active_campaign_id)
        if active and active.status == "active":
            raise ApiError(
                409, "campaign_in_progress", "A quest is already in progress",
                campaign_id=str(active.id),
            )  # fmt: skip
    sc, pack = pick_scenario(db)
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


# ---- rolls ------------------------------------------------------------------------------------
def challenge_of(db: Session, run: CampaignRun, rid: uuid.UUID) -> Challenge:
    ch = db.get(Challenge, rid)
    if ch is None or ch.campaign_id != run.id:
        raise ApiError(404, "not_found", "Challenge not found")
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
        "alt_source": ch.alt_source if ch.result == "setback" else None,
    }  # fmt: skip


def _finalize(db: Session, run: CampaignRun, pack: Pack, ch: Challenge) -> None:
    ch.state = "final"
    run.pending = None
    if ch.result == "success":
        if ch.clue_id:
            grant_clue(db, run, pack, ch.clue_id, "dice")
    else:
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
    errs: dict[str, str] = {}
    action = body.get("action", body.get("decision"))  # ``decision`` is a legacy alias
    allowed = ["invest", "dont_invest", "wait"] + (["spread"] if pack.has_fund else [])
    if action not in allowed:
        errs["action"] = "Choose a decision."
    amount = 0
    if action in ("invest", "spread"):
        a = body.get("amount_eur")
        budget = run.hp_start * 10
        if isinstance(a, bool) or not isinstance(a, int) or not 1 <= a <= budget:
            errs["amount_eur"] = f"Enter an amount from €1 to €{budget:,}."
        else:
            amount = a
    text = str(body.get("evidence") or "").strip()
    if len(text) < 20:
        errs["evidence"] = "Explain your reasoning in at least 20 characters."
    fp = body.get("forecast_pct")
    if isinstance(fp, bool) or not isinstance(fp, int | float) or fp % 5 or not 0 <= fp <= 100:
        errs["forecast_pct"] = "Pick a forecast from 0% to 100% in steps of 5%."
    conf = body.get("confidence")
    if conf not in CONF:
        errs["confidence"] = "Choose Low, Medium or High."
    return {
        "action": action,
        "amount": amount,
        "evidence": text,
        "forecast_pct": fp,
        "confidence": conf,
    }, errs


def outcome_numbers(
    pack: Pack, run: CampaignRun, action: str, amount: int
) -> tuple[Decimal, portfolio.Breakdown]:
    r = portfolio.investment_return(pack.buy_open, pack.end_close)
    b = portfolio.compute(Decimal(run.hp_start * 10), action, Decimal(amount), r, pack.fund_return)
    return r, b


def reveal_payload(
    db: Session, run: CampaignRun, pack: Pack, dec: Decision, oc: Outcome
) -> dict[str, Any]:
    """Outcome of a locked decision (POST lock and GET reveal): story labels and numbers only;
    ``locked_at`` is the story moment, never the wall-clock time."""
    r = portfolio.investment_return(pack.buy_open, pack.end_close)
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
            "starting_budget": float(Decimal(run.hp_start * 10).quantize(portfolio.CENTS)),
            "cash_kept": num(oc.cash), "invested": num(oc.invested), "value_now": num(oc.value_now),
            "fees": num(oc.fees), "final_value": num(oc.final), "pl_eur": num(oc.pnl),
            "pl_pct": num(oc.pnl_pct),
        },
        "hp_before": oc.hp_before,
        "hp_after": oc.hp_after,
        "investment_return_pct": num(portfolio.q_pct(r * 100)),
        "currency_note": portfolio.CURRENCY_NOTE,
        "phase": run.phase,
    }  # fmt: skip


def lock_decision(
    db: Session, run: CampaignRun, pack: Pack, body: dict[str, Any]
) -> tuple[Decision, Outcome]:
    existing = decision_of(db, run.id)
    if existing is not None:  # idempotent
        oc = db.get(Outcome, run.id)
        assert oc is not None
        return existing, oc
    require_phase(run, "play", "commit")
    if not decide_ready(db, run, pack):
        raise ApiError(409, "not_ready", "Keep investigating first")
    clean, errs = validate_commit(body, run, pack)
    if errs:
        raise ApiError(422, "invalid_commit", "Check your answers", fields=errs)
    r, b = outcome_numbers(pack, run, clean["action"], clean["amount"])
    dec = Decision(
        session_id=run.player_id, scenario_id=run.scenario_id, campaign_id=run.id,
        action=clean["action"], amount_cents=clean["amount"] * 100, evidence=clean["evidence"],
        forecast_pct=float(clean["forecast_pct"]), confidence=CONF[clean["confidence"]],
    )  # fmt: skip
    db.add(dec)
    oc = Outcome(
        campaign_id=run.id,
        prices={"buy_open": str(pack.buy_open), "end_close": str(pack.end_close), "r": str(r)},
        cash=str(b.cash), invested=str(b.invested), value_now=str(b.value_now), fees=str(b.fees),
        final=str(b.final), pnl=str(b.pnl), pnl_pct=str(b.pnl_pct), hp_before=b.hp_before,
        hp_after=b.hp_after,
    )  # fmt: skip
    db.add(oc)
    run.checkpoint = pack.cp_by_role("decision").id
    run.clock_day = max(run.clock_day, pack.decision_day)
    run.phase = "timeskip"
    run.commit_draft = None
    db.flush()
    run.locked_at = dec.locked_at
    append_event(db, run, "lock", {"action": dec.action, "amount_cents": dec.amount_cents})
    append_event(db, run, "time_skip", {"label": clock.horizon_skip_label(pack)})
    return dec, oc


def debrief_facts(
    db: Session, run: CampaignRun, pack: Pack, dec: Decision, oc: Outcome
) -> dict[str, Any]:
    """Engine-computed part of the debrief: what-if, forecast line, unfound clues, question."""
    r = portfolio.investment_return(pack.buy_open, pack.end_close)
    rows = whatif.whatif_rows(
        Decimal(run.hp_start * 10),
        dec.action,
        Decimal((dec.amount_cents or 0) // 100),
        r,
        pack.fund_return,
    )
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
        for x in (parts.get("sound"), parts.get("overlooked"), parts.get("luck"), line,
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
        "sound_reasoning": n.get("sound") or "", "overlooked": n.get("overlooked") or "",
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
    return {
        "evidence": str(dec.evidence or ""),
        "reflection": (deb.reflection_text or "") if deb else "",
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
    raw = nar.xp(rubric, texts)
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
    got = db.exec(select(HeroItem).where(HeroItem.earned_campaign_id == run.id)).first()
    return {"total_xp": hero.total_xp, "new_item": focus.item_out(got.item_key) if got else None}


def latest_suggestions(events: list[Event]) -> list[str]:
    """Suggestions of the latest Campaign Master reply, so a resumed screen can offer them again.
    Stored with the reply in the event log; nothing else is kept."""
    for e in reversed(events):
        p = e.payload or {}
        if e.type == "dm_reply" and p.get("suggestions") and not p.get("news_framing"):
            return [str(x) for x in p["suggestions"]]
    return []


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
    hp = oc.hp_after if oc else run.hp_start
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
        "hp": hp, "hp_eur": hp * 10, "focus_left": run.focus_left, "rerolls_left": run.rerolls_left,
        "keen_eye_left": run.keen_eye_left, "bonus_lead_available": not run.bonus_lead_used,
        "turn_count": run.turn_count, "checkpoint": run.checkpoint, "story_day": run.clock_day,
        "story_day_label": clock.day_label(run.clock_day), "news_shown": run.news_shown,
        "news": content["news"], "current_location_id": str(run.current_location_id) if run.current_location_id else None,
        "locations": [
            {"id": str(loc.id), "key": loc.key, "name": loc.name, "description": loc.description,
             "fixed": loc.fixed, "art_status": loc.art_status, "visited": loc.visited}
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
             "result": c.result, "location": c.location_key}
            for c in challenges(db, run.id) if gv.at_checkpoint(c.checkpoint)
        ],
        "pending": run.pending,
        "can_decide": decide_ready(db, run, pack) if run.phase in ("play", "commit") else False,
        "opening_done": run.opening_done,
        "commit_draft": run.commit_draft,
        "suggestions": latest_suggestions(events),
        "budget_eur": run.hp_start * 10, "horizon_days": pack.horizon_days,
        "offers_spread": pack.has_fund,
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
