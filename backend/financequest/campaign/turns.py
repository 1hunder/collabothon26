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
from financequest.agents.campaign.fake import names_travel
from financequest.api.errors import ApiError
from financequest.campaign import clock, edu, edu_turn, focus, rules, service
from financequest.campaign import reasoning as reasoning_mod
from financequest.campaign.events import append_event, campaign_events, find_by_msg_id
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
        "awaiting_reasoning": service.awaiting_trade(db, run) is not None,
        "offer": service.offer_out(run), "hp": service.hp_now(run), "hp_eur": service.hp_now(run) * service.HP_EUR,
        "edu": service.edu_state(db, run.id),
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
        "reasoning_prompt": p.get("reasoning_prompt"),
        "all_in": bool(p.get("all_in", False)), "fast_forward": bool(p.get("fast_forward", False)),
    }


def replay_streamed(db: Session, run: CampaignRun, pack: Pack, ev: Event) -> Streamed:
    """An idempotent repeat streams the stored, already guarded reply."""
    p = dict(ev.payload or {})
    delta = state_delta(db, run, pack)
    cards = [c for c in (p.get("card"), p.get("news"), p.get("scene"), p.get("offer_card")) if c]
    done = {**p, **_done_fields(p), "audio_text_id": ev.id, **delta, "replayed": True,
            "edu_new": list(p.get("edu_new") or [])}
    if (p.get("news") or {}).get("framing"):
        done["news_text"] = p["news"]["framing"]
    return Streamed(text=str(p.get("text", "")), cards=cards, state=delta, done=done)


def _streamed(
    db: Session, run: CampaignRun, pack: Pack, ev: Event, cards: list[dict[str, Any]]
) -> Streamed:
    edu_new = edu_turn.detect_for_reply(db, run, pack, ev)  # moments this reply made worth a look
    p = dict(ev.payload or {})
    delta = state_delta(db, run, pack)
    return Streamed(
        text=str(p.get("text", "")), cards=cards, state=delta,
        done={**p, **_done_fields(p), "audio_text_id": ev.id, **delta, "edu_new": edu_new},
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
        text = rules.plain_quotes(raw_text.strip())  # "I don’t take it" from a phone keyboard
        if not text:
            raise ApiError(422, "empty", "Say what you would do")
        service.require_phase(run, "play")
        if run.pending:
            raise ApiError(409, "roll_open", "Finish the dice check first")
        waiting = service.awaiting_trade(db, run)
        if waiting is not None:
            leaves = not rules.parse_decision(text)[0] and (
                names_travel(C.build_agent_context(db, run, pack, hero), text)
                or bool(_EXPLORE_RE.search(text.lower()))
            )
            if leaves and not reasoning_mod.is_skip(text):
                # Travel or exploring right after a decision: the question is dropped, never blocks.
                service.resolve_reasoning(db, run, waiting, None, skipped=True)
            else:
                append_event(db, run, "action", {"text": text, "reasoning": True},
                             f"{msg}:action" if msg else None)  # fmt: skip
                db.commit()
                return _plan_reasoning(sid, cid, text, msg, reasoning_mod.is_skip(text))
        in_scene = bool(run.market_scene)
        if not in_scene and _states_a_decision(text) and service.due_beat(
            db, run, pack, news_now=False, asked=True, story_call=False
        ) == "decision":
            # "I want to decide: I put 300 gp in because…": the player already said what they do.
            # Open the decision scene and read this message as the answer, without asking again.
            service.open_scene(db, run, pack, "decision")
            in_scene = True
        append_event(db, run, "action", {"text": text, **({"scene": True} if in_scene else {})},
                     f"{msg}:action" if msg else None)  # fmt: skip
        db.commit()
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
    if in_scene and (ctx.scene or {}).get("beat") == "offer":  # the all-in plot's open offer
        return _plan_offer_answer(sid, cid, text, ctx, msg, nar)
    if in_scene:  # the player answers the decision scene: read it, execute it, react
        return _plan_scene_answer(sid, cid, text, ctx, msg, nar)
    return _plan_normal_turn(sid, cid, text, ctx, msg, nar)


def _states_a_decision(text: str) -> bool:
    """The message already carries a trade the engine can act on: a buy or sell with a sum or a
    share, or any buy/sell/hold said together with "I want to decide" wording."""
    action, amount, portion = rules.parse_decision(text)
    if action is None:
        return False
    if rules.is_decision_intent(text):
        return True
    return action in ("buy", "sell") and (amount is not None or portion is not None)


def _plan_reasoning(
    sid: uuid.UUID, cid: uuid.UUID, text: str, msg: str | None, skip: bool
) -> StreamPlan:
    """The player's answer to the one follow-up question: recorded verbatim (or skipped) and
    acknowledged in neutral words, with no model call. The game goes on."""
    return StreamPlan(
        cid, work=lambda: None,
        commit=lambda _: commit_reasoning(sid, cid, text, skip, msg=msg), deadline_s=TURN_BUDGET_S,
    )  # fmt: skip


def commit_reasoning(
    sid: uuid.UUID, cid: uuid.UUID, text: str, skip: bool, *, msg: str | None
) -> Streamed:
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        stored = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if stored is not None:
            return replay_streamed(db, run, pack, stored)
        trade = service.awaiting_trade(db, run)
        if trade is not None:
            service.resolve_reasoning(db, run, trade, text, skipped=skip)
        say = reasoning_mod.ack_text(text, skip)
        ctx = C.build_agent_context(db, run, pack, hero)
        payload = {
            "text": say, "speaker": reasoning_mod.trader_name(cid), "speaker_id": "curious_trader",
            "speaker_kind": "npc", "intent": "reasoning",
            "suggestions": nar_suggestions(ctx), "hp_change": None, "clue_ids_given": [],
            "card": None, "news": None, "degraded": False, "nothing_more_to_uncover": False,
            "show_decide": bool(service.decide_ready(db, run, pack)), "first_visit": None,
            "location": None,
        }  # fmt: skip
        ev = append_event(db, run, "dm_reply", payload, f"{msg}:reply" if msg else None)
        _finish(db, run)
        out = _streamed(db, run, pack, ev, [])
    return _support_followup(sid, cid, out, get_narration())  # the question held the offer back


def nar_suggestions(ctx: C.AgentContext) -> list[str]:
    from financequest.agents.campaign.graphs import default_suggestions

    return default_suggestions(ctx)


def _normal_turn_work(nar: Narration, ctx: C.AgentContext, text: str) -> TurnReply:
    if ctx.scene is not None:  # the scene is being passed: the turn must not treat it as open
        ctx.scene = None
    ctx.with_deadline(TURN_BUDGET_S)
    if ctx.npc_here is not None:  # a Master-created place: its NPC answers, or hands over
        return nar.npc_turn(ctx.with_deadline(NPC_BUDGET_S), text)
    return nar.turn(ctx, text)


def _plan_normal_turn(
    sid: uuid.UUID, cid: uuid.UUID, text: str, ctx: C.AgentContext, msg: str | None, nar: Narration
) -> StreamPlan:
    return StreamPlan(
        cid, work=lambda: _normal_turn_work(nar, ctx, text),
        commit=lambda reply: commit_turn(sid, cid, reply, msg=msg, nar=nar),
        after=lambda _: maybe_summarize(sid, cid, nar),
        deadline_s=NPC_BUDGET_S if ctx.npc_here is not None else TURN_BUDGET_S,
    )  # fmt: skip


_EXPLORE_RE = re.compile(
    r"\b(explore|exploring|travel|travelling|visit|leave|walk|wander|journey|go to|going to|"
    r"head to|head over|head back|talk (?:to|with)|talking (?:to|with)|speak (?:to|with)|chat with|meet|"
    r"(?:more|other|new|another|some) (?:npcs?|people|persons?|characters?|locals?|traders?|"
    r"merchants?|witnesses?|someone|place|places|location|locations|area|areas)|"
    r"elsewhere|somewhere else|someone else)\b"
)


_SKILL_RE = re.compile(
    r"\b(search|searching|inspect|examine|investigate|look (?:for|around|closely)|study|"
    r"scrutini[sz]e|read (?:his|her|their) (?:face|eyes|expression)|watch (?:him|her|them)|"
    r"is (?:he|she|they) (?:lying|hiding)|persuade|convince|charm|bargain with|pressure|"
    r"sneak|eavesdrop|overhear|listen in|spy|recall|remember what)\b"
)


def _names_character(ctx: C.AgentContext, text: str) -> bool:
    """The player addresses a known character by name (any word of the name, e.g. "Marla" or
    "Pennywhistle", ignoring titles like "Scholar"); that is a conversation, not a trade answer."""
    low = text.lower()
    titles = {"scholar", "broker", "treasurer", "archivist", "steward", "warden", "master", "old",
              "forge-warden", "the", "of"}  # fmt: skip
    for ch in ctx.content.get("characters", []):
        for word in re.findall(r"[A-Za-z][A-Za-z'-]+", str(ch.get("name", ""))):
            if len(word) >= 3 and word.lower() not in titles and re.search(rf"\b{re.escape(word.lower())}\b", low):
                return True
    return False


def _plan_scene_answer(
    sid: uuid.UUID, cid: uuid.UUID, text: str, ctx: C.AgentContext, msg: str | None, nar: Narration
) -> StreamPlan:
    """An answer in an open decision scene is a decision, a question about the trade, or something
    else entirely (travel, talk, explore): that last one passes the scene and runs a normal turn."""

    keep_scene = False  # a skill attempt runs as a normal turn but leaves the scene open

    def work() -> DecisionReply | TurnReply:
        nonlocal keep_scene
        no_trade_words = not rules.parse_decision(text)[0]
        # Investigating the world (search, study a face, persuade, eavesdrop…) is a dice-worthy
        # action, not a question about the trade: the Master handles it (and may call for a roll),
        # and the decision scene stays open for when the player comes back to it.
        if no_trade_words and _names_character(ctx, text):
            keep_scene = True  # "Ask Marla why…": the character answers; the scene stays open
            return _normal_turn_work(nar, ctx, text)
        if no_trade_words and _SKILL_RE.search(text.lower()):
            keep_scene = True
            return _normal_turn_work(nar, ctx, text)
        # No LLM call needed: travel to a known place, or any explore/travel/talk wording with no
        # buy/sell/hold in it (e.g. "I want to explore some new locations").
        if no_trade_words and (names_travel(ctx, text) or _EXPLORE_RE.search(text.lower())):
            return _normal_turn_work(nar, ctx, text)
        reply = nar.decide(ctx, text)
        if reply.kind == "other":
            return _normal_turn_work(nar, ctx, text)
        # The model called it a decision but found no buy/sell/hold in it and neither did the
        # parser: it isn't an answer to the scene, so let the Master handle it as a normal turn.
        if reply.kind == "decision" and no_trade_words and reply.action not in ("buy", "sell", "hold"):
            return _normal_turn_work(nar, ctx, text)
        # A "hold" must be said: the model read "I want to talk with more NPCs" as holding.
        # Without hold/wait/keep/pass wording (and no buy/sell), it is not an answer to the scene.
        if reply.kind == "decision" and reply.action == "hold" and no_trade_words:
            return _normal_turn_work(nar, ctx, text)
        return reply

    def commit(reply: DecisionReply | TurnReply) -> Streamed:
        if isinstance(reply, DecisionReply):
            return commit_decision(sid, cid, text, reply, msg=msg, nar=nar)
        if not keep_scene:
            pass_scene(sid, cid, text, msg=msg)
        return commit_turn(sid, cid, reply, msg=msg, nar=nar)

    return StreamPlan(
        cid, work=work, commit=commit, deadline_s=TURN_BUDGET_S + NPC_BUDGET_S,
        after=lambda _: maybe_summarize(sid, cid, nar),
    )  # fmt: skip


def pass_scene(sid: uuid.UUID, cid: uuid.UUID, text: str, *, msg: str | None) -> None:
    """The player did something else: the open scene is passed with no trade. The journal keeps
    it as ``scene_passed``; the day-of-decision scene comes back when they ask to decide."""
    with _session() as db:
        run, _, _ = service.load(db, cid, sid)
        if find_by_msg_id(db, cid, f"{msg}:reply" if msg else None) is not None:
            return  # idempotent repeat: the reply is replayed by the turn commit
        if isinstance(run.market_scene, dict):
            beat = str(run.market_scene.get("beat", "story"))
            run.market_scene = None
            append_event(db, run, "scene_passed", {"beat": beat, "text": text})
        _finish(db, run)


def leave_scene(sid: uuid.UUID, cid: uuid.UUID) -> dict[str, Any]:
    """The player taps "Leave" in a decision scene: it is passed with no trade, as if they had
    walked away, and comes back when they ask to decide. An open offer is not left this way: it
    is answered in words (declining an all-in offer moves the plot on)."""
    with _session() as db:
        run, _, _ = service.load(db, cid, sid)
        scene = run.market_scene if isinstance(run.market_scene, dict) else None
        if scene is not None and scene.get("beat") == "offer":
            raise ApiError(409, "offer_open", "Answer the offer first")
        if scene is not None:
            run.market_scene = None
            append_event(db, run, "scene_passed", {"beat": str(scene.get("beat", "story")),
                                                   "text": "", "left": True})  # fmt: skip
        _finish(db, run)
        return {"market_scene": None}


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
        waiting = service.awaiting_trade(db, run)
        if waiting is not None:  # travelling never waits for the question
            service.resolve_reasoning(db, run, waiting, None, skipped=True)
            db.commit()
        else:
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
            loc = created
        if reply.intent == "challenge" and reply.challenge_id:
            ch = db.get(Challenge, uuid.UUID(reply.challenge_id))
            if ch and ch.campaign_id == run.id and ch.state == "open" and gv.at_checkpoint(ch.checkpoint):
                card = service.offer_roll(run, ch, hero)
        if reply.intent == "challenge" and reply.check and not reply.challenge_id:
            cur = db.get(Location, run.current_location_id) if run.current_location_id else None
            ch = service.create_adhoc_challenge(db, run, pack, reply.check, cur.key if cur else "")
            if ch is not None:
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
    return _support_followup(sid, cid, out, nar, hp_only=True)


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
    """The receipt for an executed decision: engine figures, gold pieces only."""
    return {
        "kind": "trade", "seq": trade.seq, "beat": trade.beat, "action": trade.action,
        "amount_eur": trade.amount_cents / 100, "day_label": clock.day_label(trade.story_day),
        "purse": purse,
    }  # fmt: skip


def commit_decision(
    sid: uuid.UUID, cid: uuid.UUID, text: str, reply: DecisionReply, *, msg: str | None,
    nar: Narration | None = None,
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
        hp_change = None
        prompt = None
        flag: str | None = None
        if reply.kind == "decision" and reply.action in ("buy", "sell", "hold") and run.market_scene:
            problem = service.decision_problem(db, run, reply.action, reply.amount_eur, reply.portion)
            if problem:  # nothing to execute yet: ask, and keep the scene open
                say, sugg = problem, service.DECISION_HOW_MUCH
            else:
                trade = service.record_decision(
                    db, run, pack, text, reply.action, reply.amount_eur, reply.portion,
                    reply.reasoning, reply.reasoning_sufficient,
                )
                if reply.hp_loss > 0 and run.phase == "play":  # the scene's cost, before the receipt
                    hp_change = service.apply_hp_loss(
                        db, run, pack, reply.hp_loss, (reply.hp_reason or "A costly deal")[:200]
                    )
                    say = reconcile_hp_text(say, -hp_change["delta"] if hp_change else 0)
                receipt = trade_card(trade, service.purse(db, run, pack))
                flag = service.nothing_at_stake(db, run, pack, trade, text)
                if flag and trade.reasoning_source == reasoning_mod.AWAITING:
                    # nothing left to play for: the plot moves on, the question is not asked
                    service.resolve_reasoning(db, run, trade, None, skipped=True)
                elif trade.reasoning_source == reasoning_mod.AWAITING:  # ask once, neutrally
                    say = reasoning_mod.strip_question(say)
                    prompt = reasoning_mod.reasoning_prompt(cid, trade.reasoning, trade.seq)
                    sugg = [reasoning_mod.SKIP_CHIP]
        ready = service.decide_ready(db, run, pack)
        payload = {
            "text": say, "speaker": C.DM_NAME, "speaker_id": C.CHRONICLER,
            "intent": "decision" if receipt else "scene_question", "suggestions": sugg,
            "hp_change": hp_change,
            "clue_ids_given": [], "card": receipt, "news": None, "degraded": reply.degraded,
            "nothing_more_to_uncover": False,
            "show_decide": bool(receipt and receipt["beat"] == "decision" and ready),
            "first_visit": None, "location": None, "reasoning_prompt": prompt,
            "all_in": bool(flag),
        }  # fmt: skip
        ev = append_event(db, run, "dm_reply", payload, f"{msg}:reply" if msg else None)
        if prompt:  # the trader's question is its own entry: the backlog and a replay show it
            append_event(db, run, "dm_reply", {
                "text": prompt["text"], "speaker": prompt["speaker"], "speaker_kind": "npc",
                "speaker_id": "curious_trader", "intent": "reasoning_prompt",
            })  # fmt: skip
        _finish(db, run)
        out = _streamed(db, run, pack, ev, [receipt] if receipt else [])
        reply_id = ev.id
    if flag and nar is not None and reply_id is not None:
        return _all_in_followup(sid, cid, reply_id, flag, nar, [receipt] if receipt else [], say)
    return _support_followup(sid, cid, out, nar) if nar is not None else out


# ==============================================================================================
# the all-in plot: nothing left at stake
# ==============================================================================================
def _stored_reply(sid: uuid.UUID, cid: uuid.UUID, reply_id: int, cards: list[dict[str, Any]]) -> Streamed:
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid, write=False)
        ev = db.get(Event, reply_id)
        assert ev is not None
        return _streamed(db, run, pack, ev, cards)


def _all_in_followup(
    sid: uuid.UUID, cid: uuid.UUID, reply_id: int, flag: str, nar: Narration,
    cards: list[dict[str, Any]], said: str,
) -> Streamed:
    """The decision just made left nothing at stake. The Master chooses: an in-world offer (a
    buyback or a loan, once) or the days passing; the engine supplies every figure and does the
    rest. A refused or failed model falls back to the prepared offer or the fast-forward."""
    if flag == "offer":
        with _session() as db:
            run, pack, hero = service.load(db, cid, sid, write=False)
            ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
            ctx.offer_facts = service.offer_facts(db, run, pack)
        picked = nar.offer(ctx, ["buyback", "loan", "fast_forward"])
        if picked.kind != "fast_forward":
            with _session() as db:
                run, pack, _ = service.load(db, cid, sid)
                if run.phase != "play" or run.market_scene:
                    return _stored_reply(sid, cid, reply_id, cards)
                by = {"name": picked.name, "role": picked.role}
                offer = service.open_offer(db, run, pack, picked.kind, by, picked.text)
                suggestions = picked.suggestions
                fev = append_event(db, run, "dm_reply", {
                    "text": picked.text, "speaker": picked.name, "speaker_kind": "npc",
                    "speaker_id": "offer_broker", "intent": "offer", "offer": offer,
                    "suggestions": suggestions,
                })  # fmt: skip
                run.market_scene = {**(run.market_scene or {}), "suggestions": suggestions}
                card = {
                    **offer, "kind": "offer", "offer_kind": offer["kind"], "text": picked.text,
                    "suggestions": suggestions,
                    "story_day": run.clock_day, "day_label": clock.day_label(run.clock_day),
                    "purse": service.purse(db, run, pack), "audio_text_id": fev.id,
                }  # fmt: skip
                ev = db.get(Event, reply_id)
                if ev is not None:
                    ev.payload = {**(ev.payload or {}), "offer": offer, "offer_card": card}
                    db.add(ev)
                _finish(db, run)
            return _stored_reply(sid, cid, reply_id, [*cards, card])
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid, write=False)
        ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
    ff = nar.fast_forward(ctx, "they have every coin committed (or are done) and nothing is left to decide")
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid)
        ev = db.get(Event, reply_id)
        if ev is not None and run.phase == "play":
            service.lock_decision(db, run, pack, {}, auto=True)
            ev.payload = {**(ev.payload or {}), "text": f"{said}\n\n{ff.text}".strip(),
                          "fast_forward": True, "reasoning_prompt": None, "suggestions": []}  # fmt: skip
            db.add(ev)
            _finish(db, run)
    return _stored_reply(sid, cid, reply_id, cards)


# ==============================================================================================
# the supporting hand: help for a player in trouble
# ==============================================================================================
def _support_followup(
    sid: uuid.UUID, cid: uuid.UUID, out: Streamed, nar: Narration, *, hp_only: bool = False
) -> Streamed:
    """After a reply that may have put the player in trouble (damage, a loss at the board, a sale at
    a loss) the engine checks; the Master then offers one fitting supporting hand, once per
    campaign. The engine lists the kinds it can really give and supplies every figure; a refused or
    failed model falls back to the prepared offer. Never fails the reply."""
    reply_id = out.done.get("audio_text_id")
    if not isinstance(reply_id, int) or out.done.get("replayed"):
        return out
    try:
        with _session() as db:
            run, pack, hero = service.load(db, cid, sid, write=False)
            reason = service.support_reason(db, run, pack)
            if hp_only and reason not in service.HP_SUPPORT_REASONS:
                reason = None  # a market loss is met right after a decision, not on a walk or a talk
            options = service.support_options(db, run, pack, hero) if reason else {}
            if reason is None or not options:
                return out
            ctx = C.build_agent_context(db, run, pack, hero).with_deadline(TURN_BUDGET_S)
            ctx.offer_facts = options
        picked = nar.support(ctx, reason, list(options))
        with _session() as db:
            run, pack, hero = service.load(db, cid, sid)
            options = service.support_options(db, run, pack, hero)
            if service.support_reason(db, run, pack) is None or picked.kind not in options:
                return out
            by = {"name": picked.name, "role": picked.role}
            offer = service.open_support(db, run, picked.kind, reason, by, picked.text,
                                         options[picked.kind])  # fmt: skip
            fev = append_event(db, run, "dm_reply", {
                "text": picked.text, "speaker": picked.name, "speaker_kind": "npc",
                "speaker_id": "support_helper", "intent": "support", "offer": offer,
                "suggestions": picked.suggestions,
            })  # fmt: skip
            run.market_scene = {**(run.market_scene or {}), "suggestions": picked.suggestions}
            card = {
                **offer, "kind": "offer", "offer_kind": offer["kind"], "text": picked.text,
                "suggestions": picked.suggestions, "story_day": run.clock_day,
                "day_label": clock.day_label(run.clock_day), "purse": service.purse(db, run, pack),
                "audio_text_id": fev.id,
            }  # fmt: skip
            ev = db.get(Event, reply_id)
            if ev is not None:
                ev.payload = {**(ev.payload or {}), "offer": offer, "offer_card": card}
                db.add(ev)
            _finish(db, run)
        new = _stored_reply(sid, cid, reply_id, [*out.cards, card])
        for key in ("news_text",):
            if key in out.done:
                new.done[key] = out.done[key]
        return new
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - help is a bonus: the reply stands without it
        log.warning("supporting hand failed: %s", exc)
        return out


def _note_support_taken(sid: uuid.UUID, cid: uuid.UUID, kind: str) -> None:
    """A rescue buyback went through the decision path: record that the help was taken."""
    with _session() as db:
        run, _, _ = service.load(db, cid, sid)
        if service.offer_out(run) is None and not service.support_taken(db, run.id):
            append_event(db, run, "support_taken", {"kind": kind})
        _finish(db, run)


def commit_support(
    sid: uuid.UUID, cid: uuid.UUID, text: str, reply: TurnReply, *, taken: bool, msg: str | None
) -> Streamed:
    """The answer to a supporting hand (a loan, a patron's gift, a free look, or a decline): the
    engine applies it, the Master narrates it, and the story simply goes on."""
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        stored = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if stored is not None:
            return replay_streamed(db, run, pack, stored)
        service.require_phase(run, "play")
        offer = service.offer_out(run)
        card: dict[str, Any] | None = None
        clues: list[str] = []
        if offer and offer.get("reason"):
            kind = str(offer["kind"])
            if not taken:
                service.close_offer(db, run, "support_declined", {"kind": kind, "text": text})
            else:
                if kind == "loan":
                    trade = service.accept_loan(db, run, pack, text)
                    loan = service.loan_of([trade])
                    assert loan is not None
                    card = {**trade_card(trade, service.purse(db, run, pack)), "loan": service.loan_out(loan)}
                elif kind == "patron_grant":
                    trade = service.accept_grant(db, run, pack)
                    grant = service.grant_of([trade])
                    assert grant is not None
                    card = {**trade_card(trade, service.purse(db, run, pack)), "grant": service.grant_out(grant)}
                else:
                    clues = service.accept_second_look(db, run, pack, hero)
                append_event(db, run, "support_taken", {"kind": kind, "by": offer["by"]})
        payload = _plot_payload(
            reply, intent="offer_answer", card=card, clue_ids_given=clues,
            suggestions=nar_suggestions(C.build_agent_context(db, run, pack, hero)),
        )  # fmt: skip
        ev = append_event(db, run, "dm_reply", payload, f"{msg}:reply" if msg else None)
        _finish(db, run)
        return _streamed(db, run, pack, ev, [card] if card else [])


def _plan_offer_answer(
    sid: uuid.UUID, cid: uuid.UUID, text: str, ctx: C.AgentContext, msg: str | None, nar: Narration
) -> StreamPlan:
    """The player answers the open offer in words: accept (a buyback is a sell at the board price,
    a loan adds coins now), decline, or do something else. Declining, or something else twice,
    moves the plot to its finish."""
    offer = (ctx.scene or {}).get("offer") or {}
    kind = str(offer.get("kind"))
    support = bool(offer.get("reason"))  # a supporting hand: declining just lets the story go on
    sells = kind in ("buyback", "rescue_buyback")
    ignored = int((ctx.scene or {}).get("ignored", 0))
    read = rules.read_offer_answer(text)
    action = rules.parse_decision(text)[0]
    if sells and action == "sell":
        read = "accept"
    elif sells and action == "hold":
        read = "decline"
    if read == "other" and ignored + 1 >= rules.OFFER_IGNORED_MAX:
        read = "ignored"

    def work() -> tuple[str, Any]:
        if read == "accept" and sells:
            say = text if action == "sell" else "I sell half of my coins to the broker."
            return "buyback", nar.decide(ctx, say)
        if read == "accept" and support:
            return "support", nar.support_answer(ctx, kind, True)
        if read == "accept":
            return "loan", nar.offer_answer(ctx)
        if read in ("decline", "ignored") and support:
            return "support_no", nar.support_answer(ctx, kind, False)
        if read in ("decline", "ignored"):
            why = ("declined: they turned the offer down" if read == "decline"
                   else "ignored: they paid the offer no attention twice")  # fmt: skip
            return "forward", nar.fast_forward(ctx, why)
        return "other", _normal_turn_work(nar, ctx, text)

    def commit(res: tuple[str, Any]) -> Streamed:
        tag, reply = res
        if tag == "buyback":
            if isinstance(reply, DecisionReply) and reply.kind == "decision" and reply.action == "sell" \
                    and reply.amount_eur is None and reply.portion is None:
                reply.portion = "half"  # "I accept": the default is half of what they hold
            out = commit_decision(sid, cid, text, reply, msg=msg, nar=nar)
            if support:
                _note_support_taken(sid, cid, kind)
            return out
        if tag in ("support", "support_no"):
            return commit_support(sid, cid, text, reply, taken=tag == "support", msg=msg)
        if tag == "loan":
            return commit_loan(sid, cid, text, reply, msg=msg)
        if tag == "forward":
            return commit_fast_forward(sid, cid, reply, msg=msg)
        note_offer_ignored(sid, cid, text, msg=msg)
        return commit_turn(sid, cid, reply, msg=msg, nar=nar)

    return StreamPlan(
        cid, work=work, commit=commit, deadline_s=TURN_BUDGET_S + NPC_BUDGET_S,
        after=lambda _: maybe_summarize(sid, cid, nar),
    )  # fmt: skip


def note_offer_ignored(sid: uuid.UUID, cid: uuid.UUID, text: str, *, msg: str | None) -> None:
    with _session() as db:
        run, _, _ = service.load(db, cid, sid)
        if find_by_msg_id(db, cid, f"{msg}:reply" if msg else None) is not None:
            return
        if service.offer_out(run):
            service.note_offer_ignored(db, run, text)
        _finish(db, run)


def _plot_payload(reply: TurnReply, **extra: Any) -> dict[str, Any]:
    return {
        "text": reply.text, "speaker": C.DM_NAME, "speaker_id": C.CHRONICLER,
        "suggestions": reply.suggestions, "hp_change": None, "clue_ids_given": [], "card": None,
        "news": None, "degraded": reply.degraded, "nothing_more_to_uncover": False,
        "show_decide": False, "first_visit": None, "location": None, **extra,
    }  # fmt: skip


def commit_loan(
    sid: uuid.UUID, cid: uuid.UUID, text: str, reply: TurnReply, *, msg: str | None
) -> Streamed:
    """The loan: the principal joins the purse now (a ``loan`` trade); the repayment comes off the
    final result."""
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid)
        stored = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if stored is not None:
            return replay_streamed(db, run, pack, stored)
        service.require_phase(run, "play")
        card = None
        if service.offer_out(run):
            trade = service.accept_loan(db, run, pack, text)
            loan = service.loan_of([trade])
            assert loan is not None
            card = {**trade_card(trade, service.purse(db, run, pack)), "loan": service.loan_out(loan)}
        payload = _plot_payload(reply, intent="offer_answer", card=card,
                                suggestions=nar_suggestions(C.build_agent_context(db, run, pack, hero)))
        ev = append_event(db, run, "dm_reply", payload, f"{msg}:reply" if msg else None)
        _finish(db, run)
        return _streamed(db, run, pack, ev, [card] if card else [])


def commit_fast_forward(
    sid: uuid.UUID, cid: uuid.UUID, reply: TurnReply, *, msg: str | None
) -> Streamed:
    """The offer was declined or ignored: the position is sealed as it stands and the story goes to
    its finish (phase timeskip: the client opens the outcome)."""
    with _session() as db:
        run, pack, _ = service.load(db, cid, sid)
        stored = find_by_msg_id(db, cid, f"{msg}:reply" if msg else None)
        if stored is not None:
            return replay_streamed(db, run, pack, stored)
        service.require_phase(run, "play")
        service.lock_decision(db, run, pack, {}, auto=True)
        ev = append_event(db, run, "dm_reply", _plot_payload(
            reply, intent="fast_forward", fast_forward=True, all_in=True, suggestions=[],
        ), f"{msg}:reply" if msg else None)  # fmt: skip
        _finish(db, run)
        return _streamed(db, run, pack, ev, [])


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
        adhoc = rules.is_adhoc(ch.kind)
        roll = {
            "title": ch.title, "result": ch.result, "dc": ch.dc, "clue": clue,
            "alt_source": None if adhoc else ch.alt_source,
            "total": ch.total, "used": max(ch.dice) if ch.dice else None,
            "skill": rules.adhoc_skill(ch.kind),
            "stakes": ch.alt_source if adhoc else None,
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
            out = _streamed(db, run, pack, ev, [])
        return _support_followup(sid, cid, out, nar, hp_only=True)

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
        append_event(db, run, "buddy_q", {"text": text, **({"screen": screen} if screen else {})},
                     f"{msg}:q" if msg else None)
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


# ==============================================================================================
# educational moments: the lesson (JSON, not SSE) and dismissing a bubble
# ==============================================================================================
LESSON_BUDGET_S = 10.0


def _moment(db: Session, cid: uuid.UUID, moment_id: str) -> tuple[edu.Moment, list[Event]]:
    events = campaign_events(db, cid)
    m = next((x for x in edu.moments(events) if x.id == moment_id), None)
    if m is None:
        raise ApiError(404, "not_found", "Educational moment not found")
    return m, events


def make_lesson(sid: uuid.UUID, cid: uuid.UUID, moment_id: str) -> dict[str, Any]:
    """CommerzBuddy's lesson for a moment (guarded; the prepared lesson on any failure), cached in
    the event log so asking again returns the same lesson. Marks a pending moment as viewed."""
    nar = get_narration()
    with _session() as db:
        run, pack, hero = service.load(db, cid, sid, write=False)
        m, events = _moment(db, cid, moment_id)
        have = edu.cached_lesson(events, moment_id)
        if have is None:
            ctx = C.build_agent_context(db, run, pack, hero).with_deadline(LESSON_BUDGET_S)
            moment = {"id": m.id, "concept_key": m.concept_key, "title": m.title, "facts": m.facts}
        db.rollback()
    if have is None:
        try:
            have = nar.edu_lesson(ctx, moment)
        except Exception as exc:  # noqa: BLE001 - the prepared lesson always works
            log.warning("lesson graph failed, using the prepared lesson: %s", exc)
            from financequest.agents.campaign.edu_lessons import prepared_lesson

            have = prepared_lesson(m.concept_key, m.facts)
    with _session() as db:
        run, _, _ = service.load(db, cid, sid)
        m, events = _moment(db, cid, moment_id)
        cached = edu.cached_lesson(events, moment_id)
        if cached is None:
            append_event(db, run, "edu_lesson", {"id": m.id, "lesson": have})
        else:
            have = cached
        if m.status == "pending":
            append_event(db, run, "edu_viewed", {"id": m.id})
        _finish(db, run)
    return {"id": m.id, "title": m.title, **have}


def dismiss_moment(sid: uuid.UUID, cid: uuid.UUID, moment_id: str) -> dict[str, Any]:
    with _session() as db:
        run, _, _ = service.load(db, cid, sid)
        m, _ = _moment(db, cid, moment_id)
        if m.status == "pending":
            append_event(db, run, "edu_dismissed", {"id": m.id})
        _finish(db, run)
        return {"id": m.id, "status": "dismissed" if m.status == "pending" else m.status,
                "edu": service.edu_state(db, cid)}
