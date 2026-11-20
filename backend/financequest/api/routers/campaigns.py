"""Campaign endpoints. Narrated replies (opening, actions, move, narrate-roll, buddy, focus/hint,
debrief) are Server-Sent Events built by ``campaign/turns.py`` and driven by ``api/sse.py``;
validation errors still use the JSON error envelope because they are raised before streaming."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlmodel import Session
from sse_starlette.sse import EventSourceResponse

from financequest.api.deps import DbSession, SessionId
from financequest.api.errors import ApiError
from financequest.api.sse import sse_response
from financequest.campaign import rules, service, turns
from financequest.campaign.events import append_event, campaign_events
from financequest.campaign.journal import journal
from financequest.campaign.narration import get_narration
from financequest.campaign.pack import Pack
from financequest.config import get_settings
from financequest.db.models_campaign import CampaignRun, Challenge, Hero, Location

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CreateIn(BaseModel):
    interests: list[str] = Field(default_factory=list)


class RollIn(BaseModel):
    challenge_id: uuid.UUID
    mode: Literal["normal", "advantage"] = "normal"


class TextIn(BaseModel):
    text: str
    client_msg_id: str | None = None


class BuddyIn(TextIn):
    """``screen`` names what the player has open ("market_square", "library", "document:<id>",
    "commit"); the server builds the on-screen data from the gated view, never from the client."""

    screen: str | None = None


class MoveIn(BaseModel):
    location_id: uuid.UUID
    client_msg_id: str | None = None


class NarrateIn(BaseModel):
    roll_id: uuid.UUID


class ReflectIn(BaseModel):
    text: str


def _load(
    db: Session, cid: uuid.UUID, sid: uuid.UUID, write: bool = True
) -> tuple[CampaignRun, Pack, Hero]:
    if write:
        run = service.lock_run(db, cid, sid)
    else:
        found = db.get(CampaignRun, cid)
        if found is None or found.player_id != sid:
            raise ApiError(404, "not_found", "Campaign not found")
        run = found
    hero = db.get(Hero, run.hero_id)
    assert hero is not None
    return run, service.pack_of(db, run), hero


def _finish(db: Session, run: CampaignRun) -> None:
    service.touch(run)
    db.add(run)
    db.commit()


@router.post("", status_code=201)
async def create_campaign(body: CreateIn, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run = await run_in_threadpool(service.create_campaign, db, sid, body.interests)
    s = get_settings()
    if s.fake_llm or s.google_genai_api_key:
        from financequest.media.art import start_art_job

        pack = service.pack_of(db, run)
        for loc in service.locations(db, run.id):
            if not loc.fixed:
                start_art_job(loc.id, pack.leak_terms)
    return await run_in_threadpool(lambda: service.build_state(db, run, service.pack_of(db, run)))


@router.get("/{cid}")
def get_campaign(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid, write=False)
    return service.build_state(db, run, pack)


@router.post("/{cid}/opening")
async def opening(cid: uuid.UUID, sid: SessionId) -> EventSourceResponse:
    return sse_response(await run_in_threadpool(turns.plan_opening, sid, cid))


@router.post("/{cid}/actions")
async def actions(cid: uuid.UUID, body: TextIn, sid: SessionId) -> EventSourceResponse:
    plan = await run_in_threadpool(turns.plan_action, sid, cid, body.text, body.client_msg_id)
    return sse_response(plan)


@router.post("/{cid}/move")
async def move(cid: uuid.UUID, body: MoveIn, sid: SessionId) -> EventSourceResponse:
    plan = await run_in_threadpool(
        turns.plan_move, sid, cid, body.location_id, body.client_msg_id
    )
    return sse_response(plan)


@router.post("/{cid}/rolls")
def roll(cid: uuid.UUID, body: RollIn, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, hero = _load(db, cid, sid)
    ch = service.challenge_of(db, run, body.challenge_id)
    out = service.do_roll(db, run, pack, hero, ch, body.mode)
    _finish(db, run)
    return out


@router.post("/{cid}/rolls/{rid}/reroll")
def reroll(cid: uuid.UUID, rid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, hero = _load(db, cid, sid)
    out = service.do_reroll(db, run, pack, hero, service.challenge_of(db, run, rid))
    _finish(db, run)
    return out


@router.post("/{cid}/rolls/{rid}/accept")
def accept(cid: uuid.UUID, rid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid)
    out = service.do_accept(db, run, pack, service.challenge_of(db, run, rid))
    _finish(db, run)
    return out


@router.post("/{cid}/narrate-roll")
async def narrate_roll(cid: uuid.UUID, body: NarrateIn, sid: SessionId) -> EventSourceResponse:
    return sse_response(await run_in_threadpool(turns.plan_narrate_roll, sid, cid, body.roll_id))


@router.post("/{cid}/buddy")
async def buddy(cid: uuid.UUID, body: BuddyIn, sid: SessionId) -> EventSourceResponse:
    plan = await run_in_threadpool(
        turns.plan_buddy, sid, cid, body.text, body.client_msg_id, body.screen
    )
    return sse_response(plan)


@router.post("/{cid}/focus/hint")
async def focus_hint(cid: uuid.UUID, sid: SessionId) -> EventSourceResponse:
    return sse_response(await run_in_threadpool(turns.plan_hint, sid, cid))


@router.post("/{cid}/focus/bonus-lead")
def bonus_lead(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, hero = _load(db, cid, sid)
    service.require_phase(run, "play")
    if run.focus_left < 1:
        raise ApiError(409, "no_focus", "No Focus left")
    if run.bonus_lead_used:
        raise ApiError(409, "bonus_used", "The bonus lead was already chased")
    if run.pending:
        raise ApiError(409, "roll_open", "Finish the dice check first")
    cur = db.get(Location, run.current_location_id) if run.current_location_id else None
    ch = Challenge(
        campaign_id=run.id, key=service.BONUS_CLUE, title="A bonus lead", kind="obscure_lead",
        dc=rules.BONUS_DC, checkpoint=run.checkpoint, location_key=cur.key if cur else None,
        clue_id=service.BONUS_CLUE, optional=True,
    )  # fmt: skip
    db.add(ch)
    db.flush()
    run.focus_left -= 1
    run.bonus_lead_used = True
    append_event(db, run, "focus_spend", {"kind": "bonus_lead"})
    card = service.offer_roll(run, ch, hero)
    _finish(db, run)
    return {**card, "focus_left": run.focus_left}


@router.put("/{cid}/commit-draft", status_code=204)
def commit_draft(cid: uuid.UUID, body: dict[str, Any], db: DbSession, sid: SessionId) -> Response:
    run, pack, _ = _load(db, cid, sid)
    if service.decision_of(db, cid) is not None or run.phase not in ("play", "commit"):
        raise ApiError(409, "locked", "The decision is locked")
    if not service.decide_ready(db, run, pack):
        raise ApiError(409, "not_ready", "Keep investigating first")
    allowed = ("action", "amount_eur", "evidence", "forecast_pct", "confidence")
    fields = {("action" if k == "decision" else k): v for k, v in body.items()}  # legacy alias
    run.commit_draft = {**(run.commit_draft or {}), **{k: v for k, v in fields.items() if k in allowed}}
    run.phase = "commit"
    append_event(db, run, "commit_draft", run.commit_draft)
    _finish(db, run)
    return Response(status_code=204)


@router.post("/{cid}/resume-play")
def resume_play(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid)
    service.require_phase(run, "commit", "play")
    run.phase = "play"
    _finish(db, run)
    return {"phase": run.phase, "commit_draft": run.commit_draft}


@router.post("/{cid}/lock")
def lock(cid: uuid.UUID, body: dict[str, Any], db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid)
    dec, oc = service.lock_decision(db, run, pack, body)
    _finish(db, run)
    return service.reveal_payload(db, run, pack, dec, oc)


@router.get("/{cid}/reveal")
def reveal(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid)
    dec = service.decision_of(db, cid)
    oc = service.db_outcome(db, cid)
    if dec is None or oc is None:
        raise ApiError(409, "not_locked", "Lock your decision first")
    if run.phase == "timeskip":
        run.phase = "reveal"
        append_event(db, run, "reveal", {})
        _finish(db, run)
    return service.reveal_payload(db, run, pack, dec, oc)


@router.post("/{cid}/debrief")
async def debrief(cid: uuid.UUID, sid: SessionId) -> EventSourceResponse:
    return sse_response(await run_in_threadpool(turns.plan_debrief, sid, cid))


@router.post("/{cid}/reflection")
def reflection(cid: uuid.UUID, body: ReflectIn, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid)
    dec, oc = service.decision_of(db, cid), service.db_outcome(db, cid)
    if dec is None or oc is None or run.phase in ("setup", "play", "commit", "timeskip"):
        raise ApiError(409, "wrong_phase", "Not allowed yet")
    text = body.text.strip()
    if service.has_event(db, cid, "debrief_complete"):
        return {"scenario_id": str(run.scenario_id)}
    if len(text) < 10:
        raise ApiError(422, "too_short", "Write at least 10 characters.")
    deb = service.debrief_payload(db, run, pack, dec, oc, get_narration())
    deb.reflection_text = text
    db.add(deb)
    append_event(db, run, "reflection", {"text": text})
    append_event(db, run, "debrief_complete", {})
    run.phase = "company"
    _finish(db, run)
    return {"scenario_id": str(run.scenario_id)}


@router.post("/{cid}/xp")
def xp_endpoint(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, pack, _ = _load(db, cid, sid)
    award = service.make_xp(db, run, pack, get_narration())
    _finish(db, run)
    return {"categories": award.categories, "total": award.total}


@router.post("/{cid}/finish")
def finish(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    run, _, _ = _load(db, cid, sid)
    out = service.finish(db, run)
    _finish(db, run)
    return out


@router.get("/{cid}/journal")
def get_journal(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    _load(db, cid, sid, write=False)
    return {"entries": journal(campaign_events(db, cid))}
