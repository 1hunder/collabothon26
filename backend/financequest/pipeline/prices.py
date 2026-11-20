"""Price pipeline: yfinance (or a bundled fixture) -> Parquet cache with gap flags.

Order of sources for one ticker and window: cache file, bundled fixture
(``fixtures/cases/prices/{ticker}.parquet``), then the injected downloader (yfinance by default).
"""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from financequest.pipeline.sources import FIXTURE_CASES

GAP_DAYS = 5  # calendar days between consecutive closes that counts as a gap
Downloader = Callable[[str, str, str], pd.DataFrame]  # ticker, start, end -> DataFrame[date, close]


@dataclass(frozen=True)
class PriceResult:
    ticker: str
    path: Path
    n_points: int
    first_date: str | None
    last_date: str | None
    gap_flags: list[dict[str, Any]]
    from_cache: bool


def yfinance_downloader(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        return pd.DataFrame({"date": [], "close": []})
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):  # newer yfinance returns one column per ticker
        close = close.iloc[:, 0]
    return pd.DataFrame(
        {"date": [d.date().isoformat() for d in close.index], "close": close.astype(float).values}
    )


def gap_flags(frame: pd.DataFrame, gap_days: int = GAP_DAYS) -> list[dict[str, Any]]:
    dates = [date.fromisoformat(d) for d in frame["date"]]
    return [
        {"from": a.isoformat(), "to": b.isoformat(), "days": (b - a).days}
        for a, b in zip(dates, dates[1:], strict=False)
        if (b - a).days > gap_days
    ]


def _cache_path(cache_dir: Path, ticker: str, start: str, end: str) -> Path:
    safe = ticker.replace("/", "_").replace("^", "_")
    return cache_dir / f"{safe}_{start}_{end}.parquet"


def _result(ticker: str, path: Path, frame: pd.DataFrame, cached: bool) -> PriceResult:
    return PriceResult(
        ticker=ticker,
        path=path,
        n_points=len(frame),
        first_date=str(frame["date"].iloc[0]) if len(frame) else None,
        last_date=str(frame["date"].iloc[-1]) if len(frame) else None,
        gap_flags=gap_flags(frame) if len(frame) else [],
        from_cache=cached,
    )


def fetch_prices(
    ticker: str,
    start: str,
    end: str,
    cache_dir: Path,
    downloader: Downloader | None = None,
    fixture_dir: Path | None = None,
) -> PriceResult:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, ticker, start, end)
    if path.exists():
        return _result(ticker, path, load_frame(path), True)
    fixture = (fixture_dir or FIXTURE_CASES / "prices") / f"{ticker}.parquet"
    if fixture.exists():
        full = load_frame(fixture)
        frame = full[(full["date"] >= start) & (full["date"] <= end)].reset_index(drop=True)
    else:
        frame = (downloader or yfinance_downloader)(ticker, start, end)
        frame = frame[["date", "close"]].reset_index(drop=True)
    frame.to_parquet(path, index=False)
    return _result(ticker, path, frame, False)


def load_frame(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def window_for(beat_dates: list[date], pad_days: int = 45) -> tuple[str, str]:
    return (
        (min(beat_dates) - timedelta(days=pad_days)).isoformat(),
        (max(beat_dates) + timedelta(days=pad_days)).isoformat(),
    )


def price_on_or_before(frame: pd.DataFrame, day: date) -> tuple[str, float] | None:
    """Close of the last trading day on or before ``day`` (None if the series starts later)."""
    dates = list(frame["date"])
    i = bisect.bisect_right(dates, day.isoformat()) - 1
    if i < 0:
        return None
    return str(dates[i]), float(frame["close"].iloc[i])


# ---- database glue -------------------------------------------------------
def fetch_case_prices(
    session: Any,
    case_id: str,
    cache_dir: Path,
    downloader: Downloader | None = None,
    fixture_dir: Path | None = None,
) -> PriceResult | None:
    """Fetch and cache the series for one case, record ``price_series`` and fill each beat's real
    price. A case with no ticker, no series or a beat without a price becomes ``skipped``."""
    from datetime import UTC, datetime

    from sqlmodel import select

    from financequest.db.models import PriceSeries, SourceBeat, SourceCase
    from financequest.pipeline.intake import parse_real_date
    from financequest.reid.batch import reevaluate_skip
    from financequest.reid.rules import SKIP_INCOMPLETE

    case = session.get(SourceCase, case_id)
    if case is None:
        return None
    beats = list(session.exec(select(SourceBeat).where(SourceBeat.case_id == case_id)))
    beats.sort(key=lambda b: b.idx)
    days = [parse_real_date(b.real_date or "") for b in beats]
    result: PriceResult | None = None
    missing = not case.ticker or any(d is None for d in days)
    if not missing:
        start, end = window_for([d for d in days if d is not None])
        result = fetch_prices(case.ticker or "", start, end, cache_dir, downloader, fixture_dir)
        frame = load_frame(result.path) if result.n_points else None
        for beat, day in zip(beats, days, strict=True):
            hit = price_on_or_before(frame, day) if frame is not None and day else None
            beat.real_price = hit[1] if hit else None
            session.add(beat)
            missing = missing or hit is None
        old = session.exec(select(PriceSeries).where(PriceSeries.case_id == case_id)).all()
        for o in old:
            session.delete(o)
        session.add(
            PriceSeries(
                case_id=case_id,
                ticker=case.ticker or "",
                first_date=result.first_date,
                last_date=result.last_date,
                n_points=result.n_points,
                gap_flags=result.gap_flags,
                cache_ref=str(result.path),
                fetched_at=datetime.now(UTC),
            )
        )
    if missing:
        case.status, case.skip_reason = "skipped", SKIP_INCOMPLETE
        session.add(case)
    session.flush()
    reevaluate_skip(session, case)
    session.commit()
    return result
