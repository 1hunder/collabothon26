"""Seeded dice: a pure function of (seed, challenge key, roll index)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

BONUS = 2


@dataclass(frozen=True)
class RollResult:
    dice: tuple[int, ...]
    used: int
    bonus: int
    total: int
    dc: int
    nat20: bool
    nat1: bool
    success: bool
    advantage: bool

    @property
    def result(self) -> str:
        return "success" if self.success else "setback"


def dice_values(seed: int, challenge_key: str, roll_index: int, count: int) -> tuple[int, ...]:
    digest = hashlib.sha256(f"{seed}|{challenge_key}|{roll_index}".encode()).digest()
    return tuple(int.from_bytes(digest[i * 8 : (i + 1) * 8], "big") % 20 + 1 for i in range(count))


def is_success(used: int, dc: int, bonus: int = BONUS) -> bool:
    if used == 20:
        return True
    if used == 1:
        return False
    return used + bonus >= dc


def roll(
    seed: int, challenge_key: str, roll_index: int, dc: int, advantage: bool = False
) -> RollResult:
    dice = dice_values(seed, challenge_key, roll_index, 2 if advantage else 1)
    used = max(dice)
    return RollResult(
        dice=dice,
        used=used,
        bonus=BONUS,
        total=used + BONUS,
        dc=dc,
        nat20=used == 20,
        nat1=used == 1,
        success=is_success(used, dc),
        advantage=advantage,
    )
