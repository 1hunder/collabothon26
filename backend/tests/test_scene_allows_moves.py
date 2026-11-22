# ruff: noqa: F811
"""@spec: 003-campaign-engine (an open decision scene no longer swallows travel)"""  # noqa: E501

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import campaign_state, post_sse
from test_campaign_api import enron, new_player, start  # noqa: F401

from financequest.campaign import service
from financequest.db.models import Event
from financequest.db.session import get_engine


def open_scene(h: dict[str, str], cid: str, beat: str = "story") -> None:
    with Session(get_engine()) as db:
        run, pack, _ = service.load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        service.open_scene(db, run, pack, beat)
        db.commit()


def here(client: TestClient, h: dict[str, str], cid: str) -> str:
    st = campaign_state(client, h, cid)
    return next(x["key"] for x in st["locations"] if x["id"] == st["current_location_id"])


def types(cid: str) -> list[str]:
    with Session(get_engine()) as db:
        return [e.type for e in db.exec(select(Event).where(Event.campaign_id == uuid.UUID(cid))
                                        .order_by(Event.id))]  # type: ignore[arg-type]


def act(client: TestClient, h: dict[str, str], cid: str, text: str) -> dict[str, Any]:
    return post_sse(client, f"/campaigns/{cid}/actions", h, {"text": text})[1]


def _setup(client: TestClient) -> tuple[dict[str, str], str]:
    h = new_player(client)
    cid, _ = start(client, h)
    return h, cid


def test_travel_text_in_an_open_scene_moves_the_player_and_passes_the_scene(
    client: TestClient, enron: str
) -> None:
    h, cid = _setup(client)
    assert here(client, h, cid) != "market_square"
    open_scene(h, cid)
    done = act(client, h, cid, "I want to go to the market")
    assert here(client, h, cid) == "market_square"
    assert campaign_state(client, h, cid)["market_scene"] is None
    assert done["market_scene"] is None and done["location"]
    assert "scene_passed" in types(cid)
    assert "trade" not in types(cid)


def test_head_to_the_library_also_moves(client: TestClient, enron: str) -> None:
    h, cid = _setup(client)
    open_scene(h, cid)
    act(client, h, cid, "let's head to the library")
    assert here(client, h, cid) == "library"
    assert campaign_state(client, h, cid)["market_scene"] is None


def test_buy_in_a_scene_still_trades(client: TestClient, enron: str) -> None:
    h, cid = _setup(client)
    open_scene(h, cid)
    act(client, h, cid, "buy 20")
    assert "trade" in types(cid) and "scene_passed" not in types(cid)
    assert campaign_state(client, h, cid)["market_scene"] is None


def test_a_question_about_the_trade_keeps_the_scene_open(client: TestClient, enron: str) -> None:
    h, cid = _setup(client)
    open_scene(h, cid)
    act(client, h, cid, "what is the broker's fee?")
    assert campaign_state(client, h, cid)["market_scene"] is not None
    assert "trade" not in types(cid) and "scene_passed" not in types(cid)


def test_a_skill_attempt_in_an_open_scene_gets_a_dice_card_and_keeps_the_scene(
    client: TestClient, enron: str
) -> None:
    h, cid = _setup(client)
    open_scene(h, cid)
    done = act(client, h, cid, "I search the tables carefully for any clues the traders left")
    card = done.get("card") or {}
    assert done.get("intent") == "challenge" and card.get("kind") == "dice"
    assert "scene_passed" not in types(cid) and "trade" not in types(cid)
    assert campaign_state(client, h, cid)["market_scene"] is not None  # still open for later


def test_asking_a_named_character_in_an_open_scene_is_a_conversation(
    client: TestClient, enron: str
) -> None:
    h, cid = _setup(client)
    open_scene(h, cid)
    done = act(client, h, cid, "Ask Ren Tal why the crowd is so nervous today")
    assert done.get("intent") != "scene_question"
    assert "trade" not in types(cid) and "scene_passed" not in types(cid)
    assert campaign_state(client, h, cid)["market_scene"] is not None  # still open for later
