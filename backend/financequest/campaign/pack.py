"""Loads a playable scenario into engine objects.

Real price rows exist only inside this module and ``portfolio``; everything shown goes through
``view`` (disguised, story days). Only campaign/ and engine/ read ``scenario_secret``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlmodel import Session

from financequest.campaign.adapter import NotPlayable, adapt_gate_scenario
from financequest.db.models import Scenario, ScenarioSecret


@dataclass(frozen=True)
class Cp:
    id: str
    role: str
    story_day: int
    label: str


@dataclass(frozen=True)
class Ev:
    id: str
    checkpoint: str
    location: str
    kind: str
    title: str
    text: str
    key: bool


@dataclass(frozen=True)
class Enc:
    id: str
    title: str
    checkpoint: str
    location: str
    dc: int | None
    kind: str | None
    clue_id: str
    failure_forward: str


@dataclass(frozen=True)
class Char:
    id: str
    name: str
    role: str
    location: str
    may_reveal: dict[str, list[str]]
    never: list[str]


_LOCAL_FOLK: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("exchange", "market", "steps", "square", "trader"), "odo-fenn", "Odo Fenn",
     "A lamplighter who hears the crowd talk"),
    (("hall", "guild", "council", "archive", "library"), "sela-quill", "Sela Quill",
     "A hall scribe who copies the council's papers"),
)
_LOCAL_DEFAULT = ("tobin-marsh", "Tobin Marsh", "A wandering porter who carries messages")


def ensure_local_characters(
    chars: tuple[Char, ...], seeds: tuple[dict[str, Any], ...], evidence: tuple[Ev, ...],
    checkpoints: tuple[Cp, ...],
) -> tuple[Char, ...]:
    """Every campaign location has someone to talk to. A seed location without a manifest
    character gets a generic local who may reveal only the evidence already at that place."""
    out = list(chars)
    used = {c.id for c in out}
    for seed in seeds:
        key = str(seed["key"])
        if any(c.location.removeprefix("campaign:") == key for c in out):
            continue
        low = f"{seed['key']} {seed.get('name', '')}".lower()
        cid, name, role = next(
            ((i, n, r) for kws, i, n, r in _LOCAL_FOLK if any(k in low for k in kws) and i not in used),
            _LOCAL_DEFAULT,
        )
        if cid in used:
            cid, name, role = f"local-{key}", f"Old {key.split('_')[0].title()}", "A local who knows the place"
        used.add(cid)
        here = [e for e in evidence if e.location.removeprefix("campaign:") == key]
        reveal = {
            cp.id: [e.id for e in here if e.checkpoint == cp.id]
            for cp in checkpoints if any(e.checkpoint == cp.id for e in here)
        }
        out.append(Char(
            id=cid, name=name, role=role, location=f"campaign:{key}", may_reveal=reveal,
            never=["Real names, companies or places", "What the price will do",
                   "Advice to buy, sell or invest"],
        ))  # fmt: skip
    return tuple(out)


@dataclass(frozen=True)
class Row:
    """One trading day. Real prices: engine-only."""

    day: int
    iso: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class Pack:
    scenario_id: str
    source: str
    currency: str
    title: str
    company_name: str
    trade: str
    size: str
    setting: str
    market_name: str
    checkpoints: tuple[Cp, ...]
    evidence: tuple[Ev, ...]
    documents: tuple[dict[str, Any], ...]
    characters: tuple[Char, ...]
    encounters: tuple[Enc, ...]
    news: dict[str, Any] | None
    key_figures: tuple[dict[str, Any], ...]
    rubric: tuple[tuple[str, int], ...] | None
    seeds: tuple[dict[str, Any], ...]
    decision_day: int
    horizon_day: int
    price_factor: Decimal
    rows: tuple[Row, ...]  # engine-only real rows through the horizon
    buy_open: Decimal
    end_close: Decimal
    fund_return: Decimal | None = None
    questions: tuple[str, ...] = ()
    leak_terms: tuple[str, ...] = field(default=())

    def cp(self, cid: str) -> Cp:
        return next(c for c in self.checkpoints if c.id == cid)

    def cp_by_role(self, role: str) -> Cp:
        return next(c for c in self.checkpoints if c.role == role)

    @property
    def intro(self) -> Cp:
        return self.cp_by_role("intro")

    @property
    def horizon_days(self) -> int:
        return self.horizon_day - self.decision_day

    @property
    def has_fund(self) -> bool:
        return self.fund_return is not None

    def evidence_by_id(self, eid: str) -> Ev | None:
        return next((e for e in self.evidence if e.id == eid), None)

    def display(self, price: Decimal) -> str:
        return str((price * self.price_factor).quantize(Decimal("0.0001")).normalize())

    def display_num(self, price: Decimal) -> float:
        """The same display value as a JSON number (at most 4 decimals, so the float is exact enough)."""
        return float(self.display(price))


def _resolve_csv(ref: str) -> Path:
    p = Path(ref)
    if p.exists():
        return p
    fx = Path(__file__).resolve().parent.parent / "fixtures" / "reference"
    for cand in fx.glob(f"*/{p.name}"):
        return cand
    raise FileNotFoundError(ref)


def _load_rows(ref: str, day_map: dict[str, int]) -> list[Row]:
    with _resolve_csv(ref).open(newline="", encoding="utf-8") as fh:
        out = []
        for r in csv.DictReader(fh):
            iso = r["date"]
            if iso not in day_map:
                continue
            out.append(
                Row(day_map[iso], iso, Decimal(r["open_usd"]), Decimal(r["high_usd"]),
                    Decimal(r["low_usd"]), Decimal(r["close_usd"]))
            )  # fmt: skip
    return out


def build_pack(scenario: Scenario, secret: ScenarioSecret) -> Pack:
    manifest = scenario.manifest
    if not isinstance(manifest, dict):
        manifest = adapt_gate_scenario(scenario)
    rb: dict[str, Any] = secret.real_beats if isinstance(secret.real_beats, dict) else {}
    dm = manifest["prices"]
    factor = Decimal(str(secret.price_factor)) if secret.price_factor is not None else Decimal(1)
    if "day_map" in rb and secret.price_series_ref:
        rows = _load_rows(secret.price_series_ref, {k: int(v) for k, v in rb["day_map"].items()})
        buy_open = Decimal(rb["buy_open"])
        end_close = Decimal(rb["horizon_close"])
    else:  # adapted gate scenario: disguised series; ratios are scale-invariant
        rows = [
            Row(int(p["day"]), str(p["day"]), Decimal(str(p["open"])), Decimal(str(p["high"])),
                Decimal(str(p["low"])), Decimal(str(p["close"])))
            for p in manifest["_series"]
        ]  # fmt: skip
        factor = Decimal(1)
        after = [r for r in rows if r.day > dm["decision_story_day"]]
        if not after:
            raise NotPlayable("no prices after story today")
        buy_open = after[0].open
        end_close = next(r for r in reversed(rows) if r.day <= dm["horizon_story_day"]).close
    cps = tuple(
        Cp(c["id"], c["role"], int(c["story_day"]), c["label"]) for c in manifest["checkpoints"]
    )
    ev = tuple(
        Ev(e["id"], e["checkpoint"], e["location"], e["kind"], e["title"], e["player_text"],
           bool(e.get("key")))
        for e in manifest["evidence"]
    )  # fmt: skip
    clue_by_enc = {e["id"]: e["success_clue_id"] for e in manifest["encounters"]}
    encs = tuple(
        Enc(e["id"], e["title"], e["checkpoint"], e["location"], e.get("dc"), e.get("kind"),
            clue_by_enc[e["id"]], e.get("failure_forward", ""))
        for e in manifest["encounters"]
    )  # fmt: skip
    chars = tuple(
        Char(c["id"], c["name"], c["role"], c["location"], c.get("may_reveal", {}), c.get("never", []))
        for c in manifest["characters"]
    )  # fmt: skip
    card = manifest.get("company_card", {})
    return Pack(
        scenario_id=str(scenario.id),
        source=scenario.source,
        currency=manifest["meta"].get("currency", "USD"),
        title=manifest["meta"]["campaign_title"],
        company_name=manifest["world"]["company_name"],
        trade=card.get("trade", scenario.industry_shown),
        size=card.get("size", ""),
        setting=manifest["world"]["setting_name"],
        market_name=manifest["world"].get("market_name", "Market Square"),
        checkpoints=cps,
        evidence=ev,
        documents=tuple(manifest.get("documents", [])),
        characters=ensure_local_characters(
            chars, tuple(manifest.get("campaign_location_seeds", []))[:3], ev, cps
        ),
        encounters=encs,
        news=manifest.get("news"),
        key_figures=tuple(card.get("key_figures", [])),
        rubric=tuple((r["category"], int(r["max"])) for r in manifest["rubric"])
        if manifest.get("rubric")
        else None,
        seeds=tuple(manifest.get("campaign_location_seeds", []))[:3],
        decision_day=int(dm["decision_story_day"]),
        horizon_day=int(dm["horizon_story_day"]),
        price_factor=factor,
        rows=tuple(rows),
        buy_open=buy_open,
        end_close=end_close,
        questions=tuple(manifest.get("debrief", {}).get("questions", [])),
        leak_terms=tuple(secret.leak_terms or []),
    )


def load_pack(db: Session, scenario_id: Any) -> Pack:
    sc = db.get(Scenario, scenario_id)
    sec = db.get(ScenarioSecret, scenario_id)
    if sc is None or sec is None:
        raise LookupError("scenario")
    return build_pack(sc, sec)


__all__ = ["Pack", "load_pack", "build_pack", "date"]
