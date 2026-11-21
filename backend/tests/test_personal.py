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
from financequest.refpack.approve import approve_pack

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
def fake_mode(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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
    assert client.post("/hero", json={"name": "Lena", "class": "analyst"}, headers=h).status_code == 201
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
