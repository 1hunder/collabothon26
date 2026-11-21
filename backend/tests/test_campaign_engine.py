"""@spec: 003-campaign-engine (pure engine: dice, rules, math, XP)"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from financequest.campaign import dice, focus, portfolio, rules, whatif, xp
from financequest.campaign.pack import Enc

PACK = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"


def _rows() -> list[portfolio.PriceRow]:
    with (PACK / "prices.csv").open(newline="") as fh:
        return [
            portfolio.PriceRow(
                date.fromisoformat(r["date"]),
                Decimal(r["open_usd"]),
                Decimal(r["high_usd"]),
                Decimal(r["low_usd"]),
                Decimal(r["close_usd"]),
            )
            for r in csv.DictReader(fh)
        ]


def test_enron_math_buy_next_open_end_close() -> None:
    buy, end = portfolio.buy_and_end(_rows(), date(2001, 10, 17), date(2001, 12, 31))
    assert (buy.day, buy.open) == (date(2001, 10, 18), Decimal("31.95"))
    assert (end.day, end.close) == (date(2001, 12, 31), Decimal("0.60"))
    r = portfolio.investment_return(buy.open, end.close)
    b = portfolio.compute(Decimal(1000), "invest", Decimal(400), r)
    assert b.final == Decimal("607.51")
    assert b.hp_after == 61 and b.hp_before == 100
    assert b.cash == Decimal("600.00") and b.value_now == Decimal("7.51")


def test_worked_example_minus_25_percent() -> None:
    b = portfolio.compute(Decimal(1000), "invest", Decimal(400), Decimal("-0.25"))
    assert (b.final, b.pnl, b.pnl_pct, b.hp_after) == (
        Decimal("900.00"), Decimal("-100.00"), Decimal("-10.0"), 90,
    )  # fmt: skip


def test_passive_and_spread_and_rounding() -> None:
    for a in ("dont_invest", "wait"):
        b = portfolio.compute(Decimal(1000), a, Decimal(0), Decimal("-0.9"))
        assert b.final == Decimal("1000.00") and b.hp_after == 100
    s = portfolio.compute(Decimal(1000), "spread", Decimal(1000), Decimal("-0.5"), Decimal("0.1"))
    assert s.final == Decimal("250.00") + Decimal("550.00")
    assert portfolio.hp_from_final(Decimal("605.00")) == 61  # .5 rounds up
    with pytest.raises(ValueError):
        portfolio.compute(Decimal(1000), "spread", Decimal(10), Decimal(0))


def test_same_share_same_percent_for_both_budgets() -> None:
    r = Decimal("-0.3")
    a = portfolio.compute(Decimal(1000), "invest", Decimal(500), r)
    g = portfolio.compute(Decimal(1200), "invest", Decimal(600), r)
    assert a.pnl_pct == g.pnl_pct


def test_whatif_rows_and_your_choice() -> None:
    r = Decimal("-0.25")
    rows = whatif.whatif_rows(Decimal(1000), "invest", Decimal(400), r, None)
    assert [x["key"] for x in rows] == ["dont", "half", "all", "choice"]
    assert rows[-1]["is_choice"] and rows[-1]["final"] == "900.00"
    rows = whatif.whatif_rows(Decimal(1000), "wait", Decimal(0), r, Decimal("0.1"))
    assert [x["key"] for x in rows] == ["dont", "half", "all", "spread"]
    assert [x["is_choice"] for x in rows] == [True, False, False, False]


def test_dice_deterministic_and_bounds() -> None:
    a = dice.roll(42, "ENC", 0, 12)
    assert a == dice.roll(42, "ENC", 0, 12)
    assert all(1 <= d <= 20 for s in range(200) for d in dice.dice_values(s, "k", 0, 2))
    assert a.total == a.used + 2


def test_nat20_nat1_and_dc() -> None:
    assert dice.is_success(20, 18) and not dice.is_success(1, 5)
    assert dice.is_success(16, 18) and not dice.is_success(15, 18)
    seeds20 = next(s for s in range(5000) if dice.roll(s, "k", 0, 18).nat20)
    assert dice.roll(seeds20, "k", 0, 18).result == "success"
    seed1 = next(s for s in range(5000) if dice.roll(s, "k", 0, 2).nat1)
    assert dice.roll(seed1, "k", 0, 2).result == "setback"


def test_advantage_takes_higher() -> None:
    for s in range(100):
        r = dice.roll(s, "k", 0, 12, advantage=True)
        assert len(r.dice) == 2 and r.used == max(r.dice)
        assert r.total == r.used + 2


def test_dc_manifest_else_table() -> None:
    mk = lambda dc, kind: Enc("e", "t", "G0", "library", dc, kind, "c", "")  # noqa: E731
    assert rules.encounter_dc(mk(14, None)) == 14
    assert [rules.encounter_dc(mk(None, k)) for k in rules.DC_TABLE] == [8, 12, 15, 18]


def test_news_trigger() -> None:
    f = rules.should_fire_news
    assert not f(False, 5, None) and f(False, 6, None)
    assert f(False, 3, "market_square") and not f(False, 2, "market_square")
    assert not f(False, 3, "library") and not f(True, 9, "market_square")
    assert rules.counts_as_turn("move") and rules.counts_as_turn("action")
    assert not rules.counts_as_turn("buddy")


def test_roll_options_classes() -> None:
    assert rules.roll_options(False, "analyst", 1, False).options == ("reroll", "accept")
    assert rules.roll_options(False, "analyst", 0, False).final
    assert rules.roll_options(False, "guardian", 1, False).options == ("continue",)
    assert rules.roll_options(True, "analyst", 1, False).final


def test_name_rules() -> None:
    assert rules.normalize_name("  Lena ") == "Lena"
    assert rules.normalize_name("O'Neil-3") == "O'Neil-3"
    for bad in ("a", "   ", "x" * 21, "Bad!", "no<script>"):
        assert rules.normalize_name(bad) is None


def test_xp_clamp_quote_and_loss_words() -> None:
    rubric = xp.DEFAULT_RUBRIC
    raw = [
        xp.RawScore("Evidence quality", 99, "Clear sourcing.", "cash flow"),
        xp.RawScore("Risk identification", 10, "You lost points by losing money.", "cash flow"),
        xp.RawScore("Acknowledging uncertainty", 5, "Fine.", "invented quote"),
    ]
    cats, total = xp.validate_scores(rubric, raw, "I noticed cash flow was negative")
    assert cats[0]["score"] == 25 and cats[0]["quote"] == "cash flow"
    assert cats[1]["rationale"] == xp.NEUTRAL
    assert cats[2]["quote"] == "" and cats[2]["rationale"] == xp.NEUTRAL
    assert total == 25 + 10 + 5 and len(cats) == 5 and sum(m for _, m in rubric) == 100


def test_focus_and_items() -> None:
    assert focus.starting_focus(set()) == 3 and focus.starting_focus({"calm_compass"}) == 4
    owned: set[str] = set()
    order = []
    while (n := focus.next_item(owned)) is not None:
        order.append(n)
        owned.add(n)
    assert order == ["ratio_lens", "rumour_ledger", "calm_compass"]
