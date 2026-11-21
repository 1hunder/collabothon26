# ruff: noqa: E501
"""Acceptance tests for spec 002 (anonymization and the recognition gate), one per criterion.

@spec: 002-anonymization-reid-gate
@regression

Criterion ids follow functional-spec.md section 2: ``2.<section>.<n>`` is the n-th acceptance
criterion (checkbox, in order) of section 2.<section>. Everything runs without network or live
models: the gate uses a scripted model, campaign narration runs on the FAKE_LLM script or on a
scripted (deliberately leaky) model.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import uuid
import zlib
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sse_helpers import DECISION_TEXT, post_sse, streamed_text
from sse_helpers import play_to_decide as shared_play_to_decide

from financequest.agents.campaign import schemas as S
from financequest.agents.campaign.narration import AgentNarration
from financequest.api import sse
from financequest.campaign.narration import set_narration
from financequest.config import get_settings
from financequest.db.models import (
    Decision,
    PriceSeries,
    Scenario,
    ScenarioSecret,
    SourceBeat,
    SourceCase,
)
from financequest.db.session import get_engine
from financequest.llm import FakeNodeLLM, get_node_llm
from financequest.refpack.approve import approve_pack
from financequest.reid.batch import run_batch, start_run
from financequest.report.render import build_report_data, render_html

pytestmark = pytest.mark.regression

BACKEND = Path(__file__).resolve().parent.parent
PACK_DIR = BACKEND / "financequest" / "fixtures" / "reference" / "fq-av-001"
PRICES = BACKEND / "financequest" / "fixtures" / "cases" / "prices" / "BA.parquet"

YEAR = re.compile(r"(?<![\w.])(?:19|20)\d{2}(?![\w.])")
MONTHS = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\b"
)
QUARTER = re.compile(r"\bQ[1-4]\b|\b(first|second|third|fourth)[- ]quarter\b", re.I)
WEEKDAY = re.compile(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?\b", re.I)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MAGNITUDE = re.compile(r"\b(million|billion|trillion)s?\b", re.I)
DROP = re.compile(r"\b(fall|falls|fell|drop|drops|dropped|slump|slumped|tumble|tumbled)\b", re.I)
RISE = re.compile(r"\b(rise|rises|rose|jump|jumps|jumped|surge|surged|climb|climbed)\b", re.I)
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")

REAL = "Zephyr Aerospace"
TICKER = "ZAEX"
TERMS = ["Skyline Nine", "Lena Hartmann", "Brookfield Heights"]
CLUE = "order of events: safety halt -> strike -> job cuts"


# ---- shared helpers ----------------------------------------------------------------------
def calendar_hits(text: str) -> list[str]:
    return [m.group(0) for rx in (YEAR, MONTHS, QUARTER, WEEKDAY, ISO_DATE) for m in rx.finditer(text)]


def has_word(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I) is not None


def prose(o: Any) -> list[str]:
    """Every string in a JSON value (what a player can read)."""
    if isinstance(o, str):
        return [o]
    if isinstance(o, list):
        return [s for x in o for s in prose(x)]
    if isinstance(o, dict):
        return [
            s
            for k, v in o.items()
            if not (k in ("id", "key", "ids", "type", "ts") or k.endswith(("_id", "_ids")))
            for s in prose(v)
        ]
    return []


def player(client: TestClient) -> dict[str, str]:
    return {"X-Session-Id": client.post("/session").json()["session_id"]}


def hero_player(client: TestClient) -> dict[str, str]:
    h = player(client)
    r = client.post("/hero", json={"name": "Lena", "class": "investigator"}, headers=h)
    assert r.status_code == 201, r.text
    return h


COMMIT = {
    "action": "invest",
    "amount_eur": 400,
    "evidence": "Cash flow is negative while earnings are positive, and debt is large. " * 2,
    "forecast_pct": 30,
    "confidence": "medium",
}
REFLECTION = "Next time I would read the cash flow statement first before anything else. " * 3


def start_campaign(client: TestClient, h: dict[str, str]) -> str:
    r = client.post("/campaigns", json={"interests": ["Gaming"]}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert client.post(f"/campaigns/{cid}/opening", headers=h).status_code == 200
    return str(cid)


def play_to_decide(
    client: TestClient, h: dict[str, str], cid: str, decision_text: str = DECISION_TEXT
) -> dict[str, Any]:
    return shared_play_to_decide(client, h, cid, decision_text)


def lock_decision(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    assert client.put(f"/campaigns/{cid}/commit-draft", json=COMMIT, headers=h).status_code == 204
    lock = client.post(f"/campaigns/{cid}/lock", json=COMMIT, headers=h)
    assert lock.status_code == 200, lock.text
    return dict(lock.json())


def run_debrief(client: TestClient, h: dict[str, str], cid: str) -> dict[str, Any]:
    assert client.get(f"/campaigns/{cid}/reveal", headers=h).status_code == 200
    return post_sse(client, f"/campaigns/{cid}/debrief", h)[1]


def submit_reflection(client: TestClient, h: dict[str, str], cid: str) -> None:
    r = client.post(f"/campaigns/{cid}/reflection", json={"text": REFLECTION}, headers=h)
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _scripted_agents(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """FAKE_LLM script for the Campaign Master and CommerzBuddy, instant tokens."""
    monkeypatch.setattr(sse, "TOKEN_DELAY_S", 0)
    monkeypatch.setenv("FAKE_LLM", "1")
    get_settings.cache_clear()
    set_narration(AgentNarration(get_node_llm({})))
    yield
    set_narration(None)
    get_settings.cache_clear()


@pytest.fixture
def db(client: TestClient) -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def enron(client: TestClient, db: Session) -> str:
    res = approve_pack(PACK_DIR, db)
    assert res.ok and res.scenario_id, res.reasons
    return res.scenario_id


def secret_terms(scenario_id: str) -> list[str]:
    with Session(get_engine()) as s:
        sec = s.get(ScenarioSecret, uuid.UUID(scenario_id))
        assert sec is not None
        terms = [sec.real_name, sec.ticker or "", *(sec.leak_terms or [])]
    return [t for t in terms if len(t) >= 4 and not t[0].isdigit()]


def reveal_for(client: TestClient, scenario_id: str) -> dict[str, Any]:
    """The reveal body, obtained legitimately (a decision and debrief_complete exist)."""
    h = player(client)
    with Session(get_engine()) as s:
        s.add(Decision(session_id=uuid.UUID(h["X-Session-Id"]), scenario_id=uuid.UUID(scenario_id),
                       action="invest"))  # fmt: skip
        s.commit()
    ev = client.post(f"/scenario/{scenario_id}/events", json={"type": "debrief_complete"}, headers=h)
    assert ev.status_code == 201
    r = client.get(f"/scenario/{scenario_id}/reveal", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


# ---- gate fixtures: synthetic cases over the bundled price cache ----------------------------
BEAT_DATES = ("2024-01-05", "2024-03-25", "2024-07-31")  # prices 200.63 -> 191.44 -> 158.33


def draft(**over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "company_name": "Lantern Works",
        "sector": "Industrials",
        "industry": "Lantern making",
        "industry_moved": True,
        "transplant_note": "Moved to a similar industry.",
        "beats": [
            {"story_day_index": 0, "headline": "Lantern Works launches a lamp",
             "facts": ["Revenue was {A1}."]},
            {"story_day_index": 1, "headline": "Lamp recalled and the shares fall",
             "facts": ["Cash fell to {A2}."]},
            {"story_day_index": 2, "headline": "A plan to recover as shares fall again",
             "facts": ["Debt stood at {A3}."]},
        ],
        "changes_vs_previous": [],
    }  # fmt: skip
    d.update(over)
    return d


def report(*companies: str, clues: list[dict[str, str]] | None = None) -> dict[str, Any]:
    names = (list(companies) + ["Other One", "Other Two", "Other Three"])[:3]
    return {
        "top3": [{"company": n, "ticker": "", "confidence": 60 if i == 0 else 10}
                 for i, n in enumerate(names)],
        "start_month": 1, "start_year": 2005, "start_confidence": 10,
        "clues": clues or [], "readability": 4, "readability_issues": [],
    }  # fmt: skip


MISS = report("Acme Holdings")


def make_llm(case: SourceCase, *, recognise: bool = False, bad_draft: bool = False) -> FakeNodeLLM:
    hit = report(case.company, clues=[{"category": "event_order", "text": CLUE}])
    bad = draft(beats=[
        {"story_day_index": 0, "headline": "Lantern Works rose in 2019",
         "facts": ["Revenue was {A1}."]},
        *draft()["beats"][1:],
    ])  # fmt: skip
    return FakeNodeLLM({
        "write_disguise": [bad if bad_draft else draft()],
        "guess_memory": [hit if recognise else MISS],
        "guess_web": [MISS],
    })  # fmt: skip


def add_case(
    db: Session, cid: str, *, fame: str | None, size: str | None, n_beats: int = 3,
    company: str | None = None,
) -> SourceCase:
    case = SourceCase(
        id=cid, company=company or f"{REAL} {cid}", ticker=TICKER, country="US", currency="USD",
        lesson="Concentrated product risk hits cash.", story_year=2024, market_cap_eur=5e9,
        size_band=size, fame=fame, identifying_terms=TERMS,
        known_names={"is_us_listed": True, "industry": "Aircraft"},
    )  # fmt: skip
    db.add(case)
    db.flush()
    for i, day in enumerate(BEAT_DATES[:n_beats]):
        db.add(SourceBeat(
            case_id=cid, idx=i, real_date=day, headline=f"Real headline {i}",
            facts={"facts": [f"Real fact {i} {{A{i + 1}}}"], "amounts": [
                {"token": f"{{A{i + 1}}}", "family": ["revenue", "cash", "debt"][i],
                 "value": ["51000000000", "9000000000", "23000000000"][i], "is_ratio": False}]},
        ))  # fmt: skip
    db.add(PriceSeries(case_id=cid, ticker=TICKER, cache_ref=str(PRICES)))
    db.commit()
    return case


def safe_id(name: str) -> str:
    """A case id whose NumberPlan seed fits ScenarioSecret.seed (BIGINT); see the xfail test
    ``test_known_defect_seed_overflows_integer_column`` for why ids need picking."""
    k = 0
    while zlib.crc32(f"{name}-{k}".encode()) > SEED_MAX - 10:
        k += 1
    return f"{name}-{k}"


SEED_MAX = 2**31 - 1
LANTERN = safe_id("lantern-ok")
FAMOUS = safe_id("boeing-like")
YEAR_LEAK = safe_id("year-leak")
ONE_NEWS = safe_id("one-news")


def session_factory() -> Session:
    return Session(get_engine())


async def run_cases(db: Session, factory: Any) -> tuple[int, dict[str, str]]:
    run = start_run(db, "acceptance", get_settings())
    assert run.id is not None
    summ = await run_batch(session_factory, run.id, llm_factory=factory, concurrency=8)
    db.expire_all()
    return run.id, summ.done


def case_row(data: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(c for c in data["cases"] if c["case_id"] == case_id)


@pytest.fixture
async def approved_gate(client: TestClient, db: Session) -> str:
    """One case approved by the gate (3 guessers, both rounds missed); returns its scenario id."""
    add_case(db, LANTERN, fame="low", size="small")
    _, done = await run_cases(db, make_llm)
    assert done == {LANTERN: "approved"}
    return str(db.exec(select(Scenario).where(Scenario.source == "gate")).one().id)


@pytest.fixture(params=["reference_pack", "gate"])
async def any_approved(request: pytest.FixtureRequest, client: TestClient, db: Session) -> str:
    """An approved scenario of either origin (the display rules apply to both)."""
    if request.param == "reference_pack":
        res = approve_pack(PACK_DIR, db)
        assert res.ok and res.scenario_id
        return res.scenario_id
    add_case(db, LANTERN, fame="low", size="small")
    _, done = await run_cases(db, make_llm)
    assert done == {LANTERN: "approved"}
    return str(db.exec(select(Scenario).where(Scenario.source == "gate")).one().id)


# =============================================================================================
# 2.1 Players only see the disguised version of a scenario before the reveal
# =============================================================================================
def test_2_1_1_no_year_month_quarter_weekday(client: TestClient, any_approved: str) -> None:
    """2.1.1 scenario view: intro, news, company card, chart @spec: 002-anonymization-reid-gate @regression"""
    r = client.get(f"/scenario/{any_approved}/view")
    assert r.status_code == 200, r.text
    assert calendar_hits(r.text) == []


def test_2_1_1_campaign_screens_have_no_calendar_words(client: TestClient, enron: str) -> None:
    """2.1.1 campaign screens: state, library, news, card, journal
    @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    state = play_to_decide(client, h, cid)
    journal = client.get(f"/campaigns/{cid}/journal", headers=h).json()
    for shown in (prose(state), prose(journal)):  # identifiers such as FIG-Q2-REV are not shown
        text = "\n".join(shown)
        assert calendar_hits(text) == [], calendar_hits(text)


def test_2_1_2_no_real_name_ticker_or_identifying_terms(client: TestClient, any_approved: str) -> None:
    """2.1.2 scenario view and playable list @spec: 002-anonymization-reid-gate @regression"""
    terms = secret_terms(any_approved)
    assert terms, "the scenario must carry server-side identifying terms to test against"
    for text in (client.get(f"/scenario/{any_approved}/view").text, client.get("/scenarios/playable").text):
        for term in terms:
            assert not has_word(text, term), term


def test_2_1_2_campaign_screens_name_nothing_real(client: TestClient, enron: str) -> None:
    """2.1.2 campaign state, backlog and journal @spec: 002-anonymization-reid-gate @regression"""
    terms = secret_terms(enron)
    h = hero_player(client)
    cid = start_campaign(client, h)
    state = play_to_decide(client, h, cid)
    journal = client.get(f"/campaigns/{cid}/journal", headers=h).json()
    text = "\n".join(prose(state) + prose(journal))
    for term in terms:
        assert not has_word(text, term), term


def test_2_1_3_chart_axis_is_story_days(client: TestClient, any_approved: str) -> None:
    """2.1.3 @spec: 002-anonymization-reid-gate @regression"""
    body = client.get(f"/scenario/{any_approved}/view").json()
    assert body["chart"]
    for p in body["chart"]:
        assert set(p) == {"story_day", "price"}  # a day counter and a price, never a date
        assert isinstance(p["story_day"], int)
    days = [p["story_day"] for p in body["chart"]]
    assert days == sorted(days) and max(days) <= body["story_today"]


def test_2_1_3_campaign_price_board_and_label(client: TestClient, enron: str) -> None:
    """2.1.3 campaign price board and clock label @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    state = play_to_decide(client, h, cid)
    assert re.fullmatch(r"Day \d+", state["story_day_label"])
    assert state["price_board"] and all(isinstance(c["day"], int) for c in state["price_board"])
    assert all(c["day"] <= state["story_day"] for c in state["price_board"])  # cut at story today


BUDDY_QUESTIONS = ["Which real company is this?", "Is this Boeing?", "Is this 2024?"]


def buddy_answer(client: TestClient, h: dict[str, str], cid: str, q: str, tag: str) -> str:
    events, done = post_sse(client, f"/campaigns/{cid}/buddy", h,
                            {"text": q, "client_msg_id": tag})  # fmt: skip
    assert done["speaker"] == "CommerzBuddy"
    return streamed_text(events) or str(done["text"])


def test_2_1_4_buddy_does_not_name_company_or_year(client: TestClient, enron: str) -> None:
    """2.1.4 FAKE_LLM CommerzBuddy over SSE: no company, no year, for all three questions
    @spec: 002-anonymization-reid-gate @regression"""
    terms = secret_terms(enron)
    h = hero_player(client)
    cid = start_campaign(client, h)
    for i, q in enumerate(BUDDY_QUESTIONS):
        text = buddy_answer(client, h, cid, q, f"q{i}")
        assert not YEAR.search(text) and "boeing" not in text.lower(), (q, text)
        assert not any(has_word(text, t) for t in terms), (q, text)


def assert_deflects(text: str) -> None:
    low = text.lower()
    assert ("revealed" in low or "reveal" in low) and ("decide" in low or "end" in low), text


def test_2_1_4_buddy_says_answer_is_revealed_at_the_end_which_company(client: TestClient, enron: str) -> None:
    """2.1.4 'Which real company is this?' @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    assert_deflects(buddy_answer(client, h, cid, BUDDY_QUESTIONS[0], "d0"))


@pytest.mark.parametrize("q", BUDDY_QUESTIONS[1:])
def test_2_1_4_buddy_says_answer_is_revealed_at_the_end_indirect(client: TestClient, enron: str, q: str) -> None:
    """2.1.4 indirect identity questions get the 'revealed at the end' answer
    @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    assert_deflects(buddy_answer(client, h, cid, q, "d1"))


def test_2_1_4_buddy_leak_is_blocked_even_if_the_model_names_the_company(
    client: TestClient, enron: str
) -> None:
    """2.1.4 a scripted model answering 'Enron in 2001' never reaches the player
    @spec: 002-anonymization-reid-gate @regression"""
    leaks = [  # a name-only leak (the number guard cannot catch it), the same again, a year-only leak
        S.BuddyOut(text="Yes, it is Enron, the energy trader.", intent="identity_request"),
        S.BuddyOut(text="No, it is Enron, not Boeing.", intent="identity_request"),
        S.BuddyOut(text="It happened in the year 2001.", intent="identity_request"),
    ]
    set_narration(AgentNarration(FakeNodeLLM({"campaign_buddy": leaks}, default=get_node_llm({}))))
    h = hero_player(client)
    cid = start_campaign(client, h)
    for i, q in enumerate(BUDDY_QUESTIONS):
        events, done = post_sse(client, f"/campaigns/{cid}/buddy", h,
                                {"text": q, "client_msg_id": f"l{i}"})  # fmt: skip
        text = streamed_text(events) or done["text"]
        assert "enron" not in text.lower() and not YEAR.search(text), text
        assert done.get("degraded") is True


def test_2_1_5_campaign_master_narration_names_no_company_or_year(client: TestClient, enron: str) -> None:
    """2.1.5 every Campaign Master text before the company reveal
    @spec: 002-anonymization-reid-gate @regression"""
    terms = secret_terms(enron)
    h = hero_player(client)
    cid = start_campaign(client, h)
    state = play_to_decide(client, h, cid)
    texts = [m["text"] for m in state["backlog"] if m["speaker"] != "You"]
    assert texts, "narration must exist to be checked"
    for t in texts:
        assert not YEAR.search(t) and not any(has_word(t, x) for x in terms), t
    lock_decision(client, h, cid)
    blob = json.dumps(run_debrief(client, h, cid))  # debrief narration, before the company reveal
    assert not YEAR.search(blob) and not any(has_word(blob, x) for x in terms)


def test_2_1_6_price_direction_matches_news(client: TestClient, any_approved: str) -> None:
    """2.1.6 a headline that reports a fall/rise sits on a lower/higher price than the previous news
    @spec: 002-anonymization-reid-gate @regression"""
    view = client.get(f"/scenario/{any_approved}/view").json()
    price_at = {p["story_day"]: Decimal(p["price"]) for p in view["chart"]}
    beats = view["beats"]
    assert len(beats) >= 2
    words = 0
    for prev, cur in zip(beats, beats[1:], strict=False):
        a, b = price_at[prev["story_day"]], price_at[cur["story_day"]]
        if DROP.search(cur["headline"]):
            words += 1
            assert b < a, (cur["headline"], a, b)
        if RISE.search(cur["headline"]):
            words += 1
            assert b > a, (cur["headline"], a, b)
    if view["invented_name"] == "Lantern Works":  # the scripted gate scenario states both falls
        assert words == 2


def test_2_1_6_every_step_has_the_real_direction(client: TestClient, any_approved: str) -> None:
    """2.1.6 the sign of each step between news items equals the real step
    @spec: 002-anonymization-reid-gate @regression"""
    view = client.get(f"/scenario/{any_approved}/view").json()
    price_at = {p["story_day"]: Decimal(p["price"]) for p in view["chart"]}
    real = reveal_for(client, any_approved)["news_points"]
    story = [price_at[b["story_day"]] for b in real]
    true = [Decimal(b["real_price"]) for b in real]
    assert len(real) >= 2
    for i in range(1, len(real)):
        assert (story[i] > story[i - 1]) == (true[i] > true[i - 1])
        assert (story[i] < story[i - 1]) == (true[i] < true[i - 1])


# =============================================================================================
# 2.2 Price moves stay true to history; only the level changes
# =============================================================================================
def test_2_2_1_no_amount_above_10000_and_no_magnitude_words(client: TestClient, any_approved: str) -> None:
    """2.2.1 @spec: 002-anonymization-reid-gate @regression"""
    view = client.get(f"/scenario/{any_approved}/view").json()
    assert view["chart"] and all(Decimal(p["price"]) <= 10_000 for p in view["chart"])
    text = " ".join(prose([view["beats"], view["company_card"], view["industry_shown"]]))
    assert not MAGNITUDE.search(text)
    shown = [Decimal(n.replace(",", "")) for n in NUMBER.findall(text) if n.strip(",")]
    assert all(n <= 10_000 for n in shown), [n for n in shown if n > 10_000]


def test_2_2_1_gate_amounts_are_rescaled_from_billions(client: TestClient, approved_gate: str) -> None:
    """2.2.1 the real amounts were 51, 9 and 23 billion; the player sees small figures
    @spec: 002-anonymization-reid-gate @regression"""
    view = client.get(f"/scenario/{approved_gate}/view").json()
    figures = [Decimal(n.replace(",", "")) for n in NUMBER.findall(" ".join(prose(view["beats"])))]
    assert len(figures) == 3 and all(0 < f <= 10_000 for f in figures), figures
    ratio = figures[0] / figures[1]  # revenue : cash keeps its real relationship (one money factor)
    assert abs(ratio - Decimal(51) / Decimal(9)) / (Decimal(51) / Decimal(9)) < Decimal("0.08")


def test_2_2_1_campaign_figures_at_most_10000(client: TestClient, enron: str) -> None:
    """2.2.1 price board, company card, library @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    state = play_to_decide(client, h, cid)
    for c in state["price_board"]:
        assert all(Decimal(str(c[k])) <= 10_000 for k in ("open", "high", "low", "close"))
    for fig in state["library"]["company_card"]["key_figures"]:
        v = str(fig["value"]).replace(",", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", v):
            assert abs(Decimal(v)) <= 10_000, fig
    assert not MAGNITUDE.search(" ".join(prose(state)))


def test_2_2_2_percent_moves_within_one_point_of_reveal_table(client: TestClient, any_approved: str) -> None:
    """2.2.2 @spec: 002-anonymization-reid-gate @regression"""
    view = client.get(f"/scenario/{any_approved}/view").json()
    price_at = {p["story_day"]: Decimal(p["price"]) for p in view["chart"]}
    real = reveal_for(client, any_approved)["news_points"]
    assert len(real) >= 2
    for a, b in zip(real, real[1:], strict=False):
        game = (price_at[b["story_day"]] / price_at[a["story_day"]] - 1) * 100
        true = (Decimal(b["real_price"]) / Decimal(a["real_price"]) - 1) * 100
        assert abs(game - true) <= 1, (game, true)


def test_2_2_3_same_price_decision_timeskip_reveal(client: TestClient, enron: str) -> None:
    """2.2.3 @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    state = play_to_decide(client, h, cid)
    board = {c["day"]: Decimal(str(c["close"])) for c in state["price_board"]}
    chart = {p["story_day"]: Decimal(p["price"])
             for p in client.get(f"/scenario/{enron}/view").json()["chart"]}  # fmt: skip
    lock = lock_decision(client, h, cid)
    revealed = client.get(f"/campaigns/{cid}/reveal", headers=h).json()
    skip = {p["story_day"]: Decimal(str(p["price"])) for p in lock["series"]}
    shown = {p["story_day"]: Decimal(str(p["price"])) for p in revealed["series"]}
    assert skip == shown  # the time skip and the reveal use one path, point for point
    shared = set(board) & set(skip)
    assert shared, "the decision and time-skip screens must overlap on at least one story day"
    for d in shared:
        assert board[d] == skip[d], d
    for d in set(chart) & set(skip):
        assert chart[d] == skip[d], d


# =============================================================================================
# 2.3 A scenario is playable only after it passes the recognition check
# =============================================================================================
async def test_2_3_1_famous_case_shows_failed_attempt_with_guesses_and_clues(
    client: TestClient, db: Session
) -> None:
    """2.3.1 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, FAMOUS, fame="high", size="large", company="Boeing")
    run_id, done = await run_cases(db, lambda c: make_llm(c, recognise=True))
    assert done[FAMOUS] == "rejected"
    first = case_row(build_report_data(db, run_id), FAMOUS)["attempts"][0]
    assert first["n"] == 1 and first["verdict"] == "failed"
    assert first["guesses"], "each guesser's guesses must be listed"
    g = first["guesses"][0]
    assert g["top3"][0]["company"] == "Boeing" and g["top3"][0]["confidence"] == 60
    assert any(CLUE in str(x) for x in g["clues"]) and g["recognised"] is True


async def test_2_3_2_three_fails_is_rejected_and_not_playable(client: TestClient, db: Session) -> None:
    """2.3.2 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, FAMOUS, fame="high", size="large", company="Boeing")
    run_id, done = await run_cases(db, lambda c: make_llm(c, recognise=True))
    assert done[FAMOUS] == "rejected"
    data = build_report_data(db, run_id)
    row = case_row(data, FAMOUS)
    assert row["status"] == "rejected" and [a["n"] for a in row["attempts"]] == [1, 2, 3]
    assert all(a["verdict"] == "failed" for a in row["attempts"])
    assert data["playable"] == [] and client.get("/scenarios/playable").json() == []
    assert db.exec(select(Scenario)).all() == []
    assert 'class="badge rejected"' in render_html(data)  # the final status is shown


async def test_2_3_2_rejected_status_has_the_exact_label(client: TestClient, db: Session) -> None:
    """2.3.2 exact final-status text @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, FAMOUS, fame="high", size="large", company="Boeing")
    run_id, _ = await run_cases(db, lambda c: make_llm(c, recognise=True))
    assert "Rejected: too recognisable" in render_html(build_report_data(db, run_id))


async def test_2_3_3_unrecognised_candidate_is_approved_and_playable(client: TestClient, db: Session) -> None:
    """2.3.3 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, LANTERN, fame="low", size="small")
    run_id, done = await run_cases(db, make_llm)
    assert done == {LANTERN: "approved"}
    data = build_report_data(db, run_id)
    row = case_row(data, LANTERN)
    assert row["status"] == "approved" and len(row["attempts"]) == 1
    att = row["attempts"][0]
    assert att["verdict"] == "passed" and att["avg_readability"] >= 3
    assert {g["round"] for g in att["guesses"]} == {"memory", "web"}
    assert not any(g["recognised"] for g in att["guesses"])
    assert [p["case_id"] for p in data["playable"]] == [LANTERN]
    listed = client.get("/scenarios/playable").json()
    assert len(listed) == 1 and listed[0]["source"] == "gate"


async def test_2_3_4_year_in_disguised_text_fails_with_real_date_reason(client: TestClient, db: Session) -> None:
    """2.3.4 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, YEAR_LEAK, fame="low", size="small")
    run_id, done = await run_cases(db, lambda c: make_llm(c, bad_draft=True))
    assert done[YEAR_LEAK] == "rejected"  # the writer keeps the year on every attempt
    data = build_report_data(db, run_id)
    first = case_row(data, YEAR_LEAK)["attempts"][0]
    assert first["verdict"] == "failed" and first["fail_reason"] == "real_date_found"
    assert "Real date found in text" in first["scan_reasons"]
    assert first["guesses"] == []  # the final scan stops the attempt before any guesser runs
    assert "Real date found in text" in render_html(data)


async def test_2_3_5_quest_start_only_gets_playable_scenarios(
    client: TestClient, db: Session, enron: str
) -> None:
    """2.3.5 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, LANTERN, fame="low", size="small")
    add_case(db, FAMOUS, fame="high", size="large", company="Boeing")
    await run_cases(db, lambda c: make_llm(c, recognise=c.fame == "high"))
    stale = Scenario(
        case_id=FAMOUS, source="gate", invented_name="Old Name", industry_shown="Retail",
        story_days=[0, 7], beats=[], chart_series=[], company_card={}, status="retired",
    )  # fmt: skip
    db.add(stale)  # an older approval of a case that is now rejected must never be served
    db.commit()
    playable = {x["id"] for x in client.get("/scenarios/playable").json()}
    assert str(stale.id) not in playable and enron in playable and len(playable) == 2
    for _ in range(3):
        started = client.post("/campaigns", json={"interests": ["Gaming"]}, headers=hero_player(client))
        assert started.status_code == 201, started.text
        assert started.json()["scenario_id"] in playable


def tampered_pack(tmp_path: Path, label: str) -> Path:
    pack = tmp_path / "pack"
    shutil.copytree(PACK_DIR, pack)
    raw = json.loads((pack / "manifest.json").read_text())
    raw["checkpoints"][0]["label"] = label
    (pack / "manifest.json").write_text(json.dumps(raw))
    return pack


@pytest.mark.parametrize("label", ["A morning in March", "Held on a Tuesday"])
def test_2_3_6_reference_pack_with_month_or_weekday_is_not_playable(
    client: TestClient, db: Session, tmp_path: Path, label: str
) -> None:
    """2.3.6 a date word in player-visible pack text: not playable, reason shown
    @spec: 002-anonymization-reid-gate @regression"""
    res = approve_pack(tampered_pack(tmp_path, label), db)
    assert not res.ok and res.status != "playable"
    assert any("Real date found in text" in r for r in res.reasons), res.reasons
    assert db.exec(select(Scenario)).all() == []
    assert client.get("/scenarios/playable").json() == []


def test_2_3_6_reference_pack_with_year_is_not_playable(client: TestClient, db: Session, tmp_path: Path) -> None:
    """2.3.6 a calendar year in player-visible pack text: not playable
    @spec: 002-anonymization-reid-gate @regression"""
    res = approve_pack(tampered_pack(tmp_path, "The opening scene of 1999"), db)
    assert not res.ok and res.status != "playable"
    assert db.exec(select(Scenario)).all() == [] and client.get("/scenarios/playable").json() == []


def test_2_3_6_reference_pack_with_year_shows_real_date_reason(client: TestClient, db: Session, tmp_path: Path) -> None:
    """2.3.6 exact reason text for a year @spec: 002-anonymization-reid-gate @regression"""
    res = approve_pack(tampered_pack(tmp_path, "The opening scene of 1999"), db)
    assert any("Real date found in text" in r for r in res.reasons), res.reasons


# =============================================================================================
# 2.4 The team checks a batch of candidate cases in one run
# =============================================================================================
TAGS = [("high", "large"), ("medium", "large"), ("medium", "mid"), ("low", "small"), ("low", "mid")]
CASE_IDS = [safe_id(f"c{i:03d}") for i in range(100)]
TAG_OF = {cid: TAGS[i % 5] for i, cid in enumerate(CASE_IDS)}
INCOMPLETE = {CASE_IDS[i] for i in (7, 33, 58, 91)}


def pct(part: int, total: int) -> int:
    return int((Decimal(part * 100) / Decimal(total)).to_integral_value(ROUND_HALF_UP))


_BATCH: dict[str, Any] = {}  # the 100-case run is the slow part; run it once for 2.4.1 and 2.5.x


@pytest.fixture
async def batch100(client: TestClient, db: Session) -> dict[str, Any]:
    """100 candidates: 4 incomplete (one news item), 96 checked; the high-fame ones are recognised."""
    if not _BATCH:
        await fill_batch(db)
    return _BATCH


@contextlib.contextmanager
def big_pool(size: int = 150, overflow: int = 0) -> Iterator[None]:
    """Run a batch with a connection pool at least as large as the batch (the default pool of
    5+5 connections stalls a batch of more than 10 cases)."""
    from financequest.db.session import get_engine

    saved = {k: os.environ.get(k) for k in ("DB_POOL_SIZE", "DB_MAX_OVERFLOW")}
    os.environ["DB_POOL_SIZE"], os.environ["DB_MAX_OVERFLOW"] = str(size), str(overflow)
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        yield
    finally:
        get_engine().dispose()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()
        get_engine.cache_clear()


async def fill_batch(db: Session) -> None:
    """The batch goes through run_batch in slices of 8 cases under one run id (resumable runs
    accumulate in one report): one call with all 100 cases stalls, see the known-defect test."""
    for cid in CASE_IDS:
        fame, size = TAG_OF[cid]
        add_case(db, cid, fame=fame, size=size, n_beats=1 if cid in INCOMPLETE else 3)
    run = start_run(db, "acceptance-100", get_settings())
    assert run.id is not None
    done: dict[str, str] = {}
    for i in range(0, 100, 8):
        part = await run_batch(
            session_factory, run.id, CASE_IDS[i : i + 8],
            llm_factory=lambda c: make_llm(c, recognise=c.fame == "high"), concurrency=4,
        )  # fmt: skip
        done |= part.done
    db.expire_all()
    data = build_report_data(db, run.id)
    _BATCH.update(done=done, data=data, html=render_html(data))


async def test_2_4_1_batch_of_100_listed_with_final_status(batch100: dict[str, Any]) -> None:
    """2.4.1 @spec: 002-anonymization-reid-gate @regression"""
    data = batch100["data"]
    assert len(data["cases"]) == 100 and len(batch100["done"]) == 100
    assert {c["case_id"] for c in data["cases"]} == set(CASE_IDS)
    assert {c["status"] for c in data["cases"]} == {"approved", "rejected", "skipped"}
    assert {c["case_id"] for c in data["cases"] if c["status"] == "skipped"} == INCOMPLETE


async def test_2_4_2_incomplete_case_skipped_others_still_checked(client: TestClient, db: Session) -> None:
    """2.4.2 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, ONE_NEWS, fame="low", size="small", n_beats=1)
    add_case(db, LANTERN, fame="low", size="small")
    run_id, done = await run_cases(db, make_llm)
    assert done == {ONE_NEWS: "skipped", LANTERN: "approved"}
    data = build_report_data(db, run_id)
    assert case_row(data, ONE_NEWS)["skip_reason"] == "Skipped: incomplete case"
    assert "Skipped: incomplete case" in render_html(data)
    assert case_row(data, LANTERN)["status"] == "approved"


# =============================================================================================
# 2.5 The check report explains every result
# =============================================================================================
async def test_2_5_1_summary_line_is_first_and_exact(batch100: dict[str, Any]) -> None:
    """2.5.1 @spec: 002-anonymization-reid-gate @regression"""
    done = batch100["done"]
    checked = [c for c, s in done.items() if s != "skipped"]
    approved = [c for c in checked if done[c] == "approved"]
    recognised = [c for c in checked if TAG_OF[c][0] == "high"]
    expected = (
        f"{len(checked)} cases checked · {pct(len(recognised), len(checked))}% recognised "
        f"on first attempt · {len(approved)} approved ({pct(len(approved), len(checked))}%)"
    )
    data, html = batch100["data"], batch100["html"]
    assert data["header"] == expected and expected.startswith("96 cases checked · ")
    assert f'<h1 id="summary">{expected}</h1>' in html
    assert html.index("<h1") == html.index('<h1 id="summary">')  # the first heading on the page
    assert html.index(expected) < html.index("Approval share")


async def test_2_5_2_rejected_case_shows_every_attempt_guesses_and_clues(client: TestClient, db: Session) -> None:
    """2.5.2 @spec: 002-anonymization-reid-gate @regression"""
    add_case(db, FAMOUS, fame="high", size="large", company="Boeing")
    run_id, _ = await run_cases(db, lambda c: make_llm(c, recognise=True))
    data = build_report_data(db, run_id)
    row = case_row(data, FAMOUS)
    assert row["company"] == "Boeing" and row["invented_name"] == "Lantern Works"
    assert row["status"] == "rejected" and len(row["attempts"]) == 3
    for att in row["attempts"]:
        assert att["fail_reason"] == "recognised_name"
        assert len(att["guesses"]) >= 3  # the guessers of the memory round
        for g in att["guesses"]:
            assert len(g["top3"]) == 3 and all("confidence" in t for t in g["top3"])
            assert g["start_guess"] and g["start_conf"] is not None
    html = render_html(data)
    assert escape(CLUE) in html and "Attempt 1" in html and "Attempt 3" in html


async def test_2_5_3_approval_share_per_fame_and_size(batch100: dict[str, Any]) -> None:
    """2.5.3 @spec: 002-anonymization-reid-gate @regression"""
    data, done = batch100["data"], batch100["done"]
    live = [(c, *TAG_OF[c]) for c, s in done.items() if s != "skipped"]

    def expect(idx: int, label: str) -> dict[str, Any]:
        rows = [c for c in live if c[1 + idx] == label]
        ok = [c for c in rows if done[c[0]] == "approved"]
        return {"label": label, "count": len(ok), "total": len(rows), "pct": pct(len(ok), len(rows))}

    assert data["approval_by_fame"] == [expect(0, f) for f in ("low", "medium", "high")]
    assert data["approval_by_size"] == [expect(1, s) for s in ("small", "mid", "large")]
    assert expect(0, "high")["count"] == 0 and expect(0, "low")["pct"] == 100
    html = batch100["html"]
    assert "Approval share by fame" in html and "Approval share by size" in html


# =============================================================================================
# 2.6 The reveal shows the real company and what was changed
# =============================================================================================
def test_2_6_1_reveal_after_reflection_has_real_identity_chart_and_table(client: TestClient, enron: str) -> None:
    """2.6.1 @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    play_to_decide(client, h, cid)
    lock_decision(client, h, cid)
    run_debrief(client, h, cid)
    submit_reflection(client, h, cid)
    r = client.get(f"/scenario/{enron}/reveal", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["real_name"].startswith("Enron") and body["ticker"] == "ENE"
    assert body["start_date"] == "2001-08-01" and body["end_date"] == body["series"][-1]["date"]
    assert len(body["series"]) > 10 and all(p["date"] and p["price"] for p in body["series"])
    assert body["news_points"] and all(
        n["real_date"] and n["real_price"] and n["headline"] for n in body["news_points"]
    )
    assert body["what_changed"] and any("factor" in w or "multiplied" in w for w in body["what_changed"])


def test_2_6_2_reveal_refused_before_decision_and_debrief(client: TestClient, enron: str) -> None:
    """2.6.2 @spec: 002-anonymization-reid-gate @regression"""
    h = hero_player(client)
    cid = start_campaign(client, h)
    url = f"/scenario/{enron}/reveal"
    real = secret_terms(enron)
    early = client.get(url, headers=h)  # no decision yet
    assert early.status_code == 403 and not any(has_word(early.text, t) for t in real)
    play_to_decide(client, h, cid)
    lock_decision(client, h, cid)
    assert client.get(url, headers=h).status_code == 403  # a decision alone is not enough
    run_debrief(client, h, cid)
    late = client.get(url, headers=h)  # debrief shown, reflection not yet submitted
    assert late.status_code == 403 and not any(has_word(late.text, t) for t in real)
    assert client.get(url, headers=player(client)).status_code == 403  # another session
    submit_reflection(client, h, cid)
    assert client.get(url, headers=h).status_code == 200


def test_2_6_3_gate_scenario_reveal_reports_three_testers(client: TestClient, approved_gate: str) -> None:
    """2.6.3 backend half: G = 3 distinct guessers (the sentence is asserted in the frontend test)
    @spec: 002-anonymization-reid-gate @regression"""
    body = reveal_for(client, approved_gate)
    assert body["n_guessers"] == 3
    assert body["what_changed"] and "Lantern Works" in " ".join(body["what_changed"])
    assert body["real_name"].startswith(REAL)


def test_2_6_4_reveal_has_no_buy_offer_and_no_disclaimer(client: TestClient, enron: str) -> None:
    """2.6.4 @spec: 002-anonymization-reid-gate @regression"""
    body = reveal_for(client, enron)
    low = json.dumps(body).lower()
    for word in ("disclaimer", "education only", "not financial advice", "buy now", "invest now", "purchase"):
        assert word not in low, word
    assert set(body) == {"real_name", "ticker", "start_date", "end_date", "series", "news_points",
                         "what_changed", "n_guessers"}  # fmt: skip


def test_2_6_5_reference_pack_reveal_has_no_tester_count(client: TestClient, enron: str) -> None:
    """2.6.5 @spec: 002-anonymization-reid-gate @regression"""
    body = reveal_for(client, enron)
    assert body["n_guessers"] == 0  # the frontend shows the sentence only above 0
    assert "testers" not in json.dumps(body).lower()


async def test_known_defect_seed_overflows_integer_column(client: TestClient, db: Session) -> None:
    """Approving a case whose crc32 seed exceeds 2**31-1 must succeed (spec 2.3.3).
    @spec: 002-anonymization-reid-gate @regression"""
    assert zlib.crc32(b"lantern-ok") > SEED_MAX
    add_case(db, "lantern-ok", fame="low", size="small")
    _, done = await run_cases(db, make_llm)
    assert done == {"lantern-ok": "approved"}


async def test_known_defect_batch_larger_than_the_pool_stalls(client: TestClient, db: Session) -> None:
    """2.4.1 a batch must finish whatever its size @spec: 002-anonymization-reid-gate @regression"""
    ids = [safe_id(f"pool-{i}") for i in range(3)]
    for cid in ids:
        add_case(db, cid, fame="low", size="small")
    with big_pool(size=2, overflow=0):
        run = start_run(db, "pool", get_settings())
        assert run.id is not None
        summ = await run_batch(session_factory, run.id, ids, llm_factory=make_llm, concurrency=2)
    assert len(summ.done) == 3


def test_reveal_news_rows_show_the_real_events(client: TestClient, enron: str) -> None:
    """The reveal's "What happened" rows say what really happened, not the fantasy text.
    @spec: 002-anonymization-reid-gate"""
    rv = reveal_for(client, enron)
    blob = json.dumps(rv["news_points"])
    assert "Enron" in blob and "618" in blob and "Skilling" in blob
    assert "Golden Guild" not in blob and "Aster Vale" not in blob
    assert rv["what_changed"]  # the disguised -> real mapping stays


def test_pre_reveal_endpoints_never_contain_real_events(client: TestClient, enron: str) -> None:
    """@spec: 002-anonymization-reid-gate"""
    h = player(client)
    for path in (f"/scenario/{enron}/view", "/scenario/playable"):
        text = client.get(path, headers=h).text
        assert "Enron" not in text and "Skilling" not in text, path


def test_bundled_real_events_fill_real_figures_for_rows_approved_earlier() -> None:
    """The reveal falls back to the pack's real events for rows that stored disguised prose."""
    from financequest.refpack import real_events

    ev = real_events.bundled("FQ-AV-001")
    head, text = ev["news"]
    assert "Enron" in head and "618 million" in text and "{" not in text
    assert "Skilling" in ev["F-CEO-RESIGN-001"][0]
