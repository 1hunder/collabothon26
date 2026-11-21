"""@spec: 003-campaign-engine (QA fixes: arrival figures, named characters, whole-word quotes)"""

from __future__ import annotations

import re
from types import SimpleNamespace

from test_campaign_agents import _fast_sse, go, world  # noqa: F401
from test_campaign_api import enron  # noqa: F401

from financequest.agents.campaign.fake import first_sentences
from financequest.agents.campaign.narration import AgentNarration, heuristic_xp
from financequest.campaign.xp import excerpt, quote_in, rubric_for, validate_scores
from financequest.llm import get_node_llm


def _nar() -> AgentNarration:
    return AgentNarration(get_node_llm({}))


def test_library_arrival_keeps_the_figure_in_the_clause(world: SimpleNamespace) -> None:  # noqa: F811
    reply = _nar().turn(world.ctx(), "Go to the Library")
    assert not reply.degraded
    assert "net owners' claim stood at" in reply.text
    assert re.search(r"net owners' claim stood at \d", reply.text), reply.text
    assert not re.search(r"claim\.\s*$|claim\. ", reply.text)  # no dangling clause


def test_first_sentences_cuts_at_a_clause_boundary_never_mid_clause() -> None:
    text = (
        "The guild held 10 in coin, owed 20 due soon and 30 due later, "
        "and its net claim stood at 93."
    )
    assert first_sentences(text, 1, 40) == text
    short = first_sentences(text, 1, 14)
    assert short.endswith(".") and short.count(",") >= 1 and "claim" not in short


def test_ask_ren_tal_at_market_square_is_answered_by_ren_tal(world: SimpleNamespace) -> None:  # noqa: F811
    first = _nar().turn(world.ctx(), "Go to the Market Square")
    assert any(s.startswith("Ask Ren Tal") for s in first.suggestions), first.suggestions
    go(world, "market_square")
    ctx = world.ctx()
    reply = _nar().turn(ctx, "Ask Ren Tal what the traders think of the guild")
    assert reply.intent == "talk" and reply.speaker == "Ren Tal"
    assert "not here" not in reply.text


def test_excerpt_is_whole_words_with_ellipsis_and_checks_as_substring() -> None:
    src = "I would only risk a part of the budget because the ledgers disagree about cash."
    q = excerpt(src, 30)
    assert (
        q.endswith("…")
        and not q.startswith("only risk a pa")
        and q[:-1].strip().split()[-1] in src.split()
    )
    assert quote_in(q, src) and not quote_in("invented words…", src)
    assert excerpt("Short one.", 80) == "Short one."
    rubric = rubric_for(None)
    cats, _ = validate_scores(
        rubric, heuristic_xp(rubric, {"evidence": src, "reflection": src}), src
    )
    assert all(c["quote"].endswith("…") for c in cats)  # kept, not wiped by the quote check


def test_fake_xp_rationales_differ_per_category() -> None:
    rubric = rubric_for(None)
    out = _nar().xp(
        rubric,
        {"evidence": "I compared two ledgers " * 5, "reflection": "I will check cash first. " * 5},
    )
    assert len({s.rationale for s in out}) == len(out)
