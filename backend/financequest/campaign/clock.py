"""Checkpoints and the story clock (story days only; never backwards)."""

from __future__ import annotations

from financequest.campaign.pack import Pack


def day_label(day: int) -> str:
    return f"Day {day}"


def initial_state(pack: Pack) -> tuple[str, int]:
    return pack.intro.id, pack.intro.story_day


def after_news(pack: Pack, current_day: int) -> tuple[str, int]:
    """The news moves to the disclosure checkpoint; the clock to the decision date."""
    return pack.cp_by_role("disclosure").id, max(current_day, pack.decision_day)


def time_skip_label(pack: Pack) -> str:
    days = int(pack.news["time_skip_days"]) if pack.news else 0
    return f"{days} days later…"


def horizon_label(pack: Pack) -> str:
    return f"about {pack.horizon_days} days"


def horizon_skip_label(pack: Pack) -> str:
    return f"{pack.horizon_days} days later…"
