"""Fixture export/import: approved gate scenarios plus their secrets, as versioned JSON.

One file per scenario (``gate-<scenario id>.json``). Import is idempotent (upsert by scenario id),
sets ``source = gate`` and drops the links to ``source_case``/``attempt`` rows, which may not exist
in the target database. The API calls ``load_fixtures_if_empty`` at startup.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from financequest.db.models import Scenario, ScenarioSecret

SCHEMA_VERSION = 1
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios"
log = logging.getLogger(__name__)

SCENARIO_FIELDS = (
    "invented_name", "industry_shown", "story_days", "beats", "chart_series", "company_card",
    "manifest", "status",
)  # fmt: skip
SECRET_FIELDS = (
    "real_name", "ticker", "real_beats", "price_series_ref", "amount_factors", "seed",
    "what_changed", "n_guessers", "leak_terms",
)  # fmt: skip


def export_approved(session: Session, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    rows = session.exec(
        select(Scenario).where(Scenario.source == "gate", Scenario.status == "playable")
    ).all()
    for sc in rows:
        sec = session.get(ScenarioSecret, sc.id)
        if sec is None:
            continue
        doc: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "scenario": {"id": str(sc.id), **{f: getattr(sc, f) for f in SCENARIO_FIELDS}},
            "secret": {
                **{f: getattr(sec, f) for f in SECRET_FIELDS},
                "price_factor": None if sec.price_factor is None else str(sec.price_factor),
            },
        }
        path = out_dir / f"gate-{sc.id}.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(path)
    return written


def import_fixtures(session: Session, src_dir: Path) -> int:
    n = 0
    for path in sorted(src_dir.glob("gate-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"{path.name}: unsupported schema_version {doc.get('schema_version')}")
        sid = uuid.UUID(doc["scenario"]["id"])
        sc = session.get(Scenario, sid) or Scenario(id=sid, invented_name="", industry_shown="")
        for f in SCENARIO_FIELDS:
            setattr(sc, f, doc["scenario"][f])
        sc.source, sc.case_id, sc.attempt_id = "gate", None, None
        session.add(sc)
        session.flush()
        sec = session.get(ScenarioSecret, sid) or ScenarioSecret(scenario_id=sid, real_name="")
        for f in SECRET_FIELDS:
            setattr(sec, f, doc["secret"][f])
        pf = doc["secret"].get("price_factor")
        sec.price_factor = None if pf is None else float(pf)
        session.add(sec)
        n += 1
    session.commit()
    return n


def load_fixtures_if_empty(session: Session, src_dir: Path = DEFAULT_DIR) -> int:
    """Startup hook: import exported fixtures only when the DB holds no gate scenario."""
    if session.exec(select(Scenario).where(Scenario.source == "gate")).first() is not None:
        return 0
    if not src_dir.exists():
        return 0
    n = import_fixtures(session, src_dir)
    if n:
        log.info("loaded %d exported scenario fixtures", n)
    return n
