"""@spec: quest-board (curated + personal quests, theme matching, detail view, no daily quest)"""

import re
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from financequest.config import get_settings
from financequest.db.models import ScenarioSecret
from financequest.db.models_campaign import CampaignRun
from financequest.db.models_personal import GenerationJob
from financequest.db.session import get_engine
from financequest.personal import agent, board
from financequest.refpack.approve import approve_pack

PACK_DIR = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"
YEAR = re.compile(r"(?<![\w.])(?:19|20)\d{2}(?![\w.])")


@pytest.fixture
def enron(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    s = get_settings()
    monkeypatch.setattr(s, "fake_llm", True)
    monkeypatch.setattr(s, "data_dir", str(tmp_path))
    monkeypatch.setattr(agent, "FAKE_STEP_DELAY_S", 0)
    with Session(get_engine()) as db:
        res = approve_pack(PACK_DIR, db)
        assert res.ok and res.scenario_id, res.reasons
    yield res.scenario_id


def _player(client: TestClient) -> dict[str, str]:
    sid = client.post("/session").json()["session_id"]
    h = {"X-Session-Id": sid}
    assert client.post("/hero", json={"name": "Lena", "class": "analyst"}, headers=h).status_code == 201  # noqa: E501
    return h


def _mine(client: TestClient, h: dict[str, str], card_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        card = next(c for c in client.get("/quests/board", headers=h).json()["mine"] if c["id"] == card_id)  # noqa: E501
        if card["status"] != "generating":
            return card
        time.sleep(0.3)
    raise AssertionError("quest did not finish")


def _terms(scenario_id: str) -> list[str]:
    with Session(get_engine()) as db:
        sec = db.get(ScenarioSecret, uuid.UUID(scenario_id))
        assert sec is not None
        return [t for t in [sec.real_name, *(sec.leak_terms or [])] if len(t) > 5]


def test_board_lists_curated_enron_with_board_metadata(client: TestClient, enron: str) -> None:
    h = _player(client)
    r = client.get("/quests/board", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["mine"] == []  # nothing auto-generated
    assert set(body["suggestion"]) == {"theme", "category_label", "why"}
    (card,) = body["curated"]
    assert card["id"] == enron and card["scenario_id"] == enron and card["kind"] == "curated"
    assert card["title"] == "The Lantern Guild's Long Winter"
    assert card["learn"] == ["Profit isn't cash", "Reading debt", "Reacting to news"]
    assert card["difficulty"] == "medium" and card["status"] == "ready"
    assert card["horizon_days"] > 0 and card["budget_gp"] == 1000
    assert card["played"] is False and card["finished"] is False
    low = r.text.lower()
    assert not YEAR.search(r.text)
    for term in _terms(enron):
        assert term.lower() not in low, term
    assert "enron" not in low


def test_curated_is_the_same_for_every_player(client: TestClient, enron: str) -> None:
    a, b = _player(client), _player(client)
    assert client.get("/quests/board", headers=a).json()["curated"] == \
        client.get("/quests/board", headers=b).json()["curated"]  # fmt: skip


def test_detail_has_briefing_characters_places_steps(client: TestClient, enron: str) -> None:
    h = _player(client)
    r = client.get(f"/quests/board/{enron}", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == enron and d["title"]
    det = d["details"]
    assert 3 <= len(re.findall(r"[.!?](?:\s|$)", det["briefing"])) <= 5
    assert {"name": "Elian Voss", "role": "Treasurer of the Golden Guild; voice of its management"} in det["characters"]  # noqa: E501
    assert "The Golden Guild Hall" in det["places"] and len(det["what_you_do"]) == 3
    for term in _terms(enron):
        assert term.lower() not in r.text.lower()
    assert client.get(f"/quests/board/{uuid.uuid4()}", headers=h).status_code == 404


def test_nothing_generates_without_a_request(client: TestClient, enron: str) -> None:
    h = _player(client)
    client.get("/quests/board", headers=h)
    client.get("/me/transactions", headers=h)
    assert client.post("/quests/daily", headers=h).status_code == 410
    with Session(get_engine()) as db:
        assert db.exec(select(GenerationJob)).all() == []


def test_generating_quest_shows_on_mine_then_ready(client: TestClient, enron: str) -> None:
    h = _player(client)
    card = client.post("/quests/generate", json={}, headers=h).json()
    assert card["status"] == "generating" and card["kind"] == "personal"
    assert card["scenario_id"] is None and card["step"]
    assert [c["id"] for c in client.get("/quests/board", headers=h).json()["mine"]] == [card["id"]]
    done = _mine(client, h, card["id"])
    assert done["status"] == "ready" and done["scenario_id"] and done["title"]
    # the personal quest never shows up as curated, for anyone
    other = _player(client)
    assert [c["id"] for c in client.get("/quests/board", headers=other).json()["curated"]] == [enron]  # noqa: E501
    assert client.get("/quests/board", headers=other).json()["mine"] == []
    det = client.get(f"/quests/board/{card['id']}", headers=h)
    assert det.status_code == 200 and det.json()["details"]["briefing"]
    assert client.get(f"/quests/board/{card['id']}", headers=other).status_code == 404


def test_generate_with_theme_maps_to_a_category(client: TestClient, enron: str) -> None:
    h = _player(client)
    theme = {"theme": "something about music"}
    card = client.post("/quests/generate", json=theme, headers=h).json()
    assert card["trade"] == "Music & streaming"
    with Session(get_engine()) as db:
        (job,) = db.exec(select(GenerationJob)).all()
        assert job.category == "music" and job.detail["theme"] == "something about music"
    car = client.post("/quests/generate", json={"theme": "electric cars"}, headers=h).json()
    assert car["trade"] == "Rides & mobility"
    named = client.post("/quests/generate", json={"theme": "I like Nintendo"}, headers=h).json()
    assert named["trade"] == "Games & consoles"
    with Session(get_engine()) as db:
        tickers = {j.ticker for j in db.exec(select(GenerationJob))}
    assert "7974.T" in tickers


def test_generate_without_theme_uses_the_suggestion(client: TestClient, enron: str) -> None:
    h = _player(client)
    sug = client.get("/quests/board", headers=h).json()["suggestion"]
    assert sug["theme"] == sug["category_label"] and sug["why"].startswith("You spent the most on")
    card = client.post("/quests/generate", headers=h).json()
    assert card["trade"] == sug["category_label"]
    nothing = client.post("/quests/generate", json={"theme": "qwerty zzz"}, headers=h).json()
    assert nothing["trade"] == sug["category_label"]  # no match falls back to the suggestion


def test_match_theme_is_deterministic() -> None:
    assert board.match_theme("") is None
    assert board.match_theme("zzzz") is None
    m = board.match_theme("pizza delivery")
    assert m is not None and m[0].key == "food_delivery"


def test_played_and_finished_flags(client: TestClient, enron: str) -> None:
    h = _player(client)
    assert client.post("/campaigns", json={"scenario_id": enron}, headers=h).status_code == 201
    (card,) = client.get("/quests/board", headers=h).json()["curated"]
    assert card["played"] is True and card["finished"] is False
    with Session(get_engine()) as db:
        run = db.exec(select(CampaignRun)).one()
        run.status = "finished"
        db.add(run)
        db.commit()
    (card,) = client.get("/quests/board", headers=h).json()["curated"]
    assert card["played"] is True and card["finished"] is True
    other = _player(client)
    assert client.get("/quests/board", headers=other).json()["curated"][0]["played"] is False
