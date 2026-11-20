"""Deterministic campaign rules: classes, difficulty, turns, news trigger, decide gating."""

from __future__ import annotations

import re
from dataclasses import dataclass

from financequest.campaign.pack import Enc, Pack

DC_TABLE = {"public_report": 8, "unusual_figure": 12, "cross_check": 15, "obscure_lead": 18}
BONUS_DC = DC_TABLE["obscure_lead"]
DC_FALLBACK = 12
NEWS_TURNS = 6
NEWS_MARKET_TURNS = 3

CLASSES = {
    "guardian": {"hp": 120, "rerolls": 0, "keen_eye": 0},
    "analyst": {"hp": 100, "rerolls": 1, "keen_eye": 0},
    "investigator": {"hp": 100, "rerolls": 0, "keen_eye": 1},
}
NAME_EXTRA = " -'’"


def normalize_name(name: str) -> str | None:
    n = name.strip()
    if not 2 <= len(n) <= 20:
        return None
    if not all(c.isalnum() or c in NAME_EXTRA for c in n):
        return None
    return n


def encounter_dc(enc: Enc) -> int:
    if enc.dc is not None:
        return enc.dc
    return DC_TABLE.get(enc.kind or "", DC_FALLBACK)


def counts_as_turn(kind: str) -> bool:
    return kind in ("action", "move")


def should_fire_news(news_shown: bool, turn_count: int, arrived_at: str | None) -> bool:
    if news_shown:
        return False
    if turn_count >= NEWS_TURNS:
        return True
    return arrived_at == "market_square" and turn_count >= NEWS_MARKET_TURNS


def normalize_location(loc: str) -> str:
    return loc.removeprefix("campaign:")


def gated_clue_ids(pack: Pack) -> set[str]:
    return {e.clue_id for e in pack.encounters}


def free_clues(pack: Pack, checkpoint_rank_ok) -> list[str]:  # type: ignore[no-untyped-def]
    gated = gated_clue_ids(pack)
    return [e.id for e in pack.evidence if checkpoint_rank_ok(e.checkpoint) and e.id not in gated]


def key_clues(pack: Pack, checkpoint_rank_ok) -> list[str]:  # type: ignore[no-untyped-def]
    return [e.id for e in pack.evidence if e.key and checkpoint_rank_ok(e.checkpoint)]


def can_decide(
    pack: Pack,
    at_checkpoint,  # type: ignore[no-untyped-def]
    found: set[str],
    opening_done: bool,
    pending: object,
    news_shown: bool,
) -> bool:
    if not (opening_done and news_shown) or pending:
        return False
    need = set(free_clues(pack, at_checkpoint)) | set(key_clues(pack, at_checkpoint))
    return need <= found


@dataclass(frozen=True)
class RollOptions:
    final: bool
    options: tuple[str, ...]


def roll_options(
    success: bool, hero_class: str, rerolls_left: int, already_rerolled: bool
) -> RollOptions:
    if success:
        return RollOptions(True, ("continue",))
    if hero_class == "analyst" and rerolls_left > 0 and not already_rerolled:
        return RollOptions(False, ("reroll", "accept"))
    return RollOptions(True, ("continue",))


_DECISION_RE = re.compile(
    r"\b(ready to (decide|invest)|want to decide|make my decision|decide now)\b", re.I
)


def is_decision_intent(text: str) -> bool:
    return bool(_DECISION_RE.search(text))
