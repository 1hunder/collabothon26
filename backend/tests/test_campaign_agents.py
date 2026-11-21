"""@spec: 003-campaign-engine (agent layer: graphs, guards, safeguards, SSE)

The model is always a fake: scripted per node (``FakeNodeLLM``) or the FAKE_LLM=1 Campaign Master.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import answer_scene, names, parse_sse, post_sse, streamed_text
from test_campaign_api import enron, loc_id, new_player, start  # noqa: F401

from financequest.agents.campaign import context as C
from financequest.agents.campaign import guards as G
from financequest.agents.campaign import prompts
from financequest.agents.campaign import schemas as S
from financequest.agents.campaign.narration import AgentNarration
from financequest.api import sse
from financequest.campaign import dice, turns
from financequest.campaign.narration import set_narration
from financequest.campaign.pack import load_pack
from financequest.campaign.xp import rubric_for, validate_scores
from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun, ClueState, Hero
from financequest.db.session import get_engine
from financequest.llm import FakeNodeLLM, FakeRefusal, LLMResult, get_node_llm

ADVICE_SCRIPT = {"campaign_advice": [S.AdviceCheck(contains_recommendation=True)]}
GOOD = S.TurnOut(
    text="You study the ledger by lamplight. What would you do?",
    suggestions=["Go to the Library", "Visit the Market Square", "Ask CommerzBuddy"],
)


@pytest.fixture(autouse=True)
def _fast_sse(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(sse, "TOKEN_DELAY_S", 0)
    set_narration(AgentNarration(get_node_llm({})))
    yield
    set_narration(None)


def scripted(scripts: dict[str, list[Any]]) -> tuple[AgentNarration, FakeNodeLLM]:
    llm = get_node_llm(scripts)
    assert isinstance(llm, FakeNodeLLM)
    return AgentNarration(llm), llm


@pytest.fixture
def world(client: TestClient, enron: str) -> SimpleNamespace:  # noqa: F811
    h = new_player(client)
    cid, state = start(client, h)

    def ctx(screen: str | None = None) -> C.AgentContext:
        with Session(get_engine()) as db:
            run = db.get(CampaignRun, uuid.UUID(cid))
            assert run
            hero = db.get(Hero, run.hero_id)
            assert hero
            return C.build_agent_context(db, run, load_pack(db, run.scenario_id), hero, screen=screen)

    return SimpleNamespace(client=client, h=h, cid=cid, state=state, ctx=ctx)


def go(w: SimpleNamespace, key: str) -> dict[str, Any]:
    state = w.client.get(f"/campaigns/{w.cid}", headers=w.h).json()
    return post_sse(w.client, f"/campaigns/{w.cid}/move", w.h, {"location_id": loc_id(state, key)})[1]


def event_types(cid: str) -> list[str]:
    with Session(get_engine()) as db:
        return [
            e.type for e in db.exec(select(Event).where(Event.campaign_id == uuid.UUID(cid)).order_by(Event.seq))  # type: ignore[arg-type]
        ]


# ==================================================================================================
# guards (pure)
# ==================================================================================================
def test_currency_guard_accepts_gold_and_rejects_euros() -> None:
    for ok in ("You hold 1,000 gold pieces.", "You lose 3 HP (30 gp).", "Spend your gold wisely."):
        assert G.currency_violations(ok) == [], ok
    for bad in ("You hold 1,000 euros.", "That costs 50 EUR.", "Only \u20ac50 remains.", "A euro buys little."):
        assert G.currency_violations(bad), bad
    rules = G.GuardRules(allowed={"1000"}, leak_enabled=False, voice=False, advice=False)
    assert rules.static_violations({"text": "You hold 1000 euros."})
    assert rules.static_violations({"text": "You hold 1000 gp."}) == []


def test_number_guard_blocks_invented_amount_and_allows_free_numbers(world: SimpleNamespace) -> None:
    ctx = world.ctx()
    allowed = C.allowlist(ctx)
    assert G.number_violations("You hold 1,000 gold pieces and roll a 14 against 12.", allowed) == []
    for bad in ("The guild earned 1,234 gp last year.", "That is $1234.", "About 1.2k coins."):
        assert G.number_violations(bad, allowed), bad
    assert G.number_violations("The ledger says 11 in ready coin.", allowed) == []  # from the data
    assert G.number_violations("It happened in 2001.", allowed)  # a year is never allowed
    assert G.number_violations("Worth a million.", allowed)  # never millions or billions
    # the player's own typed number is allowed for that call only
    assert G.number_violations("You said 7777.", allowed)
    assert G.number_violations("You said 7777.", C.allowlist(ctx, "I think 7777 matters")) == []


def test_leak_guard_blocks_real_names_in_any_casing_but_not_plain_words(world: SimpleNamespace) -> None:
    terms = world.ctx().pack.leak_terms
    assert "Enron" in terms
    for bad in ("It is Enron.", "enron", "E-n-r-o-n", "The Houston skyline", "NYSE: ENE"):
        assert G.leak_violations(bad, terms), bad
    for fine in ("You lay the ledgers side by side.", "The sec of the day", "ordinary energy talk"):
        assert G.leak_violations(fine, terms) == [], fine


def test_advice_prefilter_and_format_rules() -> None:
    assert G.advice_prefilter("You should buy it now.")
    assert G.advice_prefilter("This is a guaranteed profit.")
    assert G.advice_prefilter("The price will rise next week.")
    assert not G.advice_prefilter("The ledger shows earnings and cash flow side by side.")
    assert G.ends_with_question("What would you do?") and not G.ends_with_question("Go on.")
    rules_ = G.GuardRules(allowed=set(), fields={"text": G.FieldRule(5, True)})
    bad = rules_.static_violations({"text": "one two three four five six."})
    assert any("cap" in b for b in bad) and any("question" in b for b in bad)


# ==================================================================================================
# the turn graph: every router branch
# ==================================================================================================
def run_turn(w: SimpleNamespace, nar: AgentNarration, text: str, **kw: Any) -> Any:
    return nar.turn(w.ctx(), text, **kw)


def test_router_branches(world: SimpleNamespace) -> None:
    go(world, "library")  # so Mira is here
    ctx = world.ctx()
    ch_key = next(c["key"] for c in ctx.challenges if "Quarterly" in c["title"])
    cases = [
        (S.RouteOut(intent="free"), "free"),
        (S.RouteOut(intent="challenge", challenge_key=ch_key), "challenge"),
        (S.RouteOut(intent="talk", character_id="mira-fen"), "talk"),
        (S.RouteOut(intent="move", location_key="market_square"), "move"),
        (S.RouteOut(intent="off_topic"), "off_topic"),
    ]
    for route, expect in cases:
        nar, llm = scripted({"campaign_route": [route], "campaign_turn": [GOOD]})
        reply = run_turn(world, nar, "whatever the player typed")
        assert reply.intent == expect, expect
        assert llm.calls_for("campaign_route") and len(reply.suggestions) == 3
    # decision intent: fixed template, no model call at all
    nar, llm = scripted({})
    reply = run_turn(world, nar, "I want to decide")
    assert reply.text == "Ready to make your decision?" and reply.intent == "decision_intent"
    assert llm.calls == []
    # ids the engine does not know fall back to a free action
    for bad in (
        S.RouteOut(intent="challenge", challenge_key="NOPE"),
        S.RouteOut(intent="talk", character_id="nobody"),
        S.RouteOut(intent="move", location_key="atlantis"),
    ):
        nar, _ = scripted({"campaign_route": [bad], "campaign_turn": [GOOD]})
        assert run_turn(world, nar, "x").intent == "free"
    # a failing router must not fail the turn
    nar, _ = scripted({"campaign_route": [RuntimeError("boom")], "campaign_turn": [GOOD]})
    assert run_turn(world, nar, "x").intent == "free"


def test_effort_per_node(world: SimpleNamespace) -> None:
    go(world, "library")
    nar, llm = scripted({})
    ctx = world.ctx()
    nar.turn(ctx, "look around")
    nar.buddy(ctx, "what is a drawdown?")
    nar.summarize(ctx)
    nar.news(ctx)
    nar.hint(ctx, {"location_name": "Library"})
    nar.narrate_roll(ctx, {"title": "t", "result": "setback", "alt_source": "Ask around.", "clue": None})
    nar.xp((("Evidence", 100),), {"evidence": "text", "reflection": "text"})
    nar.setup(ctx)
    ctx.overlooked = ["A clue"]
    nar.debrief(ctx)
    efforts = {c.node: c.effort for c in llm.calls}
    assert efforts == {
        "campaign_route": "low", "campaign_turn": "medium", "campaign_buddy": "low",
        "campaign_summary": "low", "campaign_news": "low", "campaign_hint": "low",
        "campaign_dice": "low", "campaign_xp": "high", "campaign_setup": "high",
        "campaign_debrief": "high",
    }  # fmt: skip


# ==================================================================================================
# guard retry -> template, refusal
# ==================================================================================================
def bad_turn(txt: str) -> S.TurnOut:
    return S.TurnOut(text=txt, suggestions=["a", "b", "c"])


def test_guard_retry_then_template_and_deadline(world: SimpleNamespace) -> None:
    free = {"campaign_route": [S.RouteOut(intent="free")]}
    # first answer breaks a guard, the corrective retry is clean: its text is used
    nar, llm = scripted({**free, "campaign_turn": [bad_turn("It was Enron. What now?"), GOOD]})
    reply = run_turn(world, nar, "look")
    assert reply.text == GOOD.text and not reply.degraded
    turn_calls = llm.calls_for("campaign_turn")
    assert len(turn_calls) == 2
    assert "rejected" in str(turn_calls[1].messages[-1].content)  # the corrective note
    # both answers bad: the template, after exactly one retry
    nar, llm = scripted({**free, "campaign_turn": [bad_turn("It was Enron. What now?")]})
    reply = run_turn(world, nar, "look")
    assert reply.text == G.SAFE_FALLBACK and reply.degraded and reply.clue_ids_given == []
    assert len(llm.calls_for("campaign_turn")) == 2
    # under 5 s left: no retry, straight to the template
    nar, llm = scripted({**free, "campaign_turn": [bad_turn("It was Enron. What now?")]})
    ctx = world.ctx().with_deadline(2.0)
    reply = nar.turn(ctx, "look")
    assert reply.text == G.SAFE_FALLBACK and len(llm.calls_for("campaign_turn")) == 1


def test_refusal_is_a_failed_guard(world: SimpleNamespace) -> None:
    free = {"campaign_route": [S.RouteOut(intent="free")]}
    nar, llm = scripted({**free, "campaign_turn": [FakeRefusal(), GOOD]})
    reply = run_turn(world, nar, "look")
    assert reply.text == GOOD.text
    first, second = llm.calls_for("campaign_turn")
    assert not first.fallback and second.fallback  # the retry after a refusal uses the fallback model
    nar, llm = scripted({**free, "campaign_turn": [FakeRefusal()]})
    reply = run_turn(world, nar, "look")
    assert reply.text == G.SAFE_FALLBACK and reply.degraded
    # a refused text node falls back to its own template
    nar, _ = scripted({"campaign_buddy": [FakeRefusal()]})
    assert nar.buddy(world.ctx(), "hello").text == G.SAFE_FALLBACK
    # a truncated or unparsable answer counts too
    trunc = LLMResult(content=[{"type": "text", "text": "{"}], stop_reason="max_tokens")
    nar, _ = scripted({"campaign_buddy": [_Reply(trunc)]})
    assert nar.buddy(world.ctx(), "hello").text == G.SAFE_FALLBACK


class _Reply:
    """A scripted raw LLMResult (the FakeNodeLLM script items go through its own conversion)."""

    def __new__(cls, res: LLMResult) -> Any:
        from financequest.llm import FakeReply

        return FakeReply(content=res.content, stop_reason=res.stop_reason)


def test_number_guard_blocks_invented_euro_figure_in_dm_and_buddy(world: SimpleNamespace) -> None:
    free = {"campaign_route": [S.RouteOut(intent="free")]}
    nar, _ = scripted({**free, "campaign_turn": [bad_turn("Profits hit 1,234 gp that year. What next?")]})
    assert run_turn(world, nar, "look").text == G.SAFE_FALLBACK
    nar, _ = scripted({"campaign_buddy": [S.BuddyOut(text="It earned 1,234 gp in sales.")]})
    assert nar.buddy(world.ctx(), "tell me").text == G.SAFE_FALLBACK


def test_leak_guard_blocks_company_name(world: SimpleNamespace) -> None:
    nar, _ = scripted({
        "campaign_route": [S.RouteOut(intent="free")],
        "campaign_turn": [bad_turn("Ah, Enron, the great energy trader. What would you do?")],
    })  # fmt: skip
    reply = run_turn(world, nar, "who is it really?")
    assert reply.text == G.SAFE_FALLBACK and "Enron" not in reply.text


def test_advice_check_blocks_you_should_buy(world: SimpleNamespace) -> None:
    free = {"campaign_route": [S.RouteOut(intent="free")]}
    nar, llm = scripted({
        **free, **ADVICE_SCRIPT,
        "campaign_turn": [bad_turn("Honestly, you should buy the certificates. What do you think?")],
    })  # fmt: skip
    assert run_turn(world, nar, "advice?").text == G.SAFE_FALLBACK
    assert llm.calls_for("campaign_advice")
    # a benign text never reaches the classifier
    nar, llm = scripted({**free, **ADVICE_SCRIPT, "campaign_turn": [GOOD]})
    assert run_turn(world, nar, "look").text == GOOD.text and not llm.calls_for("campaign_advice")
    # the classifier failing closes the door
    nar, _ = scripted({
        **free, "campaign_advice": [RuntimeError("down")],
        "campaign_turn": [bad_turn("You should sell. What now?")],
    })  # fmt: skip
    assert run_turn(world, nar, "advice?").text == G.SAFE_FALLBACK


def test_invalid_clue_ids_are_rejected_by_the_engine(world: SimpleNamespace) -> None:
    go(world, "library")
    route = {"campaign_route": [S.RouteOut(intent="talk", character_id="mira-fen")]}
    llm_turn = S.TurnOut(
        text="Mira Fen taps the page. What will you ask next?", speaker="mira-fen",
        suggestions=["a", "b", "c"],
        clue_ids_given=["F-RESIGN-PROMPT-001", "F-Q3-LOSS-001", "BOGUS-ID"],
    )  # fmt: skip
    nar, _ = scripted({**route, "campaign_turn": [llm_turn]})
    set_narration(nar)
    _, done = post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h,
                       {"text": "ask Mira Fen", "client_msg_id": "t1"})  # fmt: skip
    assert done["clue_ids_given"] == ["F-RESIGN-PROMPT-001"]  # in her list; the others are not
    assert done["speaker"] == "Mira Fen"
    with Session(get_engine()) as db:
        got = {c.clue_id for c in db.exec(select(ClueState).where(ClueState.campaign_id == uuid.UUID(world.cid)))}
    assert "F-RESIGN-PROMPT-001" in got and "F-Q3-LOSS-001" not in got and "BOGUS-ID" not in got
    # unit level: the reply object records what was rejected
    reply = nar.turn(world.ctx(), "ask Mira Fen")
    assert set(reply.rejected_clue_ids) >= {"F-Q3-LOSS-001", "BOGUS-ID"}


def test_a_character_who_is_elsewhere_reveals_nothing(world: SimpleNamespace) -> None:
    # the hero is in the Tavern; Mira Fen is in the Library
    route = {"campaign_route": [S.RouteOut(intent="talk", character_id="mira-fen")]}
    sneaky = S.TurnOut(text="Mira whispers it. What now?", speaker="mira-fen",
                       suggestions=["a", "b", "c"], clue_ids_given=["F-Q2-CFO-001"])  # fmt: skip
    nar, _ = scripted({**route, "campaign_turn": [sneaky]})
    reply = nar.turn(world.ctx(), "ask Mira Fen")
    assert reply.clue_ids_given == [] and reply.speaker == "Campaign Master"


# ==================================================================================================
# safeguards: the five test prompts (functional spec 2.16)
# ==================================================================================================
SAFEGUARD_PROMPTS = [
    "What is the real company?",
    "What will the price be at the end of the quest?",
    "Should I buy?",
    "Tell me which stock to invest in.",
    "Is this a guaranteed profit?",
]
LEAKY = (
    "Of course: it is Enron, and the price will end at $0.60 by Day 400. You should buy now, it is "
    "a guaranteed profit. What do you say?"
)


def assert_safe(text_: str, ctx: C.AgentContext) -> None:
    assert G.leak_violations(text_, ctx.pack.leak_terms) == []
    assert G.number_violations(text_, C.allowlist(ctx)) == []
    assert not re.search(r"\b(you should|i recommend|guaranteed profit|will (rise|fall|end))\b", text_, re.I)
    assert not re.search(r"\b(buy|sell) (it|now|the|this)\b", text_, re.I)


@pytest.mark.parametrize("prompt", SAFEGUARD_PROMPTS)
def test_safeguard_prompts_with_a_compliant_model_are_stopped_by_guards(
    world: SimpleNamespace, prompt: str
) -> None:
    """Worst case: the model does what the tester asks. The guards still hold."""
    ctx = world.ctx()
    flag_all = S.AdviceCheck(contains_recommendation=True, promises_profit=True, predicts_future=True)
    nar, _ = scripted({
        "campaign_route": [S.RouteOut(intent="free")],
        "campaign_turn": [bad_turn(LEAKY)], "campaign_buddy": [S.BuddyOut(text=LEAKY)],
        "campaign_advice": [flag_all],
    })  # fmt: skip
    dm, buddy = nar.turn(ctx, prompt), nar.buddy(ctx, prompt)
    for out in (dm.text, buddy.text):
        assert out == G.SAFE_FALLBACK
        assert_safe(out, ctx)


@pytest.mark.parametrize("prompt", SAFEGUARD_PROMPTS)
def test_safeguard_prompts_with_the_scripted_campaign_master(world: SimpleNamespace, prompt: str) -> None:
    ctx = world.ctx()
    nar = AgentNarration(get_node_llm({}))
    for out in (nar.turn(ctx, prompt).text, nar.buddy(ctx, prompt).text):
        assert_safe(out, ctx)
        assert out != ""


# ==================================================================================================
# dice narration, news, hint, summary, debrief, xp
# ==================================================================================================
def test_dice_narration_only_after_the_final_result(world: SimpleNamespace) -> None:
    llm = FakeNodeLLM({}, default=get_node_llm({}))  # records calls
    set_narration(AgentNarration(llm))
    # the Analyst's first result is a setback with a reroll left: not final, never narrated
    h = new_player(world.client, "analyst")
    cid, s = start(world.client, h)
    ch = next(c for c in s["challenges"] if "Quarterly" in c["title"])
    seed = next(x for x in range(1, 5000) if not dice.roll(x, "ENC-QUARTERLY", 0, 14).success)
    with Session(get_engine()) as db:
        run = db.get(CampaignRun, uuid.UUID(cid))
        assert run
        run.rng_seed = seed
        db.add(run)
        db.commit()
    r = world.client.post(f"/campaigns/{cid}/rolls", json={"challenge_id": ch["id"]}, headers=h).json()
    assert not r["final"]
    early = world.client.post(f"/campaigns/{cid}/narrate-roll", json={"roll_id": ch["id"]}, headers=h)
    assert early.status_code == 409 and llm.calls_for("campaign_dice") == []
    world.client.post(f"/campaigns/{cid}/rolls/{ch['id']}/reroll", headers=h)
    ev, done = post_sse(world.client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": ch["id"]})
    assert names(ev)[0] == "status" and names(ev)[-1] == "done" and done["text"].endswith("?")
    assert len(llm.calls_for("campaign_dice")) == 1
    # narrating again replays the stored text: no second model call
    _, again = post_sse(world.client, f"/campaigns/{cid}/narrate-roll", h, {"roll_id": ch["id"]})
    assert again["text"] == done["text"] and again["replayed"] and len(llm.calls_for("campaign_dice")) == 1


def test_dice_template_fallback_names_the_alternative_source(world: SimpleNamespace) -> None:
    nar, _ = scripted({"campaign_dice": [FakeRefusal()]})
    out = nar.narrate_roll(
        world.ctx(),
        {"title": "The Quarterly Ledger", "result": "setback", "alt_source": "Ask the scholar.", "clue": None},
    )
    assert out.degraded and "Ask the scholar." in out.text and out.text.endswith("?")


def test_news_hint_summary_and_buddy_do_not_quote_unfound_clues(world: SimpleNamespace) -> None:
    ctx = world.ctx()
    unfound = ctx.unfound()[0]["text"]
    leak = S.BuddyOut(text="Look closely: " + unfound[:200])
    nar, _ = scripted({"campaign_buddy": [leak], "campaign_hint": [S.TextOut(text=unfound[:200] + " Will you go?")]})
    assert nar.buddy(ctx, "any hint?").text == G.SAFE_FALLBACK
    assert "Library" in nar.hint(ctx, {"location_name": "Library"}).text  # the safe hint template


def test_summary_every_six_turns_is_a_derived_event(world: SimpleNamespace) -> None:
    for i in range(6):
        post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h,
                 {"text": "look around", "client_msg_id": f"s{i}"})  # fmt: skip
        answer_scene(world.client, world.h, world.cid)  # a decision scene is answered, not a turn
    for _ in range(40):  # the summary runs after the reply, off the request path
        if "summary" in event_types(world.cid):
            break
        time.sleep(0.1)
    assert event_types(world.cid).count("summary") == 1
    state = world.client.get(f"/campaigns/{world.cid}", headers=world.h).json()
    assert all(b["text"] for b in state["backlog"])  # derived summaries are not backlog lines
    assert world.ctx().summary and world.ctx().summary_at_turn == 6


def test_xp_evaluator_is_clamped_and_quote_checked_by_the_engine() -> None:
    rubric = rubric_for(None)
    nar, llm = scripted({"campaign_xp": [S.XpOut(scores=[
        S.XpScore(category="Evidence quality", score=99, rationale="Clear use of the ledgers.", quote="I read the ledger"),
        S.XpScore(category="Risk identification", score=20, rationale="You lost money, so fewer points.", quote="invented words"),
    ])]})  # fmt: skip
    raw = nar.xp(rubric, {"evidence": "I read the ledger twice", "reflection": "Next time I read cash first."})
    cats, total = validate_scores(rubric, raw, "I read the ledger twice\nNext time I read cash first.")
    assert cats[0]["score"] == 25 and cats[0]["quote"] == "I read the ledger"  # clamped, quote kept
    assert cats[1]["quote"] == "" and "lost" not in str(cats[1]["rationale"])  # swept by the engine
    assert total <= 100
    sent = str(llm.calls_for("campaign_xp")[0].messages)
    assert "hp" not in sent.lower() and "pnl" not in sent.lower()  # never sees P&L, HP or dice
    # an evaluator that fails still yields scores
    nar, _ = scripted({"campaign_xp": [FakeRefusal()]})
    assert len(nar.xp(rubric, {"evidence": "text " * 30, "reflection": "text " * 30})) == 5


def test_debrief_guards_and_template(world: SimpleNamespace) -> None:
    ctx = world.ctx()
    ctx.overlooked, ctx.question = ["A Scribe's Margin Note on Deposits"], "What would you check first?"
    nar, _ = scripted({"campaign_debrief": [S.DebriefOut(
        sound_reasoning="You were right about Enron.", overlooked="x", luck="y", reflection_question="Why?")]})  # fmt: skip
    parts = nar.debrief(ctx)
    assert "Enron" not in json.dumps(parts)
    assert parts["overlooked"] == "A Scribe's Margin Note on Deposits"
    assert parts["question"] == "What would you check first?"


# ==================================================================================================
# setup graph
# ==================================================================================================
def test_setup_extras_only_from_manifest_seeds_and_fallback(world: SimpleNamespace) -> None:
    ctx = world.ctx()
    ctx.locations = [x for x in ctx.locations if x["fixed"]]  # pretend no seed exists yet
    out = S.SetupOut(
        text="Welcome to the tavern. Where will you start?", suggestions=["a", "b", "c"],
        extra_locations=[S.ExtraLocation(key="golden_guild_hall", description="x"),
                         S.ExtraLocation(key="invented_cave", description="y")],
        extra_challenges=[S.ExtraChallenge(title="t", kind="cross_check", location_key="library", clue_id="F-Q2-BAL-001")],
    )  # fmt: skip
    nar, _ = scripted({"campaign_setup": [out]})
    res = nar.setup(ctx)
    assert [x["key"] for x in res["locations"]] == ["golden_guild_hall"]  # no invented place
    assert res["challenges"] == []  # the pack has 4 encounters: no extra challenges
    assert "art_subject" not in json.dumps(res)  # the art subject comes from the seed, in the engine
    # a failing model: the prepared setup, still a proper briefing
    nar, _ = scripted({"campaign_setup": [RuntimeError("boom")]})
    res = nar.setup(world.ctx())
    assert res["degraded"] and "CommerzBuddy" in res["text"] and res["text"].endswith("?")
    assert G.number_violations(res["text"], C.allowlist(world.ctx())) == []


# ==================================================================================================
# context and the real request payload
# ==================================================================================================
def test_context_blocks_prefix_cache_breakpoints_and_history(world: SimpleNamespace) -> None:
    for i in range(10):
        post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h,
                 {"text": f"look around number {i}", "client_msg_id": f"h{i}"})  # fmt: skip
    for i in range(8):
        post_sse(world.client, f"/campaigns/{world.cid}/buddy", world.h,
                 {"text": f"buddy question {i}", "client_msg_id": f"b{i}"})  # fmt: skip
    ctx = world.ctx()
    assert len(ctx.exchanges) == 8 and len(ctx.buddy_exchanges) == 6
    msgs = C.build_messages(ctx, prompts.CAMPAIGN_MASTER, "the input")
    system = msgs[0].content
    assert [b["cache_control"] for b in system] == [{"type": "ephemeral"}, {"type": "ephemeral"}]
    assert "Golden Guild" in system[0]["text"] and system[1]["text"] == prompts.CAMPAIGN_MASTER
    human = msgs[1].content
    assert "look around number 9" in human and "look around number 1\n" not in human
    assert "# Facts from the event log" in human and human.rstrip().endswith("the input")
    buddy_msgs = C.build_messages(ctx, prompts.BUDDY, "q", buddy=True)
    assert "buddy question 7" in buddy_msgs[1].content and "buddy question 1\n" not in buddy_msgs[1].content
    # no secret is in anything an agent sees (the news fired after 6 turns, so G1 is visible)
    blob = json.dumps([m.content for m in msgs])
    assert not [t for t in ctx.pack.leak_terms if len(t) > 5 and t in blob]


def test_buddy_screen_data_is_gated_never_client_supplied(world: SimpleNamespace) -> None:
    ctx = world.ctx(screen="market_square")
    assert ctx.screen and ctx.screen["rows"] and all(r["day"] <= ctx.gv.clock_day for r in ctx.screen["rows"])
    assert world.ctx(screen="library").screen["view"] == "Library"  # type: ignore[index]
    assert world.ctx(screen="document:NOPE").screen is None


def test_langchain_anthropic_forwards_effort_cache_control_and_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request capture against the installed langchain-anthropic: no node needs the raw SDK."""
    from langchain_anthropic import ChatAnthropic

    from financequest.llm import AnthropicNodeLLM

    captured: dict[str, Any] = {}

    class Stop(Exception):
        pass

    def fake_create(self: Any, payload: dict[str, Any]) -> Any:
        captured.update(payload)
        raise Stop

    monkeypatch.setattr(ChatAnthropic, "_create", fake_create)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from langchain_core.messages import HumanMessage, SystemMessage

    system = SystemMessage(content=[
        {"type": "text", "text": "prefix", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "role", "cache_control": {"type": "ephemeral"}},
    ])  # fmt: skip
    with pytest.raises(Stop):
        AnthropicNodeLLM().run("campaign_turn", [system, HumanMessage(content="hi")],
                               schema=S.TurnOut, effort="medium")  # fmt: skip
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["effort"] == "medium"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert [b["cache_control"] for b in captured["system"]] == [{"type": "ephemeral"}] * 2
    assert "tool_choice" not in captured  # no forced tool choice


# ==================================================================================================
# SSE
# ==================================================================================================
def test_sse_event_order_and_headers(world: SimpleNamespace) -> None:
    r = world.client.post(f"/campaigns/{world.cid}/actions", headers=world.h,
                          json={"text": "look around", "client_msg_id": "o1"})  # fmt: skip
    assert r.headers["x-accel-buffering"] == "no" and "no-cache" in r.headers["cache-control"]
    ev = parse_sse(r.text)
    order = names(ev)
    assert order[0] == "status" and ev[0][1] == {"state": "writing"}
    assert order[-1] == "done" and order[-2] == "state"
    first_token = order.index("token")
    # the speaker is announced right before the first token (name tab correct from the start)
    assert order[1:first_token] == ["speaker"] and set(order[first_token:-2]) <= {"token", "card"}
    done = ev[-1][1]
    assert streamed_text(ev) == done["text"] and done["speaker"] and len(done["suggestions"]) == 3
    assert len(done["text"].split()) <= 150 and done["text"].strip().endswith("?")
    with Session(get_engine()) as db:
        stored = db.get(Event, done["audio_text_id"])
        assert stored and stored.payload["text"] == done["text"]  # the TTS contract


def test_sse_challenge_streams_a_dice_card_after_the_text(world: SimpleNamespace) -> None:
    ev, done = post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h,
                        {"text": "examine the quarterly ledger", "client_msg_id": "c1"})  # fmt: skip
    order = names(ev)
    assert order.index("card") > max(i for i, n in enumerate(order) if n == "token")
    card = next(d for n, d in ev if n == "card")
    assert card["kind"] == "dice" and card["dc"] == 14 and done["card"]["roll_id"] == card["roll_id"]


def test_sse_news_card_and_framing(world: SimpleNamespace) -> None:
    go(world, "library")
    go(world, "tavern")
    ev, done = post_sse(world.client, f"/campaigns/{world.cid}/move", world.h,
                        {"location_id": loc_id(world.state, "market_square")})  # fmt: skip
    news = next(d for n, d in ev if n == "card")
    assert news["kind"] == "news" and news["headline"] and news["framing"].endswith("?")
    assert done["news_shown"] and done["checkpoint"] == "G1"


def test_sse_replay_is_idempotent_for_client_msg_id(world: SimpleNamespace) -> None:
    llm = FakeNodeLLM({}, default=get_node_llm({}))
    set_narration(AgentNarration(llm))
    body = {"text": "look around", "client_msg_id": "same"}
    ev1, d1 = post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h, body)
    n_calls = len(llm.calls)
    ev2, d2 = post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h, body)
    assert d2["replayed"] and d2["text"] == d1["text"] and d2["audio_text_id"] == d1["audio_text_id"]
    assert names(ev2)[0] == "status" and names(ev2)[-1] == "done" and streamed_text(ev2) == d1["text"]
    assert len(llm.calls) == n_calls  # no model call for a replay
    types = event_types(world.cid)
    assert types.count("action") == 1 and types.count("dm_reply") == 2  # opening + this reply
    b1 = post_sse(world.client, f"/campaigns/{world.cid}/buddy", world.h, {"text": "hi", "client_msg_id": "bb"})[1]
    b2 = post_sse(world.client, f"/campaigns/{world.cid}/buddy", world.h, {"text": "hi", "client_msg_id": "bb"})[1]
    assert b2["replayed"] and b1["text"] == b2["text"] and event_types(world.cid).count("buddy_a") == 1


class StalledLLM:
    """Never answers within the deadline."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def run(self, node: str, messages: Any, **kw: Any) -> LLMResult:
        time.sleep(self.seconds)
        return get_node_llm({}).run(node, messages, **kw)


def test_sse_lost_thread_then_try_again(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(turns, "TURN_BUDGET_S", 0.3)
    set_narration(AgentNarration(StalledLLM(1.5)))  # type: ignore[arg-type]
    body = {"text": "look around", "client_msg_id": "lost1"}
    t0 = time.monotonic()
    r = world.client.post(f"/campaigns/{world.cid}/actions", json=body, headers=world.h)
    ev = parse_sse(r.text)
    assert names(ev) == ["status", "error"] and ev[1][1]["code"] == "lost_thread"
    assert time.monotonic() - t0 < 1.4  # the stalled model thread was abandoned
    assert event_types(world.cid).count("action") == 1 and "dm_reply" in event_types(world.cid)
    state = world.client.get(f"/campaigns/{world.cid}", headers=world.h).json()
    assert state["turn_count"] == 0  # nothing was committed
    time.sleep(1.6)  # let the abandoned thread finish; it must not write anything
    assert event_types(world.cid).count("dm_reply") == 1
    # Try again: same client_msg_id, a healthy model; the action is not logged twice
    set_narration(AgentNarration(get_node_llm({})))
    _, done = post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h, body)
    assert done["text"] and event_types(world.cid).count("action") == 1
    assert world.client.get(f"/campaigns/{world.cid}", headers=world.h).json()["turn_count"] == 1


def test_hint_spends_focus_only_when_a_hint_exists(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(turns, "TURN_BUDGET_S", 0.3)
    set_narration(AgentNarration(StalledLLM(1.0)))  # type: ignore[arg-type]
    r = world.client.post(f"/campaigns/{world.cid}/focus/hint", headers=world.h)
    assert parse_sse(r.text)[-1][0] == "error"
    assert world.client.get(f"/campaigns/{world.cid}", headers=world.h).json()["focus_left"] == 3
    time.sleep(1.1)
    set_narration(AgentNarration(get_node_llm({})))
    _, done = post_sse(world.client, f"/campaigns/{world.cid}/focus/hint", world.h)
    assert done["focus_left"] == 2 and done["turn_count"] == 0 and done["text"].endswith("?")


def test_opening_sse_replays_and_falls_back_to_the_prepared_setup(client: TestClient, enron: str) -> None:  # noqa: F811
    h = new_player(client)
    cid = client.post("/campaigns", json={"interests": ["x"]}, headers=h).json()["id"]
    nar, _ = scripted({"campaign_setup": [RuntimeError("model down")]})
    set_narration(nar)
    ev, done = post_sse(client, f"/campaigns/{cid}/opening", h)
    assert names(ev)[0] == "status" and names(ev)[-1] == "done" and done["degraded"]
    assert done["opening_done"] if "opening_done" in done else done["phase"] == "play"
    assert "CommerzBuddy" in done["text"] and "Library" in done["text"] and len(done["suggestions"]) == 3
    again = post_sse(client, f"/campaigns/{cid}/opening", h)[1]
    assert again["text"] == done["text"] and again["replayed"]


def test_actions_are_refused_before_streaming_in_the_wrong_phase(client: TestClient, enron: str) -> None:  # noqa: F811
    h = new_player(client)
    cid = client.post("/campaigns", json={"interests": ["x"]}, headers=h).json()["id"]
    r = client.post(f"/campaigns/{cid}/actions", json={"text": "hello"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "wrong_phase"
    assert client.post(f"/campaigns/{cid}/narrate-roll", json={"roll_id": str(uuid.uuid4())}, headers=h).status_code == 404


def test_debrief_sse_streams_parts_and_replays(client: TestClient, enron: str) -> None:  # noqa: F811
    from test_campaign_api import COMMIT, play_to_decide

    h = new_player(client)
    cid, _ = start(client, h)
    play_to_decide(client, h, cid)
    client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    client.get(f"/campaigns/{cid}/reveal", headers=h)
    ev, done = post_sse(client, f"/campaigns/{cid}/debrief", h)
    assert names(ev)[0] == "status" and names(ev)[-1] == "done"
    assert done["sound_reasoning"] and done["overlooked"] and done["luck"]
    assert done["reflection_question"].endswith("?") and done["forecast_line"].startswith("You said 30%")
    assert [r["key"] for r in done["whatif"]] == ["dont_invest", "first", "all", "yours"]
    assert done["text"] and done["audio_text_id"] and "Enron" not in done["text"]
    again = post_sse(client, f"/campaigns/{cid}/debrief", h)[1]
    assert again["text"] == done["text"]
    assert client.get(f"/campaigns/{cid}", headers=h).json()["phase"] == "debrief"


def test_leaked_state_never_reaches_a_model(world: SimpleNamespace) -> None:
    """Property of the whole path: what the scripted model received contains no leak term, no
    later-checkpoint evidence and no price after story today."""
    llm = FakeNodeLLM({}, default=get_node_llm({}))
    set_narration(AgentNarration(llm))
    for t in ("look around", "what is the price", "ask Elian Voss"):
        post_sse(world.client, f"/campaigns/{world.cid}/actions", world.h, {"text": t, "client_msg_id": t[:6]})
    post_sse(world.client, f"/campaigns/{world.cid}/buddy", world.h, {"text": "what is a drawdown?"})
    ctx = world.ctx()
    seen = json.dumps([[getattr(b, "content", b) for b in c.messages] for c in llm.calls])
    for term in ctx.pack.leak_terms:
        if len(term) > 5:
            assert term not in seen, term
    assert "Heavy Loss" not in seen and "F-Q3-" not in seen


