"""Decisions throughout the campaign: the ledger math and the plain reading of a decision."""

from decimal import Decimal

import pytest

from financequest.campaign import ledger
from financequest.campaign.pack import Row
from financequest.campaign.rules import parse_decision

D = Decimal


def row(day: int, close: str) -> Row:
    c = D(close)
    return Row(day, f"d{day}", c, c, c, c)


ROWS = (row(0, "10"), row(5, "20"), row(30, "5"), row(90, "8"))


def test_a_decision_fills_at_the_latest_price_the_player_can_see() -> None:
    assert ledger.fill_row(ROWS, 4).day == 0  # day 4: the board shows day 0
    assert ledger.fill_row(ROWS, 5).day == 5
    assert ledger.fill_row(ROWS, 60).day == 30
    assert ledger.fill_row(ROWS, -3).day == 0  # before the first row: the first row


def test_buy_sell_hold_move_cash_and_shares_and_never_overspend() -> None:
    pos = ledger.Position(D(1000))
    buy = ledger.execute(pos, "buy", D(400), ROWS[0])
    assert (buy.after.cash, buy.after.shares) == (D(600), D(40))
    over = ledger.execute(buy.after, "buy", D(5000), ROWS[1])
    assert over.amount == D(600) and over.after.cash == 0
    sell = ledger.execute(buy.after, "sell", D(400), ROWS[1])  # 40 shares at 20 = 800 held
    assert sell.amount == D(400) and sell.after.shares == D(20)
    hold = ledger.execute(sell.after, "hold", D(0), ROWS[2])
    assert hold.after == sell.after and hold.amount == 0


def test_selling_everything_leaves_no_dust() -> None:
    pos = ledger.Position(D(0), D(1) / D(3))
    out = ledger.execute(pos, "sell", D("6.6666"), ROWS[1])
    assert out.after.shares == 0


def test_amounts_resolve_from_euros_or_a_portion_and_are_clamped() -> None:
    pos = ledger.Position(D(1000), D(10))  # 10 shares at 20 = 200
    assert ledger.resolve_amount("buy", pos, D(20), None, "half") == D(500)
    assert ledger.resolve_amount("buy", pos, D(20), 2500, None) == D(1000)
    assert ledger.resolve_amount("sell", pos, D(20), None, "all") == D(200)
    assert ledger.resolve_amount("sell", pos, D(20), 50, None) == D(50)
    assert ledger.resolve_amount("hold", pos, D(20), 50, "all") == 0


def test_the_result_counts_every_decision_and_the_effects_add_up_to_the_profit() -> None:
    budget, end = D(1000), ROWS[-1].close  # horizon close 8
    pos = ledger.Position(budget)
    fills = []
    steps = (("buy", D(500), ROWS[0]), ("sell", D(400), ROWS[1]), ("buy", D(300), ROWS[2]))
    for action, amount, r in steps:
        f = ledger.execute(pos, action, amount, r)
        fills.append(f)
        pos = f.after
    res = ledger.result(budget, pos, end)
    effects = sum(ledger.effect(f.action, f.amount, f.shares, end) for f in fills)
    assert res.final == res.cash + res.value_now
    assert abs(effects - res.pnl) < D("0.02")
    # the buy at 10 then partial sell at 20 then buy at 5, valued at 8:
    # 50 shares, sold 20 -> 30 left, +60 -> 90 shares; cash 1000-500+400-300 = 600
    assert res.cash == D(600) and res.value_now == D(720) and res.final == D(1320)


def test_whatif_rows_put_the_players_path_next_to_simple_alternatives() -> None:
    budget = D(1000)
    mine = ledger.result(budget, ledger.Position(D(500), D(50)), D(8))
    rows = ledger.whatif_rows(budget, mine, D(10), D(5), D(8))
    keys = [r["key"] for r in rows]
    assert keys == ["dont", "first", "all", "choice"]
    assert rows[0]["final"] == "1000.00"
    assert rows[1]["final"] == "800.00"  # all at 10, valued at 8
    assert rows[2]["final"] == "1600.00"  # all at 5, valued at 8
    assert rows[3]["is_choice"] and rows[3]["final"] == "900.00"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I'll put 300 coins in, the guild report looks solid", ("buy", 300, None)),
        ("Invest everything", ("buy", None, "all")),
        ("Sell half, the news scares me", ("sell", None, "half")),
        ("I take some out", ("sell", None, "some")),
        ("I wait and watch", ("hold", None, None)),
        ("I don't invest yet", ("hold", None, None)),
        ("Keep my coins for now", ("hold", None, None)),
        ("buy €250", ("buy", 250, None)),
        ("What does the ledger say?", (None, None, None)),
    ],
)
def test_a_written_decision_reads_as_buy_sell_or_hold(text: str, expected: tuple) -> None:
    assert parse_decision(text) == expected
