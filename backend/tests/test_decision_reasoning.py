# ruff: noqa: F811
"""@spec: 003-campaign-engine (the player's reasoning behind each important decision)"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import campaign_state, post_sse
from test_campaign_api import COMMIT, enron, new_player, play_to_decide, start  # noqa: F401
from test_scene_allows_moves import act, here, open_scene, types

from financequest.campaign import reasoning, service
from financequest.db.models import Decision, Event
from financequest.db.session import get_engine


def setup(client: TestClient) -> tuple[dict[str, str], str]:
    h = new_player(client)
    cid, _ = start(client, h)
    open_scene(h, cid)
    return h, cid


def first_decision(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    return next(d for d in campaign_state(client, h, cid)["decisions"] if d["action"] != "loss")


def reasoning_events(cid: str) -> list[dict[str, Any]]:
    with Session(get_engine()) as db:
        rows = db.exec(select(Event).where(Event.campaign_id == uuid.UUID(cid),
                                           Event.type == "decision_reasoning").order_by(Event.id))  # type: ignore[arg-type]
        return [dict(e.payload) for e in rows]


# ---- scripted reading -----------------------------------------------------------------------
@pytest.mark.parametrize("text,got", [
    ("buy 20 because the cash flow keeps falling", "the cash flow keeps falling"),
    ("sell all since the auditor quit", "the auditor quit"),
    ("I invest 400 coins: the cash flow worries me", "the cash flow worries me"),
    ("buy 20", None),
])
def test_inline_reasoning_is_extracted(text: str, got: str | None) -> None:
    assert reasoning.extract_inline(text) == got


def test_sufficient_versus_thin_versus_missing() -> None:
    assert reasoning.is_sufficient("the cash flow keeps falling")
    assert reasoning.is_sufficient("debt is 5 times earnings")
    assert reasoning.is_sufficient("I read the notes and weighed them against each other")
    assert not reasoning.is_sufficient("I like it")
    assert not reasoning.is_sufficient("just because")
    assert not reasoning.is_sufficient("gut feeling")
    assert not reasoning.is_sufficient(None)


# ---- the decision turn ----------------------------------------------------------------------
def test_sufficient_inline_reasoning_is_stored_and_nothing_is_asked(
    client: TestClient, enron: str
) -> None:
    h, cid = setup(client)
    done = act(client, h, cid, "buy 20 because the cash flow keeps falling")
    assert done["awaiting_reasoning"] is False
    assert "What made you choose that?" not in done["text"]
    d = first_decision(client, h, cid)
    assert d["reasoning"] == "the cash flow keeps falling" and d["reasoning_source"] == "inline"
    assert reasoning_events(cid)[0]["source"] == "inline"


def test_missing_reasoning_is_asked_once_and_the_next_message_is_recorded_verbatim(
    client: TestClient, enron: str
) -> None:
    h, cid = setup(client)
    done = act(client, h, cid, "buy 20")
    assert done["awaiting_reasoning"] is True
    assert done["text"].rstrip().endswith("What made you choose that?")
    assert campaign_state(client, h, cid)["awaiting_reasoning"] is True
    d = first_decision(client, h, cid)
    assert d["reasoning"] is None and d["reasoning_source"] is None

    words = "The debt note scared me, honestly!  buy more"  # trade words: still not an action
    ack = act(client, h, cid, words)
    assert ack["awaiting_reasoning"] is False
    assert "What do you do next?" in ack["text"]
    judging = ("good", "great", "smart", "wise", "right", "wrong")
    assert not any(w in ack["text"].lower() for w in judging)
    d = first_decision(client, h, cid)
    assert d["reasoning"] == words and d["reasoning_source"] == "asked"
    decisions = campaign_state(client, h, cid)["decisions"]
    assert len([x for x in decisions if x["action"] != "loss"]) == 1
    assert types(cid).count("trade") == 1
    assert [e["source"] for e in reasoning_events(cid)] == ["asked"]


def test_thin_reasoning_gets_a_gentler_follow_up_and_is_extended(
    client: TestClient, enron: str
) -> None:
    h, cid = setup(client)
    done = act(client, h, cid, "buy 20 because I like it")
    assert done["awaiting_reasoning"] is True
    assert done["text"].rstrip().endswith("Can you say a bit more about why?")
    act(client, h, cid, "the report shows debt rising")
    d = first_decision(client, h, cid)
    assert d["reasoning"] == "I like it. the report shows debt rising"
    assert d["reasoning_source"] == "asked"
    # asked at most once: the next message is a normal turn, not more reasoning
    follow = act(client, h, cid, "what is cash flow?")
    assert follow["awaiting_reasoning"] is False
    assert len(reasoning_events(cid)) == 1


def test_skip_records_skipped_and_the_game_continues(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    act(client, h, cid, "buy 20")
    ack = act(client, h, cid, "skip")
    assert ack["awaiting_reasoning"] is False and "What do you do next?" in ack["text"]
    d = first_decision(client, h, cid)
    assert d["reasoning"] is None and d["reasoning_source"] == "skipped"
    assert reasoning_events(cid)[0]["skipped"] is True


def test_travel_right_after_a_decision_records_skipped_and_moves(
    client: TestClient, enron: str
) -> None:
    h, cid = setup(client)
    assert here(client, h, cid) != "market_square"
    act(client, h, cid, "buy 20")
    done = act(client, h, cid, "I want to go to the market")
    assert here(client, h, cid) == "market_square"
    assert done["awaiting_reasoning"] is False
    assert first_decision(client, h, cid)["reasoning_source"] == "skipped"


def test_move_button_also_drops_the_question(client: TestClient, enron: str) -> None:
    h, cid = setup(client)
    act(client, h, cid, "buy 20")
    st = campaign_state(client, h, cid)
    loc = next(x["id"] for x in st["locations"] if x["key"] == "library")
    moved = client.post(f"/campaigns/{cid}/move", json={"location_id": loc}, headers=h)
    assert moved.status_code == 200
    assert campaign_state(client, h, cid)["awaiting_reasoning"] is False
    assert first_decision(client, h, cid)["reasoning_source"] == "skipped"


# ---- the lock, the debrief, the XP, the veteran ----------------------------------------------
def test_lock_stores_the_commit_reasoning_and_it_flows_to_debrief_xp_and_veteran(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    open_scene(h, cid)
    act(client, h, cid, "buy 20 because the cash flow keeps falling")
    play_to_decide(client, h, cid)
    body = {**COMMIT, "evidence": "Debt is large and the auditor flagged the cash flow."}
    r = client.post(f"/campaigns/{cid}/lock", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["final_reasoning"] == {
        "reasoning": body["evidence"], "reasoning_source": "commit"
    }
    with Session(get_engine()) as db:
        dec = db.exec(select(Decision).where(Decision.campaign_id == uuid.UUID(cid))).one()
        assert (dec.reasoning, dec.reasoning_source) == (body["evidence"], "commit")
    outcome = client.get(f"/campaigns/{cid}/reveal", headers=h).json()
    mine = next(d for d in outcome["decisions"] if d["action"] != "loss")
    assert mine["reasoning"] == "the cash flow keeps falling"
    assert mine["reasoning_source"] == "inline"

    _, deb = post_sse(client, f"/campaigns/{cid}/debrief", h)
    state = campaign_state(client, h, cid)
    how = state["debrief"]["how_you_reasoned"]
    assert "the cash flow keeps falling" in how and deb["text"].count(how) == 1

    long = "Next time I would read the cash flow statement first before anything else. " * 3
    ref = client.post(f"/campaigns/{cid}/reflection", json={"text": long}, headers=h)
    assert ref.status_code == 200
    with Session(get_engine()) as db:
        run, _, _ = service.load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        texts = service.player_text(db, run, service.decision_of(db, run.id), None)  # type: ignore[arg-type]
    assert "the cash flow keeps falling" in texts["reasoning"]
    assert "At the seal: Debt is large" in texts["reasoning"]
    xp = client.post(f"/campaigns/{cid}/xp", headers=h)
    assert xp.status_code == 200, xp.text
    assert client.post(f"/campaigns/{cid}/finish", headers=h).status_code == 200

    from financequest.veteran import memory

    with Session(get_engine()) as db:
        run, _, _ = service.load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        v = memory.summarize(db, run)
        mem = memory.remember(db, run)
        detail = memory.campaign_detail(db, run, mem)
    assert any(d["reasoning"] == "the cash flow keeps falling" for d in v["decisions"])
    assert any(d["reasoning"] == "the cash flow keeps falling" for d in detail["decisions"])
