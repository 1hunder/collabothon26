"""Real-world event text for the reveal table, from a reference pack's secret section.

Rows approved before ``secret.real_events`` existed store disguised prose; the reveal falls back
to the bundled pack manifest (looked up by pack id) so those rows still show what really happened.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from financequest.engine.disguise import format_amount
from financequest.refpack.validate import PLACEHOLDER

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "reference"


def _figures(node: Any, out: dict[str, str]) -> None:
    if isinstance(node, dict):
        if "id" in node and "family" in node and "value" in node:
            out[str(node["id"])] = str(node["value"])
        for v in node.values():
            _figures(v, out)
    elif isinstance(node, list):
        for v in node:
            _figures(v, out)


def fill(text: str, figures: dict[str, str]) -> str:
    def repl(mt: re.Match[str]) -> str:
        v = figures.get(mt.group(1))
        if v is None:
            return mt.group(0)
        return format_amount(Decimal(v).copy_abs())

    return PLACEHOLDER.sub(repl, text)


@lru_cache(maxsize=8)
def bundled(pack_id: str) -> dict[str, tuple[str, str]]:
    """evidence id -> (headline, text) with real figures, for a bundled pack; {} when unknown."""
    for path in FIXTURES.glob("*/manifest.json"):
        m = json.loads(path.read_text(encoding="utf-8"))
        if m.get("meta", {}).get("case_id") != pack_id:
            continue
        figs: dict[str, str] = {}
        _figures(m, figs)
        return {
            e["evidence_id"]: (e["headline"], fill(e["text"], figs))
            for e in m.get("secret", {}).get("real_events", [])
        }
    return {}
