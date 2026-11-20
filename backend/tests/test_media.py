import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from financequest.config import get_settings
from financequest.db.models import Event, PlayerSession, Scenario, ScenarioSecret
from financequest.db.models_campaign import CampaignRun, Hero, Location, Player
from financequest.db.session import get_engine
from financequest.media import art


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FAKE_LLM", "1")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def seed(subject: str | None = "A lantern-lit guild hall", status: str = "placeholder"):
    with Session(get_engine()) as db:
        sid = uuid.uuid4()
        db.add(PlayerSession(id=sid))
        db.commit()
        db.add(Player(id=sid))
        db.commit()
        hero = Hero(player_id=sid, name="Ada", hero_class="scout")
        scen = Scenario(
            invented_name="Gilded Co",
            industry_shown="Trade",
            story_days={},
            beats=[],
            chart_series=[],
            company_card={},
            status="retired",
        )
        db.add_all([hero, scen])
        db.commit()
        db.add(ScenarioSecret(scenario_id=scen.id, real_name="Enron", leak_terms=["Skilling"]))
        run = CampaignRun(player_id=sid, hero_id=hero.id, scenario_id=scen.id, rng_seed=1)
        db.add(run)
        db.commit()
        loc = Location(
            campaign_id=run.id,
            key="hall",
            fixed=False,
            name="Hall",
            art_subject=subject,
            art_status=status,
        )
        ev = Event(
            session_id=sid,
            scenario_id=scen.id,
            campaign_id=run.id,
            type="dm_turn",
            payload={"text": "Welcome, hero. The ledger awaits."},
        )
        raw = Event(
            session_id=sid,
            scenario_id=scen.id,
            campaign_id=run.id,
            type="player_msg",
            payload={"note": "no text here"},
        )
        db.add_all([loc, ev, raw])
        db.commit()
        return loc.id, run.id, ev.id, raw.id


def status_of(loc_id: uuid.UUID) -> str:
    with Session(get_engine()) as db:
        loc = db.get(Location, loc_id)
        assert loc
        return loc.art_status


def test_prompt_has_style_negative_and_no_leak_terms() -> None:
    p = art.build_art_prompt("Enron's hall where Skilling stood", ["Enron", "Skilling"])
    assert art.STYLE_GUIDE in p
    assert art.NEGATIVE_BLOCK in p
    assert "Enron" not in p and "Skilling" not in p
    assert "#22305B" in p and "16:9" in p


async def test_job_pending_then_ready(test_db_url: str, data_dir: Path) -> None:
    loc_id, camp_id, _, _ = seed()
    seen: list[str] = []

    async def gen(prompt: str, anchor: bytes | None) -> bytes:
        seen.append(status_of(loc_id))
        assert anchor  # style anchor shipped in the repo
        return await art.fake_generate(prompt, anchor)

    assert await art.run_art_job(loc_id, generator=gen) == "ready"
    assert seen == ["pending"]
    assert status_of(loc_id) == "ready"
    assert (data_dir / "art" / str(camp_id) / f"{loc_id}.webp").is_file()


async def test_failure_keeps_placeholder(test_db_url: str, data_dir: Path) -> None:
    loc_id, camp_id, _, _ = seed()
    calls = 0

    async def boom(prompt: str, anchor: bytes | None) -> bytes:
        nonlocal calls
        calls += 1
        raise RuntimeError("nope")

    assert await art.run_art_job(loc_id, generator=boom) == "failed"
    assert calls == 2  # one retry
    assert status_of(loc_id) == "failed"
    assert not (data_dir / "art" / str(camp_id)).exists()


async def test_startup_rescan_finishes_pending(test_db_url: str) -> None:
    loc_id, _, _, _ = seed(status="pending")
    assert await art.rescan_pending(generator=art.fake_generate) == ["ready"]
    assert status_of(loc_id) == "ready"


def test_art_endpoint(client: TestClient) -> None:
    loc_id, _, _, _ = seed()
    assert client.get(f"/locations/{loc_id}/art").status_code == 404  # not ready yet
    assert client.get(f"/locations/{uuid.uuid4()}/art").status_code == 404
    import asyncio

    asyncio.run(art.run_art_job(loc_id, generator=art.fake_generate))
    r = client.get(f"/locations/{loc_id}/art")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content[:4] == b"RIFF"


def test_tts_serves_and_caches(client: TestClient, data_dir: Path) -> None:
    _, _, ev, _ = seed()
    r = client.get(f"/tts/{ev}", params={"voice": "dm"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"
    files = sorted((data_dir / "tts").glob("*.wav"))
    assert len(files) == 3  # two sentences + the whole text
    mtimes = [f.stat().st_mtime_ns for f in files]
    assert client.get(f"/tts/{ev}", params={"voice": "dm"}).content == r.content
    assert [f.stat().st_mtime_ns for f in sorted((data_dir / "tts").glob("*.wav"))] == mtimes
    client.get(f"/tts/{ev}", params={"voice": "buddy"})
    assert len(list((data_dir / "tts").glob("*.wav"))) == 6  # voices cached separately


def test_tts_rejects_unknown_and_textless(client: TestClient) -> None:
    _, _, ev, raw = seed()
    assert client.get("/tts/999999999", params={"voice": "dm"}).status_code == 404
    assert client.get(f"/tts/{raw}", params={"voice": "dm"}).status_code == 404
    assert client.get("/tts/Hello%20raw%20text", params={"voice": "dm"}).status_code == 422


def test_tts_voice_validation(client: TestClient) -> None:
    _, _, ev, _ = seed()
    assert client.get(f"/tts/{ev}", params={"voice": "robot"}).status_code == 422
    assert client.get(f"/tts/{ev}").status_code == 422
