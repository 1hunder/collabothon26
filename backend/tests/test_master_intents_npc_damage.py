# ruff: noqa: F811
"""@spec: 003-campaign-engine (Master move intents, Master-created places with an NPC agent, HP damage)"""  # noqa: E501

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import answer_scene, post_sse
from test_campaign_api import (  # noqa: F401  (fixtures + helpers)
    COMMIT,
    _challenge,
    _force_seed,
    _scripted_agents,
    enron,  # noqa: F401
    loc_id,
    new_player,
    play_to_decide,
    start,
)

from financequest.agents.campaign import context as C
from financequest.agents.campaign import fake, prompts
from financequest.agents.campaign.fake import CampaignFakeLLM
from financequest.agents.campaign.graphs import sanitize_new_location, validate_route
from financequest.agents.campaign.narration import AgentNarration
from financequest.agents.campaign.schemas import NewLocationSpec, NpcSpec, RouteOut
from financequest.campaign import dice, service, turns
from financequest.campaign.service import load
from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun, Location
from financequest.db.session import get_engine
from financequest.llm import get_node_llm
from financequest.media import art

HOLD = "I hold my coins and keep them"
WAREHOUSE = "I want to visit the guild's shipping warehouse at the docks"


@pytest.fixture(autouse=True)
def _clean_damage() -> Iterator[None]:
    fake.clear_damage()
    yield
    fake.clear_damage()


@pytest.fixture
def art_jobs(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    started: list[uuid.UUID] = []
    monkeypatch.setattr(turns, "art_enabled", lambda: True)
    monkeypatch.setattr(art, "start_art_job_in_thread", lambda lid, terms=(): started.append(lid))
    return started


def act(client: TestClient, h: dict[str, str], cid: str, text: str) -> dict[str, Any]:
    answer_scene(client, h, cid)  # a decision scene may be open: hold, then play the action
    return post_sse(client, f"/campaigns/{cid}/actions", h, {"text": text})[1]


def state(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    return dict(client.get(f"/campaigns/{cid}", headers=h).json())


def ctx_of(cid: str, h_sid: str) -> C.AgentContext:
    with Session(get_engine()) as db:
        run, pack, hero = load(db, uuid.UUID(cid), uuid.UUID(h_sid), write=False)
        return C.build_agent_context(db, run, pack, hero)


# ---------------------------------------------------------------------------------------------
# A. intent recognition
# ---------------------------------------------------------------------------------------------
MOVES = [
    ("let's go to the market", "market_square"),
    ("Let's head to the market square", "market_square"),
    ("I want to visit the exchange", "exchange_steps"),
    ("take me to the trading floor", "market_square"),
    ("off to the square", "market_square"),
    ("head to the library", "library"),
    ("I walk to the archive", "library"),
    ("go to the records", "library"),
    ("Let's visit the archives", "library"),
    ("back to the tavern", "tavern"),
    ("head back to the inn", "tavern"),
    ("I return to the tavern", "tavern"),
    ("visit the guild hall", "golden_guild_hall"),
    ("go to the Golden Guild Hall", "golden_guild_hall"),
    ("let's go to the council chamber", "golden_guild_hall"),
    ("I make my way to the steps", "exchange_steps"),
]


@pytest.mark.parametrize(("text", "key"), MOVES)
def test_fake_router_maps_phrasings_to_move(
    client: TestClient, enron: str, text: str, key: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    r = CampaignFakeLLM().route({"ctx": ctx_of(cid, h["X-Session-Id"]), "input": text})
    assert (r.intent, r.location_key) == ("move", key)


def test_examining_beats_moving_and_questions_are_not_moves(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    ctx = ctx_of(cid, h["X-Session-Id"])
    assert (
        CampaignFakeLLM().route({"ctx": ctx, "input": "What is in the library?"}).intent == "free"
    )
    assert (
        CampaignFakeLLM().route({"ctx": ctx, "input": "Examine the Quarterly report"}).intent
        == "challenge"
    )


def test_move_phrase_in_free_text_moves_the_player_over_the_api(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    done = act(client, h, cid, "let's go to the market")
    assert done["intent"] == "move" and done["location"]["key"] == "market_square"
    assert done["speaker_kind"] == "master" and done["escalated"] is False
    assert done["hp_change"] is None and done["new_location"] is None
    assert state(client, h, cid)["current_location_id"] == done["location"]["id"]


def test_router_prompt_carries_the_synonym_and_new_location_rules() -> None:
    p = prompts.ROUTER.lower()
    for word in ("exchange", "archive", "records", "inn", "back to", "let's go to", "new_location"):
        assert word in p


def test_validate_route_converts_known_place_and_rejects_bad_spec(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    ctx = ctx_of(cid, h["X-Session-Id"])
    spec = NewLocationSpec(name="Library", npc=NpcSpec(name="A B", role="x"))
    r = validate_route(ctx, RouteOut(intent="new_location", new_location=spec))
    assert (r.intent, r.location_key) == ("move", "library")  # it already exists
    assert validate_route(ctx, RouteOut(intent="new_location")).intent == "free"
    bad = NewLocationSpec(name="Hall 7", npc=NpcSpec(name="A B", role="x"))
    assert validate_route(ctx, RouteOut(intent="new_location", new_location=bad)).intent == "free"


# ---------------------------------------------------------------------------------------------
# B. Master-created places + NPC
# ---------------------------------------------------------------------------------------------
def test_new_location_creates_place_npc_art_and_moves(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID]
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    done = act(client, h, cid, WAREHOUSE)
    nl = done["new_location"]
    assert done["intent"] == "new_location" and done["speaker_kind"] == "master"
    assert nl["name"] == "Shipping Warehouse" and nl["art_status"] == "pending"
    assert nl["npc"]["name"] and nl["npc"]["role"] and nl["npc"]["id"].startswith("npc-")
    assert done["location"] == {"id": nl["id"], "key": nl["key"], "name": nl["name"]}
    assert nl["npc"]["name"] in done["text"]  # the arrival introduces the NPC
    assert art_jobs == [uuid.UUID(nl["id"])]
    s = state(client, h, cid)
    assert s["current_location_id"] == nl["id"]
    mine = next(x for x in s["locations"] if x["id"] == nl["id"])
    assert mine["generated"] is True and mine["npc"] == nl["npc"]
    assert all(
        x["generated"] is False and x["npc"] is None for x in s["locations"] if x["id"] != nl["id"]
    )
    with Session(get_engine()) as db:
        row = db.get(Location, uuid.UUID(nl["id"]))
        assert row and "No people" in (row.art_subject or "") and row.art_status == "pending"
        assert any(e.type == "location_created" for e in db.exec(select(Event)))


def test_generated_art_job_writes_the_image(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID]
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    nl = act(client, h, cid, WAREHOUSE)["new_location"]
    assert (
        asyncio.run(art.run_art_job(uuid.UUID(nl["id"]), [], generator=art.fake_generate))
        == "ready"
    )
    assert state(client, h, cid)["locations"][-1]["art_status"] in ("ready", "pending")


def test_no_cap_on_generated_places(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID]
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    for text in ("visit the warehouse", "go to the shipyard", "head to the regulator office"):
        assert act(client, h, cid, text)["intent"] == "new_location"
    fourth = act(client, h, cid, "let's visit the harbour master")
    assert fourth["intent"] == "new_location" and fourth["new_location"] is not None
    assert sum(x["generated"] for x in state(client, h, cid)["locations"]) == 4


def test_npc_answers_in_character_and_never_leaks_future_evidence(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID]
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    nl = act(client, h, cid, WAREHOUSE)["new_location"]
    done = act(client, h, cid, "What do you know about the guild?")
    assert done["speaker"] == nl["npc"]["name"] and done["speaker_kind"] == "npc"
    assert done["escalated"] is False
    ctx = ctx_of(cid, h["X-Session-Id"])
    may = set(C.npc_may_reveal(ctx))
    assert set(done["clue_ids_given"]) <= may and len(done["clue_ids_given"]) <= 2
    visible = {e["id"] for e in ctx.content["evidence"]}
    assert may <= visible  # only what the gate already shows at this checkpoint
    future = [e for e in ctx.pack.evidence if e.id not in visible]
    assert future, "the fixture has later-checkpoint evidence"
    # the NPC's own prompt never carries a future clue's id or text
    prompt = str(
        C.build_messages(ctx, prompts.NPC, "hello", extra=C.npc_may_reveal(ctx) and "x")[0].content
    )
    for e in future:
        assert e.id not in prompt and e.text not in prompt


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Let's go to the library", "move"),
        ("I am ready to invest my coins", "decision_intent"),
        ("I sneak past the guard and steal the cargo", "challenge"),  # an uncertain skill check
        ("Tell me a joke about the weather", "off_topic"),
    ],
)
def test_npc_escalates_to_the_master(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID], text: str, intent: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    act(client, h, cid, WAREHOUSE)
    done = act(client, h, cid, text)
    assert done["escalated"] is True and done["speaker_kind"] == "master"
    assert done["speaker"] == "Campaign Master" and done["intent"] == intent


def test_player_can_always_leave_via_the_map(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID]
) -> None:
    h = new_player(client)
    cid, s0 = start(client, h)
    act(client, h, cid, WAREHOUSE)
    r = client.post(f"/campaigns/{cid}/move", json={"location_id": loc_id(s0, "tavern")}, headers=h)
    assert r.status_code == 200 and '"intent": "move"' in r.text
    after = act(client, h, cid, "What do you know?")  # no NPC in the tavern: the Master answers
    assert after["speaker_kind"] == "master" and after["escalated"] is False


def test_leak_terms_never_reach_names_or_art_subjects(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    ctx = ctx_of(cid, h["X-Session-Id"])
    term = ctx.pack.leak_terms[0]
    dirty = NewLocationSpec(
        name="Dock",
        description=f"Where {term} ships sail.",
        art_subject=f"{term} harbour",
        npc=NpcSpec(name=f"{term} Vane", role=f"Agent of {term}", persona=f"Loves {term}."),
    )
    clean = sanitize_new_location(ctx, dirty)
    assert clean is not None
    blob = " ".join(
        [
            clean.name,
            clean.description,
            clean.art_subject,
            clean.npc.name,
            clean.npc.role,
            clean.npc.persona,
        ]
    ).lower()
    assert term.lower() not in blob
    assert sanitize_new_location(ctx, NewLocationSpec(name=f"{term} Docks", npc=dirty.npc)) is None


# ---------------------------------------------------------------------------------------------
# C. damage
# ---------------------------------------------------------------------------------------------
def test_damage_persists_and_reduces_the_budget(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    fake.script_damage(3, "a clerk pockets a fee")
    done = act(client, h, cid, "I look around the room")
    assert done["hp_change"] == {
        "delta": -3,
        "reason": "a clerk pockets a fee",
        "hp": 97,
        "hp_eur": 970,
    }
    assert "You lose 3 HP: a clerk pockets a fee" in done["text"]
    s = state(client, h, cid)
    assert (s["hp"], s["hp_eur"], s["hp_start"]) == (97, 970, 100)
    assert s["purse"]["cash_eur"] == 970.0
    with Session(get_engine()) as db:
        assert db.get(CampaignRun, uuid.UUID(cid)).hp_lost == 3  # type: ignore[union-attr]
        ev = [e for e in db.exec(select(Event)) if e.type == "hp_change"]
        assert len(ev) == 1 and ev[0].payload["delta"] == -3
    assert act(client, h, cid, "I look around again")["hp_change"] is None  # default: no damage


def test_damage_is_clamped_per_turn_only_and_hp_can_reach_zero(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    with Session(get_engine()) as db:  # one reply cannot take more than 10 HP
        run, pack, _ = load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        out = service.apply_hp_loss(db, run, pack, 25, "an absurd claim")
        assert out and out["delta"] == -10
        db.commit()
    for i in range(9):
        fake.script_damage(10, "a disaster")
        done = act(client, h, cid, "I look around")
        assert done["hp_change"], (i, done["text"], done["intent"], done["degraded"])
        assert done["hp_change"]["delta"] == -10
    s = state(client, h, cid)  # no floor, no 30% cap: all 100 HP are gone
    assert (s["hp"], s["hp_eur"]) == (0, 0)
    assert s["purse"]["cash_eur"] == 0.0 and s["purse"]["total_eur"] == 0.0
    fake.script_damage(5, "more")
    assert act(client, h, cid, "I look around")["hp_change"] is None  # nothing left to lose
    assert state(client, h, cid)["hp"] == 0


def test_damage_beyond_cash_comes_out_of_the_invested_draft(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    with Session(get_engine()) as db:
        run, pack, _ = load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        service.record_decision(db, run, pack, "all in", "buy", None, "all")
        assert service.position_of(run, service.trades_of(db, run.id)).cash == 0
        out = service.apply_hp_loss(db, run, pack, 10, "a fire at the stalls")
        assert out and out["delta"] == -10 and out["hp"] == 90
        trades = service.trades_of(db, run.id)
        pos = service.position_of(run, trades)
        assert trades[-1].beat == "damage" and trades[-1].amount_cents == 10000
        assert pos.cash == 0 and pos.shares > 0
        assert service.budget_now(run) == 900
        assert service.purse(db, run, pack)["total_eur"] <= 900 + 1  # the position shrank
        db.commit()
    play_to_decide(client, h, cid, HOLD)
    ok = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    assert ok.status_code == 200, ok.text
    b = ok.json()["breakdown"]
    assert b["starting_budget"] == 900.0
    effects = sum(d["effect_eur"] for d in ok.json()["decisions"])
    assert abs(effects - b["pl_eur"]) < 0.05  # damage effects keep the ledger exact


def test_lock_works_with_zero_budget(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    for _ in range(10):
        fake.script_damage(10, "ruin")
        act(client, h, cid, "I look around")
    assert state(client, h, cid)["hp"] == 0
    play_to_decide(client, h, cid, HOLD)
    ok = client.post(f"/campaigns/{cid}/lock", json={**COMMIT, "amount_cents": 0}, headers=h)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    b = body["breakdown"]
    assert b["starting_budget"] == 0 and b["final_value"] == 0 and b["pl_pct"] == 0
    assert b["cash_kept"] == 0 and b["invested"] == 0
    assert body["hp_before"] == 0 and body["hp_after"] == 0


def test_clamp_rewrites_the_stated_number() -> None:
    assert turns.reconcile_hp_text("A trap! You lose 25 HP: a fee. What now?", 10) == (
        "A trap! You lose 10 HP: a fee. What now?"
    )
    assert (
        turns.reconcile_hp_text("A trap! You lose 5 HP: a fee. What now?", 0) == "A trap! What now?"
    )


def test_moves_and_new_places_may_take_damage(
    client: TestClient, enron: str, art_jobs: list[uuid.UUID]
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    fake.script_damage(4, "a toll at the library door")
    moved = act(client, h, cid, "let's go to the library")
    assert moved["intent"] == "move" and moved["hp_change"]["delta"] == -4
    assert "You lose 4 HP" in moved["text"]
    fake.script_damage(2, "the dockhands demand a fee")
    new = act(client, h, cid, WAREHOUSE)
    assert new["intent"] == "new_location" and new["hp_change"]["delta"] == -2
    assert state(client, h, cid)["hp"] == 94
    assert act(client, h, cid, "tell me a joke about pizza")["hp_change"] is None  # off topic: none


def test_off_topic_and_questions_stay_damage_free(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    fake.script_damage(4, "x")
    assert act(client, h, cid, "tell me a joke about pizza")["hp_change"] is None
    assert act(client, h, cid, "I look around")["hp_change"]["delta"] == -4  # script kept


def test_lock_uses_the_reduced_budget_and_rejects_over_budget(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    fake.script_damage(3, "a bribe demanded")
    act(client, h, cid, "I look around")
    over = client.post(f"/campaigns/{cid}/lock", json={**COMMIT, "amount_cents": 97001}, headers=h)
    assert over.status_code == 422 and over.json()["error"]["code"] == "amount_over_budget"
    play_to_decide(client, h, cid)
    assert state(client, h, cid)["purse"]["total_eur"] == 970.0
    ok = client.post(f"/campaigns/{cid}/lock", json={**COMMIT, "amount_cents": 97000}, headers=h)
    assert ok.status_code == 200, ok.text
    b = ok.json()["breakdown"]
    assert b["starting_budget"] == 970.0 and ok.json()["hp_before"] == 97
    assert b["cash_kept"] + b["invested"] == 970.0


def test_dice_setback_can_cost_hp(client: TestClient, enron: str) -> None:
    h = new_player(client, "analyst")
    cid, s = start(client, h)
    ch = _challenge(s, "Resignation")
    _force_seed(
        cid,
        next(x for x in range(1, 5000) if not dice.roll(x, "ENC-RESIGNATION", 0, ch["dc"]).success),
    )
    client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"]}, headers=h)
    assert client.post(f"/campaigns/{cid}/rolls/{ch['id']}/accept", headers=h).status_code == 200
    fake.script_damage(2, "the lamp tips onto your purse")
    done = post_sse(client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": ch["id"]})[1]
    assert done["hp_change"]["delta"] == -2 and "You lose 2 HP" in done["text"]
    assert state(client, h, cid)["hp"] == 98


def test_dice_success_can_cost_hp_too(client: TestClient, enron: str) -> None:
    h = new_player(client, "analyst")
    cid, s = start(client, h)
    ch = _challenge(s, "Resignation")
    _force_seed(
        cid,
        next(x for x in range(1, 5000) if dice.roll(x, "ENC-RESIGNATION", 0, ch["dc"]).success),
    )
    client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"]}, headers=h)
    fake.script_damage(3, "the archivist charges for the copy")
    done = post_sse(client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": ch["id"]})[1]
    assert done["hp_change"]["delta"] == -3 and "You lose 3 HP" in done["text"]
    assert state(client, h, cid)["hp"] == 97


def test_buddy_done_payload_has_contract_fields(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    done = post_sse(client, f"/campaigns/{cid}/buddy", h, {"text": "What is revenue?"})[1]
    assert done["speaker_kind"] == "buddy" and done["hp_change"] is None
    assert done["escalated"] is False and done["new_location"] is None


def test_hp_guard_demands_the_loss_in_the_text() -> None:
    from financequest.agents.campaign.graphs import HP_NOTE, hp_checks
    from financequest.agents.campaign.schemas import TurnOut

    assert hp_checks(TurnOut(text="Nothing.", hp_loss=2)) == [HP_NOTE]
    assert hp_checks(TurnOut(text="You lose 2 HP: x.", hp_loss=2)) == []
    assert hp_checks(TurnOut(text="Nothing.")) == []


def test_agent_narration_turn_unit_defaults_to_no_damage(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    nar = AgentNarration(get_node_llm({}))
    reply = nar.turn(ctx_of(cid, h["X-Session-Id"]), "I look around")
    assert reply.hp_loss == 0 and service.HP_EUR == 10


def test_engine_creates_a_fourth_place(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    spec = {
        "name": "Place",
        "description": "d",
        "art_subject": "a",
        "npc": {"name": "Ana Bell", "role": "r", "persona": "p"},
    }
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run
        rows = [
            service.create_generated_location(db, run, {**spec, "name": f"Place {n}"})
            for n in "ABCD"
        ]
        assert len({r.key for r in rows}) == 4
        db.commit()


def test_decision_scene_reaction_may_cost_hp(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    fake.script_damage(2, "the broker takes a fee")
    nar = AgentNarration(get_node_llm({}))
    reply = nar.decide(ctx_of(cid, h["X-Session-Id"]), "I put half of my coins in")
    assert reply.kind == "decision" and reply.hp_loss == 2 and "You lose 2 HP" in reply.text
