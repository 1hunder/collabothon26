"""SSE driver for narrated replies.

Order of events: ``status`` (writing) at once; then, only after the reply passed the guards and was
committed, ``token`` word by word, ``card`` (dice | news), ``state`` (deltas), ``done`` (final text,
speaker, suggestions, ids, ``audio_text_id``). ``error`` with code ``lost_thread`` when no output
exists after the deadline. ``: ping`` heartbeats keep proxies and phones awake.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any

from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from financequest.api.errors import ApiError
from financequest.campaign.stream import Streamed, StreamPlan
from financequest.media import tts

log = logging.getLogger("financequest.sse")
TOKEN_DELAY_S = 0.035  # ~30-40 ms per word
HEARTBEAT_S = 5
LOST_THREAD = {"code": "lost_thread", "message": "The Campaign Master lost the thread."}
_WORD = re.compile(r"\S+\s*")
_locks: dict[uuid.UUID, asyncio.Lock] = {}
# The player has voice on (``X-Voice: on`` on the request): start the reply's speech early.
_voice_on: ContextVar[bool] = ContextVar("voice_on", default=False)


class VoiceHeaderMiddleware:
    """Pure ASGI, so the flag is visible to the streamed response (it runs in this context)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        on = dict(scope.get("headers") or []).get(b"x-voice", b"").lower() == b"on"
        token = _voice_on.set(on)
        try:
            await self.app(scope, receive, send)
        finally:
            _voice_on.reset(token)


def _speech_jobs(out: Streamed) -> list[tuple[str, str]]:
    """(stored text, voice) of every line this reply will speak: the reply and its cards."""
    jobs: list[tuple[str, str]] = []
    text = out.done.get("text") or out.text
    if out.done.get("audio_text_id") is not None and isinstance(text, str) and text.strip():
        jobs.append((text, tts.voice_for_speaker(out.done.get("speaker"))))
    for card in out.cards:
        if card.get("framing_audio_text_id") is not None and card.get("framing"):
            jobs.append((str(card["framing"]), "dm"))
        if card.get("kind") == "market" and card.get("audio_text_id") is not None and card.get("text"):
            jobs.append((str(card["text"]), "dm"))
    return jobs


def _prewarm(out: Streamed) -> None:
    """Synthesis starts now, while the text still streams, not when the browser asks (that
    was 2 s of streaming plus 8 s of synthesis of silence after every reply)."""
    for text, voice in _speech_jobs(out):
        task = asyncio.ensure_future(tts.prewarm(text, voice))
        _background.add(task)
        task.add_done_callback(_background.discard)
_background: set[asyncio.Future[Any]] = set()


def _lock_for(cid: uuid.UUID) -> asyncio.Lock:
    """One narrated reply per campaign at a time (single worker; DB row locks cover the rest)."""
    return _locks.setdefault(cid, asyncio.Lock())


def event(name: str, data: dict[str, Any]) -> ServerSentEvent:
    return ServerSentEvent(data=json.dumps(data, ensure_ascii=False, default=str), event=name)


async def _in_thread(fn: Any, *args: Any) -> Any:
    """Run blocking work in a thread that a timeout can abandon (anyio's default cannot)."""
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


async def _tokens(text: str) -> AsyncIterator[ServerSentEvent]:
    for w in _WORD.findall(text):
        yield event("token", {"text": w})
        if TOKEN_DELAY_S > 0:
            await asyncio.sleep(TOKEN_DELAY_S)


async def _produce(plan: StreamPlan, t0: float) -> Streamed | dict[str, Any]:
    """Phases B and C. Returns the streamed reply, or an error dict."""
    if plan.replay is not None:
        return plan.replay
    assert plan.work is not None and plan.commit is not None
    lock = _lock_for(plan.campaign_id) if plan.serialize else None
    if lock is not None:
        await lock.acquire()
    try:
        remaining = max(plan.deadline_s - (time.monotonic() - t0), 0.05)
        try:
            result = await asyncio.wait_for(_in_thread(plan.work), remaining)
        except TimeoutError:
            if plan.on_timeout is None:
                return dict(LOST_THREAD)
            result = plan.on_timeout()
        return await _in_thread(plan.commit, result)  # type: ignore[no-any-return]
    except ApiError as exc:
        return {"code": exc.code, "message": exc.message}
    except Exception:
        log.exception("narrated reply failed")
        return dict(LOST_THREAD)
    finally:
        if lock is not None:
            lock.release()


async def _stream(plan: StreamPlan) -> AsyncIterator[ServerSentEvent]:
    t0 = time.monotonic()
    yield event("status", {"state": "writing"})
    # Run the model call and the commit in their own task: if the client disconnects (reload,
    # leaving the screen) the reply is still generated and saved. Cancelling it with the stream
    # left an opening uncommitted and the campaign stuck in "setup" (every move: 409).
    task = asyncio.ensure_future(_produce(plan, t0))
    _background.add(task)
    task.add_done_callback(_background.discard)
    out = await asyncio.shield(task)
    if isinstance(out, dict):
        yield event("error", out)
        return
    if _voice_on.get():
        _prewarm(out)
    # The reply is complete before streaming, so its speaker is known: announce it first so the
    # name tab is right from the first word (an NPC, not the Campaign Master, at an NPC's place).
    # The audio id and stored text come with it too, so the voice starts with the first word
    # (its synthesis is already under way) instead of after the whole text has streamed.
    yield event("speaker", {"speaker": out.done.get("speaker"),
                            "speaker_kind": out.done.get("speaker_kind"),
                            "audio_text_id": out.done.get("audio_text_id"),
                            "audio_text": out.done.get("text") or out.text})  # fmt: skip
    async for tok in _tokens(out.text):
        yield tok
    for card in out.cards:
        yield event("card", card)
    yield event("state", out.state)
    if plan.after is not None and plan.replay is None:
        fut = asyncio.get_running_loop().run_in_executor(None, plan.after, out)
        _background.add(fut)
        fut.add_done_callback(_background.discard)
    yield event("done", out.done)


def sse_response(plan: StreamPlan) -> EventSourceResponse:
    return EventSourceResponse(
        _stream(plan), ping=HEARTBEAT_S,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )  # fmt: skip
