"""@spec: 002-anonymization-reid-gate"""

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from financequest.engine.disguise import (
    AmountFact,
    NumberPlan,
    fill_placeholders,
    find_stray_digits,
    round_sig,
)

BACKEND = Path(__file__).resolve().parent.parent


def make_series(prices: list[float], step: int = 3) -> list[tuple[int, float]]:
    return [(i * step, p) for i, p in enumerate(prices)]


@st.composite
def cases(draw):
    n = draw(st.integers(40, 80))
    prices = [draw(st.floats(5, 500)) for _ in range(n)]
    series = make_series(prices)
    idx = sorted(draw(st.sets(st.integers(0, n - 1), min_size=2, max_size=6)))
    return series, [series[i][0] for i in idx]


def test_max_price_capped_and_digits():
    series = make_series([1.5, 80.0, 123456.0, 90.0])
    plan = NumberPlan.build("case-a", 0, series, [0, 6, 9])
    shown = plan.transform_series(series)
    top = max(p.price for p in shown)
    assert top <= 10_000
    assert 100 <= top < 10_000


@settings(max_examples=60, deadline=None)
@given(cases(), st.integers(0, 5), st.text(min_size=1, max_size=8))
def test_moves_within_one_pp(case, salt, case_id):
    series, beats = case
    plan = NumberPlan.build(case_id, salt, series, beats)
    shown = plan.beat_prices(series)
    real = [Decimal(str(dict(series)[d])) for d in beats]
    for i in range(1, len(beats)):
        r = (real[i] / real[i - 1] - 1) * 100
        s = (shown[i] / shown[i - 1] - 1) * 100
        assert abs(r - s) <= 1
    assert max(p.price for p in plan.transform_series(series)) <= 10_000


@settings(max_examples=60, deadline=None)
@given(cases(), st.text(min_size=1, max_size=8))
def test_whole_weeks_and_gap_ratios(case, case_id):
    series, beats = case
    plan = NumberPlan.build(case_id, 0, series, beats)
    for i, u in enumerate(plan.gap_stretches):
        assert Decimal("0.7") <= u <= Decimal("1.3")
        gap = plan.story_days[i + 1] - plan.story_days[i]
        assert gap % 7 == 0 and gap >= 7
        real_gap = beats[i + 1] - beats[i]
        assert abs(gap - real_gap * float(u)) <= 3.5 + 7  # rounding to a week, min 7 floor


def test_series_beats_kept_and_monotonic():
    series = make_series([10 + i for i in range(30)])
    plan = NumberPlan.build("x", 1, series, [3, 30, 60])
    pts = plan.transform_series(series)
    days = [p.day for p in pts]
    assert days == sorted(set(days))
    by_day = {p.day: p.price for p in pts}
    for sd, price in zip(plan.story_days, plan.beat_prices(series), strict=True):
        assert by_day[sd] == price


def _dump(case_id: str, seed_env: str) -> str:
    code = (
        "import json;from financequest.engine.disguise import NumberPlan, AmountFact;"
        "from decimal import Decimal;"
        "s=[(i*3,10.0+i) for i in range(30)];"
        "f=[AmountFact('{A1}','revenue',Decimal('5000000')),AmountFact('{A2}','users',Decimal('42000'))];"
        f"print(json.dumps(NumberPlan.build({case_id!r},7,s,[0,15,60],f).to_dict()))"
    )
    env = {**os.environ, "PYTHONHASHSEED": seed_env}
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=BACKEND,
        env=env,
    ).stdout


def test_determinism_across_processes():
    a, b = _dump("boeing", "1"), _dump("boeing", "12345")
    assert a == b
    assert json.loads(a)["seed"] != json.loads(_dump("other", "1"))["seed"]


FACTS = [
    AmountFact("{A1}", "revenue", Decimal("8200000000")),
    AmountFact("{A2}", "cash_flow", Decimal("-1500000000")),
    AmountFact("{A3}", "debt", Decimal("4700000000")),
    AmountFact("{A4}", "users", Decimal("231000000")),
    AmountFact("{A5}", "raise", Decimal("25"), is_ratio=True),
]


def test_money_families_share_one_factor():
    plan = NumberPlan.build("c", 0, make_series([1.0, 2.0]), [0, 3], FACTS)
    assert plan.factor_for("revenue") == plan.factor_for("cash_flow") == plan.factor_for("debt")
    assert plan.factor_for("users") != plan.factor_for("revenue")
    # exact money ratios preserved
    r = Decimal("8200000000") * plan.factor_for("revenue")
    d = Decimal("4700000000") * plan.factor_for("debt")
    assert r / d == Decimal("8200000000") / Decimal("4700000000")


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.integers(1, 10**12), min_size=2, max_size=5),
    st.lists(st.integers(1, 10**9), min_size=1, max_size=3),
    st.text(min_size=1, max_size=6),
)
def test_amounts_two_sf_and_cap(money, other, case_id):
    fams = ["revenue", "profit", "cash", "debt", "equity"]
    facts = [AmountFact(f"{{A{i}}}", fams[i % 5], Decimal(v)) for i, v in enumerate(money)]
    facts += [AmountFact(f"{{B{i}}}", "users", Decimal(v)) for i, v in enumerate(other)]
    plan = NumberPlan.build(case_id, 0, make_series([1.0, 2.0]), [0, 3], facts)
    for f in facts:
        v = plan.scale_amount(f.family, f.value)
        assert v <= 10_000
        assert v == round_sig(v, 2)
    ratio = plan.scale_amount("pct", Decimal("25.5"), is_ratio=True)
    assert ratio == Decimal("25.5")
    money_top = max(plan.scale_amount(f.family, f.value) for f in facts[: len(money)])
    assert money_top <= 10_000


def test_round_sig():
    assert round_sig(Decimal("1234")) == Decimal("1200")
    assert round_sig(Decimal("0.01267")) == Decimal("0.013")
    assert round_sig(Decimal("-9960")) == Decimal("-10000")


def test_placeholders_and_stray_digits():
    plan = NumberPlan.build("c", 0, make_series([1.0, 2.0]), [0, 3], FACTS)
    vals = plan.fill_values(FACTS)
    out = fill_placeholders("Sales hit {A1}, a raise of {A5}.", vals)
    assert "{" not in out and vals["{A5}"] == "25"
    assert find_stray_digits("Sales hit {A1} after 12 days; Day 84 came") == []
    assert find_stray_digits("Sales hit {A1} and 77 users") == ["77"]
    assert find_stray_digits("77 users", allowed_numbers=["77"]) == []
