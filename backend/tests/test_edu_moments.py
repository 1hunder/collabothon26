# ruff: noqa: F811, E501
"""@spec: 003-campaign-engine (educational moments: detector, state, lesson, dismiss)"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from sse_helpers import campaign_state, post_sse
from test_all_in_plot import ALL_IN, setup  # noqa: F401
from test_campaign_api import enron, loc_id, new_player, start  # noqa: F401
from test_scene_allows_moves import act, open_scene

from financequest.agents.campaign import context as C
from financequest.agents.campaign import fake
from financequest.agents.campaign import schemas as S
from financequest.agents.campaign.edu_lessons import TERM_LESSONS, prepared_lesson
from financequest.agents.campaign.narration import AgentNarration, lesson_violations
from financequest.campaign import edu, service
from financequest.campaign.events import campaign_events
from financequest.campaign.narration import set_narration
from financequest.db.models_campaign import Hero
from financequest.db.session import get_engine
from financequest.llm import get_node_llm


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    fake.clear_offers()
    fake.clear_damage()
    yield
    fake.clear_offers()
    fake.clear_damage()


def keys(done: dict[str, Any]) -> list[str]:
    return [m["concept_key"] for m in done["edu_new"]]


def hit(**kw: Any) -> list[str]:
    return [c.concept_key for c in edu.detect(edu.EduFacts(**kw))]


# ---- the detector (engine facts in, concepts out) -------------------------------------------------
def test_detector_triggers_each_concept_from_engine_facts() -> None:
    assert hit() == []
    assert hit(news=True) == ["news_reaction"]
    assert hit(trade={"action": "buy", "amount": 400}) == ["first_trade"]
    assert hit(thin_reasoning=True) == ["thin_reasoning"]
    assert hit(loan_offered=True) == ["loan_cost", "debt_and_equity"]
    assert hit(roll={"result": "setback", "used": 5}) == ["luck_vs_skill"]
    assert hit(roll={"result": "success", "used": 20}) == ["luck_vs_skill"]
    assert hit(roll={"result": "success", "used": 12}) == []
    assert hit(hp_loss=2) == ["luck_vs_skill"]
    assert hit(all_in=True) == ["concentration"]
    assert hit(gp={"cash": 100, "position": 900, "total": 1000}) == ["concentration"]
    assert hit(gp={"cash": 300, "position": 700, "total": 1000}) == []
    assert hit(clue_texts=["Ledger The guild owed 14 due soon and its net owners' claim stood at 93"]) == ["debt_and_equity"]
    both = ["The treasury movement register shows a drain although the earnings were positive"]
    assert hit(screen_texts=both) == ["cash_vs_profit"]
    assert hit(text="Is cash flow the same as earnings?") == ["concept_question", "cash_vs_profit"]
    moved = {"first": 100, "last": 90, "change_pct": -10}
    assert hit(chart=moved, at_market=True) == ["price_move"]
    assert hit(chart=moved, screen="market_square") == ["price_move"]
    assert hit(chart=moved) == []  # not looking at the board
    assert hit(chart={"first": 100, "last": 103, "change_pct": 3}, at_market=True) == []  # under 8 percent
    assert hit(text="How do I read this chart?") == ["price_move"]  # asking about the chart is enough


def test_concept_question_names_the_term() -> None:
    (c,) = edu.detect(edu.EduFacts(text="What does a dividend mean?"))
    assert (c.concept_key, c.term, c.title) == ("concept_question", "dividend", "Dividend in plain words")
    (c,) = edu.detect(edu.EduFacts(text="what is diversification?"))
    assert c.title == "Diversification in plain words"
    assert hit(text="I like the dividend") == []  # not a question
    assert all(t in TERM_LESSONS for t in edu.TERMS if t not in ())


def test_snapshot_carries_whole_numbers_and_the_players_words() -> None:
    f = edu.EduFacts(text="What is cash flow?", gp={"cash": 400, "position": 600, "total": 1000},
                     hp=100, hp_start=100, day="Day 3", hp_loss=2)
    snap = edu.snapshot(f, edu.Candidate("luck_vs_skill", "Luck vs judgement"))
    assert snap["gp"] == {"cash": 400, "position": 600, "total": 1000} and snap["hp_loss_gp"] == 20
    q = edu.snapshot(f, edu.Candidate("concept_question", "Cash flow in plain words", "cash flow"))
    assert q["quote"] == "What is cash flow?" and q["term"] == "cash flow"


# ---- the log: dedupe, cap, skipped, dismiss -----------------------------------------------------------
def pending_ids(client: TestClient, h: dict[str, str], cid: str) -> list[str]:
    return [m["id"] for m in campaign_state(client, h, cid)["edu"]["pending"]]


def record(cid: str, h: dict[str, str], **facts: Any) -> list[dict[str, str]]:
    with Session(get_engine()) as db:
        run, _, _ = service.load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        new = edu.record(db, run, campaign_events(db, run.id), edu.EduFacts(**facts), 99)
        db.commit()
        return new


def types(cid: str) -> list[str]:
    with Session(get_engine()) as db:
        return [e.type for e in campaign_events(db, uuid.UUID(cid))]


def test_each_concept_once_cap_three_pending_and_edu_skipped(
    client: TestClient, enron: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financequest.campaign import edu as edu_mod

    monkeypatch.setattr(edu_mod, "MAX_PENDING", 3)  # the cap logic, at a small cap
    h = new_player(client)
    cid, _ = start(client, h)
    assert campaign_state(client, h, cid)["edu"] == {"pending": [], "pending_count": 0}
    new = record(cid, h, news=True, trade={"action": "buy", "amount": 5}, loan_offered=True, all_in=True)
    assert [m["concept_key"] for m in new] == ["news_reaction", "first_trade", "loan_cost"]  # priority order, cap 3
    assert all(m["title"] and m["id"] for m in new)
    assert campaign_state(client, h, cid)["edu"]["pending_count"] == 3
    assert types(cid).count("edu_skipped") == 2  # concentration and debt_and_equity were dropped
    assert record(cid, h, news=True) == []  # news_reaction fired already: once per campaign
    assert types(cid).count("edu_moment") == 3
    # a dropped concept returns once a slot is free
    first = new[0]["id"]
    r = client.post(f"/campaigns/{cid}/edu/{first}/dismiss", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "dismissed" and r.json()["edu"]["pending_count"] == 2
    again = record(cid, h, all_in=True)
    assert [m["concept_key"] for m in again] == ["concentration"]
    assert campaign_state(client, h, cid)["edu"]["pending_count"] == 3
    assert record(cid, h, text="what is a dividend?") == []  # full again: dropped, logged
    assert types(cid).count("edu_skipped") == 3


def test_concept_question_dedupes_per_term(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    assert [m["title"] for m in record(cid, h, text="what is a dividend?")] == ["Dividend in plain words"]
    assert record(cid, h, text="what is a dividend?") == []
    assert [m["title"] for m in record(cid, h, text="what is risk?")] == ["Risk in plain words"]


def test_dismiss_is_idempotent_and_unknown_moments_404(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    (m,) = record(cid, h, news=True)
    url = f"/campaigns/{cid}/edu/{m['id']}/dismiss"
    assert client.post(url, headers=h).json()["status"] == "dismissed"
    assert client.post(url, headers=h).json()["status"] == "dismissed"
    assert pending_ids(client, h, cid) == []
    assert client.post(f"/campaigns/{cid}/edu/nope/dismiss", headers=h).status_code == 404
    assert client.post(f"/campaigns/{cid}/edu/nope/lesson", headers=h).status_code == 404
    other = new_player(client)
    assert client.post(f"/campaigns/{cid}/edu/{m['id']}/dismiss", headers=other).status_code == 404


# ---- SSE: edu_new on every done, edu in the state ----------------------------------------------------
def test_enron_demo_path_shows_three_bubbles_quickly(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, st = start(client, h)
    assert st["edu"] == {"pending": [], "pending_count": 0}
    seen: list[str] = []
    for key in ("library", "market_square", "tavern", "library", "market_square"):
        st = campaign_state(client, h, cid)
        events, done = post_sse(client, f"/campaigns/{cid}/move", h, {"location_id": loc_id(st, key)})
        assert isinstance(done["edu_new"], list)
        seen += keys(done)
        assert done["edu"]["pending_count"] == len(done["edu"]["pending"]) <= 3
        state_ev = [d for n, d in events if n == "state"]
        assert not state_ev or state_ev[-1]["edu"] == done["edu"]  # the state event carries edu too
        if key == "library" and not seen:
            pytest.fail("the Library teaches nothing")
    assert {"cash_vs_profit", "debt_and_equity", "news_reaction"} <= set(seen)
    st = campaign_state(client, h, cid)
    assert st["edu"]["pending_count"] == 3 and len(set(pending_ids(client, h, cid))) == 3


def test_a_question_in_an_action_and_to_buddy_raise_moments(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    done = act(client, h, cid, "What does revenue mean?")
    assert keys(done) == ["concept_question"] and done["edu_new"][0]["title"] == "Revenue in plain words"
    _, b = post_sse(client, f"/campaigns/{cid}/buddy", h, {"text": "what is a dividend?"})
    assert keys(b) == ["concept_question"] and b["edu"]["pending_count"] == 2
    _, b = post_sse(client, f"/campaigns/{cid}/buddy", h, {"text": "hello there"})
    assert b["edu_new"] == []


def test_buddy_screen_makes_price_and_cash_moments(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    _, b = post_sse(client, f"/campaigns/{cid}/buddy", h, {"text": "explain this page", "screen": "library"})
    assert "debt_and_equity" in keys(b)  # the key figures include the owners' claim


def test_damage_makes_a_luck_moment(client: TestClient, enron: str) -> None:
    fake.script_damage(2, "a clerk pockets a fee")
    h = new_player(client)
    cid, _ = start(client, h)
    done = act(client, h, cid, "I look around the room")
    assert "luck_vs_skill" in keys(done)


def test_decision_makes_first_trade_and_thin_reasoning_moments(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    open_scene(h, cid, "story")
    done = act(client, h, cid, "I invest 100 coins")
    assert {"first_trade", "thin_reasoning"} <= set(keys(done))


def test_all_in_and_a_loan_offer_make_concentration_and_loan_moments(client: TestClient, enron: str) -> None:
    fake.script_offer("loan")
    h, cid = setup(client)
    done = act(client, h, cid, ALL_IN)
    got = keys(done)
    assert "concentration" in got and "loan_cost" in got or done["edu"]["pending_count"] == 3
    assert done["offer"]["kind"] == "loan"
    with Session(get_engine()) as db:
        concepts = {(e.payload or {}).get("concept_key") for e in campaign_events(db, uuid.UUID(cid)) if e.type in ("edu_moment", "edu_skipped")}
    assert {"concentration", "loan_cost"} <= concepts  # detected, or dropped by the cap and logged


def test_replayed_reply_keeps_its_edu_new(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    r1 = post_sse(client, f"/campaigns/{cid}/actions", h, {"text": "What does revenue mean?", "client_msg_id": "m1"})[1]
    r2 = post_sse(client, f"/campaigns/{cid}/actions", h, {"text": "What does revenue mean?", "client_msg_id": "m1"})[1]
    assert r2["replayed"] is True and r2["edu_new"] == r1["edu_new"] != []


# ---- the lesson ------------------------------------------------------------------------------------------
def lesson_of(client: TestClient, h: dict[str, str], cid: str, mid: str) -> dict[str, Any]:
    r = client.post(f"/campaigns/{cid}/edu/{mid}/lesson", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


def words(s: str) -> int:
    return len(s.split())


def test_lesson_has_the_shape_marks_viewed_and_is_cached(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    done = act(client, h, cid, "What does revenue mean?")
    (m,) = done["edu_new"]
    les = lesson_of(client, h, cid, m["id"])
    assert set(les) == {"id", "title", "what_happened", "idea", "example", "takeaway", "check"}
    assert les["id"] == m["id"] and les["title"] == "Revenue in plain words"
    assert set(les["check"]) == {"question", "options", "answer_index"}
    assert len(les["check"]["options"]) == 3 and 0 <= les["check"]["answer_index"] < 3
    assert words(les["idea"]) <= 60 and "gp" in les["example"]
    assert campaign_state(client, h, cid)["edu"] == {"pending": [], "pending_count": 0}  # viewed: slot free
    assert lesson_of(client, h, cid, m["id"]) == les  # the same lesson again
    assert types(cid).count("edu_lesson") == 1


def test_every_prepared_lesson_passes_the_lesson_guards(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    facts = {"gp": {"cash": 600, "position": 400, "total": 1000}, "hp": 100, "hp_start": 100, "day": "Day 4",
             "trade": {"action": "buy", "amount": 400}, "loan": {"principal": 500, "repay": 550, "interest": 50},
             "price": {"first": 3188, "last": 2900, "change_pct": -9}, "share_pct": 90, "hp_loss": 2, "hp_loss_gp": 20,
             "roll": {"title": "The Quarterly Ledger", "result": "setback", "used": 3}, "term": "cash flow",
             "support": {"kind": "patron_grant", "reason": "low_hp", "amount": 150}}
    with Session(get_engine()) as db:
        run, pack, hero = service.load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        ctx = C.build_agent_context(db, run, pack, hero)
    cases = [(k, {**facts, "term": None}) for k in edu.CATALOG if k != "concept_question"]
    cases += [("concept_question", {**facts, "term": t}) for t in TERM_LESSONS]
    assert len(edu.CATALOG) == 12
    for key, f in cases:
        les = prepared_lesson(key, f)
        out = S.LessonOut(what_happened=les["what_happened"], idea=les["idea"], example=les["example"],
                          takeaway=les["takeaway"], check_question=les["check"]["question"],
                          check_options=les["check"]["options"], answer_index=les["check"]["answer_index"])
        assert lesson_violations(ctx, out, f) == [], (key, f.get("term"))
        assert words(les["idea"]) <= 60


def scripted_lesson(**over: Any) -> S.LessonOut:
    base: dict[str, Any] = {
        "what_happened": "You asked what revenue means on Day 0.",
        "idea": "Revenue is the money a company bills for what it sold. Costs are not taken out yet.",
        "example": "Imagine a baker sells 100 loaves at 5 gp each. Her revenue is 500 gp.",
        "takeaway": "Revenue is what comes in before costs.",
        "check_question": "A baker sells 10 loaves at 5 gp each. What is her revenue?",
        "check_options": ["50 gp", "10 gp", "5 gp"], "answer_index": 0,
    }
    return S.LessonOut(**{**base, **over})


def serve_with(client: TestClient, bad: S.LessonOut | None) -> tuple[dict[str, str], str, dict[str, Any], dict[str, Any]]:
    h = new_player(client)
    cid, _ = start(client, h)
    (m,) = act(client, h, cid, "What does revenue mean?")["edu_new"]
    nar = AgentNarration(get_node_llm({"campaign_edu_lesson": [bad]} if bad else {}))
    set_narration(nar)
    return h, cid, m, lesson_of(client, h, cid, m["id"])


def test_a_good_generated_lesson_is_served_as_written(client: TestClient, enron: str) -> None:
    good = scripted_lesson()
    _, _, _, les = serve_with(client, good)
    assert les["example"] == good.example and les["check"]["options"] == good.check_options


@pytest.mark.parametrize("over", [
    {"takeaway": "You should buy more shares now."},
    {"idea": "Revenue is sales. I recommend you sell it."},
    {"example": "Imagine a baker sells loaves for 100 €."},
    {"example": "Imagine a baker sells loaves for 100 euros."},
    {"idea": "Revenue is stored in the field first_close."},
    {"idea": "Revenue was 4321 last year."},
    {"example": "Imagine a baker sells 137 loaves at 7 gp each."},  # not a small round number
    {"what_happened": "You lost 77 gp on Day 0 and the company grew by 4321 gp."},
    {"idea": "Real shares of Enron are great."},
    {"takeaway": "Dollars matter a lot: $50."},
    {"idea": "This is a long sentence " + "word " * 30 + "end."},
    {"check_options": ["50 gp", "50 gp", "5 gp"]},
])
def test_guards_reject_a_bad_lesson_and_fall_back_to_the_prepared_one(
    client: TestClient, enron: str, over: dict[str, Any]
) -> None:
    bad = scripted_lesson(**over)
    _, _, m, les = serve_with(client, bad)
    want = prepared_lesson("concept_question", {"term": "revenue", "day": "Day 0"})
    assert les["idea"] == want["idea"] and les["example"] == want["example"]
    assert les["takeaway"] != over.get("takeaway")


def test_lesson_survives_a_crashing_model(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    (m,) = act(client, h, cid, "What does a dividend mean?")["edu_new"]
    set_narration(AgentNarration(get_node_llm({"campaign_edu_lesson": [RuntimeError("down")]})))
    les = lesson_of(client, h, cid, m["id"])
    assert les["idea"] == TERM_LESSONS["dividend"][0]


# ---- Buddy knows what is waiting ------------------------------------------------------------------------------
def test_buddy_context_lists_pending_titles(client: TestClient, enron: str) -> None:
    h = new_player(client)
    cid, _ = start(client, h)
    act(client, h, cid, "What does revenue mean?")
    with Session(get_engine()) as db:
        run, pack, hero = service.load(db, uuid.UUID(cid), uuid.UUID(h["X-Session-Id"]))
        ctx = C.build_agent_context(db, run, pack, hero)
        assert isinstance(db.get(Hero, run.hero_id), Hero)
    assert ctx.edu_pending == ["Revenue in plain words"]
    buddy = str(C.build_messages(ctx, "ROLE", "hi", buddy=True)[1].content)
    assert "Learning moments waiting" in buddy and "Revenue in plain words" in buddy
    assert "Learning moments waiting" not in str(C.build_messages(ctx, "ROLE", "hi")[1].content)
