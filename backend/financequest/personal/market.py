"""Deterministic market step of a personal quest: price history -> lesson windows -> prices.csv.

Code, not the model, picks the dates. A window is built around a sharp multi-day move (a "shock"):

- G0 intro: about ``INTRO_TRADING_DAYS`` trading days before the shock (the player starts here)
- G1 disclosure: the shock day (the news event the game fires)
- G2 decision: the next trading day after the shock (the player decides here)
- horizon: about ``HORIZON_TRADING_DAYS`` trading days after the decision (the outcome)

The prices CSV uses the reference-pack column layout, so ``refpack approve`` can read it.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

INTRO_TRADING_DAYS = 55
HORIZON_TRADING_DAYS = 60
MOVE_DAYS = 5
MIN_MOVE = 0.15  # |5-day move| that counts as a shock
MIN_SPACING_DAYS = 365  # candidates at least a year apart
HISTORY_START = "2005-01-01"
HISTORY_END = "2024-06-30"  # keep the horizon inside a period the model can research

OhlcDownloader = Callable[[str, str, str], pd.DataFrame]


@dataclass(frozen=True)
class Window:
    index: int
    intro: date
    shock: date
    decision: date
    buy: date
    horizon: date
    move_pct: float  # 5-day move into the shock, percent
    after_pct: float  # decision close -> horizon close, percent

    def describe(self) -> str:
        direction = "fell" if self.move_pct < 0 else "rose"
        return (
            f"[{self.index}] intro {self.intro}, shock {self.shock} (stock {direction} "
            f"{abs(self.move_pct):.0f}% over {MOVE_DAYS} trading days), decision {self.decision}, "
            f"horizon {self.horizon} (then {self.after_pct:+.0f}% to the horizon)"
        )


def yfinance_ohlc(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    def col(name: str) -> pd.Series:
        c = raw[name]
        return c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c

    return pd.DataFrame(
        {
            "date": [d.date().isoformat() for d in raw.index],
            "open": col("Open").astype(float).values,
            "high": col("High").astype(float).values,
            "low": col("Low").astype(float).values,
            "close": col("Close").astype(float).values,
            "volume": col("Volume").astype(float).values,
        }
    ).dropna()


def load_history(
    ticker: str, cache_dir: Path, downloader: OhlcDownloader | None = None
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace("/", "_").replace("^", "_")
    path = cache_dir / f"ohlc_{safe}_{HISTORY_START}_{HISTORY_END}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    frame = (downloader or yfinance_ohlc)(ticker, HISTORY_START, HISTORY_END)
    frame = frame.reset_index(drop=True)
    if len(frame):
        frame.to_parquet(path, index=False)
    return frame


def find_windows(frame: pd.DataFrame, limit: int = 5) -> list[Window]:
    """Up to ``limit`` shock windows: the sharpest drops first, then the sharpest jumps."""
    n = len(frame)
    if n < INTRO_TRADING_DAYS + MOVE_DAYS + HORIZON_TRADING_DAYS + 5:
        return []
    close = frame["close"].to_numpy()
    dates = [date.fromisoformat(d) for d in frame["date"]]
    lo, hi = INTRO_TRADING_DAYS + MOVE_DAYS, n - HORIZON_TRADING_DAYS - 2
    moves = [(i, close[i] / close[i - MOVE_DAYS] - 1.0) for i in range(lo, hi)]
    drops = sorted((m for m in moves if m[1] <= -MIN_MOVE), key=lambda m: m[1])
    jumps = sorted((m for m in moves if m[1] >= MIN_MOVE), key=lambda m: -m[1])
    picked: list[int] = []
    for pool, quota in ((drops, limit - 1), (jumps, 1)):
        taken = 0
        for i, _ in pool:
            if taken >= quota or len(picked) >= limit:
                break
            if all(abs((dates[i] - dates[j]).days) >= MIN_SPACING_DAYS for j in picked):
                picked.append(i)
                taken += 1
    out: list[Window] = []
    for k, i in enumerate(picked):
        # the shock day is the sharpest single day inside the 5-day move
        days = range(i - MOVE_DAYS + 1, i + 1)
        shock = max(days, key=lambda d: abs(close[d] / close[d - 1] - 1.0))
        dec, buy = shock + 1, shock + 2
        hor = min(dec + HORIZON_TRADING_DAYS, n - 1)
        out.append(
            Window(
                index=k,
                intro=dates[shock - INTRO_TRADING_DAYS],
                shock=dates[shock],
                decision=dates[dec],
                buy=dates[buy],
                horizon=dates[hor],
                move_pct=round((close[i] / close[i - MOVE_DAYS] - 1.0) * 100, 1),
                after_pct=round((close[hor] / close[dec] - 1.0) * 100, 1),
            )
        )
    return out


def write_prices_csv(frame: pd.DataFrame, window: Window, path: Path, ticker: str) -> int:
    """Slice from a few days before the intro to the horizon, in the reference-pack layout."""
    start = window.intro.isoformat()
    sub = frame[(frame["date"] >= start) & (frame["date"] <= window.horizon.isoformat())]
    first = frame.index[frame["date"] >= start][0]
    lead = frame.iloc[max(0, first - 5) : first]
    rows = pd.concat([lead, sub])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "open_usd", "high_usd", "low_usd", "close_usd", "volume_shares",
                    "source_id", "source_url"])  # fmt: skip
        for r in rows.itertuples(index=False):
            w.writerow([r.date, f"{r.open:.4f}", f"{r.high:.4f}", f"{r.low:.4f}",
                        f"{r.close:.4f}", int(r.volume), "yfinance",
                        f"https://finance.yahoo.com/quote/{ticker}/history"])  # fmt: skip
    return len(rows)


def price_summary(frame: pd.DataFrame, window: Window) -> str:
    """A short real-price digest for the research agent (it never sees future-only prices it
    could not research anyway; this is the reference data, server-side)."""
    sub = frame[(frame["date"] >= window.intro.isoformat())
                & (frame["date"] <= window.horizon.isoformat())]  # fmt: skip
    pts = sub.iloc[:: max(1, len(sub) // 12)]
    return ", ".join(f"{r.date}: {r.close:.2f}" for r in pts.itertuples(index=False))
