"""Prompt text for the intake and gate graphs (plain constants, no templating engine)."""

from financequest.reid.prompts.guesser import (
    DISGUISE_RULES_DESCRIPTION,
    GUESSER_SYSTEM,
    PERSONA_SUFFIX,
)
from financequest.reid.prompts.intake import EXTRACT_SYSTEM
from financequest.reid.prompts.writer import REWRITE_CHECKLIST, WRITER_SYSTEM

__all__ = [
    "DISGUISE_RULES_DESCRIPTION",
    "EXTRACT_SYSTEM",
    "GUESSER_SYSTEM",
    "PERSONA_SUFFIX",
    "REWRITE_CHECKLIST",
    "WRITER_SYSTEM",
]
