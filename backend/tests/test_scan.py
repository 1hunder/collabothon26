"""@spec: 002-anonymization-reid-gate"""

import pytest

from financequest.reid.scan import (
    REASON_CAP,
    REASON_DATE,
    REASON_DATING,
    REASON_MOVE,
    REASON_NAME,
    REASON_STRAY,
    REASON_UNITS,
    ScanContext,
    price_moves_ok,
    scan_case,
)

CTX = ScanContext(
    real_name="Boeing",
    ticker="BA",
    aliases=("Boeing Company",),
    identifying_terms=("737 MAX", "Seattle"),
    executives=("Dave Calhoun", "Jack Deal"),
)


def reasons(text: str, **kw) -> list[str]:
    return scan_case({"story": text}, CTX, **kw).reasons


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Boeing struggled.", REASON_NAME),
        ("the ba shares fell", None),  # ticker of 2 chars is case-sensitive
        ("BA shares fell", REASON_NAME),
        ("The 737 MAX was grounded", REASON_NAME),
        ("A firm near seattle.", REASON_NAME),
        ("Calhoun spoke", REASON_NAME),
        ("Jack Deal spoke", REASON_NAME),
        ("In 2019 sales fell", REASON_DATE),
        ("It happened in March", REASON_DATE),
        ("In Sept. results", REASON_DATE),
        ("Dec results were fine", REASON_DATE),
        ("On Tuesday the board met", REASON_DATE),
        ("Q3 was weak", REASON_DATE),
        ("The fourth quarter was weak", REASON_DATE),
        ("Sales rose to 3 million", REASON_UNITS),
        ("Sales rose to 3bn", REASON_UNITS),
        ("revenue of 12,500 units", REASON_CAP),
        ("worst in decades", REASON_DATING),
        ("the biggest drop since the crisis", REASON_DATING),
        ("first time in its history", REASON_DATING),
        ("Sales hit 77", REASON_STRAY),
    ],
)
def test_scan_hits(text: str, reason: str | None) -> None:
    got = reasons(text)
    if reason is None:
        assert got == []
    else:
        assert reason in got


@pytest.mark.parametrize(
    "text",
    [
        "The deal fell through and a big deal was struck.",
        "Calendar of events: may the board decide, we may proceed.",
        "We march on; the sun rose.",
        "Sales hit {A1} after Day 84, about 3 weeks later.",
        "A day later the plan was set.",
    ],
)
def test_scan_clean(text: str) -> None:
    assert reasons(text) == []


def test_year_as_amount_is_not_a_date():
    assert reasons("Revenue was 1993", allowed_numbers=["1993"]) == []
    assert REASON_DATE in reasons("Revenue was 1993")
    assert REASON_DATE not in reasons("It served 1993 users")


def test_may_only_as_month():
    assert REASON_DATE in reasons("Results came in May")
    assert REASON_DATE in reasons("May 5 was quiet")
    assert REASON_DATE not in reasons("It may rain")


def test_prose_fields_all_scanned_and_field_reported():
    res = scan_case({"a": "fine", "b": "Boeing"}, CTX)
    assert not res.passed and res.findings[0].field == "b"


def test_price_moves():
    assert price_moves_ok([100, 110, 99], [1000, 1100, 990]) == []
    assert price_moves_ok([100, 110], [100, 112]) == [1]
    assert price_moves_ok([100, 110], [100, 110.9]) == []
    r = scan_case({"s": "ok"}, CTX, real_prices=[100, 110], shown_prices=[100, 120])
    assert REASON_MOVE in r.reasons
