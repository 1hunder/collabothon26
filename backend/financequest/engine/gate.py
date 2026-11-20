"""Hidden-future gate: nothing after story today leaves the engine.

Spec 003 extends this with checkpoints (``GatedView(checkpoint, clock)``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class StoryClock:
    today: int  # story day


def gate_by_day[T](items: Sequence[T], clock: StoryClock, day_of: Callable[[T], int]) -> list[T]:
    """Keep items on or before story today, preserving order."""
    return [i for i in items if day_of(i) <= clock.today]


def gate_chart[T](points: Sequence[T], clock: StoryClock, day_of: Callable[[T], int]) -> list[T]:
    return gate_by_day(points, clock, day_of)


def gate_beats[T](beats: Sequence[T], clock: StoryClock, day_of: Callable[[T], int]) -> list[T]:
    return gate_by_day(beats, clock, day_of)


# ---- spec 003: checkpoint-aware gate -------------------------------------------------------
CHECKPOINT_ORDER: tuple[str, ...] = ("G0", "G1", "G2", "G3", "G4")


def checkpoint_rank(checkpoint: str) -> int:
    return CHECKPOINT_ORDER.index(checkpoint)


@dataclass(frozen=True)
class GatedView:
    """The single filter every outbound payload and agent input of a running campaign passes.

    Evidence, documents, encounters and character reveals are visible from their checkpoint on,
    chart rows up to the story clock, the news only once shown. The secret part of a pack and
    anything after decision day never reach it.
    """

    checkpoint: str
    clock_day: int
    news_shown: bool = False

    def at_checkpoint(self, checkpoint: str) -> bool:
        return checkpoint_rank(checkpoint) <= checkpoint_rank(self.checkpoint)

    def by_checkpoint[T](self, items: Sequence[T], checkpoint_of: Callable[[T], str]) -> list[T]:
        return [i for i in items if self.at_checkpoint(checkpoint_of(i))]

    def chart[T](self, rows: Sequence[T], day_of: Callable[[T], int]) -> list[T]:
        return gate_chart(rows, StoryClock(self.clock_day), day_of)

    def news_item[T](self, item: T | None) -> T | None:
        return item if self.news_shown else None
