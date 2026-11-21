# ruff: noqa: F811
"""@spec: 003-campaign-engine (ad-hoc skill checks: an uncertain skilled action gets a dice card)"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import post_sse
from test_campaign_api import (  # noqa: F401  (fixtures + helpers)
    _force_seed,
    _scripted_agents,
    enron,  # noqa: F401
    loc_id,
    new_player,
    start,
)
from test_master_intents_npc_damage import act, ctx_of, state

from financequest.agents.campaign import fake
from financequest.agents.campaign.graphs import validate_route
from financequest.agents.campaign.schemas import CheckSpec, RouteOut
from financequest.campaign import dice, rules, service
from financequest.db.models_campaign import Challenge, ClueState
from financequest.db.session import get_engine


@pytest.fixture(autouse=True)
def _clean_damage() -> Iterator[None]:
    fake.clear_damage()
    yield
    fake.clear_damage()


def goto_market(client: TestClient, h: dict[str, str], cid: str) -> None:
    s = state(client, h, cid)
    r = client.post(f"/campaigns/{cid}/move", json={"location_id": loc_id(s, "market_square")},
                    headers=h)
    assert r.status_code == 200, r.text


def adhoc_rows(cid: str) -> list[Challenge]:
    with Session(get_engine()) as db:
        return [c for c in service.challenges(db, uuid.UUID(cid)) if rules.is_adhoc(c.kind)]


def roll(client: TestClient, h: dict[str, str], cid: str, card: dict[str, Any]) -> dict[str, Any]:
    body = {"challenge_id": card["challenge_id"]}
    r = client.post(f"/campaigns/{cid}/rolls", json=body, headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


def seed_for(cid: str, key: str, dc: int, success: bool) -> None:
    ok = (x for x in range(1, 20000) if dice.roll(x, key, 0, dc).success == success)
    _force_seed(cid, next(ok))


def test_search_the_room_opens_an_investigation_dice_card(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    done = act(client, h, cid, "I search the room for clues")
    card = done["card"]
    assert card["kind"] == "dice" and card["skill"] == "Investigation" and card["dc"] == 10
    low = done["text"].lower()
    assert card["title"] and "dice" not in low and "roll" not in low
    st = state(client, h, cid)
    assert st["pending"]["challenge_id"] == card["challenge_id"]
    ch = next(c for c in st["challenges"] if c["id"] == card["challenge_id"])
    assert ch["skill"] == "Investigation" and ch["dc"] == 10  # the card survives a reload


def test_insight_on_ren_tal_is_an_insight_check_on_ren_tal(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    goto_market(client, h, cid)
    done = act(client, h, cid, "I try to read whether Ren Tal is lying")
    card = done["card"]
    assert card["skill"] == "Insight" and card["dc"] == 13 and card["title"] == "Ren Tal"
    (row,) = adhoc_rows(cid)
    assert row.kind == "skill:insight" and row.location_key == "market_square"
    # everything Ren Tal can say at this point is free or already behind a listed challenge:
    # nothing real is left to reveal, so a success tells a small non-evidence detail only
    assert row.clue_id is None
    seed_for(cid, row.key, row.dc, success=True)
    before = {c["clue_id"] for c in state(client, h, cid)["clues"]}
    assert roll(client, h, cid, card)["result"] == "success"
    narr = post_sse(client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": card["roll_id"]})[1]
    assert "dice" not in narr["text"].lower()
    assert {c["clue_id"] for c in state(client, h, cid)["clues"]} == before


def test_success_reveals_an_unfound_unlocked_clue_only(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    client.post(f"/campaigns/{cid}/move", json={"location_id": loc_id(s, "golden_guild_hall")},
                headers=h)
    ctx = ctx_of(cid, h["X-Session-Id"])
    elian = next(c for c in ctx.content["characters"] if c["name"] == "Elian Voss")
    gated = rules.gated_clue_ids(ctx.pack)
    held = [i for i in elian["may_reveal"] if i not in ctx.found and i not in gated]
    assert held, "fixture: the treasurer holds clues the hero has not found"
    card = act(client, h, cid, "I try to read whether Elian Voss is lying")["card"]
    assert card["skill"] == "Insight" and card["title"] == "Elian Voss"
    (row,) = adhoc_rows(cid)
    assert row.clue_id == held[0]  # unlocked (visible at this checkpoint), unfound, not dice-gated
    assert row.clue_id not in ctx.found and row.clue_id not in gated
    seed_for(cid, row.key, row.dc, success=True)
    res = roll(client, h, cid, card)
    assert res["result"] == "success" and res["final"] and res["skill"] == "Insight"
    narr = post_sse(client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": card["roll_id"]})[1]
    assert "learn" in narr["text"] and "dice" not in narr["text"].lower()
    assert held[0] in {c["clue_id"] for c in state(client, h, cid)["clues"]}
    with Session(get_engine()) as db:
        src = db.exec(select(ClueState).where(ClueState.clue_id == held[0])).one().source
    assert src == "dice"


def test_failure_gives_setback_and_may_cost_hp_but_no_clue(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    card = act(client, h, cid, "I search the room for clues")["card"]
    (row,) = adhoc_rows(cid)
    seed_for(cid, row.key, row.dc, success=False)
    before = {c["clue_id"] for c in state(client, h, cid)["clues"]}
    res = roll(client, h, cid, card)
    assert res["result"] == "setback" and res["final"] and res["alt_source"] is None
    fake.script_damage(2, "you knock over a vendor's tray and pay for it")
    narr = post_sse(client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": card["roll_id"]})[1]
    assert narr["hp_change"]["delta"] == -2 and "You lose 2 HP" in narr["text"]
    st = state(client, h, cid)
    assert st["hp"] == 98 and {c["clue_id"] for c in st["clues"]} == before


def test_repeat_attempt_is_narrated_without_a_second_roll(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    card = act(client, h, cid, "I search the room for clues")["card"]
    (row,) = adhoc_rows(cid)
    seed_for(cid, row.key, row.dc, success=False)
    roll(client, h, cid, card)
    again = act(client, h, cid, "I search the room again")
    assert again["card"] is None and "already" in again["text"]
    assert len(adhoc_rows(cid)) == 1 and state(client, h, cid)["pending"] is None


def test_trivial_actions_get_no_dice(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    for text in ("I read the notice board", "I ask the barkeep what is on the menu",
                 "What does revenue mean?"):
        done = act(client, h, cid, text)
        assert done["card"] is None, text
    assert adhoc_rows(cid) == []


def test_unlisted_skills_route_by_phrase(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    ctx = ctx_of(cid, h["X-Session-Id"])
    from financequest.agents.campaign.fake import CampaignFakeLLM

    llm = CampaignFakeLLM()
    for text, skill in (("I eavesdrop on the next table", "stealth"),
                        ("I try to persuade the barkeep to talk", "persuasion"),
                        ("I slip past the guards unseen", "stealth")):
        r = llm.route({"ctx": ctx, "input": text})
        assert r.intent == "challenge" and r.check and r.check.skill == skill, text


def test_route_validation_prefers_a_listed_challenge_and_rejects_bad_input(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    ctx = ctx_of(cid, h["X-Session-Id"])
    listed = ctx.challenges[0]["key"]
    chk = CheckSpec(skill="investigation", target="the room", difficulty="easy")
    r = validate_route(ctx, RouteOut(intent="challenge", challenge_key=listed, check=chk))
    assert r.intent == "challenge" and r.challenge_key == listed and r.check is None
    # a person who is elsewhere cannot be read: that is a plain talk
    far = CheckSpec(skill="insight", target="Ren Tal", difficulty="medium")
    assert validate_route(ctx, RouteOut(intent="challenge", check=far)).intent == "talk"
    assert rules.adhoc_dc("easy") == 10 and rules.adhoc_dc("medium") == 13 \
        and rules.adhoc_dc("hard") == 15
