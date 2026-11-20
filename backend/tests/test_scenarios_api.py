"""@spec: 002-anonymization-reid-gate (Slice 4: scenario player API and gated reveal)"""

import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from financequest.db.models import Decision, Scenario, ScenarioSecret
from financequest.db.session import get_engine
from financequest.refpack.approve import approve_pack

PACK_DIR = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"
YEAR = re.compile(r"(?<![\w.])(?:19|20)\d{2}(?![\w.])")
MONTHS = re.compile(
    r"\b(January|February|March|April|June|July|August|September|October|November|December)\b"
)


@pytest.fixture
def enron(client: TestClient) -> Iterator[str]:
    with Session(get_engine()) as db:
        res = approve_pack(PACK_DIR, db)
        assert res.ok and res.scenario_id, res.reasons
        yield res.scenario_id  # tables are emptied by the autouse isolation fixture


def player(client: TestClient) -> dict[str, str]:
    return {"X-Session-Id": client.post("/session").json()["session_id"]}


def lock_decision(sid: str, scenario_id: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            Decision(session_id=uuid.UUID(sid), scenario_id=uuid.UUID(scenario_id), action="invest")
        )
        db.commit()


def leak_terms(scenario_id: str) -> list[str]:
    with Session(get_engine()) as db:
        sec = db.get(ScenarioSecret, uuid.UUID(scenario_id))
        assert sec is not None
        terms = [sec.real_name, *(sec.leak_terms or [])]
    return [t for t in terms if len(t) > 5]


def test_playable_lists_without_real_name(client: TestClient, enron: str) -> None:
    r = client.get("/scenarios/playable")
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == [enron]
    assert set(rows[0]) == {"id", "industry_shown", "source"}
    assert rows[0]["source"] == "reference_pack"
    assert "enron" not in r.text.lower()


def test_view_is_disguised_and_dateless(client: TestClient, enron: str) -> None:
    r = client.get(f"/scenario/{enron}/view")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "invented_name", "industry_shown", "story_today", "beats", "chart", "company_card",
    }  # fmt: skip
    assert body["beats"] and body["chart"]
    assert set(body["beats"][0]) == {"story_day", "headline", "facts"}
    assert set(body["chart"][0]) == {"story_day", "price"}
    assert all(p["story_day"] <= body["story_today"] for p in body["chart"] + body["beats"])
    assert not YEAR.search(r.text) and not MONTHS.search(r.text)
    assert not re.search(r"\d{4}-\d{2}", r.text)
    for term in leak_terms(enron):
        assert term.lower() not in r.text.lower(), term
    assert client.get(f"/scenario/{uuid.uuid4()}/view").status_code == 404


def test_secret_never_in_campaign_responses(client: TestClient, enron: str) -> None:
    h = player(client)
    assert (
        client.post("/hero", json={"name": "Lena", "class": "analyst"}, headers=h).status_code
        == 201
    )
    cid = client.post("/campaigns", json={"interests": ["Tech"]}, headers=h).json()["id"]
    assert client.post(f"/campaigns/{cid}/opening", headers=h).status_code == 200
    bodies = [
        client.get(f"/campaigns/{cid}", headers=h).text,
        client.get(f"/campaigns/{cid}/journal", headers=h).text,
        client.get("/scenarios/playable").text,
        client.get(f"/scenario/{enron}/view").text,
    ]
    for text in bodies:
        assert "scenario_secret" not in text and "real_name" not in text
        for term in leak_terms(enron):
            assert term.lower() not in text.lower(), term


def test_events_and_debrief_guard(client: TestClient, enron: str) -> None:
    h = player(client)
    assert client.post(f"/scenario/{enron}/events", json={"type": "viewed"}).status_code == 401
    ok = client.post(f"/scenario/{enron}/events", json={"type": "viewed"}, headers=h)
    assert ok.status_code == 201 and ok.json()["type"] == "viewed"
    early = client.post(f"/scenario/{enron}/events", json={"type": "debrief_complete"}, headers=h)
    assert early.status_code == 409
    lock_decision(h["X-Session-Id"], enron)
    done = client.post(f"/scenario/{enron}/events", json={"type": "debrief_complete"}, headers=h)
    assert done.status_code == 201


def test_reveal_locked_until_decision_and_debrief(client: TestClient, enron: str) -> None:
    h = player(client)
    url = f"/scenario/{enron}/reveal"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=h).status_code == 403
    lock_decision(h["X-Session-Id"], enron)
    assert client.get(url, headers=h).status_code == 403  # decision alone is not enough
    client.post(f"/scenario/{enron}/events", json={"type": "debrief_complete"}, headers=h)
    other = player(client)  # another session stays locked
    assert client.get(url, headers=other).status_code == 403
    r = client.get(url, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "real_name", "ticker", "start_date", "end_date", "series", "news_points", "what_changed",
        "n_guessers",
    }  # fmt: skip
    assert body["real_name"].startswith("Enron") and body["n_guessers"] == 0
    assert body["ticker"] == "ENE"
    assert body["series"][0]["date"] == body["start_date"] == "2001-08-01"
    assert body["end_date"] == body["series"][-1]["date"]
    assert set(body["news_points"][0]) == {"story_day", "real_date", "real_price", "headline"}
    assert body["what_changed"]
    assert "disclaimer" not in json.dumps(body).lower()


def test_gate_scenario_reveal_uses_cached_series(client: TestClient) -> None:
    with Session(get_engine()) as db:
        sc = Scenario(
            invented_name="Brightwell", industry_shown="Retail", story_days=[0, 30],
            beats=[{"story_day": 0, "price": "10", "headline": "Opens", "facts": ["a"]},
                   {"story_day": 30, "price": "9", "headline": "Slips", "facts": []}],
            chart_series=[{"day": 0, "close": "10"}, {"day": 30, "close": "9"}],
            company_card={"name": "Brightwell"},
        )  # fmt: skip
        db.add(sc)
        db.flush()
        db.add(ScenarioSecret(
            scenario_id=sc.id, real_name="Real Co", ticker="RC", n_guessers=3,
            real_beats={"beats": [{"date": "2010-01-04", "day": 0, "price": "1", "headline": "H"}],
                        "series": [{"date": "2010-01-04", "price": "100"}]},
            what_changed=["x"], leak_terms=["Real Co"],
        ))  # fmt: skip
        db.commit()
        scenario_id = str(sc.id)
    assert client.get("/scenarios/playable").json()[0]["source"] == "gate"
    h = player(client)
    lock_decision(h["X-Session-Id"], scenario_id)
    client.post(f"/scenario/{scenario_id}/events", json={"type": "debrief_complete"}, headers=h)
    body: Any = client.get(f"/scenario/{scenario_id}/reveal", headers=h).json()
    assert body["real_name"] == "Real Co" and body["n_guessers"] == 3
    assert body["series"] == [{"date": "2010-01-04", "price": "100"}]
