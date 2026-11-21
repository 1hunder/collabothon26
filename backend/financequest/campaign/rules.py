"""Deterministic campaign rules: classes, difficulty, turns, news trigger, decide gating."""

from __future__ import annotations

import re
from dataclasses import dataclass

from financequest.campaign.pack import Enc, Pack

DC_TABLE = {"public_report": 8, "unusual_figure": 12, "cross_check": 15, "obscure_lead": 18}
BONUS_DC = DC_TABLE["obscure_lead"]
DC_FALLBACK = 12
# Ad-hoc skill checks (an uncertain, skill-based action the player attempts anywhere). The DC comes
# from the difficulty the Master judged, through this table only, never from the model.
SKILLS = {
    "investigation": "Investigation", "insight": "Insight", "persuasion": "Persuasion",
    "stealth": "Stealth", "knowledge": "Knowledge",
}
ADHOC_DC = {"easy": 10, "medium": 13, "hard": 15}
ADHOC_KIND = "skill:"
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


# ---- decisions throughout the campaign --------------------------------------------------------
_BUY_RE = re.compile(r"\b(buy|buying|bought|invest|investing|put|putting|stake|purchase)\b", re.I)
_SELL_RE = re.compile(r"\b(sell|selling|sold|take (it |them |my coins |some |half )?out|cash out|exit|dump)\b", re.I)
_HOLD_RE = re.compile(r"\b(hold|wait|keep|nothing|stay out|pass|watch)\b", re.I)
_NEG_RE = re.compile(r"\b(don'?t|do not|not|never|won'?t|will not|no)\s+(yet\s+)?(buy|invest|put|sell|stake)", re.I)
_PORTION_RE = (
    ("all", re.compile(r"\b(all|everything|every coin|whole|entire)\b", re.I)),
    ("most", re.compile(r"\b(most|three quarters)\b", re.I)),
    ("half", re.compile(r"\b(half)\b", re.I)),
    ("some", re.compile(r"\b(some|a little|a bit|a quarter|small)\b", re.I)),
)
_AMOUNT_RE = re.compile(r"(?:€\s*)?(\d[\d,]*)(?:\s*(?:€|eur|euros?|coins?|gold))?", re.I)


def parse_decision(text: str) -> tuple[str | None, int | None, str | None]:
    """A plain reading of a written decision: (action, amount_eur, portion). Used by the scripted
    Campaign Master and as the fallback when the model's reading fails the guards."""
    low = text.lower()
    action = None
    if _NEG_RE.search(low):
        action = "hold"
    elif _SELL_RE.search(low):
        action = "sell"
    elif _BUY_RE.search(low):
        action = "buy"
    elif _HOLD_RE.search(low):
        action = "hold"
    if action is None or action == "hold":
        return action, None, None
    portion = next((name for name, rx in _PORTION_RE if rx.search(low)), None)
    m = _AMOUNT_RE.search(text)
    amount = int(m.group(1).replace(",", "")) if m else None
    if portion and (amount is None or re.search(r"\bof\b", low)):  # "half of my 1000 coins"
        return action, None, portion
    return action, amount, None if amount is not None else portion


# ---- ad-hoc skill checks ----------------------------------------------------------------------
def is_adhoc(kind: str | None) -> bool:
    return bool(kind) and str(kind).startswith(ADHOC_KIND)


def adhoc_skill(kind: str | None) -> str | None:
    """The display name of an ad-hoc check's skill, or None for a predefined encounter."""
    return SKILLS.get(str(kind)[len(ADHOC_KIND):]) if is_adhoc(kind) else None


def adhoc_dc(difficulty: str) -> int:
    return ADHOC_DC.get(difficulty, ADHOC_DC["medium"])


def adhoc_key(skill: str, target: str, location_key: str) -> str:
    """One check per skill + target + place: the key is the identity (campaign + key is unique)."""
    slug = "-".join(re.findall(r"[a-z0-9]+", target.lower()))[:40] or "here"
    return f"skill-{skill}-{slug}-{location_key}"


# ---- the all-in plot: nothing left at stake ------------------------------------------------------
ALL_IN_CASH_PCT = 2  # free cash at or under this share of the starting budget counts as all in
LOAN_PRINCIPAL_PCT = 50  # a moneylender lends up to this share of the starting budget
LOAN_INTEREST_PCT = 10  # flat, repaid with the principal at the end of the horizon
OFFER_IGNORED_MAX = 2  # something else twice in front of an open offer: the plot moves on

_DONE_RE = re.compile(r"\b(done|that'?s it|that is it|finished|all out|out for good|no more|enough)\b", re.I)
_DECLINE_RE = re.compile(
    r"\b(no|nope|decline|declined|refuse|reject|not interested|no thanks|pass|never|don'?t|do not|"
    r"won'?t|will not|keep (my|what|it)|hold)\b", re.I)
_ACCEPT_RE = re.compile(
    r"\b(accept|agree|deal|yes|yeah|yep|sure|okay|ok|take (it|the|your|that)|i'?ll take|let'?s do it|"
    r"borrow|sell|lend|go ahead)\b", re.I)
_LOAN_AMOUNT_RE = re.compile(r"(?:€\s*)?(\d[\d,]*)(?!\s*%)", re.I)


def says_done(text: str) -> bool:
    return bool(_DONE_RE.search(text))


def read_offer_answer(text: str) -> str:
    """accept / decline / other: a plain reading of the player's words about an open offer. A
    refusal wins over acceptance wording; anything that is neither is "other" (something else)."""
    if _DECLINE_RE.search(text):
        return "decline"
    if _ACCEPT_RE.search(text):
        return "accept"
    return "other"


def loan_amount(text: str, maximum: int) -> int:
    """The sum the player asks to borrow (a number or "half"), clamped to the offer; else all of it."""
    m = _LOAN_AMOUNT_RE.search(text)
    if m and 0 < int(m.group(1).replace(",", "")) <= maximum:
        return int(m.group(1).replace(",", ""))
    if "half" in text.lower():
        return maximum // 2
    return maximum
