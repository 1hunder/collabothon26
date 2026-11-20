"""Guess matching: normalised exact match plus the substring rule (names >= 4 chars)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "plc",
        "ag",
        "se",
        "ltd",
        "limited",
        "nv",
        "co",
        "sa",
        "gmbh",
        "llc",
        "lp",
        "company",
    }
)
MIN_SUBSTRING_LEN = 4


def normalise(name: str) -> str:
    text = name.casefold().replace(".", "")
    text = re.sub(r"[^\w\s]|_", " ", text)
    tokens = text.split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    if len(tokens) > 1 and tokens[0] == "the":
        tokens.pop(0)
    return " ".join(tokens)


@dataclass(frozen=True)
class MatchTargets:
    company: str
    ticker: str = ""
    parent: str = ""
    subsidiaries: Sequence[str] = field(default_factory=tuple)
    former_names: Sequence[str] = field(default_factory=tuple)

    def names(self) -> list[str]:
        raw = [self.company, self.ticker, self.parent, *self.subsidiaries, *self.former_names]
        out = [normalise(n) for n in raw if n and n.strip()]
        return [n for n in dict.fromkeys(out) if n]


def is_correct_guess(guess: str, targets: MatchTargets) -> bool:
    g = normalise(guess)
    if not g:
        return False
    for name in targets.names():
        if g == name:
            return True
        if len(name) >= MIN_SUBSTRING_LEN and name in g:
            return True
    return False


def any_correct(guesses: Sequence[str], targets: MatchTargets, top: int = 3) -> bool:
    return any(is_correct_guess(g, targets) for g in guesses[:top])
