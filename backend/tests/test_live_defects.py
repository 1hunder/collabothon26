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
