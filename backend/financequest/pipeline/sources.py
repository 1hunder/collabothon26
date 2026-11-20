"""Data-source interfaces for the offline pipeline.

The news provider is undecided (David owns the choice), so only a fixture-backed ``NewsSource`` and
a stub ``MetadataSource`` exist. Both are Protocols: a real provider plugs in without touching the
pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

FIXTURE_CASES = Path(__file__).resolve().parent.parent / "fixtures" / "cases"


@dataclass(frozen=True)
class NewsItem:
    date: str  # ISO date as written in the source
    headline: str
    facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompanyMetadata:
    ticker: str
    name: str | None = None
    exchange: str | None = None
    country: str | None = None
    currency: str | None = None
    market_cap_local: float | None = None


class MetadataSource(Protocol):
    def get(self, ticker: str) -> CompanyMetadata | None: ...


class NewsSource(Protocol):
    def news(self, ticker: str, start: str, end: str) -> list[NewsItem]: ...


class StubMetadataSource:
    """Knows nothing; every lookup is a miss (tags then stay untagged)."""

    def get(self, ticker: str) -> CompanyMetadata | None:
        return None


class FixtureNewsSource:
    """Reads ``{ticker: [{date, headline, facts}]}`` from a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or FIXTURE_CASES / "news.json"
        self._data: dict[str, list[dict[str, Any]]] | None = None

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if self._data is None:
            self._data = (
                json.loads(self._path.read_text(encoding="utf-8")) if self._path.exists() else {}
            )
        return self._data

    def news(self, ticker: str, start: str, end: str) -> list[NewsItem]:
        items = self._load().get(ticker, [])
        return [
            NewsItem(i["date"], i["headline"], tuple(i.get("facts", [])))
            for i in items
            if start <= i["date"] <= end
        ]
