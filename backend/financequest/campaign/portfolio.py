"""Portfolio math on Decimal. Only recorded prices count; no exchange rates in the quest (currency note)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
PCT = Decimal("0.1")
ZERO = Decimal(0)
CURRENCY_NOTE = "Every figure here is in gold pieces (gp)."
ACTIONS = ("invest", "spread", "dont_invest", "wait")


def q_cents(x: Decimal) -> Decimal:
    return x.quantize(CENTS, ROUND_HALF_UP)


def q_pct(x: Decimal) -> Decimal:
    return x.quantize(PCT, ROUND_HALF_UP)


def hp_from_final(final: Decimal) -> int:
    return int((final / 10).quantize(Decimal(1), ROUND_HALF_UP))


def investment_return(buy_open: Decimal, end_close: Decimal) -> Decimal:
    """r = close(horizon_end) / open(buy day) - 1"""
    if buy_open <= 0:
        raise ValueError("buy price must be positive")
    return end_close / buy_open - 1


@dataclass(frozen=True)
class PriceRow:
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def buy_and_end(
    rows: list[PriceRow], decision_date: date, horizon_end: date
) -> tuple[PriceRow, PriceRow]:
    """Buy at the open of the first trading day after the decision date; end at horizon close."""
    buy = next((r for r in rows if r.day > decision_date), None)
    if buy is None:
        raise ValueError("no trading day after the decision date")
    end = next((r for r in reversed(rows) if r.day <= horizon_end), None)
    if end is None or end.day < buy.day:
        raise ValueError("horizon ends before the buying day")
    return buy, end


@dataclass(frozen=True)
class Breakdown:
    budget: Decimal
    cash: Decimal
    invested: Decimal
    value_now: Decimal
    fees: Decimal
    final: Decimal
    pnl: Decimal
    pnl_pct: Decimal
    hp_before: int
    hp_after: int

    def as_strings(self) -> dict[str, str | int]:
        return {
            "budget": str(self.budget),
            "cash": str(self.cash),
            "invested": str(self.invested),
            "value_now": str(self.value_now),
            "fees": str(self.fees),
            "final": str(self.final),
            "pnl": str(self.pnl),
            "pnl_pct": str(self.pnl_pct),
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
        }


def compute(
    budget: Decimal,
    action: str,
    amount: Decimal,
    r_company: Decimal,
    r_fund: Decimal | None = None,
    fees: Decimal = ZERO,
) -> Breakdown:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action}")
    if action in ("dont_invest", "wait"):
        amount = ZERO
    if not ZERO <= amount <= budget:
        raise ValueError("amount outside the budget")
    if action == "spread":
        if r_fund is None:
            raise ValueError("spread needs a fund series")
        half = amount / 2
        value = half * (1 + r_company) + half * (1 + r_fund)
    else:
        value = amount * (1 + r_company)
    value_now = q_cents(value)
    cash = q_cents(budget - amount)
    final = q_cents(cash + value_now - fees)
    pnl = final - q_cents(budget)
    pnl_pct = q_pct(pnl / budget * 100) if budget else ZERO
    return Breakdown(
        budget=q_cents(budget),
        cash=cash,
        invested=q_cents(amount),
        value_now=value_now,
        fees=q_cents(fees),
        final=final,
        pnl=q_cents(pnl),
        pnl_pct=pnl_pct,
        hp_before=hp_from_final(budget),
        hp_after=hp_from_final(final),
    )
