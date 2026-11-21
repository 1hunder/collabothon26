"""No internal identifiers in player-facing text; every figure a model sees is a whole number."""

from __future__ import annotations

import re
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from test_campaign_agents import GOOD, _fast_sse, run_turn, scripted, world  # noqa: F401
from test_campaign_api import enron  # noqa: F401

from financequest.agents.campaign import context as C
from financequest.agents.campaign import guards as G
from financequest.agents.campaign import schemas as S

SNAKE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")


@pytest.mark.parametrize(
    "bad",
    [
        "The price board shows a change_pct of -5.9 from first close to last close.",
        "Read F-CEO-RESIGN-001 again. What now?",
        "The hp_eur field is low.",
        "Look at storyDay carefully.",
    ],
)
def test_ident_guard_rejects_identifiers(bad: str) -> None:
    assert G.ident_violations(bad) == [G.IDENT_NOTE]
    rules = G.GuardRules(allowed={str(i) for i in range(100)})
    assert G.IDENT_NOTE in rules.static_violations({"text": bad})


@pytest.mark.parametrize(
    "fine",
    [
        "The price fell about 6 percent over the period shown. What do you make of it?",
        "E-mail the broker; the T-shirt stall is closed, said McDonald.",
    ],
)
def test_ident_guard_allows_plain_words(fine: str) -> None:
    assert G.ident_violations(fine) == []


def test_identifier_triggers_retry_then_template(world: SimpleNamespace) -> None:  # noqa: F811
    free = {"campaign_route": [S.RouteOut(intent="free")]}
    bad = S.TurnOut(text="Note the change_pct here. What now?", suggestions=["a", "b", "c"])
    nar, llm = scripted({**free, "campaign_turn": [bad, GOOD]})
    assert run_turn(world, nar, "look").text == GOOD.text
    assert len(llm.calls_for("campaign_turn")) == 2
    nar, llm = scripted({**free, "campaign_turn": [bad]})
    reply = run_turn(world, nar, "look")
    assert reply.text == G.SAFE_FALLBACK and reply.degraded
    assert len(llm.calls_for("campaign_turn")) == 2


def test_guard_log_line_reports_ident() -> None:
    from financequest.agents.campaign.graphs import guard_results

    assert guard_results([G.IDENT_NOTE])["ident"] == "fail"
    assert guard_results([])["ident"] == "pass"


def test_whole_rounds_half_up() -> None:
    assert [G.whole(x) for x in ("607.51", Decimal("-5.9"), 0.5, "1,234.4", 12)] == [
        "608", "-6", "1", "1234", "12"]  # fmt: skip


def test_context_uses_labels_and_whole_numbers(world: SimpleNamespace) -> None:  # noqa: F811
    ctx = world.ctx(screen="market_square")
    summ = C.chart_summary(ctx.content)
    assert summ and all("." not in str(v) for v in summ.values())
    sentence = C.summary_sentence(summ)
    assert "change over the period shown" in sentence or int(summ["change_pct"]) == 0
    prefix = C.stable_prefix(ctx)
    body = str(C.build_messages(ctx, "role", "hi")[1].content)
    for blob in (sentence, prefix, body):
        assert not SNAKE.search(sentence) and "change_pct" not in blob
        assert "first_close" not in blob and "last_close" not in blob and "hp_eur" not in blob
    # price board rows carry no decimals
    for line in prefix.splitlines():
        if line.startswith("- day "):
            assert "." not in line, line


def test_outcome_rendering_is_plain_and_whole() -> None:
    text = C.render_outcome({
        "action": "buy", "amount_eur": 300, "budget": 1000, "cash": "700.00", "invested": "300.00",
        "value_now": "607.51", "final": "1307.51", "pnl": "307.51", "pnl_pct": "-39.2",
        "hp_before": 100, "hp_after": 61,
    })  # fmt: skip
    assert "608 gold pieces" in text and "1308 gold pieces" in text and "39 percent" in text
    assert not SNAKE.search(text) and not re.search(r"\d\.\d", text)


def test_prompts_forbid_identifiers_and_ask_for_whole_numbers() -> None:
    from financequest.agents.campaign import prompts
    from financequest.agents.veteran import prompts as vp

    for p in (prompts.CAMPAIGN_MASTER, prompts.BUDDY, prompts.NPC, vp.VETERAN):
        assert "snake_case" in p and "whole number" in p


def test_scripted_buddy_board_text_is_whole(world: SimpleNamespace) -> None:  # noqa: F811
    ctx = world.ctx(screen="market_square")
    assert ctx.screen and ctx.screen["summary"]
    s: dict[str, Any] = ctx.screen["summary"]
    assert re.fullmatch(r"-?\d+", s["first_close"]) and re.fullmatch(r"-?\d+", s["change_pct"])


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Earnings were 6.7, of which 6 recurring.", "Earnings were 7, of which 6 recurring."),
        ("A close of 3188.139 on day 0.", "A close of 3188 on day 0."),
        ("The guild held 6.9.", "The guild held 7."),
        ("Halves round up: 2.5 and 1,234.5 gp.", "Halves round up: 3 and 1,235 gp."),
        (
            "Keys and dates stay: F-1.2, v2.0, 2001.05.12.",
            "Keys and dates stay: F-1.2, v2.0, 2001.05.12.",
        ),
        ("No decimals here: 1,000 gold pieces.", "No decimals here: 1,000 gold pieces."),
    ],
)
def test_round_decimals(text: str, want: str) -> None:
    assert G.round_decimals(text) == want


def test_agent_output_is_rounded_but_quotes_and_keys_stay_exact() -> None:
    turn = S.TurnOut(text="Earnings of 6.7 beside a drain of 11.4. What now?", hp_reason="lost 2.5")
    out = G.whole_numbers(turn)
    assert out.text == "Earnings of 7 beside a drain of 11. What now?"
    assert out.hp_reason == "lost 3"
    xp = S.XpOut.model_validate(
        {
            "scores": [
                {
                    "category": "Evidence",
                    "score": 3,
                    "rationale": "You cited 6.7.",
                    "quote": "earnings of 6.7",
                }
            ]
        }  # fmt: skip
    )
    got = G.whole_numbers(xp).scores[0]
    assert (got.rationale, got.quote) == ("You cited 7.", "earnings of 6.7")


def test_rounded_figures_pass_the_number_guard() -> None:
    allowed = G.build_allowlist(["earnings of 6.7, a loss of 2.5"], [])
    assert G.number_violations(G.round_decimals("earnings of 6.7, a loss of 2.5"), allowed) == []
