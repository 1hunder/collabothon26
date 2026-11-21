"""@spec: personal-daily-quests (mock transactions -> per-company agent -> disguised daily quest)"""

import time
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from financequest.config import get_settings
from financequest.db.session import get_engine
from financequest.personal import agent, market
from financequest.personal import transactions as tx
from financequest.refpack.approve import ApproveResult, approve_pack

PACK_DIR = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"
TABLES = (
    "generation_job, xp_award, debrief, outcome, clue_state, challenge, location, campaign_run, "
    "hero_item, hero, player, event, decision, scenario_secret, scenario, session"
)


# ---- pure parts -------------------------------------------------------------------------------


def test_spending_ranks_categories_and_ignores_income() -> None:
    ranked = tx.spending_by_category(tx.LENA)
    keys = [k for k, _ in ranked]
    assert "income" not in keys
    assert set(keys) <= set(tx.CATEGORIES)
    assert [v for _, v in ranked] == sorted((v for _, v in ranked), reverse=True)


def test_candidate_queue_rotates_categories_and_skips_used() -> None:
    q0 = tx.candidate_queue(tx.LENA, set(), seed=0)
    q1 = tx.candidate_queue(tx.LENA, set(), seed=1)
    assert q0[0][0].key != q1[0][0].key  # a new day starts in another category
    tickers = [c.ticker for _, c in q0]
    assert len(tickers) == len(set(tickers))
    used = {tickers[0], tickers[1]}
    assert not used & {c.ticker for _, c in tx.candidate_queue(tx.LENA, used, seed=0)}


def _frame(n: int = 400, shock_at: int = 200) -> pd.DataFrame:
    start = date(2015, 1, 5)
    days, closes, price = [], [], 100.0
    d = start
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if shock_at <= i < shock_at + 3:
            price *= 0.88  # ~-32% over three days
        else:
            price *= 1.001
        days.append(d.isoformat())
        closes.append(price)
        d += timedelta(days=1)
    return pd.DataFrame({"date": days, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1000] * n})  # fmt: skip


def test_find_windows_builds_intro_shock_decision_horizon() -> None:
    frame = _frame()
    windows = market.find_windows(frame)
    assert windows, "a 30% drop must produce a window"
    w = windows[0]
    assert w.move_pct < -15
    assert w.intro < w.shock < w.decision < w.buy < w.horizon
    dates = list(frame["date"])
    assert dates.index(w.decision.isoformat()) == dates.index(w.shock.isoformat()) + 1


def test_prices_csv_covers_intro_to_horizon(tmp_path: Path) -> None:
    frame = _frame()
    w = market.find_windows(frame)[0]
    n = market.write_prices_csv(frame, w, tmp_path / "prices.csv", "TEST")
    rows = pd.read_csv(tmp_path / "prices.csv")
    assert n == len(rows)
    assert rows["date"].iloc[0] < w.intro.isoformat() <= rows["date"].iloc[5]
    assert rows["date"].iloc[-1] == w.horizon.isoformat()
    assert list(rows.columns)[:5] == ["date", "open_usd", "high_usd", "low_usd", "close_usd"]


def test_parse_research_reads_choice_and_strips_fences() -> None:
    body = "---\ncase_id: X\n---\n# T\n\n## 1. Purpose\n" + "text " * 400
    idx, case = agent.parse_research(f"CHOSEN_WINDOW: 2\n```markdown\n{body}\n```", 4)
    assert idx == 2
    assert case.startswith("---") and "```" not in case
    with pytest.raises(agent.QuestFailed):
        agent.parse_research("CHOSEN_WINDOW: 1\nsorry, nothing found", 4)


# ---- API flow (FAKE_LLM: sample pack, fake guessers) ------------------------------------------


@pytest.fixture
def fake_mode(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # noqa: E501
    s = get_settings()
    monkeypatch.setattr(s, "fake_llm", True)
    monkeypatch.setattr(s, "data_dir", str(tmp_path))
    monkeypatch.setattr(s, "demo_mode", False)
    monkeypatch.setattr(agent, "FAKE_STEP_DELAY_S", 0)
    yield
    with Session(get_engine()) as db:
        db.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        db.commit()


def _player(client: TestClient) -> dict[str, str]:
    sid = client.post("/session").json()["session_id"]
    h = {"X-Session-Id": sid}
    assert client.post("/hero", json={"name": "Lena", "class": "analyst"}, headers=h).status_code == 201  # noqa: E501
    return h


def _wait_ready(client: TestClient, h: dict[str, str], job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = next(j for j in client.get("/quests", headers=h).json() if j["id"] == job_id)
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.3)
    raise AssertionError("quest job did not finish")


def test_transactions_are_listed(client: TestClient, fake_mode: None) -> None:
    h = _player(client)
    rows = client.get("/me/transactions", headers=h).json()
    assert len(rows) == len(tx.LENA)
    assert {"date", "merchant", "amount_eur", "category_label"} <= set(rows[0])


def test_daily_quest_generates_once_and_is_playable(client: TestClient, fake_mode: None) -> None:
    h = _player(client)
    first = client.post("/quests/daily", headers=h).json()
    assert first["kind"] == "daily" and first["category_label"]
    assert "company" not in first and "ticker" not in first  # server-only
    assert client.post("/quests/daily", headers=h).json()["id"] == first["id"]  # idempotent
    job = _wait_ready(client, h, first["id"])
    assert job["status"] == "ready", job
    assert job["scenario_id"]
    r = client.post("/campaigns", json={"interests": ["Music"], "scenario_id": job["scenario_id"]},
                    headers=h)  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["scenario_id"] == job["scenario_id"]


def test_extra_quest_uses_another_company(client: TestClient, fake_mode: None) -> None:
    h = _player(client)
    daily = client.post("/quests/daily", headers=h).json()
    extra = client.post("/quests/generate", headers=h).json()
    assert extra["kind"] == "extra" and extra["id"] != daily["id"]
    _wait_ready(client, h, daily["id"])
    _wait_ready(client, h, extra["id"])
    from financequest.db.models_personal import GenerationJob

    with Session(get_engine()) as db:
        tickers = {j.ticker for j in db.exec(GenerationJob.__table__.select())}  # type: ignore[attr-defined]
    assert len(tickers) == 2


def test_personal_quest_is_private_to_its_player(client: TestClient, fake_mode: None) -> None:
    owner = _player(client)
    job = _wait_ready(client, owner, client.post("/quests/daily", headers=owner).json()["id"])
    other = _player(client)
    r = client.post("/campaigns", json={"interests": [], "scenario_id": job["scenario_id"]},
                    headers=other)  # fmt: skip
    assert r.status_code == 404


def test_demo_mode_assigns_the_pre_created_quest_instantly(
    client: TestClient, fake_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(get_engine()) as db:
        res = approve_pack(PACK_DIR, db)
    assert res.ok
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    h = _player(client)
    job = client.post("/quests/daily", headers=h).json()
    assert job["status"] == "ready"
    assert job["scenario_id"] == res.scenario_id


# ---- daily reuse, regeneration, no recognition gate, scan rewrite -------------------------------


@pytest.fixture
def graph_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """One entry per generation started (each lists the progress labels it reported)."""
    calls: list[list[str]] = []
    real = agent.build_quest_graph

    def spy(*args: object, **kwargs: object) -> object:
        labels: list[str] = []
        calls.append(labels)
        progress = args[4]

        def wrapped(label: str, extra: dict[str, object]) -> None:
            labels.append(label)
            progress(label, extra)  # type: ignore[operator]

        return real(*args[:4], wrapped, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(agent, "build_quest_graph", spy)
    return calls


def _daily_ready(client: TestClient, h: dict[str, str]) -> dict[str, object]:
    return _wait_ready(client, h, client.post("/quests/daily", headers=h).json()["id"])


def test_daily_twice_makes_no_second_generation(
    client: TestClient, fake_mode: None, graph_calls: list[list[str]]
) -> None:
    h = _player(client)
    first = _daily_ready(client, h)
    assert first["status"] == "ready" and len(graph_calls) == 1
    again = client.post("/quests/daily", headers=h).json()
    assert again["id"] == first["id"] and again["scenario_id"] == first["scenario_id"]
    assert len(graph_calls) == 1  # zero LLM work on the second call


def test_second_session_reuses_the_ready_quest(
    client: TestClient, fake_mode: None, graph_calls: list[list[str]]
) -> None:
    a, b = _player(client), _player(client)
    first = _daily_ready(client, a)
    second = client.post("/quests/daily", headers=b).json()
    assert second["status"] == "ready" and second["scenario_id"] == first["scenario_id"]
    assert second["id"] != first["id"]  # job rows stay per session
    assert len(graph_calls) == 1
    assert len(client.get("/quests", headers=b).json()) == 1
    # the reused quest is startable by its new owner
    r = client.post("/campaigns", json={"interests": [], "scenario_id": second["scenario_id"]},
                    headers=b)  # fmt: skip
    assert r.status_code == 201, r.text


def test_regenerate_builds_a_new_quest_that_replaces_today(
    client: TestClient, fake_mode: None, graph_calls: list[list[str]]
) -> None:
    h = _player(client)
    first = _daily_ready(client, h)
    new = client.post("/quests/daily?regenerate=true", headers=h).json()
    assert new["id"] != first["id"] and new["category"] == first["category"]
    done = _wait_ready(client, h, new["id"])
    assert done["status"] == "ready" and done["scenario_id"] != first["scenario_id"]
    assert len(graph_calls) == 2
    today = client.post("/quests/daily", headers=h).json()  # now returns the regenerated one
    assert today["id"] == new["id"] and len(graph_calls) == 2
    other = _player(client)  # later players get the newest ready quest
    assert client.post("/quests/daily", headers=other).json()["scenario_id"] == done["scenario_id"]


def test_no_recognition_gate_in_the_pipeline(
    client: TestClient, fake_mode: None, graph_calls: list[list[str]]
) -> None:
    assert not hasattr(agent, "call_node") and not hasattr(agent, "player_view_text")
    h = _player(client)
    assert _daily_ready(client, h)["status"] == "ready"
    labels = " ".join(graph_calls[0]).lower()
    assert "investigator" not in labels and "rewriting the disguise" not in labels


def _stub_scan(monkeypatch: pytest.MonkeyPatch, fail_times: int) -> list[int]:
    real = agent.approve_pack
    n: list[int] = []

    def stub(*args: object, **kwargs: object) -> object:
        n.append(1)
        if len(n) <= fail_times:
            return ApproveResult(False, reasons=["scan: real name in intro: 'Acme'"])
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(agent, "approve_pack", stub)
    return n


def _detail(job_id: str) -> dict[str, object]:
    import uuid as _uuid

    from financequest.db.models_personal import GenerationJob

    with Session(get_engine()) as db:
        j = db.get(GenerationJob, _uuid.UUID(job_id))
        assert j is not None
        return dict(j.detail or {})


def test_scan_failure_triggers_one_rewrite_then_succeeds(
    client: TestClient, fake_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_scan(monkeypatch, fail_times=1)
    h = _player(client)
    job = _daily_ready(client, h)
    assert job["status"] == "ready" and len(calls) == 2
    steps = [e["step"] for e in _detail(str(job["id"]))["log"]]  # type: ignore[attr-defined]
    assert "scan" in steps and "redraft" in steps


def test_scan_failing_twice_fails_the_job_and_keeps_its_log(
    client: TestClient, fake_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_scan(monkeypatch, fail_times=5)
    h = _player(client)
    job = _daily_ready(client, h)
    assert job["status"] == "failed" and len(calls) == agent.MAX_DRAFTS == 2
    detail = _detail(str(job["id"]))
    assert [e["step"] for e in detail["log"]].count("scan") == 2  # type: ignore[attr-defined]


def test_crash_persists_the_log_in_detail(
    client: TestClient, fake_mode: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: object, **k: object) -> object:
        raise RuntimeError("kaput")

    monkeypatch.setattr(agent, "approve_pack", boom)
    h = _player(client)
    job = _daily_ready(client, h)
    assert job["status"] == "failed"
    assert _detail(str(job["id"])).get("log") is not None


def test_documents_are_saved_to_storage(client: TestClient, fake_mode: None) -> None:
    from financequest.storage import get_storage

    h = _player(client)
    job = _daily_ready(client, h)
    st = get_storage()
    for name in ("case.md", "prices.csv", "manifest.json"):
        assert st.exists(f"quests/{job['id']}/{name}")


def test_a_failed_daily_quest_is_not_restarted_by_polling(
    client: TestClient, fake_mode: None
) -> None:
    """Regression: the page polls POST /quests/daily; a failed job used to start a new company on
    every poll. Only the regenerate button may start again."""
    from financequest.db.models_personal import GenerationJob

    h = _player(client)
    first = client.post("/quests/daily", headers=h).json()
    _wait_ready(client, h, first["id"])
    with Session(get_engine()) as s:
        job = s.get(GenerationJob, __import__("uuid").UUID(first["id"]))
        assert job is not None
        job.status, job.step = "failed", "Failed"
        s.add(job)
        s.commit()
    for _ in range(3):
        again = client.post("/quests/daily", headers=h).json()
        assert again["id"] == first["id"] and again["status"] == "failed"
    with Session(get_engine()) as s:
        n = len(s.exec(text("select id from generation_job")).all())
    assert n == 1  # nothing new was started
    regen = client.post("/quests/daily?regenerate=true", headers=h).json()
    assert regen["id"] != first["id"]
