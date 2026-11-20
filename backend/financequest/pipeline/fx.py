"""Market cap to EUR at the story year. A static table of approximate yearly averages is enough
for the three size bands; the rate used is returned so the caller can record it."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Units of currency per 1 EUR; anchor years, nearest year wins. Approximate.
RATES_PER_EUR: dict[str, dict[int, str]] = {
    "EUR": {2000: "1"},
    "USD": {
        2000: "0.92", 2003: "1.13", 2005: "1.25", 2008: "1.47", 2010: "1.33", 2013: "1.33",
        2015: "1.11", 2018: "1.18", 2020: "1.14", 2022: "1.05", 2024: "1.08", 2025: "1.13",
    },
    "GBP": {2000: "0.61", 2010: "0.86", 2020: "0.89", 2024: "0.85"},
    "CHF": {2000: "1.56", 2010: "1.38", 2020: "1.07", 2024: "0.95"},
    "JPY": {2000: "99", 2010: "116", 2020: "122", 2024: "164"},
}  # fmt: skip


@dataclass(frozen=True)
class FxResult:
    eur: Decimal
    rate: Decimal  # currency units per EUR
    currency: str
    year_used: int


def rate_per_eur(currency: str, year: int) -> tuple[Decimal, int]:
    table = RATES_PER_EUR.get(currency.upper())
    if not table:
        raise KeyError(f"no static FX rate for {currency!r}")
    nearest = min(table, key=lambda y: abs(y - year))
    return Decimal(table[nearest]), nearest


def to_eur(amount: Decimal | float | str, currency: str, year: int) -> FxResult:
    rate, used = rate_per_eur(currency, year)
    return FxResult(Decimal(str(amount)) / rate, rate, currency.upper(), used)
