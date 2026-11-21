# ruff: noqa: E501
"""TTS: bounded concurrency, per-sentence timeout and retry, quick 503, deduped requests."""

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from financequest.media import tts
from tests.test_media import data_dir, seed  # noqa: F401

TEXT = "One sentence here. Two sentence here. Three sentence here. Four sentence here. Five sentence here. Six sentence here."


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tts, "SENTENCE_TIMEOUT_S", 0.2)
    monkeypatch.setattr(tts, "TOTAL_TIMEOUT_S", 2.0)
    monkeypatch.setattr(tts, "_blocked_until", 0.0)
    tts._inflight.clear()


async def test_one_provider_call_per_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini TTS allows 10 requests a minute: a reply is one call, not one per sentence."""
    calls: list[str] = []

    async def record(text: str, voice: str) -> bytes:
        calls.append(text)
        return tts.silent_pcm(0.01)

    monkeypatch.setattr(tts, "_synth_pcm", record)
    wav = await tts.synthesize(TEXT, "dm")
    assert wav[:4] == b"RIFF"
    assert calls == [TEXT.strip()]


def test_quota_cooldown_follows_googles_retry_delay() -> None:
    msg = "429 Rate limit exceeded (limit: 10 requests per minute). Please retry in 43.5s or upgrade"
    assert tts._cooldown_s(RuntimeError(msg)) == 43.5
    assert tts._cooldown_s(RuntimeError("Please retry in 900s")) == 120.0  # capped
    assert tts._cooldown_s(RuntimeError("429 RESOURCE_EXHAUSTED")) == tts.QUOTA_COOLDOWN_S


async def test_hanging_provider_raises_unavailable_quickly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def hang(sentence: str, voice: str) -> bytes:
        nonlocal calls
        calls += 1
        await asyncio.sleep(60)
        return b""

    monkeypatch.setattr(tts, "_synth_pcm", hang)
    t0 = time.monotonic()
    with pytest.raises(tts.TtsUnavailable):
        await tts.synthesize("Only one. Second one.", "dm")
    assert time.monotonic() - t0 < 1.5
    assert calls == 2  # one call for the reply, tried twice


async def test_one_retry_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    n = 0

    async def flaky(sentence: str, voice: str) -> bytes:
        nonlocal n
        n += 1
        if n == 1:
            await asyncio.sleep(60)
        return tts.silent_pcm(0.01)

    monkeypatch.setattr(tts, "_synth_pcm", flaky)
    assert (await tts.synthesize("Just one sentence.", "dm"))[:4] == b"RIFF"


async def test_concurrent_requests_share_one_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def slow(sentence: str, voice: str) -> bytes:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return tts.silent_pcm(0.01)

    monkeypatch.setattr(tts, "_synth_pcm", slow)
    a, b, c = await asyncio.gather(*(tts.synthesize("Solo sentence.", "dm") for _ in range(3)))
    assert a == b == c and calls == 1


def test_endpoint_answers_503_fast_when_provider_hangs(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    async def hang(sentence: str, voice: str) -> bytes:
        await asyncio.sleep(60)
        return b""

    monkeypatch.setattr(tts, "_synth_pcm", hang)
    _, _, ev, _ = seed()
    t0 = time.monotonic()
    r = client.get(f"/tts/{ev}", params={"voice": "dm"})
    assert r.status_code == 503
    assert time.monotonic() - t0 < 2.5


async def test_quota_error_fails_at_once_and_pauses_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    class Quota(Exception):
        status_code = 429

    calls = 0

    async def limited(sentence: str, voice: str) -> bytes:
        nonlocal calls
        calls += 1
        raise Quota("rate limited, retry in 21h")

    monkeypatch.setattr(tts, "_synth_pcm", limited)
    with pytest.raises(tts.TtsUnavailable):
        await tts.synthesize("One. Two. Three.", "dm")
    assert calls <= 3  # no per-sentence retry on a quota error
    before = calls
    with pytest.raises(tts.TtsUnavailable):
        await tts.synthesize("Another text.", "dm")
    assert calls == before  # cooling down: not even asked
