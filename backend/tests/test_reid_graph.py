"""Gate and intake graph tests with a scripted fake model (no network).

@spec: 002-anonymization-reid-gate
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from financequest.llm import FakeNodeLLM, FakeRefusal, FakeReply, get_node_llm
from financequest.reid.graph import (
    parse_web_blocks,
    run_gate,
    run_intake,
    split_case_chunks,
)
from financequest.reid.schemas import CaseAmount, CaseBeat, GateCase

REAL = "Zephyr Aerospace"
TICKER = "ZAEX"
TERM = "Skyline Nine"


def make_case() -> GateCase:
    series = [(d, 100.0 + (d % 50) + d / 10) for d in range(0, 301)]
    return GateCase(
        case_id="zae-001",
        company=REAL,
        ticker=TICKER,
        identifying_terms=[TERM],
        industry="Aircraft manufacturing",
        lesson="Concentrated product risk hits cash flow.",
        real_start=(2019, 3),
        beats=[
            CaseBeat(real_day=10, headline=f"{REAL} ships {TERM}", facts=["Revenue was {A1}."]),
            CaseBeat(real_day=100, headline=f"{TERM} grounded", facts=["Cash fell to {A2}."]),
            CaseBeat(real_day=200, headline="Recovery plan", facts=["Debt stood at {A3}."]),
        ],
        series=series,
        amounts=[
            CaseAmount(token="{A1}", family="revenue", value=Decimal("5100")),
            CaseAmount(token="{A2}", family="cash", value=Decimal("900")),
            CaseAmount(token="{A3}", family="debt", value=Decimal("2300")),
        ],
    )


def draft(**over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "company_name": "Lantern Works",
        "sector": "Industrials",
        "industry": "Lantern making",
        "industry_moved": True,
        "transplant_note": "Moved to a similar industry.",
        "beats": [
            {
                "story_day_index": 0,
                "headline": "Lantern Works launches a lamp",
                "facts": ["Revenue was {A1}."],
            },
            {"story_day_index": 1, "headline": "Lamp recalled", "facts": ["Cash fell to {A2}."]},
            {
                "story_day_index": 2,
                "headline": "A plan to recover",
                "facts": ["Debt stood at {A3}."],
            },
        ],
        "changes_vs_previous": [],
    }
    d.update(over)
    return d


def report(
    *companies: str,
    year: int = 2005,
    conf: int = 10,
    read: int = 4,
    clues: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    names = (list(companies) + ["Other One", "Other Two", "Other Three"])[:3]
    return {
        "top3": [{"company": n, "ticker": "", "confidence": 20} for n in names],
        "start_month": 1,
        "start_year": year,
        "start_confidence": conf,
        "clues": clues or [],
        "readability": read,
        "readability_issues": [],
    }


MISS = report("Acme Holdings")
HIT = report(
    "Zephyr Aerospace",
    clues=[
        {
            "category": "event_order",
            "text": "Looks like Zephyr Aerospace and Skyline Nine grounding, then a cash squeeze",
        }
    ],
)


def make_llm(**scripts: list[Any]) -> FakeNodeLLM:
    base: dict[str, list[Any]] = {
        "write_disguise": [draft()],
        "guess_memory": [MISS],
        "guess_web": [MISS],
    }
    base.update({k.replace("__", ":"): v for k, v in scripts.items()})
    return FakeNodeLLM(base)


def test_pass_on_first_attempt() -> None:
    llm = make_llm()
    out = run_gate(make_case(), llm=llm)
    assert out["status"] == "approved"
    assert len(out["attempts"]) == 1 and out["attempts"][0].verdict == "passed"
    assert len(llm.calls_for("guess_memory")) == 3
    web = llm.calls_for("guess_web")
    assert len(web) == 3 and all(c.web_search_max_uses == 12 and c.effort == "high" for c in web)
    assert {c.persona for c in web} == {"generalist", "forensic", "industry"}
    assert llm.calls_for("write_disguise")[0].effort == "medium"
    tel = out["telemetry"]
    assert {t["node"] for t in tel} == {"write_disguise", "guess_memory", "guess_web"}
    assert all("latency_s" in t and "stop_reason" in t and "cache_read_tokens" in t for t in tel)
    # amounts filled by code from the plan, within the display cap
    scn = out["attempts"][0].scenario
    assert scn is not None and "{A" not in " ".join(f for b in scn.beats for f in b.facts)


def test_fail_then_pass_rewrites_from_clues() -> None:
    llm = make_llm(guess_memory__generalist=[HIT, MISS])
    out = run_gate(make_case(), llm=llm)
    assert out["status"] == "approved"
    assert [a.verdict for a in out["attempts"]] == ["failed", "passed"]
    assert out["attempts"][0].fail_reason == "recognised_name"
    assert len(llm.calls_for("guess_web")) == 3  # only attempt 2 reached the web round
    assert "REWRITE" in str(llm.calls_for("write_disguise")[1].messages[1].content)


def test_three_fails_is_rejected_and_web_skipped() -> None:
    llm = make_llm(guess_memory__generalist=[HIT])
    out = run_gate(make_case(), llm=llm)
    assert out["status"] == "rejected"
    assert len(out["attempts"]) == 3
    assert llm.calls_for("guess_web") == []


def test_scan_fail_short_circuits_guessers() -> None:
    bad = draft(
        beats=[
            {
                "story_day_index": 0,
                "headline": "Lantern Works rose in 2019",
                "facts": ["Revenue was {A1}."],
            },
            *draft()["beats"][1:],
        ]
    )
    llm = make_llm(write_disguise=[bad, draft()])
    out = run_gate(make_case(), llm=llm)
    first = out["attempts"][0]
    assert first.verdict == "failed" and first.fail_reason == "real_date_found"
    assert first.guesses == []
    assert out["status"] == "approved"
    assert len(llm.calls_for("guess_memory")) == 3  # attempt 2 only


def test_refusal_is_retried_once_then_error() -> None:
    llm = make_llm(guess_memory__forensic=[FakeRefusal()])
    out = run_gate(make_case(), llm=llm)
    assert out["status"] == "error"
    assert out["attempts"][0].fail_reason == "error"
    forensic = [c for c in llm.calls_for("guess_memory") if c.persona == "forensic"]
    assert [c.fallback for c in forensic] == [False, True]
    assert llm.calls_for("guess_web") == []
    errs = [r for r in out["attempts"][0].guesses if r.error]
    assert errs and errs[0].error == "refusal"


def test_rewrite_prompt_never_contains_real_company() -> None:
    llm = make_llm(guess_memory__generalist=[HIT])
    run_gate(make_case(), llm=llm)
    writes = llm.calls_for("write_disguise")
    assert len(writes) == 3
    for call in writes:  # first attempt and rewrites alike
        text = " ".join(str(m.content) for m in call.messages).casefold()
        for secret in (REAL, TICKER, TERM, "zephyr"):
            assert secret.casefold() not in text
    assert "[a company]" in str(writes[1].messages[1].content)  # clue was redacted, not dropped


def test_guessers_never_see_the_case() -> None:
    llm = make_llm()
    run_gate(make_case(), llm=llm)
    for call in [*llm.calls_for("guess_memory"), *llm.calls_for("guess_web")]:
        text = " ".join(str(m.content) for m in call.messages).casefold()
        assert REAL.casefold() not in text and TICKER.casefold() not in text
        assert "aircraft" not in text and "factor" in text  # rules described, factors hidden


WEB_BLOCKS: list[dict[str, Any]] = [
    {"type": "text", "text": "Let me look this up."},
    {
        "type": "server_tool_use",
        "id": "s1",
        "name": "web_search",
        "input": {"query": "lantern maker recall grounding cash squeeze"},
    },
    {
        "type": "web_search_tool_result",
        "tool_use_id": "s1",
        "content": [
            {"type": "web_search_result", "url": "https://example.org/a", "title": "A"},
            {"type": "web_search_result", "url": "https://example.org/b", "title": "B"},
        ],
    },
    {
        "type": "server_tool_use",
        "id": "s2",
        "name": "web_search",
        "input": {"query": "lamp recall debt"},
    },
    {
        "type": "web_search_tool_result",
        "tool_use_id": "s2",
        "content": [{"type": "web_search_result", "url": "https://example.org/a", "title": "A"}],
    },
    {
        "type": "text",
        "text": "Done.\n```json\n" + __import__("json").dumps(MISS) + "\n```",
        "citations": [
            {"type": "web_search_result_location", "url": "https://example.org/c", "title": "C"}
        ],
    },
]


def test_web_blocks_parse_into_queries_citations_and_searches() -> None:
    trace = parse_web_blocks(WEB_BLOCKS, usage_searches=2)
    assert trace.queries == ["lantern maker recall grounding cash squeeze", "lamp recall debt"]
    assert [c["url"] for c in trace.citations] == [
        "https://example.org/a",
        "https://example.org/b",
        "https://example.org/c",
    ]
    assert trace.searches_used == 2 and not trace.usage_mismatch
    assert parse_web_blocks(WEB_BLOCKS, usage_searches=3).usage_mismatch


def test_replayed_web_reply_is_recorded_on_the_guess() -> None:
    reply = FakeReply(content=WEB_BLOCKS, usage={"web_search_requests": 2, "input_tokens": 9})
    out = run_gate(make_case(), llm=make_llm(guess_web=[reply]))
    assert out["status"] == "approved"
    rec = [g for g in out["attempts"][0].guesses if g.round == "web"][0]
    assert rec.searches_used == 2 and len(rec.queries) == 2 and len(rec.citations) == 3
    assert rec.report is not None and rec.report.top3[0].company == "Acme Holdings"
    assert any(t.get("web_searches") == 2 for t in out["telemetry"])


def test_fake_llm_default_runs_whole_graph_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from financequest.config import get_settings

    monkeypatch.setenv("FAKE_LLM", "1")
    get_settings.cache_clear()
    try:
        out = run_gate(make_case(), llm=get_node_llm())
    finally:
        monkeypatch.delenv("FAKE_LLM")
        get_settings.cache_clear()
    assert out["status"] == "approved"


COLLECTION = """# Collection

## Alpha Corp
Lesson: diversify. Stuff happened.

## Beta Inc
More text.
### sub heading
still Beta.

## Gamma
x
"""


def test_split_cases_one_chunk_per_heading() -> None:
    chunks = split_case_chunks(COLLECTION)
    assert [c.title for c in chunks] == ["Alpha Corp", "Beta Inc", "Gamma"]
    assert "still Beta" in chunks[1].body and "Beta" not in chunks[0].body


def test_intake_extracts_and_applies_skip_rules() -> None:
    good = {
        "company": "Alpha Corp",
        "lesson": "Diversify.",
        "identifying_terms": ["Alpha"],
        "country": "US",
        "story_year": 2019,
        "market_cap_eur": 5e9,
        "is_us_listed": True,
        "beats": [{"real_date": "x", "headline": "h", "facts": []}] * 3,
    }
    thin = {**good, "lesson": None}
    llm = FakeNodeLLM({"extract_case": [good, thin, FakeRefusal()]})
    res = run_intake(COLLECTION, llm=llm)
    assert [r.title for r in res] == ["Alpha Corp", "Beta Inc", "Gamma"]
    # parallel fan-out consumes scripted replies in arrival order, so compare as a multiset
    assert sorted(r.status for r in res) == ["error", "ok", "skipped"]
    assert all(c.effort == "low" for c in llm.calls_for("extract_case"))
