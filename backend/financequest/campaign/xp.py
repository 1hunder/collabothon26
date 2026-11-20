"""XP: rubric from the manifest (or default), clamp, quote check, loss/profit word check."""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_RUBRIC: tuple[tuple[str, int], ...] = (
    ("Evidence quality", 25),
    ("Risk identification", 25),
    ("Acknowledging uncertainty", 20),
    ("Logic and consistency", 20),
    ("Reflection after the reveal", 10),
)
NEUTRAL = "Scored on the clarity of your reasoning."
_BAD = re.compile(
    r"\b(profit\w*|loss(es)?|lost|lose|losing|gain(ed|s)?|won|win|money|earn(ed)?|return(s)?|"
    r"rich|payoff|aggressive)\b",
    re.I,
)


@dataclass(frozen=True)
class RawScore:
    category: str
    score: int
    rationale: str
    quote: str


def rubric_for(manifest_rubric: tuple[tuple[str, int], ...] | None) -> tuple[tuple[str, int], ...]:
    return manifest_rubric or DEFAULT_RUBRIC


def validate_scores(
    rubric: tuple[tuple[str, int], ...], raw: list[RawScore], player_text: str
) -> tuple[list[dict[str, object]], int]:
    by_cat = {r.category: r for r in raw}
    out: list[dict[str, object]] = []
    total = 0
    for name, mx in rubric:
        r = by_cat.get(name)
        score = max(0, min(mx, int(r.score))) if r else 0
        rationale = r.rationale if r else NEUTRAL
        quote = r.quote if r else ""
        if quote and quote not in player_text:
            quote, rationale = "", NEUTRAL
        if _BAD.search(rationale):
            rationale = NEUTRAL
        total += score
        out.append(
            {"name": name, "score": score, "max": mx, "rationale": rationale, "quote": quote}
        )
    return out, total
