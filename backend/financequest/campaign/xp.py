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


_VERB_FIX = {"is": "are", "has": "have", "does": "do", "was": "were", "doesn't": "don't",
             "hasn't": "haven't", "isn't": "aren't", "wasn't": "weren't"}
_THIRD = re.compile(
    r"\b(?:The\s+)?(?:player|hero|learner|reader)(?P<poss>'s)?\b(?P<verb>\s+[a-z']+)?", re.I
)


def to_second_person(text: str) -> str:
    """"The player cites X" -> "You cite X": feedback is spoken to the player."""
    def verb(w: str) -> str:
        low = w.lower()
        if low in _VERB_FIX:
            return _VERB_FIX[low]
        if low.endswith("ies") and len(low) > 4:
            return w[:-3] + "y"
        if low.endswith(("sses", "shes", "ches", "xes")):
            return w[:-2]
        if low.endswith("s") and not low.endswith("ss"):
            return w[:-1]
        return w

    out = text
    for m in reversed(list(_THIRD.finditer(text))):
        head = text[: m.start()].rstrip()
        sentence_start = not head or head.endswith((".", "!", "?"))
        if m.group("poss"):
            new = ("Your" if sentence_start else "your") + (m.group("verb") or "")
        else:
            new = "You" if sentence_start else "you"
            if m.group("verb"):
                new += " " + verb(m.group("verb").strip())
        out = out[: m.start()] + new + out[m.end():]
    return out


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
        rationale = to_second_person(r.rationale) if r else NEUTRAL
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
