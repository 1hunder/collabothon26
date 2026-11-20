"""What-if rewind: the same function on the same real prices for fixed alternatives."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from financequest.campaign.portfolio import ZERO, Breakdown, compute


def _row(key: str, label: str, b: Breakdown, chosen: bool) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "final": str(b.final),
        "pnl_pct": str(b.pnl_pct),
        "hp_after": b.hp_after,
        "is_choice": chosen,
    }


def whatif_rows(
    budget: Decimal,
    action: str,
    amount: Decimal,
    r_company: Decimal,
    r_fund: Decimal | None,
    fees: Decimal = ZERO,
) -> list[dict[str, Any]]:
    """Don't / half / all (/ spread everything when a fund exists), plus a "Your choice" row when
    the player's choice matches none of the presets."""
    passive = action in ("dont_invest", "wait")
    presets: list[tuple[str, str, str, Decimal, bool]] = [
        ("dont", "Don't invest", "dont_invest", ZERO, passive),
        ("half", "Invest half", "invest", budget / 2, action == "invest" and amount == budget / 2),
        ("all", "Invest everything", "invest", budget, action == "invest" and amount == budget),
    ]
    if r_fund is not None:
        presets.append(
            (
                "spread",
                "Spread everything",
                "spread",
                budget,
                action == "spread" and amount == budget,
            )
        )
    rows = [
        _row(k, label, compute(budget, a, amt, r_company, r_fund, fees), chosen)
        for k, label, a, amt, chosen in presets
    ]
    if not any(r["is_choice"] for r in rows):
        mine = compute(budget, action, amount, r_company, r_fund, fees)
        rows.append(_row("choice", "Your choice", mine, True))
    return rows
