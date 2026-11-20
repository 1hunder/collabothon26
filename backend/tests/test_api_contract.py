"""@spec: 003-campaign-engine (wire contract: spec 003 api-contract.md)"""

# ruff: noqa: F811 - the imported fixtures are used by their parameter names

from typing import Any

from fastapi.testclient import TestClient
from sse_helpers import names, post_sse
from test_campaign_api import (  # noqa: F401 - fixtures are imported by name
    COMMIT,
    _scripted_agents,
    enron,
    loc_id,
    new_player,
    play_to_decide,
    start,
)


def test_error_envelope_everywhere(client: TestClient, enron: str) -> None:
    r = client.get("/hero")  # no session header
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    h = new_player(client)
    r = client.get("/campaigns/00000000-0000-0000-0000-000000000000", headers=h)
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message"}
    r = client.post("/campaigns/not-a-uuid/opening", headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error" and "cid" in r.json()["error"]["fields"]
    r = client.post("/hero", json={"name": "Zed"}, headers={"X-Session-Id": h["X-Session-Id"]})
    assert r.status_code == 422 and "class" in r.json()["error"]["fields"]


def test_hero_wire_shape(client: TestClient, enron: str) -> None:
    h = new_player(client, "analyst")
    hero = client.get("/hero", headers=h).json()
    assert set(hero) == {"name", "class", "total_xp", "items", "history", "active_campaign_id"}
    assert hero["class"] == "analyst" and hero["items"] == [] and hero["history"] == []


def test_state_resume_fields_and_sse_shapes(client: TestClient, enron: str) -> None:
    h = new_player(client)
    st = client.post("/campaigns", json={"interests": ["Gaming"]}, headers=h).json()
    assert st["phase"] == "setup" and st["suggestions"] == []
    cid = st["id"]
    ev, done = post_sse(client, f"/campaigns/{cid}/opening", h)
    assert names(ev)[0] == "status" and ev[0][1] == {"state": "writing"}
    assert names(ev)[-1] == "done"
    assert done["speaker"] == "Campaign Master" and len(done["suggestions"]) == 3
    assert isinstance(done["can_decide"], bool) and done["audio_text_id"]
    state = client.get(f"/campaigns/{cid}", headers=h).json()
    assert state["suggestions"] == done["suggestions"]  # resume offers the same choices
    assert state["budget_eur"] == 1000 and state["horizon_days"] > 0
    assert state["offers_spread"] in (True, False) and state["opening_done"]
    assert all(isinstance(r["close"], float) for r in state["price_board"])
    assert set(state["price_board"][0]) == {"day", "open", "high", "low", "close"}
    # a move reply carries location, first_visit and suggestions
    _, mv = post_sse(
        client, f"/campaigns/{cid}/move", h, {"location_id": loc_id(state, "library")}
    )
    assert mv["location"]["key"] == "library" and mv["first_visit"] is True and mv["suggestions"]
    assert client.get(f"/campaigns/{cid}", headers=h).json()["suggestions"] == mv["suggestions"]


def test_news_card_kind_and_text_survive_replay(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    seen: list[dict[str, Any]] = []
    for i, key in enumerate(("library", "tavern", "market_square")):
        s = client.get(f"/campaigns/{cid}", headers=h).json()
        ev, done = post_sse(
            client, f"/campaigns/{cid}/move", h,
            {"location_id": loc_id(s, key), "client_msg_id": f"m{i}"},
        )  # fmt: skip
        seen = [d for n, d in ev if n == "card"]
    assert seen and seen[-1]["kind"] == "news" and seen[-1]["time_skip_label"].endswith("later…")
    assert done["news_text"] == seen[-1]["framing"]
    ev2, done2 = post_sse(
        client, f"/campaigns/{cid}/move", h,
        {"location_id": loc_id(s, "market_square"), "client_msg_id": "m2"},
    )  # fmt: skip
    assert done2["replayed"] and done2["news_text"] == done["news_text"]
    assert [d for n, d in ev2 if n == "card"][-1]["kind"] == "news"


def test_commit_flow_phases_and_outcome_shape(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    play_to_decide(client, h, cid)
    # opening the commit screen from play moves the phase; an empty draft is fine
    assert client.put(f"/campaigns/{cid}/commit-draft", json={}, headers=h).status_code == 204
    assert client.get(f"/campaigns/{cid}", headers=h).json()["phase"] == "commit"
    # "Back to investigating"
    back = client.post(f"/campaigns/{cid}/resume-play", headers=h).json()
    assert back["phase"] == "play"
    assert client.get(f"/campaigns/{cid}", headers=h).json()["phase"] == "play"
    part = {"action": "invest", "amount_eur": 50}
    client.put(f"/campaigns/{cid}/commit-draft", json=part, headers=h)
    draft = client.get(f"/campaigns/{cid}", headers=h).json()["commit_draft"]
    assert draft == {"action": "invest", "amount_eur": 50}
    # lock: the legacy key ``decision`` still works; the answer is the outcome shape
    legacy = {k: v for k, v in COMMIT.items() if k != "action"} | {"decision": "invest"}
    lk = client.post(f"/campaigns/{cid}/lock", json=legacy, headers=h).json()
    assert client.get(f"/campaigns/{cid}", headers=h).json()["phase"] == "timeskip"
    rv = client.get(f"/campaigns/{cid}/reveal", headers=h).json()
    assert rv == lk | {"phase": "reveal"}
    assert set(rv["breakdown"]) == {
        "starting_budget", "cash_kept", "invested", "value_now", "fees", "final_value", "pl_eur",
        "pl_pct",
    }  # fmt: skip
    assert rv["locked_at"].startswith("Day ")
    assert rv["series"][-1]["story_day"] > rv["decision_day"] and rv["action"] == "invest"
