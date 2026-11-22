"""Quest Board card text derived from a (rendered, player-safe) manifest.

Used at publish time for personal quests and as a fallback for packs without a ``board`` block.
Pure functions over the rendered manifest dict: they add no real names, dates or figures.
"""

from __future__ import annotations

from typing import Any

DEFAULT_ORDER = 1000
FALLBACK_LEARN = ["Reading the ledger", "Weighing risk", "Reacting to news"]
WHAT_YOU_DO = [
    "Look around: read the ledgers and talk to the folk of the market.",
    "Weigh what you found, then choose how much gold to commit.",
    "Say what you expect to happen, then see how it really went.",
]


def _difficulty(m: dict[str, Any]) -> str:
    dcs = [int(e["dc"]) for e in m.get("encounters", []) if isinstance(e.get("dc"), int)]
    if not dcs:
        return "medium"
    avg = sum(dcs) / len(dcs)
    return "easy" if avg < 11.5 else "medium" if avg < 13.5 else "hard"


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def derive_briefing(m: dict[str, Any]) -> str:
    w, card = m.get("world", {}), m.get("company_card", {})
    parts = [
        f"The tale is set in {w.get('setting_name', 'a far-off realm')}, where the "
        f"{w.get('market_name', 'market')} is the heart of every trade.",
        f"{w.get('company_name', card.get('name', 'A great house'))} is "
        f"{_lower_first(card.get('trade', 'a trading house'))}.",
    ]
    if card.get("size"):
        parts.append(f"{card['size']}.".replace("..", "."))
    parts.append(
        "Something has stirred the market, and the folk are talking. "
        "Your question: what is really going on, and how much gold would you risk on it?"
    )
    return " ".join(parts)


def derive_board(m: dict[str, Any]) -> dict[str, Any]:
    w, card = m.get("world", {}), m.get("company_card", {})
    teaser = (
        f"{w.get('company_name', card.get('name', 'A great house'))} of "
        f"{w.get('setting_name', 'a far-off realm')} is {_lower_first(card.get('trade', ''))}. "
        "The market has begun to whisper. Read the ledgers, ask around and decide where your "
        "gold belongs."
    )
    learn = [r["category"] for r in (m.get("rubric") or [])[:3] if r.get("category")]
    return {
        "title": m.get("meta", {}).get("campaign_title", "A New Quest"),
        "teaser": teaser,
        "difficulty": _difficulty(m),
        "learn": learn or list(FALLBACK_LEARN),
        "order": DEFAULT_ORDER,
        "briefing": derive_briefing(m),
    }
