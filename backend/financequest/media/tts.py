"""Gemini TTS: streamed synthesis of a whole reply, cached by hash(text, voice) under DATA_DIR/tts.

Only guarded text stored in the event log is ever synthesized. FAKE_LLM=1 returns silence.

One reply is one provider call (Gemini TTS allows 10 requests a minute), streamed: the first audio
arrives after about 3 s instead of the 8-12 s a whole reply takes, so the browser starts playing
while the rest is still being made. Several listeners share one synthesis (a ``_Job``): the
reply's own prewarm, started by the server as soon as the text is final, and the browser's
``GET /tts``. A finished job is cached as one WAV file.

Each attempt has a timeout for the first chunk and between chunks; a failure before any audio is
retried once, a quota error pauses all calls for Google's "retry in Ns". Any failure before the
first chunk raises ``TtsUnavailable`` (the API answers 503 and the client falls back to Web
Speech); a failure after it ends the audio early and caches nothing.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import re
import struct
import time
import wave
from collections.abc import AsyncIterator
from typing import Any, Literal

from financequest.config import get_settings
from financequest.storage import get_storage

log = logging.getLogger("financequest.tts")

Voice = Literal["dm", "buddy", "veteran"]
SAMPLE_RATE = 24000
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
MAX_CONCURRENT = 4
SENTENCE_TIMEOUT_S = 20.0  # to the first chunk of one attempt (measured: about 3 s)
CHUNK_GAP_TIMEOUT_S = 15.0  # between two chunks once audio flows
TOTAL_TIMEOUT_S = 60.0  # one whole reply, both attempts
ATTEMPTS = 2  # one try and one retry, only while no audio has been produced


QUOTA_COOLDOWN_S = 60.0  # when Google gives no "retry in Ns"; the limit is per minute
_blocked_until = 0.0


def _is_quota(exc: BaseException) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return code == 429 or "429" in str(exc)[:200] or "RESOURCE_EXHAUSTED" in str(exc)[:200]


def _cooldown_s(exc: BaseException) -> float:
    """Google says how long to wait ("Please retry in 43s"); never more than two minutes."""
    m = re.search(r"retry in ([0-9.]+)s", str(exc))
    return min(max(float(m.group(1)), 5.0), 120.0) if m else QUOTA_COOLDOWN_S


class TtsUnavailable(RuntimeError):
    """Speech could not be produced in time; the caller answers 503."""


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]


def voice_name(voice: str) -> str:
    s = get_settings()
    return {"dm": s.tts_voice_dm, "veteran": s.tts_voice_veteran}.get(voice, s.tts_voice_buddy)


def voice_for_speaker(speaker: object) -> Voice:
    """The voice the play screen reads a speaker with (DialogueBox picks it the same way)."""
    if speaker == "CommerzBuddy":
        return "buddy"
    if speaker == "Brannoc":
        return "veteran"
    return "dm"


def cache_key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}\x00{text}".encode()).hexdigest()


def cache_name(text: str, voice: str) -> str:
    return f"tts/{cache_key(text, voice)}.wav"


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def streaming_wav_header() -> bytes:
    """A WAV header for audio of unknown length: browsers play it as the data arrives."""
    unknown = 0xFFFFFFFF
    return (
        b"RIFF" + struct.pack("<I", unknown) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        + b"data" + struct.pack("<I", unknown)
    )  # fmt: skip


def silent_pcm(seconds: float = 0.3) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * seconds)


_client: Any = None
_sems: dict[int, asyncio.Semaphore] = {}


def _get_client() -> Any:
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        s = get_settings()
        # The SDK honours Retry-After on 429 (free tier: ~21 h), which looked like a hang. Never
        # retry inside the SDK; this module owns the timeouts, the single retry and the breaker.
        _client = genai.Client(
            api_key=s.google_genai_api_key,
            http_options=types.HttpOptions(
                api_version="v1beta", timeout=int(TOTAL_TIMEOUT_S * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    return _client


def _sem() -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _sems:
        _sems.clear()  # one loop at a time in practice; drop semaphores of dead loops
        _sems[loop_id] = asyncio.Semaphore(MAX_CONCURRENT)
    return _sems[loop_id]


async def _stream_pcm(text: str, voice: str) -> AsyncIterator[bytes]:
    """One streamed provider call: PCM chunks as Google makes them (tests replace this)."""
    s = get_settings()
    if s.fake_llm:
        yield silent_pcm()
        return
    # Speech generation lives on the Interactions API (generate_content rejects speechConfig).
    stream = await _get_client().aio.interactions.create(
        model=s.tts_model,
        input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
        response_format={"type": "audio", "mime_type": "audio/l16", "sample_rate": SAMPLE_RATE},
        generation_config={"speech_config": [{"voice": voice_name(voice)}]},
        stream=True,
    )
    async for ev in stream:
        if getattr(ev, "event_type", None) == "error" or getattr(ev, "error", None):
            raise RuntimeError(f"TTS stream error: {getattr(ev, 'error', ev)}")
        data = getattr(getattr(ev, "delta", None), "data", None)
        if data:
            yield base64.b64decode(data) if isinstance(data, str) else bytes(data)


class _Job:
    """One synthesis, shared by every listener; each reads all chunks from the start."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.done = False
        self.error: TtsUnavailable | None = None
        self._cond = asyncio.Condition()
        self.task: asyncio.Task[None] | None = None

    async def push(self, chunk: bytes) -> None:
        async with self._cond:
            self.chunks.append(chunk)
            self._cond.notify_all()

    async def finish(self, error: TtsUnavailable | None = None) -> None:
        async with self._cond:
            self.done, self.error = True, error
            self._cond.notify_all()

    async def first(self) -> None:
        """Wait for the first chunk; raise ``TtsUnavailable`` when the job failed before it."""
        async with self._cond:
            await self._cond.wait_for(lambda: bool(self.chunks) or self.done)
            if not self.chunks:
                raise self.error or TtsUnavailable("no audio")

    async def read(self) -> AsyncIterator[bytes]:
        i = 0
        while True:
            async with self._cond:
                await self._cond.wait_for(lambda n=i: len(self.chunks) > n or self.done)
                new, done = self.chunks[i:], self.done
            i += len(new)
            for chunk in new:
                yield chunk
            if done and i >= len(self.chunks):
                return

    async def complete(self) -> bytes:
        """All audio, or ``TtsUnavailable`` when the job did not finish cleanly."""
        async with self._cond:
            await self._cond.wait_for(lambda: self.done)
        if self.error is not None:
            raise self.error
        return b"".join(self.chunks)


_inflight: dict[str, _Job] = {}


async def _attempt(job: _Job, text: str, voice: str) -> bool:
    """One provider call into ``job``. True when it produced any audio."""
    produced = False
    agen = _stream_pcm(text, voice).__aiter__()
    try:
        async with _sem():
            while True:
                gap = CHUNK_GAP_TIMEOUT_S if produced else SENTENCE_TIMEOUT_S
                try:
                    chunk = await asyncio.wait_for(agen.__anext__(), gap)
                except StopAsyncIteration:
                    break
                if chunk:
                    produced = True
                    await job.push(chunk)
    except Exception:
        if produced:  # the listeners already play it: end the audio here, no retry
            raise _CutOff() from None
        raise
    finally:
        aclose = getattr(agen, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 - the stream is gone either way
                pass
    if not produced:
        raise RuntimeError("TTS returned no audio")
    return produced


class _CutOff(Exception):
    """Audio stopped after it had started (timeout or provider error mid-stream)."""


async def _run(job: _Job, key: str, text: str, voice: str) -> None:
    global _blocked_until
    error: TtsUnavailable | None = None
    try:
        last: BaseException | None = None
        for attempt in range(ATTEMPTS):
            try:
                await _attempt(job, text, voice)
                wav = pcm_to_wav(b"".join(job.chunks))
                name = cache_name(text, voice)
                await asyncio.to_thread(get_storage().put_bytes, name, wav, "audio/wav")
                return
            except _CutOff:
                log.warning("tts stream cut off after it started")
                error = TtsUnavailable("cut off")
                return
            except Exception as exc:  # noqa: BLE001 - timeout, network or provider error
                last = exc
                log.warning("tts attempt %d failed: %s", attempt + 1, type(exc).__name__)
                if _is_quota(exc):  # a retry cannot help; stop asking for a while
                    _blocked_until = time.monotonic() + _cooldown_s(exc)
                    error = TtsUnavailable("quota")
                    return
        error = TtsUnavailable(type(last).__name__ if last else "unknown")
    except asyncio.CancelledError:
        error = TtsUnavailable("cancelled")
        raise
    finally:
        _inflight.pop(key, None)
        await job.finish(error)


async def _guarded_run(job: _Job, key: str, text: str, voice: str) -> None:
    try:
        await asyncio.wait_for(_run(job, key, text, voice), TOTAL_TIMEOUT_S)
    except TimeoutError:
        log.warning("tts reply took longer than %.0f s", TOTAL_TIMEOUT_S)


async def _cached(text: str, voice: str) -> bytes | None:
    store, name = get_storage(), cache_name(text, voice)
    if await asyncio.to_thread(store.exists, name):
        return await asyncio.to_thread(store.get_bytes, name)
    return None


def _job(text: str, voice: str) -> _Job:
    """The running synthesis of this text and voice, started if there is none."""
    key = cache_key(text, voice)
    job = _inflight.get(key)
    if job is None:
        if time.monotonic() < _blocked_until:
            raise TtsUnavailable("quota cooldown")
        job = _Job()
        _inflight[key] = job
        job.task = asyncio.ensure_future(_guarded_run(job, key, text, voice))
    return job


async def prewarm(text: str, voice: str) -> None:
    """Start synthesizing a reply the moment its text is final, before the browser asks.
    Never raises: a reply without speech still plays (the browser voice takes over)."""
    if not text.strip():
        return
    try:
        if await _cached(text, voice) is None:
            _job(text, voice)
    except Exception:  # noqa: BLE001 - quota cooldown, storage: the reply goes on
        log.info("tts prewarm skipped", exc_info=True)


async def open_audio(text: str, voice: str) -> bytes | AsyncIterator[bytes]:
    """The reply's audio: the cached WAV bytes, or a WAV stream that starts as soon as the
    first chunk exists. Raises ``TtsUnavailable`` when no audio can be had."""
    cached = await _cached(text, voice)
    if cached is not None:
        return cached
    job = _job(text, voice)
    await job.first()

    async def stream() -> AsyncIterator[bytes]:
        yield streaming_wav_header()
        async for chunk in job.read():
            yield chunk

    return stream()


async def synthesize(text: str, voice: str) -> bytes:
    """WAV bytes for guarded text (cached); raises ``TtsUnavailable``."""
    cached = await _cached(text, voice)
    if cached is not None:
        return cached
    job = _job(text, voice)
    return pcm_to_wav(await asyncio.shield(job.complete()))
