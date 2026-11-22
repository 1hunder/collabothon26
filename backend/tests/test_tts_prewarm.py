"""The reply's speech starts on the server as soon as its text is final, only with voice on, and
the browser learns the audio id with the first word (the ``speaker`` event)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sse_helpers import post_sse
from test_veteran import _scripted, enron, new_player, start  # noqa: F401

from financequest.api import sse as sse_mod
from financequest.media import tts


@pytest.fixture
def prewarmed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def record(text: str, voice: str) -> None:
        calls.append((text, voice))

    monkeypatch.setattr(tts, "prewarm", record)
    return calls


def _act(client: TestClient, h: dict[str, str], cid: str, voice: str | None) -> list[Any]:
    headers = {**h, **({"X-Voice": voice} if voice else {})}
    events, done = post_sse(
        client, f"/campaigns/{cid}/actions", headers, {"text": "I read the guild ledgers."}
    )
    assert done, events
    return events


def test_speaker_event_carries_the_audio_id_before_the_first_word(
    client: TestClient,
    enron: str,  # noqa: F811
    prewarmed: list[tuple[str, str]],
) -> None:
    h = new_player(client)
    cid = start(client, h)
    events = _act(client, h, cid, "on")
    names = [n for n, _ in events]
    first_token = names.index("token")
    speaker = next(d for n, d in events if n == "speaker")
    assert names.index("speaker") < first_token
    done = next(d for n, d in events if n == "done")
    assert speaker["audio_text_id"] == done["audio_text_id"] is not None
    assert speaker["audio_text"] == done["text"]  # the stored text, what GET /tts reads


def test_voice_on_starts_the_speech_early_voice_off_does_not(
    client: TestClient,
    enron: str,  # noqa: F811
    prewarmed: list[tuple[str, str]],
) -> None:
    h = new_player(client)
    cid = start(client, h)
    events = _act(client, h, cid, "on")
    done = next(d for n, d in events if n == "done")
    assert (done["text"], tts.voice_for_speaker(done.get("speaker"))) in prewarmed
    prewarmed.clear()
    _act(client, h, cid, "off")
    _act(client, h, cid, None)  # an older client sends nothing: no extra Google calls
    assert prewarmed == []


def test_speech_jobs_cover_the_reply_and_its_spoken_cards() -> None:
    out = sse_mod.Streamed(
        text="The reply.",
        done={"text": "The reply.", "audio_text_id": 7, "speaker": "CommerzBuddy"},
        cards=[
            {"kind": "news", "framing": "News framing.", "framing_audio_text_id": 8},
            {"kind": "market", "text": "The scene.", "audio_text_id": 9},
            {"kind": "dice", "text": "not spoken by the server voice"},
        ],
    )
    assert sse_mod._speech_jobs(out) == [
        ("The reply.", "buddy"),
        ("News framing.", "dm"),
        ("The scene.", "dm"),
    ]
