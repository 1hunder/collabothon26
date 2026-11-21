"""Reasoning behind a decision: reading it from the player's words, judging whether it is enough,
and the engine's own (templated, neutral) questions and acknowledgements.

The agent layer may return ``reasoning`` and ``reasoning_sufficient`` for a decision; this module
holds the scripted/fallback reading used by the fake Campaign Master and when the model fails.
Nothing here judges whether the decision was right: only whether a reason was given.
"""

from __future__ import annotations

import re

SOURCES = ("inline", "asked", "commit", "skipped")
AWAITING = "awaiting"  # transient reasoning_source: the question was asked, the answer is pending

ASK_MISSING = "What made you choose that?"
ASK_THIN = "Can you say a bit more about why?"
SKIP_CHIP = "I'd rather skip that"
ACKS = (
    "Noted. I have written down your reasoning. What do you do next?",
    "Understood, I have put your reasons in the ledger. What do you do next?",
    "Thank you. Your reasoning is recorded. What do you do next?",
)
SKIP_ACK = "As you wish, I will leave it blank. What do you do next?"

_STRONG = re.compile(r"\b(?:because|since|given that|due to|considering)\b[\s,:]+(.+)$", re.I | re.S)
_WEAK = re.compile(r"\b(?:as|so that|so)\b[\s,:]+(.+)$", re.I | re.S)
_SKIP = re.compile(
    r"\b(skip|no reason|no comment|rather not|prefer not|pass|no thanks|nothing to say|don'?t want to say)\b",
    re.I,
)
_VAGUE = re.compile(
    r"^\W*(just because|because|gut(?: feeling)?|a gut feeling|i like it|i just do|idk|dunno|"
    r"i don'?t know|why not|feels? right|felt right|no idea|whatever|it'?s fine|sure|ok(?:ay)?)\W*$",
    re.I,
)
_CLUE_WORDS = re.compile(
    r"\b(cash|debt|revenue|profit|loss|losses|margin|ledger|report|filing|auditor|audit|news|"
    r"risk|clue|figure|trend|falling|rising|dropped|rose|growth|rumou?r|evidence|price|cost|"
    r"declin\w*|warning|lawsuit|dividend|earnings|flow)\b",
    re.I,
)
SUFFICIENT_WORDS = 6


def extract_inline(text: str) -> str | None:
    """The reasoning inside a decision message ("buy 20 because the cash flow keeps falling")."""
    t = text.strip()
    for rx in (_STRONG, None, _WEAK):
        if rx is None:  # "buy 400: the cash flow keeps falling"
            head, sep, tail = t.partition(":")
            m_text = tail if sep and len(tail.split()) >= 3 else ""
        else:
            m = rx.search(t)
            m_text = m.group(1) if m else ""
        reason = m_text.strip(" .,;:!")
        if reason and (rx is not _WEAK or len(reason.split()) >= 3):
            return reason
    return None


def is_sufficient(reason: str | None) -> bool:
    """Scripted judgement: a concrete reason has a figure, a clue word or at least 6 words."""
    if not reason or not reason.strip():
        return False
    r = reason.strip()
    if _VAGUE.match(r):
        return False
    return len(r.split()) >= SUFFICIENT_WORDS or bool(re.search(r"\d", r) or _CLUE_WORDS.search(r))


def is_skip(text: str) -> bool:
    t = text.strip()
    return len(t.split()) <= 8 and bool(_SKIP.search(t))


def ask_text(said: str, thin: str | None) -> str:
    """The reaction with its own closing question replaced by the one neutral follow-up."""
    sentences = re.split(r"(?<=[.!?])\s+", said.strip())
    if sentences and sentences[-1].endswith("?"):
        sentences = sentences[:-1]
    body = " ".join(sentences).strip()
    return f"{body} {ASK_THIN if thin else ASK_MISSING}".strip()
