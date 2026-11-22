"""The Veteran: long-term memory of finished campaigns, the conversation, and its isolation from
the running campaign (no turns, no focus, no news, no leaks)."""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, select
from sse_helpers import campaign_state, post_sse, streamed_text

from financequest.agents.campaign.guards import build_allowlist, number_violations
from financequest.agents.campaign.narration import AgentNarration
from financequest.agents.veteran.context import real_case_lines
from financequest.agents.veteran.narration import VeteranNarration, set_veteran
from financequest.agents.veteran.schemas import VeteranOut
from financequest.api import sse
from financequest.campaign.narration import set_narration
from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun, Hero, Trade
from financequest.db.models_veteran import VeteranMemory, VeteranProfile
from financequest.db.session import get_engine
from financequest.llm import get_node_llm
from financequest.refpack.approve import approve_pack
from financequest.veteran import memory, real_case

PACK_DIR = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"

TABLES = (
    "veteran_lesson, veteran_message, veteran_profile, veteran_memory, campaign_trade, xp_award, "
    "debrief, outcome, clue_state, challenge, location, campaign_run, hero_item, hero, player, "
    "event, decision, scenario_secret, scenario, session"
)
REAL = "Enron"

# Three ways to play the same road: the words decide the judgement, the prices decide the luck.
PANIC = {  # whichever later scene comes (news or decision day), the hero sells in a hurry
    "opening": (
        "I buy 300 coins: the guild ledgers look clean and the docks are busy, so I take a stake."
    ),
    "news": "Get out before it sinks! Sell everything, quick!",
    "decision": "Get out before it sinks! Sell everything, quick!",
}
CAREFUL = {
    "opening": "I keep my coins until I have read the ledgers in the library.",
    "news": (
        "The news is loud, but the cash flow ledger has not changed, so I hold and read further."
    ),
    "decision": (
        "I stay out because cash flow is negative while earnings look positive, and debt is large."
    ),
}
REFLECTION = (
    "Next time I would read the cash flow statement before anything else, and I would write down "
    "why I act before I act, because fear made my choices when the news broke."
)


@pytest.fixture(autouse=True)
def _scripted(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(sse, "TOKEN_DELAY_S", 0)
    set_narration(AgentNarration(get_node_llm({})))
    set_veteran(VeteranNarration(get_node_llm({})))
    yield
    set_narration(None)
    set_veteran(None)


@pytest.fixture
def enron(client: TestClient) -> Iterator[str]:
    with Session(get_engine()) as db:
        res = approve_pack(PACK_DIR, db)
        assert res.ok, res.reasons
        sid = res.scenario_id
    yield str(sid)
    with Session(get_engine()) as db:
        db.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        db.commit()


def new_player(client: TestClient, name: str = "Lena") -> dict[str, str]:
    sid = client.post("/session").json()["session_id"]
    h = {"X-Session-Id": sid}
    assert (
        client.post("/hero", json={"name": name, "class": "investigator"}, headers=h).status_code
        == 201
    )
    return h


def start(client: TestClient, h: dict[str, str]) -> str:
    r = client.post("/campaigns", json={"interests": ["Gaming"]}, headers=h)
    assert r.status_code == 201, r.text
    cid = str(r.json()["id"])
    assert client.post(f"/campaigns/{cid}/opening", headers=h).status_code == 200
    return cid


_ROUTE = ("library", "tavern", "market_square", "library", "market_square", "tavern")


def play(client: TestClient, h: dict[str, str], cid: str, script: dict[str, str]) -> None:
    for i in range(40):
        state = campaign_state(client, h, cid)
        if state["can_decide"]:
            return
        scene = state.get("market_scene")
        if scene:
            post_sse(
                client,
                f"/campaigns/{cid}/actions",
                h,
                {"text": script.get(scene["beat"], script["decision"])},
            )
            continue
        loc = next(x["id"] for x in state["locations"] if x["key"] == _ROUTE[i % len(_ROUTE)])
        assert (
            client.post(f"/campaigns/{cid}/move", json={"location_id": loc}, headers=h).status_code
            == 200
        )
    raise AssertionError("never reached the seal")


def finish(
    client: TestClient, h: dict[str, str], script: dict[str, str], forecast: int, conf: str
) -> str:
    cid = start(client, h)
    play(client, h, cid, script)
    commit = {
        "action": "invest",
        "amount_eur": 0,
        "forecast_pct": forecast,
        "confidence": conf,
        "evidence": "The ledgers and the news are what I weighed before deciding here. " * 2,
    }
    assert client.post(f"/campaigns/{cid}/lock", json=commit, headers=h).status_code == 200
    assert client.get(f"/campaigns/{cid}/reveal", headers=h).status_code == 200
    post_sse(client, f"/campaigns/{cid}/debrief", h)
    assert (
        client.post(
            f"/campaigns/{cid}/reflection", json={"text": REFLECTION}, headers=h
        ).status_code
        == 200
    )
    assert client.post(f"/campaigns/{cid}/xp", headers=h).status_code == 200
    r = client.post(f"/campaigns/{cid}/finish", headers=h)
    assert r.status_code == 200, r.text
    return cid


def talk(
    client: TestClient, h: dict[str, str], text_: str = "", topic: str | None = None
) -> dict[str, Any]:
    events, done = post_sse(client, "/hero/veteran/talk", h, {"text": text_, "topic": topic})
    assert done, events
    assert streamed_text(events).strip() == done["text"]
    return done


def overview(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    r = client.get("/hero/veteran", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


def hero_id(h: dict[str, str]) -> Any:
    with Session(get_engine()) as db:
        hero = db.exec(select(Hero).where(Hero.player_id == h["X-Session-Id"])).one()
        return hero.id


# ---- pure rules --------------------------------------------------------------------------------
def test_judgement_comes_from_the_words_not_the_outcome() -> None:
    def tr(action: str, words: str, beat: str = "decision") -> Trade:
        return Trade(
            campaign_id=uuid.uuid4(), seq=1, beat=beat, story_day=1, text=words, action=action
        )

    assert memory.judge(tr("sell", "Get out before it sinks!", "news")) == (
        "hasty",
        ["sold_on_news", "panic"],
    )
    assert (
        memory.judge(tr("buy", "I buy because the cash flow ledger looks healthy and debt is low"))[
            0
        ]
        == "sound"
    )
    assert memory.judge(tr("hold", "Hmm."))[0] == "thin"


def test_forecast_band() -> None:
    from financequest.db.models import Decision

    d = Decision(session_id=None, scenario_id=None, action="invest", forecast_pct=85, confidence=3)  # type: ignore[arg-type]
    assert memory.forecast_band(d, went_up=False) == "overconfident"
    assert memory.forecast_band(d, went_up=True) == "well_matched"
    d.forecast_pct = 50
    assert memory.forecast_band(d, went_up=False) == "hedged"


# ---- empty state ---------------------------------------------------------------------------------
def test_new_player_gets_an_introduction_and_an_invitation(client: TestClient, enron: str) -> None:
    h = new_player(client)
    ov = overview(client, h)
    assert ov["has_memory"] is False and ov["quests"] == [] and ov["profile"] is None
    assert ov["name"] == "Brannoc Greyhallow"
    done = talk(client, h, "Hello there.", topic="habits")  # a topic without memory is ignored
    assert done["speaker"] == "Brannoc" and done["speaker_id"] == "veteran"
    assert "first quest" in done["text"] and done["text"].rstrip().endswith("?")
    assert len(done["suggestions"]) == 3 and done["mood"] == "listening"
    assert done["audio_text_id"].startswith("v")
    story = talk(client, h, "Tell me another story")
    assert story["text"] != done["text"] and story["text"].rstrip().endswith("?")
    assert len(overview(client, h)["messages"]) == 4


def test_requires_a_hero(client: TestClient, enron: str) -> None:
    sid = client.post("/session").json()["session_id"]
    assert client.get("/hero/veteran", headers={"X-Session-Id": sid}).status_code == 404


# ---- memory --------------------------------------------------------------------------------------
def test_memory_is_created_when_a_campaign_finishes(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid = finish(client, h, PANIC, forecast=85, conf="high")
    with Session(get_engine()) as db:
        mem = db.get(VeteranMemory, uuid.UUID(cid))
        assert mem is not None and mem.number == 1
        trades = list(db.exec(select(Trade).where(Trade.campaign_id == mem.campaign_id)))
        v = mem.verdicts
        assert [d["seq"] for d in v["decisions"]] == [t.seq for t in trades]
        # derived only: none of the player's words are copied into the memory
        assert all(t.text not in str(v) for t in trades)
        assert "panic_sell" in v["tags"] and v["forecast"] == "overconfident"
        prof = db.get(VeteranProfile, mem.hero_id)
        assert prof is not None and prof.data["quests"] == 1
        assert [m["key"] for m in prof.data["milestones"]][0] == "first_quest"
    ov = overview(client, h)
    assert ov["has_memory"] and ov["quests"][0]["real_name"] == "Enron Corporation"


def test_profile_updates_over_several_campaigns(client: TestClient, enron: str) -> None:
    h = new_player(client)
    finish(client, h, PANIC, forecast=85, conf="high")
    p1 = overview(client, h)["profile"]
    assert p1["quests"] == 1 and p1["weaknesses"] == []  # one road is not a pattern yet
    assert {r["tag"] for r in p1["emerging"]} >= {"panic_sell", "overconfident"}
    finish(client, h, PANIC, forecast=90, conf="high")
    p2 = overview(client, h)["profile"]
    assert p2["quests"] == 2
    assert {r["tag"] for r in p2["weaknesses"]} >= {"panic_sell", "overconfident"}
    finish(client, h, CAREFUL, forecast=30, conf="medium")
    p3 = overview(client, h)["profile"]
    assert p3["quests"] == 3 and "third_quest" in [m["key"] for m in p3["milestones"]]
    assert next(r for r in p3["weaknesses"] if r["tag"] == "panic_sell")["count"] == 2
    assert len(overview(client, h)["quests"]) == 3


def test_memory_rebuilds_from_the_campaign_tables(client: TestClient, enron: str) -> None:
    h = new_player(client)
    finish(client, h, PANIC, forecast=85, conf="high")
    finish(client, h, CAREFUL, forecast=30, conf="medium")
    hid = hero_id(h)
    with Session(get_engine()) as db:
        before = {m.campaign_id: m.verdicts for m in db.exec(select(VeteranMemory))}
        prof_before = db.get(VeteranProfile, hid).data  # type: ignore[union-attr]
        memory.rebuild(db, hid)
        db.commit()
    with Session(get_engine()) as db:
        after = {m.campaign_id: m.verdicts for m in db.exec(select(VeteranMemory))}
        assert after == before and db.get(VeteranProfile, hid).data == prof_before  # type: ignore[union-attr]
        # and lazily: a hero whose memory is gone gets it back on the next visit
        db.execute(text("DELETE FROM veteran_memory; DELETE FROM veteran_profile"))
        db.commit()
    assert overview(client, h)["profile"]["quests"] == 2


# ---- the conversation ----------------------------------------------------------------------------
def test_walkthrough_quotes_the_players_words_in_order(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid = finish(client, h, PANIC, forecast=85, conf="high")
    first = talk(client, h, topic=cid)
    assert "“I buy 300 coins" in first["text"] and first["show_timeline"] is True
    assert first["text"].rstrip().endswith("?")
    second = talk(client, h, "Go on to the next one", topic=cid)
    assert "Get out before it sinks" in second["text"] and second["mood"] == "stern"
    assert "fear" in second["text"].lower() or "hurry" in second["text"].lower()
    # an aside does not skip a step of the walkthrough
    talk(client, h, "Should I buy shares?", topic=cid)
    third = talk(client, h, "Go on", topic=cid)
    assert "forecast" in third["text"].lower() and "85%" in third["text"]
    habits = talk(client, h, topic="habits")
    assert habits["text"].rstrip().endswith("?")


def test_advice_requests_are_turned_back_to_reasoning(client: TestClient, enron: str) -> None:
    h = new_player(client)
    finish(client, h, CAREFUL, forecast=30, conf="medium")
    done = talk(client, h, "Should I buy shares in the next company?")
    assert done["mood"] == "stern" and "orders" in done["text"]
    assert done["text"].rstrip().endswith("?")


def test_timeline_and_lessons(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid = finish(client, h, PANIC, forecast=85, conf="high")
    tl = client.get(f"/hero/veteran/quests/{cid}/timeline", headers=h).json()
    assert [d["judgement"] for d in tl["decisions"]][:2] == ["sound", "hasty"]
    assert tl["decisions"][1]["text"] == PANIC["news"] and tl["real_name"] == "Enron Corporation"
    assert all(d["luck"] in ("kind", "cruel", "neutral") for d in tl["decisions"])
    r = client.post(
        "/hero/veteran/lessons",
        json={"text": "Reread my reasons before I sell.", "campaign_id": cid},
        headers=h,
    )
    assert r.status_code == 201 and r.json()["quest_title"]
    assert overview(client, h)["lessons"][0]["text"] == "Reread my reasons before I sell."
    assert client.post("/hero/veteran/lessons", json={"text": "x"}, headers=h).status_code == 422
    other = new_player(client, "Mira")
    assert client.get(f"/hero/veteran/quests/{cid}/timeline", headers=other).status_code == 404


def test_tts_speaks_only_stored_veteran_replies(client: TestClient, enron: str) -> None:
    assert client.get("/tts/v999999", params={"voice": "veteran"}).status_code == 404
    assert client.get("/tts/vx", params={"voice": "veteran"}).status_code == 422


# ---- isolation from the running campaign ---------------------------------------------------------
def _snapshot(cid: str) -> tuple[dict[str, Any], int]:
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run is not None
        row = run.model_dump()
        n = len(list(db.exec(select(Event).where(Event.campaign_id == run.id))))
        return row, n


def test_talking_never_touches_the_running_campaign(client: TestClient, enron: str) -> None:
    h = new_player(client)
    finish(client, h, PANIC, forecast=85, conf="high")
    cid = start(client, h)
    before = _snapshot(cid)
    state_before = campaign_state(client, h, cid)
    for msg in ("Hello.", "Tell me a story", "What happens next in my quest right now?"):
        talk(client, h, msg)
    talk(client, h, topic="habits")
    overview(client, h)
    assert _snapshot(cid) == before
    after = campaign_state(client, h, cid)
    for k in ("turn_count", "focus_left", "news_shown", "story_day", "checkpoint", "phase"):
        assert after.get(k) == state_before.get(k), k


def test_running_campaign_on_the_same_company_seals_the_old_one(
    client: TestClient, enron: str
) -> None:
    h = new_player(client)
    old = finish(client, h, PANIC, forecast=85, conf="high")
    start(client, h)  # the same scenario again: the old road would give the new one away
    ov = overview(client, h)
    assert ov["running"] is True and ov["quests"] == [] and ov["has_memory"] is False
    done = talk(client, h, "Tell me about my last quest")
    assert REAL not in done["text"]
    r = client.post("/hero/veteran/talk", json={"topic": old}, headers=h)
    assert r.status_code == 404
    assert client.get(f"/hero/veteran/quests/{old}/timeline", headers=h).status_code == 404


def test_guards_replace_a_leaking_or_invented_reply(client: TestClient, enron: str) -> None:
    h = new_player(client)
    finish(client, h, PANIC, forecast=85, conf="high")
    start(client, h)
    leak = VeteranOut(
        text="Your quest now is Enron, mark my words. Is that clear?",
        mood="stern",
        suggestions=["a", "b", "c"],
    )
    invented = VeteranOut(
        text="You made 37 percent on that road. Proud?", suggestions=["a", "b", "c"]
    )
    advice = VeteranOut(
        text="You should buy shares now, they will rise. Ready?", suggestions=["a", "b", "c"]
    )
    for bad in (leak, invented, advice):
        set_veteran(VeteranNarration(get_node_llm({"veteran_talk": [bad]})))
        done = talk(client, h, "Hello.")
        assert done["degraded"] is True, bad.text
        assert (
            REAL not in done["text"]
            and "37" not in done["text"]
            and "should buy" not in done["text"]
        )
        assert done["text"].rstrip().endswith("?")


# ---- the real case: history for teaching, after the quest ---------------------------------------
def test_real_prices_and_dates_read_as_whole_numbers() -> None:
    assert [real_case.usd(x) for x in ("42.93", "0.26", "0.004", "1234.5", "0.01")] == [
        "$43", "26 cents", "0 cents", "$1,235", "1 cent",
    ]  # fmt: skip
    assert real_case.long_date("2001-08-14") == "14 August 2001"
    assert real_case.long_date("Day 3") == "Day 3"


def test_number_guard_allows_millions_only_for_history() -> None:
    allowed = build_allowlist(["a net loss of 618"], [])
    assert number_violations("a loss of $618 million", allowed)  # a quest reply: never
    assert number_violations("a loss of $618 million", allowed, big_words=True) == []


def test_timeline_shows_the_real_case(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid = finish(client, h, PANIC, forecast=85, conf="high")
    rc = client.get(f"/hero/veteran/quests/{cid}/timeline", headers=h).json()["real_case"]
    assert rc["company"] == "Enron Corporation" and rc["ticker"] == "ENE"
    assert rc["start"]["date"].endswith("2001") and rc["end"]["date"].endswith("2001")
    prices = [rc["start"]["price"], rc["end"]["price"], *(d["price"] for d in rc["decisions"])]
    assert all(p.startswith("$") or p.endswith("cent") or p.endswith("cents") for p in prices)
    assert all("." not in p for p in prices)  # whole dollars or cents, never decimals
    assert [d["seq"] for d in rc["decisions"]] == list(range(1, len(rc["decisions"]) + 1))
    assert all(d["date"].endswith("2001") for d in rc["decisions"])
    assert rc["events"], "the real headlines are part of the lesson"
    assert all("Golden Guild" not in e["headline"] for e in rc["events"])  # real text, not disguise
    assert isinstance(rc["move_pct"], int)


def test_the_veteran_teaches_with_the_real_case(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid = finish(client, h, PANIC, forecast=85, conf="high")
    replies = [talk(client, h, topic=cid)]
    for _ in range(10):
        replies.append(talk(client, h, "Go on", topic=cid))
        if "real story" in replies[-1]["text"]:
            break
    story = replies[-1]
    assert "real story" in story["text"], [r["text"] for r in replies]
    assert "Enron Corporation" in story["text"] and "2001" in story["text"]
    assert "$" in story["text"] or "cents" in story["text"]
    assert story["degraded"] is False and story["text"].rstrip().endswith("?")
    asked = [r for r in replies if "What really happened to the company?" in r["suggestions"]]
    assert asked, "the hero is offered the real story"


def test_real_case_reaches_the_prompt_only_for_the_quest_discussed() -> None:
    rc = {
        "company": "Enron Corporation", "ticker": "ENE",
        "start": {"date": "1 August 2001", "price": "$43"},
        "decision_day": {"date": "7 September 2001", "price": "$31"},
        "end": {"date": "30 November 2001", "price": "26 cents"},
        "move_pct": -99, "move_after_decision_pct": -99, "high": "$45", "low": "26 cents",
        "decisions": [{"seq": 1, "action": "buy", "date": "3 August 2001", "price": "$42"}],
        "events": [{"date": "14 August 2001", "headline": "CEO resigns", "price": "$43"}],
    }  # fmt: skip
    lines = "\n".join(real_case_lines(rc))
    assert "Enron Corporation (ticker ENE)" in lines and "26 cents" in lines
    assert "1. buy | 3 August 2001 | $42" in lines
    assert "- 14 August 2001 | CEO resigns | $43" in lines
    assert real_case_lines(None) == []


# ---- the demo hero -------------------------------------------------------------------------------
def test_demo_hero_has_finished_campaigns_and_a_profile(client: TestClient, enron: str) -> None:
    from financequest.veteran.demo import seed_demo_hero

    out = seed_demo_hero(name="Tarn", campaigns=3)
    assert len(out["campaigns"]) == 3 and out["distinct_companies"] == 1
    h = {"X-Session-Id": out["session_id"]}
    ov = overview(client, h)
    assert ov["has_memory"] and len(ov["quests"]) == 3 and ov["running"] is False
    p = ov["profile"]
    assert p["quests"] == 3 and "third_quest" in [m["key"] for m in p["milestones"]]
    assert p["strengths"] or p["weaknesses"]  # something recurs across the three roads
    hab = talk(client, h, topic="habits")
    assert hab["text"].rstrip().endswith("?") and hab["degraded"] is False
