"""Batch statistics and the exact summary line."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

FinalStatus = Literal["approved", "rejected", "skipped", "error"]


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    status: FinalStatus
    recognised_first_attempt: bool = False
    fame: str | None = None
    size: str | None = None


@dataclass(frozen=True)
class Share:
    count: int
    total: int

    @property
    def pct(self) -> int:
        return pct(self.count, self.total)


@dataclass(frozen=True)
class BatchStats:
    checked: int
    skipped: int
    recognised_first: int
    approved: int
    approval_by_fame: dict[str, Share]
    approval_by_size: dict[str, Share]

    @property
    def summary_line(self) -> str:
        return (
            f"{self.checked} cases checked · {pct(self.recognised_first, self.checked)}% "
            f"recognised on first attempt · {self.approved} approved "
            f"({pct(self.approved, self.checked)}%)"
        )


def pct(part: int, total: int) -> int:
    if total == 0:
        return 0
    return int((Decimal(part * 100) / Decimal(total)).to_integral_value(ROUND_HALF_UP))


def compute_stats(outcomes: Sequence[CaseOutcome]) -> BatchStats:
    checked = [o for o in outcomes if o.status != "skipped"]
    fame_tot: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    size_tot: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for o in checked:
        for table, key in ((fame_tot, o.fame), (size_tot, o.size)):
            if key is not None:
                table[key][1] += 1
                table[key][0] += o.status == "approved"
    return BatchStats(
        checked=len(checked),
        skipped=len(outcomes) - len(checked),
        recognised_first=sum(o.recognised_first_attempt for o in checked),
        approved=sum(o.status == "approved" for o in checked),
        approval_by_fame={k: Share(*v) for k, v in sorted(fame_tot.items())},
        approval_by_size={k: Share(*v) for k, v in sorted(size_tot.items())},
    )
