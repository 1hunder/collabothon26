"""The investment ledger: decisions the player makes throughout the campaign, executed at once.

Pure Decimal math over the pack's real price rows (engine-only). A decision fills at the close of
the latest trading day up to its story day: a price the player can already see on the board, so
the purse never leaks a future price. The result is valued at the horizon close, and every
decision's own effect is computed so that the effects add up exactly to the profit or loss.

Share counts and fill prices are real-price figures and never leave the engine; responses carry
euro amounts only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from financequest.campaign.pack import Row
from financequest.campaign.portfolio import ZERO, hp_from_final, q_cents, q_pct

ACTIONS = ("buy", "sell", "hold")
PORTIONS = {"all": Decimal(1), "most": Decimal("0.75"), "half": Decimal("0.5"),
            "some": Decimal("0.25"), "quarter": Decimal("0.25")}  # fmt: skip


def fill_row(rows: Sequence[Row], story_day: int) -> Row:
    """The latest trading day on or before ``story_day`` (else the first one)."""
    if not rows:
        raise ValueError("no prices")
    before = [r for r in rows if r.day <= story_day]
    return before[-1] if before else rows[0]


@dataclass(frozen=True)
class Position:
    cash: Decimal
    shares: Decimal = ZERO

    def value(self, price: Decimal) -> Decimal:
        return self.shares * price


@dataclass(frozen=True)
class Fill:
    action: str
    amount: Decimal  # euros moved: spent on a buy, received on a sell (0 for hold)
    shares: Decimal  # +bought / -sold
    price: Decimal
    fill_day: int
    after: Position


def resolve_amount(
    action: str, pos: Position, price: Decimal, amount_eur: int | None, portion: str | None
) -> Decimal:
    """The euro amount a decision asks for, clamped to what the player has: cash for a buy, the
    position's current value for a sell."""
    if action == "hold":
        return ZERO
    cap = pos.cash if action == "buy" else pos.value(price)
    if portion and portion in PORTIONS:
        want = cap * PORTIONS[portion]
    elif amount_eur is not None:
        want = Decimal(max(0, int(amount_eur)))
    else:
        want = ZERO
    return q_cents(min(max(want, ZERO), cap))


def execute(pos: Position, action: str, amount: Decimal, row: Row) -> Fill:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action}")
    price = row.close
    if price <= 0:
        raise ValueError("price must be positive")
    if action == "hold" or amount <= 0:
        return Fill("hold" if action == "hold" else action, ZERO, ZERO, price, row.day, pos)
    if action == "buy":
        amount = min(amount, pos.cash)
        shares = amount / price
        return Fill("buy", amount, shares, price, row.day, Position(pos.cash - amount, pos.shares + shares))
    shares = min(amount / price, pos.shares)  # sell
    proceeds = q_cents(shares * price)
    left = pos.shares - shares
    if left * price < Decimal("0.005"):  # selling (almost) everything: no dust left behind
        shares, left = pos.shares, ZERO
        proceeds = q_cents(shares * price)
    return Fill("sell", proceeds, -shares, price, row.day, Position(pos.cash + proceeds, left))


def effect(fill_action: str, amount: Decimal, shares: Decimal, end_close: Decimal) -> Decimal:
    """What one decision did to the final result versus not making it: a buy gains or loses
    what the shares did until the horizon; a sell avoids (or misses) exactly that."""
    if fill_action == "buy":
        return shares * end_close - amount
    if fill_action in ("sell", "loss"):  # a loss removes coins at the board price, paying nothing out
        return amount + shares * end_close  # shares is negative
    return ZERO


@dataclass(frozen=True)
class LedgerResult:
    budget: Decimal
    cash: Decimal
    invested: Decimal  # money still in the company: budget minus cash
    value_now: Decimal
    final: Decimal
    pnl: Decimal
    pnl_pct: Decimal
    hp_before: int
    hp_after: int


def result(
    budget: Decimal, pos: Position, end_close: Decimal,
    loan_principal: Decimal = ZERO, loan_repay: Decimal = ZERO,
) -> LedgerResult:
    """The loan's principal sits in ``pos.cash`` (it was paid in); its repayment comes off the
    final value. ``invested`` is what went into the company: the budget plus the borrowed money
    minus the cash left."""
    value_now = q_cents(pos.value(end_close))
    cash = q_cents(pos.cash)
    final = q_cents(cash + value_now - loan_repay)
    pnl = final - q_cents(budget)
    return LedgerResult(
        budget=q_cents(budget), cash=cash, invested=q_cents(budget + loan_principal - pos.cash),
        value_now=value_now, final=final, pnl=pnl,
        pnl_pct=q_pct(pnl / budget * 100) if budget else ZERO,
        hp_before=hp_from_final(budget), hp_after=hp_from_final(final),
    )  # fmt: skip


def _row(key: str, label: str, r: LedgerResult, mine: bool) -> dict[str, object]:
    return {"key": key, "label": label, "final": str(r.final), "pnl_pct": str(r.pnl_pct),
            "hp_after": r.hp_after, "is_choice": mine}  # fmt: skip


def whatif_rows(
    budget: Decimal, mine: LedgerResult, first_price: Decimal | None, decision_price: Decimal,
    end_close: Decimal,
) -> list[dict[str, object]]:
    """The player's path next to simple alternatives on the same real prices: never investing,
    everything at the first decision and held, everything on decision day and held."""
    never = result(budget, Position(budget), end_close)

    def all_in(price: Decimal) -> LedgerResult:  # never borrows: the loan is the player's own path
        return result(budget, Position(ZERO, budget / price), end_close)

    rows = [_row("dont", "Never invest", never, False)]
    if first_price is not None and first_price != decision_price:
        rows.append(_row("first", "Everything at your first decision, then hold", all_in(first_price), False))
    rows.append(_row("all", "Everything on decision day, then hold", all_in(decision_price), False))
    rows.append(_row("choice", "Your decisions", mine, True))
    return rows
