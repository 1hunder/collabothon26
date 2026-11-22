"""Curated Guild-notice packs: they validate, seed idempotently, show on the Quest Board (Enron is
playable but unlisted) and play end to end like real generated quests."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session
from sse_helpers import campaign_state, post_sse
from test_campaign_api import (  # noqa: F401  (fixture)
    COMMIT,
    TABLES,
    _scripted_agents,
    new_player,
    play_to_decide,
)

from financequest.db.session import get_engine
from financequest.refpack.approve import approve_pack
from financequest.refpack.manifest import CampaignManifest
from financequest.refpack.validate import validate_manifest

ROOT = Path(__file__).resolve().parents[1] / "financequest" / "fixtures" / "reference"
PACKS = sorted(p for p in ROOT.iterdir() if (p / "manifest.json").exists())
GUILD = [p for p in PACKS if p.name != "fq-av-001"]


def _manifest(pack: Path) -> CampaignManifest:
    return CampaignManifest.model_validate_json((pack / "manifest.json").read_text("utf-8"))


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.name)
def test_every_pack_validates(pack: Path) -> None:
    m = _manifest(pack)
    dates = [date.fromisoformat(r["date"]) for r in csv.DictReader((pack / "prices.csv").open())]
    report = validate_manifest(m, dates)
    assert report.ok, report.errors
    assert (pack / "case.md").read_text("utf-8").strip()


@pytest.mark.parametrize("pack", GUILD, ids=lambda p: p.name)
def test_guild_packs_have_board_metadata_and_whole_percentages(pack: Path) -> None:
    m = _manifest(pack)
    assert m.board is not None and m.board.listed and m.board.title and m.board.briefing
    assert m.board.difficulty in ("easy", "medium", "hard") and len(m.board.learn) == 3
    pcts = [f.value for e in m.evidence for f in e.figures if f.family == "percent"]
    assert all(v == v.to_integral_value() for v in pcts)  # whole numbers only


@pytest.fixture
def seeded(client: TestClient) -> Iterator[dict[str, str]]:
    ids: dict[str, str] = {}
    for pack in PACKS:
        with Session(get_engine()) as db:
            first = approve_pack(pack, db)
        with Session(get_engine()) as db:
            again = approve_pack(pack, db)  # idempotent: same scenario
        assert first.ok and again.ok and first.scenario_id == again.scenario_id, first.reasons
        ids[pack.name] = str(first.scenario_id)
    yield ids
    with Session(get_engine()) as db:
        db.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        db.commit()


def test_board_lists_the_guild_quests_in_order_without_enron(
    client: TestClient, seeded: dict[str, str]
) -> None:
    h = new_player(client)
    board = client.get("/quests/board", headers=h).json()
    curated = board["curated"]
    assert [c["scenario_id"] for c in curated][0] == seeded["fq-gme-2021"]  # the demo case first
    assert seeded["fq-av-001"] not in {c["scenario_id"] for c in curated}  # playable but unlisted
    assert {c["scenario_id"] for c in curated} == {seeded[p.name] for p in GUILD}
    blob = json.dumps(curated, ensure_ascii=False)
    for pack in GUILD:
        for term in _manifest(pack).secret.leak_terms:
            flags = 0 if len(term) <= 3 else re.I
            pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
            assert not re.search(pattern, blob, flags), term
    assert not re.search(r"20\d\d", blob)


def _start(client: TestClient, h: dict[str, str], scenario_id: str) -> str:
    r = client.post("/campaigns", json={"scenario_id": scenario_id}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert client.post(f"/campaigns/{cid}/opening", headers=h).status_code == 200
    return str(cid)


def _finish(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    lock = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    assert lock.status_code == 200, lock.text
    assert client.get(f"/campaigns/{cid}/reveal", headers=h).status_code == 200
    _, debrief = post_sse(client, f"/campaigns/{cid}/debrief", h)
    long = "Next time I would separate the crowd from the ledgers before deciding anything. " * 3
    ref = client.post(f"/campaigns/{cid}/reflection", json={"text": long}, headers=h)
    assert ref.status_code == 200, ref.text
    xp = client.post(f"/campaigns/{cid}/xp", headers=h)
    assert xp.status_code == 200, xp.text
    return {"lock": lock.json(), "debrief": debrief, "xp": xp.json(), "ref": ref.json()}


@pytest.mark.parametrize("name", [p.name for p in GUILD])
def test_guild_quest_plays_to_the_reveal(
    client: TestClient, seeded: dict[str, str], name: str
) -> None:
    h = new_player(client)
    cid = _start(client, h, seeded[name])
    state = campaign_state(client, h, cid)
    assert state["scenario_id"] == seeded[name]
    parts = _finish(client, h, cid)
    bd = parts["lock"]["breakdown"]
    assert bd["starting_budget"] == 1000.0 and bd["cash_kept"] == 600.0
    assert round(bd["final_value"] - bd["starting_budget"], 2) == bd["pl_eur"]
    assert parts["ref"]["scenario_id"] == seeded[name]
    assert parts["xp"]["total"] <= 100
    reveal = client.get(f"/scenario/{seeded[name]}/reveal", headers=h).json()
    assert reveal["real_name"] == _manifest(ROOT / name).secret.real_entity


def test_gamestop_demo_maths_and_story(client: TestClient, seeded: dict[str, str]) -> None:
    """400 gp put in on decision day; the squeeze peaked and then fell below the decision price."""
    h = new_player(client)
    cid = _start(client, h, seeded["fq-gme-2021"])
    parts = _finish(client, h, cid)
    bd = parts["lock"]["breakdown"]
    assert bd["final_value"] < 1000.0  # bought into the frenzy, ended lower
    series = parts["lock"]["series"]
    prices = [p["price"] for p in series]
    assert max(prices) > 4 * prices[0]  # the chart shows the explosion
    st = campaign_state(client, h, cid)
    assert {loc["key"] for loc in st["locations"]} >= {"tavern", "market_square", "library"}


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.name)
def test_no_required_clue_hides_in_a_master_created_place(pack: Path) -> None:
    """The seal needs every non-dice clue; a place the Master only creates on request must never
    hold one, or a player who never asks to go there can never decide."""
    m = _manifest(pack)
    gated = {en.success_clue_id for en in m.encounters}
    stuck = [e.id for e in m.evidence if e.location.startswith("campaign:") and e.id not in gated]
    assert not stuck
