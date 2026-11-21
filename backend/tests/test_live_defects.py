# ruff: noqa: E501
"""@spec: 003-campaign-engine. Defects found in the live Enron run (D4 to D8)."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from test_campaign_agents import (  # noqa: F401
    GOOD,
    _fast_sse,
    bad_turn,
    go,
    run_turn,
    scripted,
    world,
)
from test_campaign_api import enron  # noqa: F401

from financequest.agents.campaign import guards as G
from financequest.agents.campaign import schemas as S

FREE = {"campaign_route": [S.RouteOut(intent="free")]}


# ---- D4: guard results are observable --------------------------------------------------------
def test_d4_one_structured_log_line_per_guarded_call(
    world: SimpleNamespace, caplog: pytest.LogCaptureFixture  # noqa: F811
) -> None:
    nar, _ = scripted({**FREE, "campaign_turn": [bad_turn("It was Enron, a sure thing. What now?"), GOOD]})
    with caplog.at_level(logging.INFO, logger="financequest.agents"):
        run_turn(world, nar, "look")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("guarded ")]
    assert len(lines) == 1
    rec = json.loads(lines[0].removeprefix("guarded "))
    assert rec["graph"] == "campaign_turn" and rec["retry"] is True and rec["fallback"] is False
    first, second = rec["trail"]
    assert first["leak"] == "fail" and first["number"] == "pass" and first["attempt"] == 1
    assert second["leak"] == "pass" and second["advice"] == "pass" and second["word_cap"] == "pass"
    assert isinstance(rec["ms"], int)
    assert "Enron" not in lines[0] and "sure thing" not in lines[0]


def test_d4_fallback_is_logged(world: SimpleNamespace, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    nar, _ = scripted({**FREE, "campaign_turn": [bad_turn("It was Enron. What now?")]})
    with caplog.at_level(logging.INFO, logger="financequest.agents"):
        run_turn(world, nar, "look")
    rec = json.loads(next(r.getMessage() for r in caplog.records if r.getMessage().startswith("guarded "))[8:])
    assert rec["fallback"] is True and rec["attempts"] == 2


# ---- D5: voice -------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [
    "The engine rolls the dice for you. What would you do?",
    "You roll well and the page opens. What would you do?",
    "The hero opens the ledger. What would you do?",
])
def test_d5_mechanics_and_third_person_are_rejected_with_a_retry(world: SimpleNamespace, bad: str) -> None:  # noqa: F811
    nar, llm = scripted({**FREE, "campaign_turn": [bad_turn(bad), GOOD]})
    reply = run_turn(world, nar, "look")
    assert reply.text == GOOD.text and len(llm.calls_for("campaign_turn")) == 2


def test_d5_hero_name_in_third_person_is_rejected(world: SimpleNamespace) -> None:  # noqa: F811
    name = world.ctx().hero_name
    assert G.voice_violations(f"{name} opens the ledger.", name)
    assert not G.voice_violations("You open the ledger.", name)
    nar, llm = scripted({**FREE, "campaign_turn": [bad_turn(f"{name} opens the ledger. What now?"), GOOD]})
    assert run_turn(world, nar, "look").text == GOOD.text


def test_d5_promised_check_gets_a_dice_card_in_the_same_turn(world: SimpleNamespace) -> None:  # noqa: F811
    go(world, "library")
    promised = bad_turn("Let's see if you can spot the pattern in the figures. What would you do?")
    nar, _ = scripted({**FREE, "campaign_turn": [promised]})
    reply = run_turn(world, nar, "look closer at the numbers")
    assert reply.intent == "challenge" and reply.challenge_id  # the card follows with the text


def test_d5_promised_check_with_no_challenge_here_is_retried(world: SimpleNamespace) -> None:  # noqa: F811
    promised = bad_turn("A test of your wits awaits. What would you do?")
    nar, llm = scripted({**FREE, "campaign_turn": [promised, GOOD]})
    reply = run_turn(world, nar, "look")  # the Tavern has no open challenge
    assert reply.intent != "challenge" and reply.text == GOOD.text


def test_d5_prompts_ban_mechanics() -> None:
    from financequest.agents.campaign import prompts

    for p in (prompts.CAMPAIGN_MASTER, prompts.DICE, prompts.BUDDY):
        assert "Never mention" in p and "dice" in p


# ---- D6: the hint carries 3 suggestions --------------------------------------------------------
def test_d6_focus_hint_returns_three_suggestions(world: SimpleNamespace) -> None:  # noqa: F811
    from sse_helpers import post_sse

    _, done = post_sse(world.client, f"/campaigns/{world.cid}/focus/hint", world.h)
    assert len(done["suggestions"]) == 3 and all(s.strip() for s in done["suggestions"])


# ---- D7: XP feedback ----------------------------------------------------------------------------
def test_d7_xp_feedback_is_second_person() -> None:
    from financequest.campaign.xp import RawScore, to_second_person, validate_scores

    assert to_second_person("The player cites the ledger.") == "You cite the ledger."
    assert to_second_person("The player's forecast is clear.") == "Your forecast is clear."
    assert to_second_person("The player has no plan.") == "You have no plan."
    cats, _ = validate_scores(
        (("Evidence literacy", 25),),
        [RawScore("Evidence literacy", 20, "The player cites the cash figures.", "")], "x",
    )
    assert cats[0]["rationale"] == "You cite the cash figures."


def test_d7_forecast_clarity_uses_the_committed_forecast_pct() -> None:
    from financequest.agents.campaign.narration import AgentNarration
    from financequest.llm import get_node_llm

    rubric = (("Forecast clarity", 15),)
    decision = {"action": "invest", "amount_eur": 300, "forecast_pct": 40, "confidence": "medium"}
    texts = {"evidence": "I read the cash flow ledger twice.", "reflection": "Next time cash first."}
    # the evaluator sees the committed forecast
    llm = get_node_llm({"campaign_xp": [S.XpOut(scores=[S.XpScore(category="Forecast clarity", score=12, rationale="You committed to a number.")])]})
    AgentNarration(llm).xp(rubric, texts, decision)  # type: ignore[arg-type]
    seen = " ".join(str(m.content) for m in llm.calls_for("campaign_xp")[0].messages)  # type: ignore[attr-defined]
    assert "forecast 40%" in seen and "medium" in seen
    # the degraded scorer names it too, never "no explicit probability"
    out = AgentNarration(get_node_llm({"campaign_xp": [RuntimeError("down")]})).xp(rubric, texts, decision)  # type: ignore[arg-type]
    assert "40%" in out[0].rationale and "no explicit" not in out[0].rationale.lower()
    assert out[0].score == 15


def test_d7_xp_prompt_demands_second_person_and_uses_forecast() -> None:
    from financequest.agents.campaign import prompts

    assert "second person" in prompts.XP and "Forecast clarity" in prompts.XP


def test_d7_shown_horizon_and_time_skip_use_the_same_story_days(client, enron) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    from sse_helpers import post_sse
    from test_campaign_api import new_player, start

    h = new_player(client)
    cid, state = start(client, h)
    first_day = state["story_day"]
    seen: dict[str, Any] = {}
    for i in range(12):  # keep acting until the news fires
        ev, _ = post_sse(client, f"/campaigns/{cid}/actions", h, {"text": f"look around {i}"})
        news = next((c for n, c in ev if n == "card" and c["kind"] == "news"), None)
        if news:
            seen = news
            break
    assert seen, "the news card never fired"
    after = client.get(f"/campaigns/{cid}", headers=h).json()
    skip = int(seen["time_skip_label"].split()[0])
    assert skip == after["story_day"] - first_day  # the label is the clock's own jump
    assert f"{after['scenario']['horizon_label']}".startswith("about ")


# ---- D8: every campaign location has someone to talk to ------------------------------------------
def test_d8_every_campaign_location_has_a_character(world: SimpleNamespace) -> None:  # noqa: F811
    ctx = world.ctx()
    seeds = [s["key"] for s in ctx.pack.seeds]
    assert "exchange_steps" in seeds
    for key in seeds:
        here = [c for c in ctx.pack.characters if c.location.removeprefix("campaign:") == key]
        assert here, f"nobody at {key}"
    local = next(c for c in ctx.pack.characters if c.location.endswith("exchange_steps"))
    evid = {e.id for e in ctx.pack.evidence if e.location.removeprefix("campaign:") == "exchange_steps"}
    assert {i for ids in local.may_reveal.values() for i in ids} <= evid  # only what is already there
    assert "Enron" not in local.name + local.role


def test_d8_arrival_names_who_is_there_and_offers_to_ask(world: SimpleNamespace) -> None:  # noqa: F811
    from sse_helpers import post_sse
    from test_campaign_api import loc_id

    state = world.client.get(f"/campaigns/{world.cid}", headers=world.h).json()
    local = next(c for c in world.ctx().pack.characters if c.location.endswith("exchange_steps"))
    _, done = post_sse(world.client, f"/campaigns/{world.cid}/move", world.h,
                       {"location_id": loc_id(state, "exchange_steps")})  # fmt: skip
    assert local.name in done["text"]
    assert any(s.startswith(f"Ask {local.name}") for s in done["suggestions"])
