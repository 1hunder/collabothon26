"""The Veteran's endpoints behind the router: overview, conversation, timeline card, lessons.

Everything here is hero-scoped. Nothing reads the running campaign beyond its leak terms, and
nothing writes to ``campaign_run`` or the campaign event log: talking to the Veteran spends no
turn and no focus and never moves the story clock or the news.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlmodel import Session, col, select

from financequest.agents.veteran.context import (
    HISTORY_TURNS,
    VETERAN_ID,
    VETERAN_NAME,
    VeteranContext,
)
from financequest.agents.veteran.fake import aside
from financequest.agents.veteran.narration import VeteranReply, get_veteran
from financequest.api.errors import ApiError
from financequest.campaign import service as cs
from financequest.campaign.stream import Streamed, StreamPlan
from financequest.db.models_campaign import CampaignRun, Hero
from financequest.db.models_veteran import (
    VeteranLesson,
    VeteranMemory,
    VeteranMessage,
    VeteranProfile,
)
from financequest.db.session import get_engine
from financequest.veteran import memory

FULL_NAME = "Brannoc Greyhallow"
TALK_BUDGET_S = 15.0
RECENT = 3
LESSON_MAX = 280
HABITS = "habits"


def _session() -> Session:
    return Session(get_engine())


def hero_of(db: Session, sid: uuid.UUID) -> Hero:
    hero = cs.get_hero(db, sid)
    if hero is None:
        raise ApiError(404, "no_hero", "No hero yet")
    return hero


def _memories(
    db: Session, hero: Hero, sealed: memory.Sealed
) -> list[tuple[VeteranMemory, CampaignRun]]:
    """The hero's remembered campaigns, oldest first, minus any the running campaign seals."""
    out = []
    for m in memory.ensure_memory(db, hero.id):
        run = db.get(CampaignRun, m.campaign_id)
        if run is not None and not sealed.covers(db, run):
            out.append((m, run))
    return out


def _message_out(m: VeteranMessage) -> dict[str, Any]:
    p = m.payload or {}
    return {
        "id": f"v{m.id}",
        "role": m.role,
        "topic": m.topic,
        "text": m.text,
        "mood": p.get("mood"),
        "suggestions": p.get("suggestions") or [],
        "show_timeline": bool(p.get("show_timeline")),
    }


def _lessons(db: Session, hero: Hero) -> list[dict[str, Any]]:
    rows = db.exec(
        select(VeteranLesson)
        .where(VeteranLesson.hero_id == hero.id)
        .order_by(col(VeteranLesson.created_at))
    )
    out = []
    for les in rows:
        title = None
        if les.campaign_id:
            run = db.get(CampaignRun, les.campaign_id)
            title = cs.pack_of(db, run).title if run else None
        out.append(
            {
                "id": les.id,
                "text": les.text,
                "campaign_id": str(les.campaign_id) if les.campaign_id else None,
                "quest_title": title,
                "created_at": les.created_at.date().isoformat(),
            }
        )
    return out


def overview(db: Session, sid: uuid.UUID) -> dict[str, Any]:
    hero = hero_of(db, sid)
    sealed = memory.sealed_for(db, hero)
    mems = _memories(db, hero, sealed)
    prof = db.get(VeteranProfile, hero.id)
    msgs = list(
        db.exec(
            select(VeteranMessage)
            .where(VeteranMessage.hero_id == hero.id)
            .order_by(col(VeteranMessage.id).desc())
            .limit(20)
        )
    )
    db.commit()  # ensure_memory may have filled gaps
    return {
        "name": FULL_NAME,
        "speaker": VETERAN_NAME,
        "speaker_id": VETERAN_ID,
        "has_memory": bool(mems),
        "running": sealed.scenario_id is not None,
        "quests": [memory.short(m, r, db) for m, r in reversed(mems)],  # newest first
        "profile": (prof.data if prof and mems else None),
        "lessons": _lessons(db, hero),
        "messages": [_message_out(m) for m in reversed(msgs)],
    }


def _topic_of(raw: str | None, allowed: dict[str, tuple[VeteranMemory, CampaignRun]]) -> str | None:
    if raw in (None, "", "none"):
        return None
    if raw == HABITS:
        return HABITS
    if raw in allowed:
        return raw
    raise ApiError(404, "unknown_topic", "The Veteran has no memory of that quest")


def _opening_line(
    topic: str | None, allowed: dict[str, tuple[VeteranMemory, CampaignRun]], db: Session
) -> str:
    if topic == HABITS:
        return "What habits do you see in me across my quests?"
    if topic:
        return f"Let's talk about {cs.pack_of(db, allowed[topic][1]).title}."
    return "Hello."


def build_context(
    db: Session,
    hero: Hero,
    topic: str | None,
    mems: list[tuple[VeteranMemory, CampaignRun]],
    sealed: memory.Sealed,
) -> VeteranContext:
    msgs = list(
        db.exec(
            select(VeteranMessage)
            .where(
                VeteranMessage.hero_id == hero.id,
                VeteranMessage.topic == topic if topic else col(VeteranMessage.topic).is_(None),
            )
            .order_by(col(VeteranMessage.id))
        )
    )
    step = sum(1 for m in msgs if m.role == "veteran" and (m.payload or {}).get("walk"))
    focus = None
    if topic and topic != HABITS:
        m, run = next((m, r) for m, r in mems if str(r.id) == topic)
        focus = memory.campaign_detail(db, run, m)
    prof = db.get(VeteranProfile, hero.id)
    return VeteranContext(
        hero_name=hero.name,
        hero_class=hero.hero_class,
        topic=topic,
        profile=prof.data if prof and mems else None,
        recent=[memory.short(m, r, db) for m, r in mems[-RECENT:]],
        focus=focus,
        history=[(m.role, m.text) for m in msgs[-HISTORY_TURNS:]],
        step=step,
        running=sealed.scenario_id is not None,
        leak_terms=sealed.leak_terms,
    )


def _msg_key(hero_id: uuid.UUID, msg: str | None, part: str) -> str | None:
    return f"veteran:{hero_id}:{msg}:{part}" if msg else None


def _streamed(m: VeteranMessage) -> Streamed:
    p = m.payload or {}
    done = {
        "text": m.text,
        "speaker": VETERAN_NAME,
        "speaker_id": VETERAN_ID,
        "topic": m.topic,
        "mood": p.get("mood"),
        "suggestions": p.get("suggestions") or [],
        "show_timeline": bool(p.get("show_timeline")),
        "degraded": bool(p.get("degraded")),
        "audio_text_id": f"v{m.id}",
        "message_id": f"v{m.id}",
    }
    return Streamed(text=m.text, done=done)


def plan_talk(sid: uuid.UUID, topic_raw: str | None, raw_text: str, msg: str | None) -> StreamPlan:
    with _session() as db:
        hero = hero_of(db, sid)
        done = (
            db.exec(
                select(VeteranMessage).where(
                    VeteranMessage.client_msg_id == _msg_key(hero.id, msg, "a")
                )
            ).first()
            if msg
            else None
        )
        if done is not None:
            s = _streamed(done)
            s.done["replayed"] = True
            return StreamPlan(hero.id, replay=s)
        sealed = memory.sealed_for(db, hero)
        mems = _memories(db, hero, sealed)
        allowed = {str(r.id): (m, r) for m, r in mems}
        # a hero with nothing to remember only gets small talk, but a quest id must exist
        asks_quest = topic_raw not in (None, "", HABITS)
        topic = _topic_of(topic_raw, allowed) if mems or asks_quest else None
        text = raw_text.strip()[:600] or _opening_line(topic, allowed, db)
        ctx = build_context(db, hero, topic, mems, sealed).with_deadline(TALK_BUDGET_S)
        walk = aside(text) is None
        db.add(
            VeteranMessage(
                hero_id=hero.id,
                role="player",
                topic=topic,
                text=text,
                client_msg_id=_msg_key(hero.id, msg, "q"),
            )
        )
        db.commit()
        hero_id = hero.id

    def commit(reply: VeteranReply) -> Streamed:
        with _session() as db:
            m = VeteranMessage(
                hero_id=hero_id,
                role="veteran",
                topic=topic,
                text=reply.text,
                payload={
                    "mood": reply.mood,
                    "suggestions": reply.suggestions,
                    "show_timeline": reply.show_timeline and bool(ctx.focus),
                    "degraded": reply.degraded,
                    "walk": walk,
                },
                client_msg_id=_msg_key(hero_id, msg, "a"),
            )
            db.add(m)
            db.commit()
            db.refresh(m)
            return _streamed(m)

    return StreamPlan(
        hero_id, work=lambda: get_veteran().talk(ctx, text), commit=commit, deadline_s=TALK_BUDGET_S
    )


def timeline(db: Session, sid: uuid.UUID, cid: uuid.UUID) -> dict[str, Any]:
    hero = hero_of(db, sid)
    sealed = memory.sealed_for(db, hero)
    pair = next(((m, r) for m, r in _memories(db, hero, sealed) if r.id == cid), None)
    db.commit()
    if pair is None:
        raise ApiError(404, "unknown_topic", "The Veteran has no memory of that quest")
    d = memory.campaign_detail(db, pair[1], pair[0])
    return {
        k: d[k]
        for k in (
            "campaign_id",
            "number",
            "title",
            "company",
            "real_name",
            "decisions",
            "forecast",
            "result",
            "missed",
            "xp",
            "sound_overall",
            "real_case",
        )
    }


def add_lesson(db: Session, sid: uuid.UUID, text: str, cid: uuid.UUID | None) -> dict[str, Any]:
    hero = hero_of(db, sid)
    clean = " ".join(text.split())
    if not 3 <= len(clean) <= LESSON_MAX:
        raise ApiError(422, "invalid_lesson", f"A lesson is 3–{LESSON_MAX} characters.")
    if cid is not None:
        run = db.get(CampaignRun, cid)
        if run is None or run.hero_id != hero.id or run.status != "finished":
            raise ApiError(404, "unknown_topic", "The Veteran has no memory of that quest")
    les = VeteranLesson(hero_id=hero.id, campaign_id=cid, text=clean)
    db.add(les)
    db.commit()
    return next(x for x in _lessons(db, hero) if x["id"] == les.id)


def spoken_text(db: Session, message_id: int) -> str | None:
    m = db.get(VeteranMessage, message_id)
    return m.text if m and m.role == "veteran" else None
