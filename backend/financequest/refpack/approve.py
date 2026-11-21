"""``refpack approve``: disguise a reviewed reference pack and store it as a playable scenario.

Deterministic code owns every number. The pack's real figures are scaled with spec 002's
``NumberPlan`` (one price factor, one shared money factor, own factors for other families),
checkpoint dates become story days, every player-visible text is rendered and run through the
final scan (``reid/scan.py``). Only a pack that passes is stored with ``status = playable``.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from financequest.db.models import Scenario, ScenarioSecret
from financequest.engine.disguise import (
    DISPLAY_CAP,
    AmountFact,
    NumberPlan,
    format_amount,
    round_sig,
)
from financequest.refpack.manifest import CampaignManifest, Figure
from financequest.refpack.validate import PLACEHOLDER, SHORT_TERM_LEN, _leak_hits, validate_manifest
from financequest.reid.scan import ScanContext, scan_case

RATIO_FAMILIES = frozenset({"percent", "ratio"})
YEAR_LIKE = (Decimal(1800), Decimal(2100))
SALT_TRIES = 50
# Keys whose string values are identifiers or enums, not player prose.
SKIP_KEYS = frozenset(
    {
        "id", "ids", "evidence_ids", "success_clue_id", "case_id", "pack_id", "version",
        "location", "checkpoint", "family", "kind", "role", "currency", "key", "may_reveal",
    }
)  # fmt: skip


@dataclass
class ApproveResult:
    ok: bool
    scenario_id: str | None = None
    status: str = "not_playable"
    reasons: list[str] = field(default_factory=list)
    salt: int = 0


def _real_day(d: date) -> int:
    return d.toordinal()


def _fmt(value: Decimal) -> str:
    return format_amount(value)


def _collect_figures(m: CampaignManifest) -> dict[str, Figure]:
    figs: dict[str, Figure] = {}
    for e in m.evidence:
        for f in e.figures:
            figs.setdefault(f.id, f)
    for kf in m.company_card.key_figures:
        figs.setdefault(kf.id, kf)
    return figs


def _disguised_values(plan: NumberPlan, figs: dict[str, Figure]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for fid, f in figs.items():
        if f.family in RATIO_FAMILIES:
            out[fid] = f.value
        elif f.family == "per_share":  # EPS etc. follow the price factor so P/E survives
            out[fid] = round_sig(f.value * plan.price_factor, 2)
        else:
            out[fid] = plan.scale_amount(f.family, f.value)
    return out


def _fill(text: str, values: dict[str, Decimal], problems: list[str], where: str) -> str:
    def repl(mt: re.Match[str]) -> str:
        fid = mt.group(1)
        if fid not in values:
            problems.append(f"unknown placeholder {{{fid}}} in {where}")
            return mt.group(0)
        v = values[fid]
        if mt.group(0).endswith(":abs}"):
            v = v.copy_abs()
        return _fmt(v)

    return PLACEHOLDER.sub(repl, text)


def _render(obj: Any, values: dict[str, Decimal], problems: list[str], where: str = "") -> Any:
    if isinstance(obj, str):
        return _fill(obj, values, problems, where)
    if isinstance(obj, list):
        return [_render(x, values, problems, f"{where}[{i}]") for i, x in enumerate(obj)]
    if isinstance(obj, dict):
        return {k: _render(v, values, problems, f"{where}.{k}") for k, v in obj.items()}
    return obj


def prose_fields(obj: Any, where: str = "") -> dict[str, str]:
    """Every player-visible prose string in a rendered structure (ids and enums skipped)."""
    out: dict[str, str] = {}
    if isinstance(obj, str):
        out[where] = obj
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            out.update(prose_fields(x, f"{where}[{i}]"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS or k == "value":
                continue
            out.update(prose_fields(v, f"{where}.{k}"))
    return out


def _load_prices(pack: Path, rel: str) -> list[dict[str, Any]]:
    with (pack / rel).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {
            "date": date.fromisoformat(r["date"]),
            "open": Decimal(r["open_usd"]),
            "high": Decimal(r["high_usd"]),
            "low": Decimal(r["low_usd"]),
            "close": Decimal(r["close_usd"]),
        }
        for r in rows
    ]


def _build_plan(
    m: CampaignManifest, rows: list[dict[str, Any]], figs: dict[str, Figure], salt: int
) -> NumberPlan:
    facts = [
        AmountFact(f"{{A{i}}}", f.family, f.value, f.family in RATIO_FAMILIES)
        for i, f in enumerate(figs.values(), 1)
    ]
    series = [(_real_day(r["date"]), r["high"]) for r in rows]  # max over all OHLC = max high
    beat_days = [_real_day(c.cutoff_date) for c in m.checkpoints]
    return NumberPlan.build(m.meta.case_id, salt, series, beat_days, facts)


def _year_like(values: dict[str, Decimal]) -> bool:
    return any(v == v.to_integral_value() and YEAR_LIKE[0] <= v.copy_abs() <= YEAR_LIKE[1]
               for v in values.values())  # fmt: skip


def approve_pack(pack_dir: Path, session: Session, salt: int = 0) -> ApproveResult:
    manifest_path = pack_dir / "manifest.json"
    try:
        m = CampaignManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report any schema problem as a reason
        return ApproveResult(False, reasons=[f"manifest does not load: {exc}"])
    rows = _load_prices(pack_dir, m.prices.path)
    report = validate_manifest(m, [r["date"] for r in rows])
    if not report.ok:
        return ApproveResult(False, reasons=[f"validation: {e}" for e in report.errors])

    figs = _collect_figures(m)
    plan = values = None
    used_salt = salt
    for used_salt in range(salt, salt + SALT_TRIES):  # noqa: B007
        plan = _build_plan(m, rows, figs, used_salt)
        values = _disguised_values(plan, figs)
        if not _year_like(values):
            break
    else:
        return ApproveResult(False, reasons=["every salt tried left a year-like number"])
    assert plan is not None and values is not None

    problems: list[str] = []
    cps = {c.id: c for c in m.checkpoints}
    # Re-base so the earliest day a player can see (chart start or first checkpoint) is day 0;
    # every story day below (checkpoints, beats, chart, day_map) shifts by this one offset.
    shown_days = [plan.story_day(_real_day(c.cutoff_date)) for c in m.checkpoints]
    shown_days += [
        plan.story_day(_real_day(r["date"])) for r in rows if r["date"] <= m.prices.decision_date
    ]
    offset = min(shown_days)

    def sday(d: date) -> int:
        return plan.story_day(_real_day(d)) - offset

    sd = {c.id: sday(c.cutoff_date) for c in m.checkpoints}
    pub = m.public_dict()
    pub["checkpoints"] = [
        {"id": c.id, "role": c.role, "label": c.label, "story_day": sd[c.id]} for c in m.checkpoints
    ]
    pub["prices"] = {
        "decision_story_day": sday(m.prices.decision_date),
        "horizon_story_day": sday(m.prices.horizon_end),
    }
    pub.pop("fund", None)
    ids = [c.id for c in m.checkpoints]
    ni = ids.index(m.news.checkpoint)
    news = pub["news"]
    assert isinstance(news, dict)
    news["time_skip_days"] = sd[ids[ni]] - sd[ids[ni - 1]] if ni > 0 else sd[ids[ni]]
    pub["debrief"] = {"questions": m.debrief.questions}
    pub["pack_id"] = m.meta.case_id

    def apply_values(node: Any, vals: dict[str, Decimal]) -> None:
        if isinstance(node, dict):
            if "id" in node and "family" in node and "value" in node:
                node["value"] = _fmt(vals[node["id"]])
            for v in node.values():
                apply_values(v, vals)
        elif isinstance(node, list):
            for v in node:
                apply_values(v, vals)

    rendered: dict[str, Any] = _render(pub, values, problems)
    apply_values(rendered, values)
    if problems:
        return ApproveResult(False, reasons=problems, salt=used_salt)

    terms = list(m.secret.leak_terms)
    long_terms = [t for t in terms if len(t) > SHORT_TERM_LEN]
    ctx = ScanContext(
        real_name=m.secret.real_entity,
        ticker=m.secret.ticker,
        identifying_terms=[t for t in long_terms if not re.fullmatch(r"[\d\-]+", t)],
    )
    allowed = sorted(
        {_fmt(v.copy_abs()) for v in values.values()} | {_fmt(v) for v in values.values()}
    )
    prose = prose_fields(rendered)
    closes = [r for r in rows if r["date"] <= m.prices.decision_date]
    result = scan_case(
        prose,
        ctx,
        real_prices=[float(r["close"]) for r in closes],
        shown_prices=[float(plan.scale_price(r["close"])) for r in closes],
        allowed_numbers=allowed,
    )
    reasons = [f"scan: {f.reason} in {f.field}: {f.excerpt!r}" for f in result.findings]
    for path, text in prose.items():  # short terms are case-sensitive ("Lay", "SEC", "ENE")
        reasons += [f"leak term {t!r} in {path}" for t in _leak_hits(text, terms)]
    reasons = list(dict.fromkeys(reasons))
    existing = _find_existing(session, m.meta.case_id)
    if reasons:
        if existing is not None:
            existing.status = "retired"
            session.add(existing)
            session.commit()
        return ApproveResult(False, reasons=reasons, salt=used_salt)

    # ---- chart, beats, secret -------------------------------------------------
    day_map = {r["date"].isoformat(): sday(r["date"]) for r in rows}
    chart: dict[int, dict[str, str]] = {}
    for r in closes:
        chart[day_map[r["date"].isoformat()]] = {
            "close": str(plan.scale_price(r["close"])),
            "open": str(plan.scale_price(r["open"])),
            "high": str(plan.scale_price(r["high"])),
            "low": str(plan.scale_price(r["low"])),
        }
    chart_series = [{"day": d, **v} for d, v in sorted(chart.items())]

    def close_on(d: date) -> Decimal:
        return next(r["close"] for r in reversed(rows) if r["date"] <= d)

    beat_src = [(e.checkpoint, e.id, e.title, e.player_text) for e in m.evidence
                if e.kind in ("announcement", "news")]  # fmt: skip
    beat_src.append((m.news.checkpoint, "news", m.news.headline, m.news.summary))
    beats, real_beats = [], []
    rev = {fid: f.value for fid, f in figs.items()}
    for cp, eid, title, text in sorted(beat_src, key=lambda b: ids.index(b[0])):
        day = sd[cp]
        beats.append(
            {"day": day, "evidence_id": eid, "title": title, "text": _fill(text, values, [], eid)}
        )
        real_beats.append(
            {
                "date": cps[cp].cutoff_date.isoformat(),
                "day": day,
                "price": str(close_on(cps[cp].cutoff_date)),
                "evidence_id": eid,
                "text": _fill(text, rev, [], eid),
            }
        )
    beats = _render(beats, values, [])
    buy = next(r for r in rows if r["date"] > m.prices.decision_date)
    horizon_close = next(r for r in reversed(rows) if r["date"] <= m.prices.horizon_end)
    money = plan.amount_factors.get("money")
    what_changed = [
        f"Company name {m.secret.real_entity} became {m.world.company_name}; "
        f"ticker {m.secret.ticker} hidden.",
        "All dates were replaced by story days; gaps between checkpoints were stretched or "
        "squeezed by up to 30 percent, in whole weeks.",
        f"Prices were multiplied by {plan.price_factor} (percentage moves unchanged).",
        f"All money amounts share one factor ({money}), so ledger comparisons still hold; "
        "values are rounded to 2 significant figures and shown at most 10,000.",
        "Per-share amounts use the price factor; percentages and ratios are unchanged.",
        *[f"Real term hidden: {t}" for t in m.secret.alias_map],
    ]
    scenario_json: dict[str, Any] = {
        "story_days": [sd[i] for i in ids],
        "chart_series": chart_series,
        "company_card": rendered["company_card"],
    }
    secret_json: dict[str, Any] = {
        "real_beats": {
            "beats": real_beats,
            "day_map": day_map,
            "checkpoint_days": sd,
            "decision_date": m.prices.decision_date.isoformat(),
            "buy_date": buy["date"].isoformat(),
            "horizon_end": m.prices.horizon_end.isoformat(),
            "decision_story_day": rendered["prices"]["decision_story_day"],
            "horizon_story_day": rendered["prices"]["horizon_story_day"],
            "buy_open": str(buy["open"]),
            "horizon_close": str(horizon_close["close"]),
            "post_reveal_facts": list(m.debrief.post_reveal_facts),
            "later_events": [e.model_dump() for e in m.secret.later_events],
        },
        "amount_factors": {
            **{k: str(v) for k, v in sorted(plan.amount_factors.items())},
            "price": str(plan.price_factor),
            "salt": used_salt,
        },
    }
    sc = existing or Scenario(
        invented_name=m.world.company_name, industry_shown=m.company_card.trade
    )
    sc.source = "reference_pack"
    sc.case_id = None
    sc.invented_name = m.world.company_name
    sc.industry_shown = m.company_card.trade
    sc.story_days = scenario_json["story_days"]
    sc.beats = beats
    sc.chart_series = scenario_json["chart_series"]
    sc.company_card = scenario_json["company_card"]
    sc.manifest = rendered
    sc.status = "playable"
    session.add(sc)
    session.flush()
    secret = session.get(ScenarioSecret, sc.id) or ScenarioSecret(scenario_id=sc.id, real_name="")
    secret.real_name = m.secret.real_entity
    secret.ticker = m.secret.ticker
    secret.real_beats = json.loads(json.dumps(secret_json["real_beats"], default=str))
    secret.price_series_ref = str((pack_dir / m.prices.path).resolve())
    secret.price_factor = plan.price_factor  # type: ignore[assignment]
    secret.amount_factors = secret_json["amount_factors"]
    secret.seed = plan.seed  # BIGINT: crc32(case_id) + salt
    secret.what_changed = what_changed
    secret.n_guessers = 0
    secret.leak_terms = terms
    session.add(secret)
    session.commit()
    return ApproveResult(True, str(sc.id), "playable", [], used_salt)


def _find_existing(session: Session, pack_id: str) -> Scenario | None:
    for sc in session.exec(select(Scenario).where(Scenario.source == "reference_pack")):
        if isinstance(sc.manifest, dict) and sc.manifest.get("pack_id") == pack_id:
            return sc
    return None


__all__ = ["ApproveResult", "approve_pack", "prose_fields", "DISPLAY_CAP"]
