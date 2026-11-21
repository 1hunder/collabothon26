"""Narrated replies of a campaign: the builders behind the SSE endpoints.

Each ``plan_*`` function runs phase A (short transaction, may raise ``ApiError`` before any byte
is streamed) and returns a ``StreamPlan`` whose ``work`` (the graph) and ``commit`` (engine
effects + the stored, guarded reply) the SSE driver runs. See ``stream.py``.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlmodel import Session, select

from financequest.agents.campaign import context as C
from financequest.agents.campaign import graphs
from financequest.api.errors import ApiError
from financequest.campaign import clock, focus, rules, service
from financequest.campaign.events import append_event, find_by_msg_id
from financequest.campaign.narration import DecisionReply, Narration, TurnReply, get_narration
from financequest.campaign.pack import Pack
from financequest.campaign.stream import Streamed, StreamPlan
from financequest.campaign.view import gated_view, visible_evidence
from financequest.config import get_settings
from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun, Challenge, Location, Trade
from financequest.db.session import get_engine

log = logging.getLogger("financequest.turns")
TURN_BUDGET_S = 15.0
NPC_BUDGET_S = 30.0  # the NPC answers first and may hand over to the Master in the same turn
SETUP_BUDGET_S = 40.0
DEBRIEF_BUDGET_S = 30.0
SUMMARY_EVERY = 6


def _session() -> Session:
    return Session(get_engine())


# ---- shared payloads ---------------------------------------------------------------------------------
def state_delta(db: Session, run: CampaignRun, pack: Pack) -> dict[str, Any]:
    locs = service.locations(db, run.id)
    return {
        "can_decide": service.decide_ready(db, run, pack), "turn_count": run.turn_count,
        "focus_left": run.focus_left, "rerolls_left": run.rerolls_left,
        "keen_eye_left": run.keen_eye_left, "story_day": run.clock_day,
        "checkpoint": run.checkpoint, "news_shown": run.news_shown, "phase": run.phase,
        "current_location_id": str(run.current_location_id) if run.current_location_id else None,
        "art_ready": [str(x.id) for x in locs if x.art_status == "ready"],
        "purse": service.purse(db, run, pack), "market_scene": service.scene_out(run),
        "hp": service.hp_now(run), "hp_eur": service.hp_now(run) * service.HP_EUR,
        "locations": [
            {"id": str(x.id), "key": x.key, "name": x.name, "description": x.description,
             "fixed": x.fixed, "art_status": x.art_status, "visited": x.visited,
             "generated": x.generated, "npc": service.npc_out(x)}
            for x in locs
        ],
    }  # fmt: skip


def _finish(db: Session, run: CampaignRun) -> None:
    service.touch(run)
    db.add(run)
    db.commit()


def _speaker_kind(p: dict[str, Any]) -> str:
    if p.get("speaker_kind"):
        return str(p["speaker_kind"])
    return "buddy" if p.get("speaker") == C.BUDDY_NAME else "master"


def _done_fields(p: dict[str, Any]) -> dict[str, Any]:
    """Fields every done payload carries (the contract): who spoke, damage, a created place."""
    return {
        "speaker_kind": _speaker_kind(p), "escalated": bool(p.get("escalated", False)),
        "hp_change": p.get("hp_change"), "new_location": p.get("new_location"),
    }


def replay_streamed(db: Session, run: CampaignRun, pack: Pack, ev: Event) -> Streamed:
    """An idempotent repeat streams the stored, already guarded reply."""
    p = dict(ev.payload or {})
    delta = state_delta(db, run, pack)
    cards = [c for c in (p.get("card"), p.get("news"), p.get("scene")) if c]
    done = {**p, **_done_fields(p), "audio_text_id": ev.id, **delta, "replayed": True}
    if (p.get("news") or {}).get("framing"):
        done["news_text"] = p["news"]["framing"]
    return Streamed(text=str(p.get("text", "")), cards=cards, state=delta, done=done)


def _streamed(
    db: Session, run: CampaignRun, pack: Pack, ev: Event, cards: list[dict[str, Any]]
) -> Streamed:
    p = dict(ev.payload or {})
    delta = state_delta(db, run, pack)
    return Streamed(
        text=str(p.get("text", "")), cards=cards, state=delta,
        done={**p, **_done_fields(p), "audio_text_id": ev.id, **delta},
    )  # fmt: skip


def _gate_clue(pack: Pack, run: CampaignRun, clue_id: str) -> bool:
    ev = pack.evidence_by_id(clue_id)
    return ev is not None and gated_view(run).at_checkpoint(ev.checkpoint)


# ---- damage and created places ----------------------------------------------------------------
_HP_NUM = re.compile(r"\b\d+\s*HP\b")
_HP_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def reconcile_hp_text(text: str, applied: int) -> str:
    """The text must say exactly what the engine applied after clamping: fix the number, or drop
    the sentences that announce a loss that did not happen."""
    if applied > 0:
        return _HP_NUM.sub(f"{applied} HP", text)
    parts = _HP_SENTENCE.split(text)
    kept = [p for p in parts if not re.search(r"\bHP\b", p)]
    return " ".join(kept) if kept else text


def apply_damage(db: Session, run: CampaignRun, pack: Pack, reply: TurnReply) -> dict[str, Any] | None:
    if reply.hp_loss <= 0:
        return None
    reason = reply.hp_reason
    if not reason:  # fall back to the sentence that states the loss
        reason = next((p.strip() for p in _HP_SENTENCE.split(reply.text) if "HP" in p), "A costly turn")
    return service.apply_hp_loss(db, run, pack, reply.hp_loss, reason[:200])


def art_enabled() -> bool:
    s = get_settings()
    return bool(s.fake_llm or s.google_genai_api_key)


def start_generated_art(location_id: uuid.UUID, leak_terms: Any) -> None:
    from financequest.media import art

    art.start_art_job_in_thread(location_id, leak_terms)


def new_location_out(db: Session, loc: Location, art_job: bool) -> dict[str, Any]:
    if art_job:
        loc.art_status = "pending"
        db.add(loc)
    return {
        "id": str(loc.id), "key": loc.key, "name": loc.name, "description": loc.description,
        "art_status": loc.art_status, "npc": service.npc_out(loc),
    }  # fmt: skip


# ==============================================================================================
# opening
# ==============================================================================================
def _opening_event(db: Session, cid: uuid.UUID) -> Event | None:
    for e in db.exec(
        select(Event).where(Event.campaign_id == cid, Event.type == "dm_reply").order_by(Event.seq)  # type: ignore[arg-type]
    ):
        if (e.payload or {}).get("opening"):
            return e
    return None


def plan_opening(sid: uuid.UUID, cid: uuid.UUID) -> StreamPlan:
    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        if run.opening_done:
            ev = _opening_event(db, cid)
            assert ev is not None
            return StreamPlan(cid, replay=replay_streamed(db, run, pack, ev))
        service.require_phase(run, "setup")
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(SETUP_BUDGET_S)
        db.rollback()  # nothing written: release the row lock before the model call

    def prepared() -> dict[str, Any]:
        out = graphs.prepared_setup(ctx)
        return {"text": out.text, "speaker": C.DM_NAME, "degraded": True,
                **graphs.validate_setup(ctx, out)}  # fmt: skip

    def work() -> dict[str, Any]:
        try:
            return nar.setup(ctx)
        except Exception as exc:  # noqa: BLE001 - the prepared setup always works
            log.warning("setup graph failed, using the prepared setup: %s", exc)
            return prepared()

    def commit(result: dict[str, Any]) -> Streamed:
        new_art: list[uuid.UUID] = []
        with _session() as db:
            run, pack, _ = service.load(db, cid, sid)
            if run.opening_done:
                ev = _opening_event(db, cid)
                assert ev is not None
                return replay_streamed(db, run, pack, ev)
            seeds = {s["key"]: s for s in pack.seeds}
            have = {x.key for x in service.locations(db, cid)}
            for loc in result.get("locations", []):
                seed = seeds.get(loc["key"])
                if seed is None or loc["key"] in have:
                    continue
                row = Location(
                    campaign_id=cid, key=seed["key"], fixed=False, name=seed["name"],
                    description=loc.get("description") or seed["description"],
                    art_subject=seed.get("art_subject"),
                )  # fmt: skip
                db.add(row)
                new_art.append(row.id)
            known = {c.key for c in service.challenges(db, cid)}
            for ch in result.get("challenges", []):
                if ch["key"] in known:
                    continue
                db.add(Challenge(
                    campaign_id=cid, key=ch["key"], title=ch["title"], kind=ch["kind"],
                    dc=int(ch["dc"]), checkpoint=ch["checkpoint"], location_key=ch["location_key"],
                    clue_id=ch["clue_id"], alt_source="",
                ))  # fmt: skip
            db.flush()
            payload = {
                "text": result["text"], "speaker": result.get("speaker", C.DM_NAME),
                "suggestions": result.get("suggestions", []), "opening": True,
                "degraded": bool(result.get("degraded")),
            }  # fmt: skip
            ev = append_event(db, run, "dm_reply", payload)
            run.opening_done, run.phase = True, "play"
            _finish(db, run)
            out = _streamed(db, run, pack, ev, [])
            leaks = pack.leak_terms
        s = get_settings()
        if new_art and (s.fake_llm or s.google_genai_api_key):
            from financequest.media.art import start_art_job

            for lid in new_art:
                start_art_job(lid, leaks)
        return out

    return StreamPlan(cid, work=work, commit=commit, deadline_s=SETUP_BUDGET_S, on_timeout=prepared)


# ==============================================================================================
# actions and moves (the turn graph)
# ==============================================================================================
def plan_action(
    sid: uuid.UUID, cid: uuid.UUID, raw_text: str, msg: str | None
) -> StreamPlan:
    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        done = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if done is not None:  # idempotent "Try again"
            return StreamPlan(cid, replay=replay_streamed(db, run, pack, done))
        text = raw_text.strip()
        if not text:
            raise ApiError(422, "empty", "Say what you would do")
        service.require_phase(run, "play")
        if run.pending:
            raise ApiError(409, "roll_open", "Finish the dice check first")
        in_scene = bool(run.market_scene)
        append_event(db, run, "action", {"text": text, **({"scene": True} if in_scene else {})},
                     f"{msg}:action" if msg else None)  # fmt: skip
        db.commit()
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
    if in_scene:  # the player answers the decision scene: read it, execute it, react
        return StreamPlan(
            cid, work=lambda: nar.decide(ctx, text),
            commit=lambda reply: commit_decision(sid, cid, text, reply, msg=msg),
            deadline_s=TURN_BUDGET_S,
        )
    if ctx.npc_here is not None:  # a Master-created place: its NPC answers, or hands over
        ctx.with_deadline(NPC_BUDGET_S)
        return StreamPlan(
            cid, work=lambda: nar.npc_turn(ctx, text),
            commit=lambda reply: commit_turn(sid, cid, reply, msg=msg, nar=nar),
            after=lambda _: maybe_summarize(sid, cid, nar), deadline_s=NPC_BUDGET_S,
        )  # fmt: skip
    return StreamPlan(
        cid, work=lambda: nar.turn(ctx, text),
        commit=lambda reply: commit_turn(sid, cid, reply, msg=msg, nar=nar),
        after=lambda _: maybe_summarize(sid, cid, nar), deadline_s=TURN_BUDGET_S,
    )  # fmt: skip


def plan_move(
    sid: uuid.UUID, cid: uuid.UUID, location_id: uuid.UUID, msg: str | None = None
) -> StreamPlan:
    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        done = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if done is not None:
            return StreamPlan(cid, replay=replay_streamed(db, run, pack, done))
        service.require_phase(run, "play")
        if run.pending:
            raise ApiError(409, "roll_open", "Finish the dice check first")
        loc = db.get(Location, location_id)
        if loc is None or loc.campaign_id != run.id:
            raise ApiError(404, "not_found", "Location not found")
        key, name = loc.key, loc.name
        db.rollback()
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
    return StreamPlan(
        cid, work=lambda: nar.turn(ctx, f"Go to the {name}", forced_move=key),
        commit=lambda reply: commit_turn(sid, cid, reply, msg=msg, nar=nar),
        after=lambda _: maybe_summarize(sid, cid, nar), deadline_s=TURN_BUDGET_S,
    )  # fmt: skip


def commit_turn(
    sid: uuid.UUID, cid: uuid.UUID, reply: TurnReply, *, msg: str | None, nar: Narration
) -> Streamed:
    """Phase C of an action or a move: engine effects first, then the stored reply."""
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        stored = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if stored is not None:
            return replay_streamed(db, run, pack, stored)
        service.require_phase(run, "play")
        if run.pending:
            raise ApiError(409, "roll_open", "Finish the dice check first")
        gv = gated_view(run)
        card: dict[str, Any] | None = None
        granted: list[str] = []
        kind, arrived_at = "action", None
        art_start = art_enabled()
        loc = (
            service.location_by_key(db, run.id, reply.location_key)
            if reply.intent == "move" and reply.location_key else None
        )  # fmt: skip
        created: Location | None = None
        if reply.intent == "new_location" and reply.new_location:
            created = service.create_generated_location(db, run, reply.new_location)
            loc = created  # None when the cap was reached meanwhile: the reply stays a plain turn
        if reply.intent == "challenge" and reply.challenge_id:
            ch = db.get(Challenge, uuid.UUID(reply.challenge_id))
            if ch and ch.campaign_id == run.id and ch.state == "open" and gv.at_checkpoint(ch.checkpoint):
                card = service.offer_roll(run, ch, hero)
        if loc is not None:
            granted, first = service.arrive(db, run, pack, loc)
            append_event(db, run, "move", {"location_id": str(loc.id), "key": loc.key,
                                           "name": loc.name, "first_visit": first})  # fmt: skip
            kind, arrived_at = "move", loc.key
            if created is not None:
                append_event(db, run, "location_created", {
                    "location_id": str(created.id), "key": created.key, "name": created.name,
                    "npc": service.npc_out(created),
                })  # fmt: skip
        else:
            for c in reply.clue_ids_given:
                if _gate_clue(pack, run, c):
                    if service.grant_clue(db, run, pack, c, "character"):
                        granted.append(c)
        news = service.count_turn(db, run, pack, kind, arrived_at=arrived_at)
        if news and loc is not None:  # free clues of the new checkpoint at this place
            granted += service.grant_free_at(db, run, pack, loc.key)
        beat = None if card else service.due_beat(
            db, run, pack, news_now=bool(news), asked=reply.intent == "decision_intent",
            story_call=reply.calls_for_decision,
        )  # fmt: skip
        if beat:
            service.open_scene(db, run, pack, beat)
        ready = service.decide_ready(db, run, pack)
        text_out = reply.text
        if beat and reply.intent == "decision_intent":
            text_out = "Then the moment has come."
        hp_change = apply_damage(db, run, pack, reply)
        if reply.hp_loss > 0:
            text_out = reconcile_hp_text(text_out, -hp_change["delta"] if hp_change else 0)
        new_loc = new_location_out(db, created, art_start) if created is not None else None
        payload = {
            "text": text_out, "speaker": reply.speaker, "speaker_id": reply.speaker_id,
            "speaker_kind": reply.speaker_kind, "escalated": reply.escalated,
            "hp_change": hp_change, "new_location": new_loc,
            "intent": reply.intent, "suggestions": reply.suggestions,
            "clue_ids_given": granted if loc is not None else list(reply.clue_ids_given),
            "card": card, "news": news, "degraded": reply.degraded,
            "nothing_more_to_uncover": reply.nothing_more_to_uncover and ready,
            "show_decide": reply.intent == "decision_intent" and ready,
            "first_visit": (first if loc is not None else None),
            "location": {"id": str(loc.id), "key": loc.key, "name": loc.name} if loc else None,
        }  # fmt: skip
        ev = append_event(db, run, "dm_reply", payload, f"{msg}:reply" if msg else None)
        _finish(db, run)
        assert ev.id is not None
        reply_id, news_card = ev.id, dict(news) if news else None
        art_job = (created.id, pack.leak_terms) if created is not None and art_start else None
    if art_job is not None:
        start_generated_art(*art_job)
    cards: list[dict[str, Any]] = [card] if card else []
    if news_card:
        news_card = frame_news(sid, cid, reply_id, news_card, nar)
        cards.append(news_card)
    if beat:
        cards.append(frame_scene(sid, cid, reply_id, beat, nar))
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid, write=False)
        stored_ev = db.get(Event, reply_id)
        assert stored_ev is not None
        out = _streamed(db, run, pack, stored_ev, cards)
    if news_card:
        out.done["news_text"] = news_card.get("framing")
    return out


def frame_news(
    sid: uuid.UUID, cid: uuid.UUID, reply_id: int, news: dict[str, Any], nar: Narration
) -> dict[str, Any]:
    """The news card text is verbatim from the pack; the model only frames it. The framing is
    guarded and falls back to a fixed question, so this never fails the turn."""
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid, write=False)
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(10.0)
    framing = nar.news(ctx)
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid)
        fev = append_event(db, run, "dm_reply", {"text": framing.text, "speaker": C.DM_NAME,
                                                 "news_framing": True})  # fmt: skip
        card = {**news, "framing": framing.text, "framing_audio_text_id": fev.id}
        ev = db.get(Event, reply_id)
        if ev is not None:
            ev.payload = {**(ev.payload or {}), "news": card}
            db.add(ev)
        _finish(db, run)
    return card


def frame_scene(
    sid: uuid.UUID, cid: uuid.UUID, reply_id: int, beat: str, nar: Narration
) -> dict[str, Any]:
    """The Campaign Master sets the decision scene the engine opened. Guarded, with a fixed
    fallback, so it never fails the turn. The card carries the engine's purse figures."""
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid, write=False)
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(10.0)
    framed = nar.market_scene(ctx, beat)
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid)
        fev = append_event(db, run, "dm_reply", {"text": framed.text, "speaker": C.DM_NAME,
                                                 "market_scene": beat,
                                                 "suggestions": framed.suggestions})  # fmt: skip
        if isinstance(run.market_scene, dict):
            run.market_scene = {**run.market_scene, "text": framed.text,
                                "suggestions": framed.suggestions}  # fmt: skip
        card = {
            "kind": "market", "beat": beat, "text": framed.text, "suggestions": framed.suggestions,
            "story_day": run.clock_day, "day_label": clock.day_label(run.clock_day),
            "purse": service.purse(db, run, pack), "audio_text_id": fev.id,
        }  # fmt: skip
        ev = db.get(Event, reply_id)
        if ev is not None:
            ev.payload = {**(ev.payload or {}), "scene": card}
            db.add(ev)
        _finish(db, run)
    return card


def trade_card(trade: Trade, purse: dict[str, Any]) -> dict[str, Any]:
    """The receipt for an executed decision: engine figures, euros only."""
    return {
        "kind": "trade", "seq": trade.seq, "beat": trade.beat, "action": trade.action,
        "amount_eur": trade.amount_cents / 100, "day_label": clock.day_label(trade.story_day),
        "purse": purse,
    }  # fmt: skip


def commit_decision(
    sid: uuid.UUID, cid: uuid.UUID, text: str, reply: DecisionReply, *, msg: str | None
) -> Streamed:
    """Phase C of an answer in a decision scene: execute it now, then store the reaction."""
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid)
        stored = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if stored is not None:
            return replay_streamed(db, run, pack, stored)
        service.require_phase(run, "play")
        receipt = None
        say, sugg = reply.text, reply.suggestions
        if reply.kind == "decision" and reply.action in ("buy", "sell", "hold") and run.market_scene:
            problem = service.decision_problem(db, run, reply.action, reply.amount_eur, reply.portion)
            if problem:  # nothing to execute yet: ask, and keep the scene open
                say, sugg = problem, service.DECISION_HOW_MUCH
            else:
                trade = service.record_decision(
                    db, run, pack, text, reply.action, reply.amount_eur, reply.portion
                )
                receipt = trade_card(trade, service.purse(db, run, pack))
        ready = service.decide_ready(db, run, pack)
        payload = {
            "text": say, "speaker": C.DM_NAME, "speaker_id": C.CHRONICLER,
            "intent": "decision" if receipt else "scene_question", "suggestions": sugg,
            "clue_ids_given": [], "card": receipt, "news": None, "degraded": reply.degraded,
            "nothing_more_to_uncover": False,
            "show_decide": bool(receipt and receipt["beat"] == "decision" and ready),
            "first_visit": None, "location": None,
        }  # fmt: skip
        ev = append_event(db, run, "dm_reply", payload, f"{msg}:reply" if msg else None)
        _finish(db, run)
        out = _streamed(db, run, pack, ev, [receipt] if receipt else [])
    return out


def maybe_summarize(sid: uuid.UUID, cid: uuid.UUID, nar: Narration) -> None:
    """Rolling summary every 6 turns: a derived ``summary`` event, regenerable from the log."""
    try:
        with _session() as db:
            run, pack, hero = service.load(db, cid, sid, write=False)
            n = run.turn_count
            if n == 0 or n % SUMMARY_EVERY:
                return
            ctx = C.build_agent_context(db, run, pack, hero).with_deadline(20.0)
            if ctx.summary_at_turn >= n:
                return
        text = nar.summarize(ctx)
        with _session() as db:
            run, _, _ = service.load(db, cid, sid)
            append_event(db, run, "summary", {"summary": text, "turn_count": n})
            _finish(db, run)
    except Exception as exc:  # noqa: BLE001 - derived data, never fails a reply
        log.warning("summary failed: %s", exc)


# ==============================================================================================
# dice narration
# ==============================================================================================
def plan_narrate_roll(sid: uuid.UUID, cid: uuid.UUID, roll_id: uuid.UUID) -> StreamPlan:
    nar = get_narration()
    key = f"narr-{roll_id}"
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        ch = service.challenge_of(db, run, roll_id)
        if ch.state != "final":
            raise ApiError(409, "roll_open", "Narration runs only on the final result")
        stored = find_by_msg_id(db, cid, key)
        if stored is not None:
            return StreamPlan(cid, replay=replay_streamed(db, run, pack, stored))
        clue = None
        if ch.result == "success" and ch.clue_id:
            ev = pack.evidence_by_id(ch.clue_id)
            clue = {"title": ev.title, "text": ev.text} if ev else {
                "title": "A bonus lead", "text": service.BONUS_TEXT}  # fmt: skip
        roll = {
            "title": ch.title, "result": ch.result, "alt_source": ch.alt_source, "dc": ch.dc,
            "total": ch.total, "used": max(ch.dice) if ch.dice else None, "clue": clue,
        }  # fmt: skip
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
        db.rollback()

    def commit(reply: TurnReply) -> Streamed:
        with _session() as db:
            run, pack, _ = service.load(db, cid, sid)
            hp_change = apply_damage(db, run, pack, reply)
            text = reconcile_hp_text(reply.text, -hp_change["delta"] if hp_change else 0) \
                if reply.hp_loss > 0 else reply.text
            payload = {"text": text, "speaker": C.DM_NAME, "roll_id": str(roll_id),
                       "speaker_kind": "master", "hp_change": hp_change,
                       "degraded": reply.degraded, "suggestions": reply.suggestions}  # fmt: skip
            ev = append_event(db, run, "dm_reply", payload, key)
            _finish(db, run)
            return _streamed(db, run, pack, ev, [])

    return StreamPlan(cid, work=lambda: nar.narrate_roll(ctx, roll), commit=commit,
                      deadline_s=TURN_BUDGET_S)


# ==============================================================================================
# Buddy (not a turn)
# ==============================================================================================
def plan_buddy(
    sid: uuid.UUID, cid: uuid.UUID, raw_text: str, msg: str | None, screen: str | None
) -> StreamPlan:
    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        done = find_by_msg_id(db, cid, f"{msg}:a" if msg else None)
        if done is not None:
            return StreamPlan(cid, replay=replay_streamed(db, run, pack, done))
        text = raw_text.strip()
        if not text:
            raise ApiError(422, "empty", "Ask a question")
        append_event(db, run, "buddy_q", {"text": text}, f"{msg}:q" if msg else None)
        db.commit()
        ctx = C.build_agent_context(db, run, pack, hero, screen=screen).with_deadline(TURN_BUDGET_S)

    def commit(reply: TurnReply) -> Streamed:
        with _session() as db:
            run, pack, _ = service.load(db, cid, sid)
            payload = {"text": reply.text, "speaker": C.BUDDY_NAME, "speaker_kind": "buddy",
                       "hp_change": None, "intent": reply.intent,
                       "mood": reply.mood, "degraded": reply.degraded}  # fmt: skip
            ev = append_event(db, run, "buddy_a", payload, f"{msg}:a" if msg else None)
            _finish(db, run)
            return _streamed(db, run, pack, ev, [])

    return StreamPlan(cid, work=lambda: nar.buddy(ctx, text), commit=commit, serialize=False,
                      deadline_s=TURN_BUDGET_S)


# ==============================================================================================
# Focus hint
# ==============================================================================================
def plan_hint(sid: uuid.UUID, cid: uuid.UUID) -> StreamPlan:
    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        service.require_phase(run, "play")
        if run.focus_left < 1:
            raise ApiError(409, "no_focus", "No Focus left")
        target = _hint_target(db, run, pack)
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
        db.rollback()

    def commit(reply: TurnReply) -> Streamed:
        with _session() as db:
            run, pack, _ = service.load(db, cid, sid)
            service.require_phase(run, "play")
            if run.focus_left < 1:
                raise ApiError(409, "no_focus", "No Focus left")
            run.focus_left -= 1  # spent atomically with its event, only once a hint exists
            append_event(db, run, "focus_spend", {"kind": "hint"})
            ev = append_event(db, run, "dm_reply", {
                "text": reply.text, "speaker": C.DM_NAME, "hint_location": target["location_key"],
                "suggestions": reply.suggestions, "degraded": reply.degraded,
            })  # fmt: skip
            _finish(db, run)
            return _streamed(db, run, pack, ev, [])

    return StreamPlan(cid, work=lambda: nar.hint(ctx, target), commit=commit, deadline_s=TURN_BUDGET_S)


def _hint_target(db: Session, run: CampaignRun, pack: Pack) -> dict[str, Any]:
    gv = gated_view(run)
    vis = {e.id for e in visible_evidence(pack, gv)}
    clue = focus.hint_target(pack, vis, service.found_ids(db, run.id))
    if clue is None:
        raise ApiError(409, "no_target", "Nothing left to find")
    ev = pack.evidence_by_id(clue)
    assert ev is not None
    loc = service.location_by_key(db, run.id, rules.normalize_location(ev.location))
    return {"location_name": loc.name if loc else ev.location, "location_key": loc.key if loc else None}


# ==============================================================================================
# debrief
# ==============================================================================================
def _debrief_streamed(db: Session, run: CampaignRun, pack: Pack, deb: Any, ev: Event | None) -> Streamed:
    out = service.debrief_out(deb)
    parts = deb.narrative or {}
    text = service.debrief_text(parts, deb.forecast_line or "")
    return Streamed(
        text=text, state={"phase": run.phase},
        done={**out, "text": text, "speaker": C.DM_NAME, "speaker_kind": "master",
              "escalated": False, "hp_change": None, "new_location": None,
              "audio_text_id": ev.id if ev else None, "phase": run.phase},
    )  # fmt: skip


def _debrief_event(db: Session, cid: uuid.UUID) -> Event | None:
    return db.exec(
        select(Event).where(Event.campaign_id == cid, Event.type == "debrief").order_by(Event.seq)  # type: ignore[arg-type]
    ).first()


def plan_debrief(sid: uuid.UUID, cid: uuid.UUID) -> StreamPlan:
    from financequest.db.models_campaign import Debrief

    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        dec, oc = service.decision_of(db, cid), service.db_outcome(db, cid)
        if dec is None or oc is None:
            raise ApiError(409, "not_locked", "Lock your decision first")
        existing = db.get(Debrief, cid)
        if existing is not None:
            if run.phase in ("timeskip", "reveal"):
                run.phase = "debrief"
                _finish(db, run)
            return StreamPlan(
                cid, replay=_debrief_streamed(db, run, pack, existing, _debrief_event(db, cid))
            )
        facts = service.debrief_facts(db, run, pack, dec, oc)
        ctx = C.build_agent_context(
            db, run, pack, hero, whatif=facts["rows"], overlooked=facts["missed"],
            question=facts["question"],
        ).with_deadline(DEBRIEF_BUDGET_S)  # fmt: skip
        db.rollback()

    def commit(parts: dict[str, Any]) -> Streamed:
        with _session() as db:
            run, pack, _ = service.load(db, cid, sid)
            deb = db.get(Debrief, cid)
            if deb is None:
                deb = service.store_debrief(db, run, facts, parts)
                if run.phase in ("timeskip", "reveal"):
                    run.phase = "debrief"
                _finish(db, run)
            return _debrief_streamed(db, run, pack, deb, _debrief_event(db, cid))

    return StreamPlan(cid, work=lambda: nar.debrief(ctx), commit=commit, deadline_s=DEBRIEF_BUDGET_S)


__all__ = [
    "plan_action", "plan_buddy", "plan_debrief", "plan_hint", "plan_move", "plan_narrate_roll",
    "plan_opening",
]  # fmt: skip
