"""Focus and items. Essential information never costs Focus; items never touch money."""

from __future__ import annotations

from financequest.campaign.pack import Pack

BASE_FOCUS = 3
ITEM_ORDER = ("ratio_lens", "rumour_ledger", "calm_compass")
ITEM_NAMES = {"ratio_lens": "Ratio Lens", "rumour_ledger": "Rumour Ledger", "calm_compass": "Calm Compass"}
ITEM_INFO = {
    "ratio_lens": "Library: every key figure on the company card gets a plain-language explanation.",
    "rumour_ledger": "Market Square: a summary of every rumour heard so far in the campaign.",
    "calm_compass": "Start each campaign with 4 Focus instead of 3.",
}
ITEM_XP_THRESHOLD = 70


def starting_focus(items: set[str]) -> int:
    return BASE_FOCUS + 1 if "calm_compass" in items else BASE_FOCUS


def next_item(owned: set[str]) -> str | None:
    return next((i for i in ITEM_ORDER if i not in owned), None)


def hint_target(pack: Pack, visible_ids: set[str], found: set[str]) -> str | None:
    """Engine picks the target clue: key clues first."""
    unfound = [e for e in pack.evidence if e.id in visible_ids and e.id not in found]
    unfound.sort(key=lambda e: (not e.key,))
    return unfound[0].id if unfound else None


def item_out(key: str) -> dict[str, str]:
    """Wire shape of an item: ``id`` is the stable key the campaign state lists in ``hero.items``."""
    return {"id": key, "key": key, "name": ITEM_NAMES[key], "description": ITEM_INFO[key]}
