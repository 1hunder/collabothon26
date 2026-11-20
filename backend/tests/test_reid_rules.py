"""@spec: 002-anonymization-reid-gate"""

import pytest

from financequest.config import Settings
from financequest.reid.match import MatchTargets, is_correct_guess, normalise
from financequest.reid.rules import (
    REASON_UNREADABLE,
    CaseFacts,
    GuesserResult,
    case_fame,
    evaluate_attempt,
    fame,
    is_untagged,
    route_attempt,
    size_band,
    skip_reason,
)
from financequest.report.stats import CaseOutcome, compute_stats

T = MatchTargets(
    company="Alphabet Inc.",
    ticker="GOOGL",
    parent="Holding Group plc",
    subsidiaries=("YouTube",),
    former_names=("Google Corp",),
)
S = Settings(_env_file=None)
START = (2024, 6)


def test_normalise():
    assert normalise("Siemens AG") == "siemens"
    assert normalise("Royal Dutch N.V.") == "royal dutch"
    assert normalise("  The Acme, Inc. ") == "acme"
    assert normalise("Inc") == "inc"


@pytest.mark.parametrize(
    "guess,ok",
    [
        ("alphabet", True),
        ("ALPHABET INC", True),
        ("googl", True),
        ("Holding Group", True),
        ("YouTube LLC", True),
        ("google", True),
        ("goog", False),
        ("Google Corp", True),
        ("Alphabet Inc. (Google)", True),
        ("Nvidia", False),
        ("", False),
        ("a", False),
    ],
)
def test_matching(guess, ok):
    assert is_correct_guess(guess, T) is ok


def test_short_names_exact_only():
    t = MatchTargets(company="Ab")
    assert is_correct_guess("AB Inc", t)
    assert not is_correct_guess("Abacus", t)


def g(top=("Nope",), y=None, m=None, c=0, r=4, err=False):
    return GuesserResult(top, y, m, c, r, err)


_DEFAULT_WEB = (g(),)


def verdict(mem, web=_DEFAULT_WEB, scan=True):
    return evaluate_attempt(
        scan_passed=scan, memory_round=mem, web_round=web, targets=T, real_start=START, settings=S
    )


def test_verdict_pass_and_scan_fail():
    assert verdict([g(), g()]).passed
    v = verdict([g()], scan=False)
    assert v.status == "failed" and not v.recognised


def test_verdict_top3_either_round():
    assert verdict([g(top=("x", "y", "Alphabet"))]).recognised
    v = verdict([g()], web=[g(top=("Alphabet",))])
    assert v.status == "failed" and v.recognised
    assert verdict([g(top=("a", "b", "c", "Alphabet"))]).passed  # fourth is outside top 3


@pytest.mark.parametrize(
    "y,m,c,fails",
    [
        (2024, 3, 30, True),
        (2024, 9, 30, True),
        (2024, 2, 30, False),
        (2024, 10, 30, False),
        (2024, 6, 29, False),
        (2024, 6, 30, True),
        (2023, 12, 80, False),
        (2024, 3, 29, False),
    ],
)
def test_start_window_and_confidence(y, m, c, fails):
    assert (verdict([g(y=y, m=m, c=c)]).status == "failed") is fails


def test_readability_boundary():
    assert verdict([g(r=3), g(r=3)]).passed
    v = verdict([g(r=3), g(r=2)], web=())
    assert v.status == "failed" and v.reasons == (REASON_UNREADABLE,)
    assert verdict([g(r=2), g(r=4)]).passed  # average 3.0


def test_guesser_error_never_passes():
    assert verdict([g(), g(err=True)]).status == "error"
    assert verdict([g(top=("Alphabet",)), g(err=True)]).status == "failed"


def test_web_required_to_pass():
    with pytest.raises(ValueError):
        verdict([g()], web=None)
    assert verdict([g(top=("Alphabet",))], web=None).status == "failed"


def test_routing():
    ok, bad, err = verdict([g()]), verdict([g(top=("Alphabet",))]), verdict([g(err=True)])
    assert route_attempt(1, ok) == "approved"
    assert route_attempt(1, bad) == "retry" and route_attempt(2, bad) == "retry"
    assert route_attempt(3, bad) == "rejected"
    assert route_attempt(1, err) == "error"


def case(**kw):
    base = dict(
        lesson="l",
        identifying_terms=("x",),
        beat_prices=(1.0, 2.0),
        market_cap_eur=5e9,
        is_us_listed=True,
        country="US",
        story_year=2020,
    )
    return CaseFacts(**{**base, **kw})


def test_skip_rules():
    assert skip_reason(case()) is None
    assert skip_reason(case(lesson=" ")) == "Skipped: incomplete case"
    assert skip_reason(case(identifying_terms=())) is not None
    assert skip_reason(case(beat_prices=(1.0, None))) is not None
    assert skip_reason(case(beat_prices=(1.0,))) is not None
    assert skip_reason(case(beat_prices=(1.0,) * 7)) is not None
    assert skip_reason(case(beat_prices=(1.0,) * 6)) is None


@pytest.mark.parametrize(
    "cap,untagged",
    [
        (2.1e9, True),
        (1.9e9, True),
        (2.11e9, False),
        (1.89e9, False),
        (10.5e9, True),
        (9.5e9, True),
        (10.6e9, False),
        (5e9, False),
    ],
)
def test_band_boundaries(cap, untagged):
    assert is_untagged(case(market_cap_eur=cap)) is untagged


def test_untagged_missing():
    assert is_untagged(case(country=""))
    assert is_untagged(case(story_year=None))
    assert case_fame(case(is_us_listed=None)) is None


def test_size_and_fame():
    assert [size_band(x) for x in (1.99e9, 2e9, 10e9, 10.01e9)] == ["small", "mid", "mid", "large"]
    assert fame("large", True) == "high"
    assert fame("large", False) == "medium" and fame("mid", True) == "medium"
    assert fame("mid", False) == "low" and fame("small", True) == "low"
    assert case_fame(case(market_cap_eur=50e9)) == "high"


def test_stats_summary_exact():
    outs = [
        CaseOutcome("a", "approved", False, "low", "small"),
        CaseOutcome("b", "rejected", True, "high", "large"),
        CaseOutcome("c", "approved", True, "low", "small"),
        CaseOutcome("d", "skipped"),
    ]
    st = compute_stats(outs)
    assert st.checked == 3 and st.skipped == 1
    assert st.summary_line == "3 cases checked · 67% recognised on first attempt · 2 approved (67%)"
    assert st.approval_by_fame["low"].pct == 100 and st.approval_by_fame["high"].pct == 0
    assert st.approval_by_size["small"].count == 2
    assert compute_stats([]).summary_line == (
        "0 cases checked · 0% recognised on first attempt · 0 approved (0%)"
    )
