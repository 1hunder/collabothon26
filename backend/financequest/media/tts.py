"""Gemini TTS: per-sentence synthesis, cached by hash(text, voice) under DATA_DIR/tts.

Only guarded text stored in the event log is ever synthesized. FAKE_LLM=1 returns silence.

Sentences are synthesized concurrently (bounded), each with a timeout and one retry; any failure
raises ``TtsUnavailable`` (the API answers 503 and the client falls back to Web Speech).
Concurrent requests for the same text share one synthesis.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import re
import time
import wave
from typing import Any, Literal

from financequest.config import get_settings
from financequest.storage import get_storage

log = logging.getLogger("financequest.tts")

Voice = Literal["dm", "buddy", "veteran"]
SAMPLE_RATE = 24000
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
MAX_CONCURRENT = 4
SENTENCE_TIMEOUT_S = 20.0
TOTAL_TIMEOUT_S = 45.0
ATTEMPTS = 2  # one try and one retry per sentence


QUOTA_COOLDOWN_S = 300.0
_blocked_until = 0.0


def _is_quota(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return code == 429 or "429" in str(exc)[:200] or "RESOURCE_EXHAUSTED" in str(exc)[:200]


class TtsUnavailable(RuntimeError):
    """Speech could not be produced in time; the caller answers 503."""



def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]


def voice_name(voice: str) -> str:
    s = get_settings()
    return {"dm": s.tts_voice_dm, "veteran": s.tts_voice_veteran}.get(voice, s.tts_voice_buddy)


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


def silent_pcm(seconds: float = 0.3) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * seconds)


_client: Any = None
_sems: dict[int, asyncio.Semaphore] = {}
_inflight: dict[str, asyncio.Task[bytes]] = {}


def _get_client() -> Any:
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        s = get_settings()
        # The SDK honours Retry-After on 429 (free tier: ~21 h), which looked like a hang. Never
        # retry inside the SDK; this module owns the timeout, the single retry and the breaker.
        _client = genai.Client(
            api_key=s.google_genai_api_key,
            http_options=types.HttpOptions(
                api_version="v1beta", timeout=int(SENTENCE_TIMEOUT_S * 1000),
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


async def _synth_pcm(sentence: str, voice: str) -> bytes:
    """One provider call (tests replace this)."""
    s = get_settings()
    if s.fake_llm:
        return silent_pcm()
    # Speech generation lives on the Interactions API (generate_content rejects speechConfig).
    interaction = await _get_client().aio.interactions.create(
        model=s.tts_model,
        input=[{"type": "user_input", "content": [{"type": "text", "text": sentence}]}],
        response_format={"type": "audio", "mime_type": "audio/l16", "sample_rate": 24000},
        generation_config={"speech_config": [{"voice": voice_name(voice)}]},
    )
    audio = getattr(interaction, "output_audio", None)
    data = getattr(audio, "data", None)
    if data:
        return base64.b64decode(data) if isinstance(data, str) else bytes(data)
    raise RuntimeError("TTS returned no audio")


async def _bounded_synth(sentence: str, voice: str) -> bytes:
    global _blocked_until
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            async with _sem():
                return await asyncio.wait_for(_synth_pcm(sentence, voice), SENTENCE_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - timeout, network or provider error
            last = exc
            log.warning("tts attempt %d failed: %s", attempt + 1, type(exc).__name__)
            if _is_quota(exc):  # a retry cannot help; stop asking for a while
                _blocked_until = time.monotonic() + QUOTA_COOLDOWN_S
                raise TtsUnavailable("quota") from None
    raise TtsUnavailable(type(last).__name__ if last else "unknown")


async def _sentence_wav_pcm(sentence: str, voice: str) -> bytes:
    key = cache_name(sentence, voice)
    store = get_storage()
    if await asyncio.to_thread(store.exists, key):
        data = await asyncio.to_thread(store.get_bytes, key)
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.readframes(w.getnframes())
    pcm = await _bounded_synth(sentence, voice)
    await asyncio.to_thread(store.put_bytes, key, pcm_to_wav(pcm), "audio/wav")
    return pcm


async def _build(text: str, voice: str) -> bytes:
    sentences = split_sentences(text) or [text]
    try:
        parts = await asyncio.wait_for(
            asyncio.gather(*(_sentence_wav_pcm(x, voice) for x in sentences)), TOTAL_TIMEOUT_S
        )
    except TimeoutError:
        raise TtsUnavailable("timeout") from None
    wav = pcm_to_wav(b"".join(parts))
    await asyncio.to_thread(get_storage().put_bytes, cache_name(text, voice), wav, "audio/wav")
    return wav


async def synthesize(text: str, voice: str) -> bytes:
    """WAV bytes for guarded text; sentences cached separately; raises ``TtsUnavailable``."""
    store, name = get_storage(), cache_name(text, voice)
    if await asyncio.to_thread(store.exists, name):
        return await asyncio.to_thread(store.get_bytes, name)
    if time.monotonic() < _blocked_until:
        raise TtsUnavailable("quota cooldown")
    key = cache_key(text, voice)
    task = _inflight.get(key)
    if task is None:
        task = asyncio.ensure_future(_build(text, voice))
        _inflight[key] = task
        task.add_done_callback(lambda _t: _inflight.pop(key, None))
    try:
        return await asyncio.shield(task)
    except TtsUnavailable:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TtsUnavailable(type(exc).__name__) from None
