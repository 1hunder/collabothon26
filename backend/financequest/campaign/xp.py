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


ELLIPSIS = "…"


def excerpt(text: str, max_chars: int = 80) -> str:
    """A quotable excerpt of ``text``: whole words (or the first sentence when it fits), with a
    trailing ellipsis when shortened. ``quote_in`` accepts it as a substring check."""
    t = " ".join(text.split())
    if len(t) <= max_chars:
        return t
    sentence = re.match(r".+?[.!?](?=\s|$)", t)
    if sentence and len(sentence.group(0)) <= max_chars:
        return sentence.group(0)
    cut = t[:max_chars]
    if not t[max_chars].isspace():  # mid-word: back off to the last whole word
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(" ,;:-") + ELLIPSIS


def quote_in(quote: str, player_text: str) -> bool:
    """Whether ``quote`` is a verbatim excerpt; a trailing ellipsis marks a shortened quote."""
    q = quote.rstrip()
    for mark in (ELLIPSIS, "..."):
        if q.endswith(mark):
            q = q[: -len(mark)].rstrip()
            break
    norm = " ".join(player_text.split())
    return bool(q) and (q in player_text or q in norm)


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
        if quote and not quote_in(quote, player_text):
            quote, rationale = "", NEUTRAL
        if _BAD.search(rationale):
            rationale = NEUTRAL
        total += score
        out.append(
            {"name": name, "score": score, "max": mx, "rationale": rationale, "quote": quote}
        )
    return out, total
