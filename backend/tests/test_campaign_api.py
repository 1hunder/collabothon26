"""@spec: 003-campaign-engine (API flow on the approved Enron scenario, gate, rules)"""

import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlmodel import Session
from sse_helpers import post_sse  # noqa: E402

from financequest.agents.campaign.narration import AgentNarration
from financequest.api import sse
from financequest.campaign import dice, focus
from financequest.campaign.adapter import adapt_gate_scenario
from financequest.campaign.narration import set_narration
from financequest.campaign.pack import Pack, build_pack, load_pack
from financequest.campaign.view import gated_content
from financequest.db.models import Event, Scenario, ScenarioSecret
from financequest.db.models_campaign import CampaignRun
from financequest.db.session import get_engine
from financequest.engine.gate import GatedView, checkpoint_rank
from financequest.llm import get_node_llm
from financequest.refpack.approve import approve_pack

PACK_DIR = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"
TABLES = (
    "xp_award, debrief, outcome, clue_state, challenge, location, campaign_run, hero_item, hero, "
    "player, event, decision, scenario_secret, scenario, session"
)


@pytest.fixture(autouse=True)
def _scripted_agents(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The agent graphs over the scripted Campaign Master (what FAKE_LLM=1 runs), instant tokens."""
    monkeypatch.setattr(sse, "TOKEN_DELAY_S", 0)
    set_narration(AgentNarration(get_node_llm({})))
    yield
    set_narration(None)


@pytest.fixture
def enron(client: TestClient) -> Iterator[str]:
    """Approve the fixture into the throwaway DB, and wipe everything afterwards so other tests
    (healthz) still see an empty database."""
    with Session(get_engine()) as db:
        res = approve_pack(PACK_DIR, db)
        assert res.ok, res.reasons
        assert res.scenario_id
        sid = res.scenario_id
    yield sid
    with Session(get_engine()) as db:
        db.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        db.commit()


def new_player(client: TestClient, cls: str = "investigator") -> dict[str, str]:
    sid = client.post("/session").json()["session_id"]
    h = {"X-Session-Id": sid}
    r = client.post("/hero", json={"name": "Lena", "class": cls}, headers=h)
    assert r.status_code == 201, r.text
    return h


def start(client: TestClient, h: dict[str, str]) -> tuple[str, dict[str, Any]]:
    st_ = client.post("/campaigns", json={"interests": ["Gaming"]}, headers=h)
    assert st_.status_code == 201, st_.text
    cid = st_.json()["id"]
    assert client.post(f"/campaigns/{cid}/opening", headers=h).status_code == 200
    return cid, client.get(f"/campaigns/{cid}", headers=h).json()


def loc_id(state: dict[str, Any], key: str) -> str:
    return next(x["id"] for x in state["locations"] if x["key"] == key)


def play_to_decide(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    state = client.get(f"/campaigns/{cid}", headers=h).json()
    for key in ("library", "tavern", "market_square", "library", "market_square"):
        if state["can_decide"]:
            break
        r = client.post(
            f"/campaigns/{cid}/move", json={"location_id": loc_id(state, key)}, headers=h
        )
        assert r.status_code == 200, r.text
        state = client.get(f"/campaigns/{cid}", headers=h).json()
    assert state["can_decide"]
    return state


COMMIT = {
    "action": "invest",
    "amount_eur": 400,
    "evidence": "Cash flow is negative while earnings are positive, and debt is large. " * 2,
    "forecast_pct": 30,
    "confidence": "medium",
}


def finish_campaign(client: TestClient, h: dict[str, str]) -> tuple[str, dict[str, Any]]:
    cid, _ = start(client, h)
    play_to_decide(client, h, cid)
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    lock = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    assert lock.status_code == 200, lock.text
    assert client.get(f"/campaigns/{cid}/reveal", headers=h).status_code == 200
    _, deb_done = post_sse(client, f"/campaigns/{cid}/debrief", h)
    long = "Next time I would read the cash flow statement first before anything else. " * 3
    ref = client.post(f"/campaigns/{cid}/reflection", json={"text": long}, headers=h)
    assert ref.status_code == 200, ref.text
    xp = client.post(f"/campaigns/{cid}/xp", headers=h)
    assert xp.status_code == 200, xp.text
    return cid, {"lock": lock.json(), "debrief": deb_done, "xp": xp.json(), "ref": ref.json()}


def test_hero_validation(client: TestClient) -> None:
    sid = client.post("/session").json()["session_id"]
    h = {"X-Session-Id": sid}
    assert client.get("/hero", headers=h).status_code == 404
    for bad in ("a", "   ", "x" * 21, "bad!"):
        assert (
            client.post("/hero", json={"name": bad, "class": "analyst"}, headers=h).status_code
            == 422
        )
    assert (
        client.post("/hero", json={"name": "Lena", "class": "wizard"}, headers=h).status_code == 422
    )
    ok = client.post("/hero", json={"name": "  Lena  ", "class": "analyst"}, headers=h)
    assert ok.status_code == 201 and ok.json()["name"] == "Lena" and ok.json()["class"] == "analyst"
    assert (
        client.post("/hero", json={"name": "Other", "class": "analyst"}, headers=h).status_code
        == 409
    )
    assert client.get("/hero", headers=h).json()["total_xp"] == 0
    assert client.get("/hero").status_code == 401


def test_campaign_needs_hero(client: TestClient, enron: str) -> None:
    sid = client.post("/session").json()["session_id"]
    r = client.post("/campaigns", json={"interests": []}, headers={"X-Session-Id": sid})
    assert r.status_code == 409 and r.json()["error"]["code"] == "hero_required"


def test_classes_and_state(client: TestClient, enron: str) -> None:
    for cls, hp, rerolls, keen in (
        ("guardian", 120, 0, 0),
        ("analyst", 100, 1, 0),
        ("investigator", 100, 0, 1),
    ):
        h = new_player(client, cls)
        r = client.post("/campaigns", json={"interests": ["Tech"]}, headers=h).json()
        assert (r["hp"], r["hp_eur"], r["rerolls_left"], r["keen_eye_left"]) == (
            hp,
            hp * 10,
            rerolls,
            keen,
        )
        assert r["focus_left"] == 3 and r["phase"] == "setup" and r["scenario_id"] == enron
        assert {x["key"] for x in r["locations"]} >= {"tavern", "market_square", "library"}
        assert r["story_day"] >= 0 and r["scenario"]["horizon_label"].startswith("about ")
        # a second quest while one is active is refused
        assert client.post("/campaigns", json={"interests": []}, headers=h).status_code == 409


def test_news_trigger_and_can_decide(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    assert not s["can_decide"] and not s["news_shown"]
    assert all(
        set(e) == {"id", "title", "text"} for d in s["library"]["documents"] for e in d["entries"]
    )
    assert not any("Heavy Loss" in d["title"] for d in s["library"]["documents"])

    def m(k: str) -> Any:
        return post_sse(client, f"/campaigns/{cid}/move", h, {"location_id": loc_id(s, k)})[1]

    assert not m("library")["news_shown"]
    assert not m("tavern")["news_shown"]
    r = m("market_square")  # arrived at Market Square with 3 turns
    assert r["news_shown"] and r["news"]["kind"] == "news" and r["checkpoint"] == "G1"
    s2 = client.get(f"/campaigns/{cid}", headers=h).json()
    assert any("Heavy Loss" in d["title"] for d in s2["library"]["documents"])
    assert s2["price_board"][-1]["day"] == s2["story_day"] > s["story_day"]
    assert s2["news"]["headline"]
    assert "news" in [
        e["type"] for e in client.get(f"/campaigns/{cid}/journal", headers=h).json()["entries"]
    ]


def test_full_flow_enron_numbers_and_finish(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, parts = finish_campaign(client, h)
    lk = parts["lock"]
    assert lk["breakdown"]["final_value"] == 607.51 and lk["breakdown"]["cash_kept"] == 600.0
    assert lk["breakdown"]["pl_eur"] == -392.49 and lk["breakdown"]["starting_budget"] == 1000.0
    assert lk["locked_at"].startswith("Day ") and lk["series"][0].keys() == {"story_day", "price"}
    assert (lk["hp_before"], lk["hp_after"]) == (100, 61)
    assert lk["currency_note"].startswith("Prices in the company's original currency")
    assert lk["horizon_label"].startswith("about ")
    assert not re.search(
        r"20\d\d|Enron|31\.95",
        json.dumps(
            {k: v for k, v in lk.items() if k != "series"}, ensure_ascii=False
        ),
    )
    assert parts["ref"]["scenario_id"] == enron
    assert [r["key"] for r in parts["debrief"]["whatif"]][:3] == ["dont_invest", "half", "all"]
    assert parts["debrief"]["whatif"][0].keys() == {
        "key", "label", "final_value", "pct", "hp_after", "is_yours",
    }
    assert parts["debrief"]["forecast_line"] == "You said 30% likely higher — it ended lower."
    with Session(get_engine()) as db:
        types = [e.type for e in db.query(Event).filter(Event.campaign_id == uuid.UUID(cid))]
        assert (
            "debrief_complete" in types and "lock" in types and types.count("debrief_complete") == 1
        )
    # reflection is idempotent: no second debrief_complete
    h2 = h
    client.post(
        f"/campaigns/{cid}/reflection", json={"text": "another long answer here"}, headers=h2
    )
    with Session(get_engine()) as db:
        assert [e.type for e in db.query(Event).filter(Event.campaign_id == uuid.UUID(cid))].count(
            "debrief_complete"
        ) == 1
    xp = parts["xp"]
    assert xp["total"] == 100 and [c["max"] for c in xp["categories"]] == [25, 25, 20, 15, 15]
    f1 = client.post(f"/campaigns/{cid}/finish", headers=h).json()
    f2 = client.post(f"/campaigns/{cid}/finish", headers=h).json()
    assert f1 == f2 == {"total_xp": 100, "new_item": focus.item_out("ratio_lens")}
    assert f1["new_item"]["name"] == "Ratio Lens" and f1["new_item"]["id"] == "ratio_lens"
    hero = client.get("/hero", headers=h).json()
    assert hero["total_xp"] == 100 and hero["active_campaign_id"] is None
    assert hero["history"][0]["total_xp"] == 100 and hero["history"][0]["result_pct"] == -39.2
    assert hero["items"][0]["id"] == "ratio_lens" and hero["items"][0]["name"] == "Ratio Lens"
    # second and third campaigns earn the next items in order, HP starts fresh
    cid2, _ = finish_campaign(client, h)
    fin2 = client.post(f"/campaigns/{cid2}/finish", headers=h).json()
    assert fin2["new_item"]["id"] == "rumour_ledger"
    cid3, _ = finish_campaign(client, h)
    assert client.post(f"/campaigns/{cid3}/finish", headers=h).json() == {
        "total_xp": 300,
        "new_item": focus.item_out("calm_compass"),
    }
    st4 = client.post("/campaigns", json={"interests": []}, headers=h).json()
    assert st4["focus_left"] == 4 and st4["hp"] == 100


def test_lock_rules_and_idempotency(client: TestClient, enron: str) -> None:
    h = new_player(client, "guardian")
    cid, s = start(client, h)
    assert (
        client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h).status_code == 409
    )  # not ready
    assert (
        client.put(
            f"/campaigns/{cid}/commit-draft", json={"action": "wait"}, headers=h
        ).status_code
        == 409
    )
    play_to_decide(client, h, cid)
    bad = {**COMMIT, "amount_eur": 1201, "evidence": "short"}
    r = client.post(f"/campaigns/{cid}/lock", json=bad, headers=h)
    assert r.status_code == 422 and set(r.json()["error"]["fields"]) == {"amount_eur", "evidence"}
    assert "€1,200" in r.json()["error"]["fields"]["amount_eur"]
    assert (
        client.post(
            f"/campaigns/{cid}/lock", json={**COMMIT, "action": "spread"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/campaigns/{cid}/commit-draft", json={"evidence": "draft text"}, headers=h
        ).status_code
        == 204
    )
    assert (
        client.get(f"/campaigns/{cid}", headers=h).json()["commit_draft"]["evidence"]
        == "draft text"
    )
    a = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    b = client.post(f"/campaigns/{cid}/lock", json={**COMMIT, "amount_eur": 5}, headers=h)
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert a.json()["breakdown"]["starting_budget"] == 1200.0
    assert (
        client.put(
            f"/campaigns/{cid}/commit-draft", json={"evidence": "x" * 30}, headers=h
        ).status_code
        == 409
    )
    with Session(get_engine()) as db:
        assert (
            db.execute(
                text("select count(*) from decision where campaign_id = :c"), {"c": cid}
            ).scalar()
            == 1
        )
    assert client.post(f"/campaigns/{cid}/xp", headers=h).status_code == 409  # no reflection yet


def test_dont_invest_keeps_budget(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    play_to_decide(client, h, cid)
    r = client.post(
        f"/campaigns/{cid}/lock", json={**COMMIT, "action": "wait", "amount_eur": None}, headers=h
    )
    assert r.json()["breakdown"]["final_value"] == 1000.0 and r.json()["hp_after"] == 100
    assert r.json()["breakdown"]["invested"] == 0.0


def _force_seed(cid: str, seed: int) -> None:
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run
        run.rng_seed = seed
        db.add(run)
        db.commit()


def _challenge(state: dict[str, Any], title_part: str) -> dict[str, Any]:
    return next(c for c in state["challenges"] if title_part in c["title"])


def test_analyst_reroll_and_move_blocked(client: TestClient, enron: str) -> None:
    h = new_player(client, "analyst")
    cid, s = start(client, h)
    ch = _challenge(s, "Quarterly")  # DC 14
    seed = next(x for x in range(1, 5000) if not dice.roll(x, "ENC-QUARTERLY", 0, 14).success)
    _force_seed(cid, seed)
    r = client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"]}, headers=h).json()
    assert r["result"] == "setback" and not r["final"] and r["options"] == ["reroll", "accept"]
    mv = client.post(
        f"/campaigns/{cid}/move", json={"location_id": loc_id(s, "library")}, headers=h
    )
    assert mv.status_code == 409  # open roll
    assert (
        client.post(
            f"/campaigns/{cid}/narrate-roll", json={"roll_id": ch["id"]}, headers=h
        ).status_code
        == 409
    )
    rr = client.post(f"/campaigns/{cid}/rolls/{ch['id']}/reroll", headers=h).json()
    assert rr["final"] and rr["rerolled"] and rr["rerolls_left"] == 0
    assert rr["dice"] == list(dice.roll(seed, "ENC-QUARTERLY", 1, 14).dice)
    assert client.post(f"/campaigns/{cid}/rolls/{ch['id']}/reroll", headers=h).status_code == 409
    again = client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"]}, headers=h)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_resolved"
    assert (
        client.post(
            f"/campaigns/{cid}/narrate-roll", json={"roll_id": ch["id"]}, headers=h
        ).status_code
        == 200
    )
    assert client.get(f"/campaigns/{cid}", headers=h).json()["hp"] == 100  # dice never move HP


def test_analyst_accept_keeps_reroll_and_guardian_has_none(client: TestClient, enron: str) -> None:
    h = new_player(client, "analyst")
    cid, s = start(client, h)
    ch = _challenge(s, "Quarterly")
    _force_seed(
        cid, next(x for x in range(1, 5000) if not dice.roll(x, "ENC-QUARTERLY", 0, 14).success)
    )
    client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"]}, headers=h)
    acc = client.post(f"/campaigns/{cid}/rolls/{ch['id']}/accept", headers=h).json()
    assert acc["final"] and acc["rerolls_left"] == 1 and acc["alt_source"]
    g = new_player(client, "guardian")
    gcid, gs = start(client, g)
    gch = _challenge(gs, "Quarterly")
    _force_seed(
        gcid, next(x for x in range(1, 5000) if not dice.roll(x, "ENC-QUARTERLY", 0, 14).success)
    )
    r = client.post(f"/campaigns/{gcid}/rolls", json={"challenge_id": gch["id"]}, headers=g).json()
    assert r["final"] and r["options"] == ["continue"]
    assert client.post(f"/campaigns/{gcid}/rolls/{gch['id']}/reroll", headers=g).status_code == 409


def test_keen_eye_advantage(client: TestClient, enron: str) -> None:
    h = new_player(client, "investigator")
    cid, s = start(client, h)
    ch = _challenge(s, "Quarterly")
    r = client.post(
        f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"], "mode": "advantage"}, headers=h
    ).json()
    assert len(r["dice"]) == 2 and r["used"] == max(r["dice"]) and r["keen_eye_left"] == 0
    ch2 = _challenge(s, "Crowd")
    bad = client.post(
        f"/campaigns/{cid}/rolls", json={"challenge_id": ch2["id"], "mode": "advantage"}, headers=h
    )
    assert bad.status_code == 409
    g = new_player(client, "guardian")
    gcid, gs = start(client, g)
    assert (
        client.post(
            f"/campaigns/{gcid}/rolls",
            json={"challenge_id": _challenge(gs, "Crowd")["id"], "mode": "advantage"},
            headers=g,
        ).status_code
        == 409
    )


def test_focus_hint_and_bonus_lead(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    hint = post_sse(client, f"/campaigns/{cid}/focus/hint", h)[1]
    assert hint["focus_left"] == 2 and hint["turn_count"] == 0 and hint["text"]
    card = client.post(f"/campaigns/{cid}/focus/bonus-lead", headers=h).json()
    assert card["dc"] == 18 and card["focus_left"] == 1
    assert client.post(f"/campaigns/{cid}/focus/bonus-lead", headers=h).status_code == 409
    client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": card["challenge_id"]}, headers=h)
    client.post(f"/campaigns/{cid}/focus/hint", headers=h)
    r = client.post(f"/campaigns/{cid}/focus/hint", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_focus"


def test_actions_idempotent_and_decision_intent(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    body = {"text": "Let me check the quarterly ledger", "client_msg_id": "m1"}
    a = post_sse(client, f"/campaigns/{cid}/actions", h, body)[1]
    assert a["intent"] == "challenge" and a["card"]["kind"] == "dice" and a["audio_text_id"]
    assert client.get(f"/campaigns/{cid}", headers=h).json()["pending"]["state"] == "offered"
    b = post_sse(client, f"/campaigns/{cid}/actions", h, body)[1]
    assert b["replayed"] and b["text"] == a["text"]
    assert client.get(f"/campaigns/{cid}", headers=h).json()["turn_count"] == 1
    blocked = client.post(
        f"/campaigns/{cid}/actions", json={"text": "hello", "client_msg_id": "m2"}, headers=h
    )
    assert blocked.status_code == 409
    assert client.post(
        f"/campaigns/{cid}/actions", json={"text": "   "}, headers=h
    ).status_code in (409, 422)
    q = post_sse(client, f"/campaigns/{cid}/buddy", h, {"text": "What is a drawdown?"})[1]
    assert (
        q["speaker"] == "CommerzBuddy"
        and client.get(f"/campaigns/{cid}", headers=h).json()["turn_count"] == 1
    )


def test_other_session_cannot_touch_campaign(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    other = new_player(client)
    assert client.get(f"/campaigns/{cid}", headers=other).status_code == 404
    assert client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=other).status_code == 404


def test_reveal_requires_lock(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    assert client.get(f"/campaigns/{cid}/reveal", headers=h).status_code == 409
    assert (
        client.post(
            f"/campaigns/{cid}/reflection", json={"text": "long enough text"}, headers=h
        ).status_code
        == 409
    )


# ---- gate ---------------------------------------------------------------------------------------
@pytest.fixture
def pack_and_terms(client: TestClient, enron: str) -> Pack:
    with Session(get_engine()) as db:
        return load_pack(db, uuid.UUID(enron))


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(cp=st.sampled_from(["G0", "G1", "G2"]), day=st.integers(-30, 200), news=st.booleans())
def test_gate_property_nothing_after_clock_or_secret(
    pack_and_terms: Pack, cp: str, day: int, news: bool
) -> None:
    pack = pack_and_terms
    gv = GatedView(cp, day, news)
    out = gated_content(pack, gv)
    blob = json.dumps(out)
    assert all(p["day"] <= day for p in out["chart"])
    assert all(checkpoint_rank(e["checkpoint"]) <= checkpoint_rank(cp) for e in out["evidence"])
    assert (out["news"] is not None) == news
    for e in pack.evidence:
        if checkpoint_rank(e.checkpoint) > checkpoint_rank(cp):
            assert e.text not in blob
    for term in pack.leak_terms:
        if len(term) > 5:
            assert term not in blob
    assert "secret" not in out and "buy_open" not in blob and "31.95" not in blob
    assert max((p["day"] for p in out["chart"]), default=-999) <= pack.decision_day


def test_state_before_lock_has_no_future_or_identity(
    client: TestClient, enron: str, pack_and_terms: Pack
) -> None:
    h = new_player(client)
    cid, s = start(client, h)
    state = play_to_decide(client, h, cid)
    blob = json.dumps(state)
    assert (
        max(p["day"] for p in state["price_board"])
        <= state["story_day"]
        <= pack_and_terms.decision_day
    )
    assert "outcome" not in state and "horizon_close" not in blob
    assert not re.search(r"Enron|Skilling|Houston|2001", blob)
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", blob)
    for term in pack_and_terms.leak_terms:
        if len(term) > 5:
            assert term not in blob


def test_routers_do_not_import_secret_table() -> None:
    root = Path(__file__).parent.parent / "financequest" / "api" / "routers"
    for name in ("hero.py", "campaigns.py"):
        assert "ScenarioSecret" not in (root / name).read_text()


def test_adapter_builds_playable_minimal_manifest() -> None:
    sc = Scenario(
        invented_name="Brightwater Works",
        industry_shown="Solar panels",
        source="gate",
        story_days=[0, 60, 120],
        beats=[
            {"day": 0, "title": "Launch", "text": "A new line is announced."},
            {"day": 40, "title": "Order", "text": "A big order arrives."},
            {"day": 80, "title": "Warning", "text": "The company warns of weak demand."},
        ],
        chart_series=[{"day": d, "close": 10 + d / 10} for d in range(0, 161, 10)],
    )
    sc.story_days = {"today": 80, "horizon_end": 160}
    pack = build_pack(sc, ScenarioSecret(scenario_id=sc.id, real_name="x"))
    assert len(pack.encounters) == 2 and pack.news and pack.news["headline"] == "Warning"
    assert (pack.decision_day, pack.horizon_day) == (80, 160)
    assert {rules_dc for rules_dc in (e.kind for e in pack.encounters)} == {
        "public_report",
        "unusual_figure",
    }
    assert pack.buy_open > 0 and pack.end_close > pack.buy_open
    assert adapt_gate_scenario(sc)["checkpoints"][2]["story_day"] == 80
