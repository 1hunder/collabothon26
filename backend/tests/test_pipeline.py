"""Pipeline tests: prices cache, intake, batch runner, report, fixture export/import."""

import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import delete
from sqlmodel import Session, select

from financequest.config import get_settings
from financequest.db.models import (
    Attempt,
    CaseResult,
    CheckRun,
    Decision,
    Event,
    Guess,
    PriceSeries,
    Scenario,
    ScenarioSecret,
    SourceBeat,
    SourceCase,
)
from financequest.db.session import get_engine
from financequest.pipeline.export import export_approved, import_fixtures, load_fixtures_if_empty
from financequest.pipeline.fx import to_eur
from financequest.pipeline.intake import (
    FixtureIntakeLLM,
    parse_real_date,
    persist_results,
    read_results,
    tokenise_facts,
    write_spotcheck,
)
from financequest.pipeline.prices import fetch_case_prices, fetch_prices
from financequest.pipeline.sources import FixtureNewsSource
from financequest.reid import schemas
from financequest.reid.batch import (
    default_gate_runner,
    dry_run_llm_factory,
    run_batch,
    start_run,
)
from financequest.report.render import CAVEAT, build_report_data, render_html, render_json

SAMPLE = Path(__file__).parent.parent / "financequest" / "fixtures" / "cases" / "sample_cases.md"


@pytest.fixture
def db(test_db_url: str) -> Session:
    """Clean pipeline tables; only gate scenarios created by the test itself are removed."""
    with Session(get_engine()) as s:
        keep = set(s.exec(select(Scenario.id).where(Scenario.source == "gate")).all())

        def wipe() -> None:
            s.rollback()
            mine = [i for i in s.exec(select(Scenario.id).where(Scenario.source == "gate")).all()
                    if i not in keep]  # fmt: skip
            for t in (Event, Decision):
                s.exec(delete(t).where(t.scenario_id.in_(mine)))  # type: ignore[attr-defined]
            s.exec(delete(ScenarioSecret).where(ScenarioSecret.scenario_id.in_(mine)))  # type: ignore[attr-defined]
            s.exec(delete(Scenario).where(Scenario.id.in_(mine)))  # type: ignore[attr-defined]
            for table in (
                CaseResult,
                Guess,
                Attempt,
                CheckRun,
                PriceSeries,
                SourceBeat,
                SourceCase,
            ):
                s.exec(delete(table))  # type: ignore[arg-type]
            s.commit()

        wipe()
        yield s
        wipe()


@pytest.fixture
def loaded(db: Session, tmp_path: Path) -> Session:
    """The three sample cases ingested and priced from the bundled fixtures."""
    persist_results(db, read_results(SAMPLE, FixtureIntakeLLM.for_md(SAMPLE)))
    for cid in db.exec(select(SourceCase.id)).all():
        fetch_case_prices(db, cid, tmp_path / "cache")
    return db


def _factory() -> Session:
    return Session(get_engine())


# ---- prices ------------------------------------------------------------------
def test_prices_cache_with_mocked_yfinance(tmp_path: Path) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_download(ticker: str, start: str, end: str) -> pd.DataFrame:
        calls.append((ticker, start, end))
        return pd.DataFrame(
            {"date": ["2020-01-02", "2020-01-03", "2020-01-20"], "close": [10.0, 10.5, 11.0]}
        )

    kw = {"cache_dir": tmp_path, "downloader": fake_download, "fixture_dir": tmp_path / "none"}
    first = fetch_prices("ZZZ", "2020-01-01", "2020-02-01", **kw)  # type: ignore[arg-type]
    second = fetch_prices("ZZZ", "2020-01-01", "2020-02-01", **kw)  # type: ignore[arg-type]
    assert len(calls) == 1 and not first.from_cache and second.from_cache
    assert first.path.exists() and first.n_points == 3
    assert first.gap_flags == [{"from": "2020-01-03", "to": "2020-01-20", "days": 17}]


# ---- fx, sources, parsing --------------------------------------------------------
def test_fx_records_rate() -> None:
    r = to_eur(1_080_000_000, "USD", 2024)
    assert str(r.rate) == "1.08" and int(r.eur) == 1_000_000_000


def test_fixture_news_source(tmp_path: Path) -> None:
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"X": [{"date": "2020-01-02", "headline": "h"}]}))
    src = FixtureNewsSource(p)
    assert [n.headline for n in src.news("X", "2020-01-01", "2020-12-31")] == ["h"]
    assert src.news("X", "2021-01-01", "2021-12-31") == []


def test_parse_dates_and_tokenise() -> None:
    assert str(parse_real_date("March 11, 2019")) == "2019-03-11"
    assert parse_real_date("2019") is None and parse_real_date("soon") is None
    facts, amounts = tokenise_facts([["Cost $4.2 million, up 35%."], ["Nothing."]])
    assert facts[0] == ["Cost {A1}, up {A2}%."]
    assert amounts[0]["value"] == "4200000" and amounts[1]["is_ratio"] is True


# ---- intake ------------------------------------------------------------------------
def test_intake_skip_untagged_and_spotcheck(db: Session, tmp_path: Path) -> None:
    beats = [schemas.SourceBeatDraft(real_date="2021-01-04", headline="h")] * 2
    full = schemas.SourceCaseDraft(
        company="Acme", ticker="ACM", lesson="l", identifying_terms=["Acme"], beats=beats
    )  # no market cap, country or year -> untagged
    results = [
        schemas.IntakeResult(title="Acme 2021", draft=full, status="untagged"),
        schemas.IntakeResult(
            title="Thin 2021",
            draft=full.model_copy(update={"company": "Thin"}),
            status="skipped",
            skip_reason="Skipped: incomplete case",
        ),
        schemas.IntakeResult(title="Broken", status="error", error="boom"),
    ]
    summ = persist_results(db, results)
    assert (summ.untagged, summ.skipped, summ.errors) == (1, 1, 1)
    acme = db.get(SourceCase, "acme-2021")
    assert acme is not None and acme.status == "untagged" and acme.fame is None
    thin = db.get(SourceCase, "thin-2021")
    assert thin is not None and thin.status == "skipped" and thin.skip_reason
    assert db.get(SourceCase, "broken") is None
    csv_path = tmp_path / "spot.csv"
    assert write_spotcheck(db, csv_path) == 2
    text = csv_path.read_text()
    assert "acme-2021" in text and "Skipped: incomplete case" in text


def test_intake_tags_sample_cases(loaded: Session) -> None:
    boeing = loaded.get(SourceCase, "boeing-2024")
    assert boeing is not None and (boeing.size_band, boeing.fame) == ("large", "high")
    assert loaded.get(SourceCase, "tidewell-ferries").status == "skipped"  # type: ignore[union-attr]


# ---- batch -------------------------------------------------------------------------
async def test_batch_commit_per_case_and_outcomes(loaded: Session) -> None:
    run = start_run(loaded, "t", get_settings())
    assert run.id is not None
    seen: dict[str, bool] = {}

    def on_done(case_id: str, status: str) -> None:
        with Session(get_engine()) as other:  # a separate connection sees only committed rows
            seen[case_id] = (
                other.exec(
                    select(CaseResult).where(
                        CaseResult.case_id == case_id, CaseResult.run_id == run.id
                    )
                ).first()
                is not None
            )

    summ = await run_batch(
        _factory, run.id, llm_factory=dry_run_llm_factory, concurrency=2, on_case_done=on_done
    )
    assert summ.done == {
        "boeing-2024": "rejected",
        "marrow-bay-brewing": "approved",
        "tidewell-ferries": "skipped",
    }
    assert all(seen.values()) and len(seen) == 3
    loaded.expire_all()
    assert len(loaded.exec(select(Attempt).where(Attempt.case_id == "boeing-2024")).all()) == 3
    assert loaded.exec(select(Guess)).first() is not None
    assert loaded.exec(select(Scenario).where(Scenario.source == "gate")).all()
    tel = loaded.get(CheckRun, run.id).config["telemetry"]  # type: ignore[union-attr]
    assert tel["calls"] > 0 and tel["output_tokens"] > 0


async def test_batch_resumable(loaded: Session) -> None:
    run = start_run(loaded, "resume", get_settings())
    assert run.id is not None
    ran: list[str] = []

    def runner(case, salt, llm):  # type: ignore[no-untyped-def]
        ran.append(case.case_id)
        return default_gate_runner(case, salt, llm)

    first = await run_batch(
        _factory,
        run.id,
        ["marrow-bay-brewing"],
        llm_factory=dry_run_llm_factory,
        gate_runner=runner,
    )
    assert first.done == {"marrow-bay-brewing": "approved"}
    again = start_run(loaded, "resume", get_settings())  # same label, unfinished? finished now
    assert again.id != run.id
    # resume the original run explicitly: finished cases are skipped, the rest are run
    ran.clear()
    second = await run_batch(_factory, run.id, llm_factory=dry_run_llm_factory, gate_runner=runner)
    assert second.already_done == ["marrow-bay-brewing"]
    assert "marrow-bay-brewing" not in ran and "boeing-2024" in ran
    loaded.expire_all()
    assert len(loaded.exec(select(CaseResult).where(CaseResult.run_id == run.id)).all()) == 3


async def test_batch_error_case_does_not_stop_run(loaded: Session) -> None:
    run = start_run(loaded, "err", get_settings())
    assert run.id is not None

    def runner(case, salt, llm):  # type: ignore[no-untyped-def]
        if case.case_id == "boeing-2024":
            raise RuntimeError("boom")
        return default_gate_runner(case, salt, llm)

    summ = await run_batch(_factory, run.id, llm_factory=dry_run_llm_factory, gate_runner=runner)
    assert summ.done["boeing-2024"] == "error" and summ.done["marrow-bay-brewing"] == "approved"


# ---- report --------------------------------------------------------------------------
HEADER = "2 cases checked · 0% recognised on first attempt · 1 approved (50%)"


async def _run_sample(db: Session) -> int:
    run = start_run(db, "rep", get_settings())
    assert run.id is not None
    await run_batch(_factory, run.id, llm_factory=dry_run_llm_factory)
    db.expire_all()
    return run.id


async def test_report_header_and_sections(loaded: Session) -> None:
    run_id = await _run_sample(loaded)
    data = build_report_data(loaded, run_id)
    html = render_html(data)
    # Boeing's fake guessers name it on every attempt: recognised on first attempt, 1 of 2 checked
    assert data["header"] == "2 cases checked · 50% recognised on first attempt · 1 approved (50%)"
    assert f'<h1 id="summary">{data["header"]}</h1>' in html
    assert html.index(data["header"]) < html.index("Approval share by fame")
    for section in ("Approval share by size", "Playable scenarios", "Skipped", CAVEAT):
        assert section in html
    assert "Skipped: incomplete case" in html and "Marrow Bay Brewing" in html
    assert "Attempt 3" in html and "recognised_name" in html
    assert "Telemetry:" in html and "http://" not in html and "https://" not in html
    payload = json.loads(render_json(data))
    assert payload["header"] == data["header"]
    assert {c["status"] for c in payload["cases"]} == {"approved", "rejected", "skipped"}


# ---- export / import -------------------------------------------------------------------
async def test_export_import_round_trip(loaded: Session, tmp_path: Path) -> None:
    await _run_sample(loaded)
    out = tmp_path / "fx"
    files = export_approved(loaded, out)
    docs = [json.loads(f.read_text()) for f in files]
    doc = next(d for d in docs if d["secret"]["real_name"] == "Marrow Bay Brewing")
    assert doc["schema_version"] == 1 and doc["secret"]["real_name"] == "Marrow Bay Brewing"
    sc = loaded.exec(
        select(Scenario).where(
            Scenario.case_id == "marrow-bay-brewing", Scenario.status == "playable"
        )
    ).one()
    mine = tmp_path / "mine"
    mine.mkdir()
    (mine / f"gate-{sc.id}.json").write_text(json.dumps(doc))
    assert load_fixtures_if_empty(loaded, mine) == 0  # a gate scenario exists: nothing to load
    sid, before = sc.id, (sc.invented_name, sc.beats, sc.chart_series, sc.story_days)
    sec = loaded.get(ScenarioSecret, sid)
    assert sec is not None
    sec_before = (sec.real_name, sec.real_beats, sec.n_guessers, float(sec.price_factor or 0))
    loaded.exec(delete(ScenarioSecret).where(ScenarioSecret.scenario_id == sid))  # type: ignore[arg-type]
    loaded.exec(delete(Scenario).where(Scenario.id == sid))  # type: ignore[arg-type]
    loaded.commit()

    assert import_fixtures(loaded, mine) == 1
    assert import_fixtures(loaded, mine) == 1  # idempotent: upserts, no duplicate
    assert len(loaded.exec(select(Scenario).where(Scenario.id == sid)).all()) == 1
    loaded.expire_all()
    back = loaded.get(Scenario, sid)
    sec2 = loaded.get(ScenarioSecret, sid)
    assert back is not None and sec2 is not None and back.source == "gate"
    assert (back.invented_name, back.beats, back.chart_series, back.story_days) == before
    assert (
        sec2.real_name,
        sec2.real_beats,
        sec2.n_guessers,
        float(sec2.price_factor or 0),
    ) == sec_before


async def test_skipped_for_missing_price_is_rechecked_after_prices(
    loaded: Session, tmp_path: Path
) -> None:
    case = loaded.get(SourceCase, "marrow-bay-brewing")
    assert case is not None
    ps = loaded.exec(select(PriceSeries).where(PriceSeries.case_id == case.id)).one()
    cols = ("ticker", "first_date", "last_date", "n_points", "cache_ref")
    saved = {c: getattr(ps, c) for c in cols}
    loaded.delete(ps)
    case.status, case.skip_reason = "skipped", "Skipped: incomplete case"
    loaded.add(case)
    loaded.commit()
    run = start_run(loaded, "a", get_settings())
    assert run.id is not None
    s1 = await run_batch(_factory, run.id, [case.id], llm_factory=dry_run_llm_factory)
    assert s1.done[case.id] == "skipped"
    loaded.add(PriceSeries(case_id=case.id, **saved))  # prices arrive later
    loaded.commit()
    run2 = start_run(loaded, "b", get_settings())
    assert run2.id is not None
    s2 = await run_batch(_factory, run2.id, [case.id], llm_factory=dry_run_llm_factory)
    assert s2.done[case.id] == "approved"
    loaded.expire_all()
    fresh = loaded.get(SourceCase, case.id)
    assert fresh is not None and fresh.status == "ok" and fresh.skip_reason is None
