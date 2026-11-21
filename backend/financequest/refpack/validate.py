"""Deterministic invariants for a campaign manifest (spec 003 tech section 2.4)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from financequest.refpack.manifest import CampaignManifest

PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_-]+)(?::abs)?\}")
MAGNITUDE_WORDS = re.compile(r"\b(?:million|billion|trillion)s?\b", re.IGNORECASE)
MONTHS = "January|February|April|June|July|August|September|October|November|December"
MONTH_WORDS = re.compile(rf"\b(?:{MONTHS})\b")
REASON_DATE = "Real date found in text"  # spec 2.3.6
YEAR_WORDS = re.compile(r"(?<!\d)(?:1[5-9]|20)\d\d(?!\d)")
WEEKDAY_WORDS = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.IGNORECASE
)
SHORT_TERM_LEN = 3  # terms this short are matched case-sensitively ("Lay", "ENE", "SEC")


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_rows: list[tuple[str, str, str, bool, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_markdown(self, title: str = "Reference pack validation report") -> str:
        lines = [f"# {title}", "", f"Result: **{'PASS' if self.ok else 'FAIL'}**", ""]
        lines += [f"## Errors ({len(self.errors)})", ""]
        lines += [f"- {e}" for e in self.errors] or ["- none"]
        lines += ["", f"## Warnings ({len(self.warnings)})", ""]
        lines += [f"- {w}" for w in self.warnings] or ["- none"]
        lines += ["", "## Evidence for review", ""]
        lines += ["| id | checkpoint | location | key | source |", "|---|---|---|---|---|"]
        for eid, cp, loc, key, src in self.evidence_rows:
            lines.append(f"| {eid} | {cp} | {loc} | {'yes' if key else ''} | {src} |")
        return "\n".join(lines) + "\n"


def player_texts(m: CampaignManifest) -> list[tuple[str, str]]:
    """Every string a player can see before the reveal (debrief and secret excluded)."""
    out: list[tuple[str, str]] = []

    def add(path: str, text: str) -> None:
        if text:
            out.append((path, text))

    add("meta.campaign_title", m.meta.campaign_title)
    for i, o in enumerate(m.meta.learning_objectives):
        add(f"meta.learning_objectives[{i}]", o)
    for k, v in m.world.model_dump().items():
        add(f"world.{k}", str(v))
    for cp in m.checkpoints:
        add(f"checkpoints.{cp.id}.label", cp.label)
    cc = m.company_card
    for k in ("name", "trade", "size"):
        add(f"company_card.{k}", getattr(cc, k))
    for kf in cc.key_figures:
        add(f"company_card.{kf.id}.label", kf.label)
        add(f"company_card.{kf.id}.period", kf.period or "")
        add(f"company_card.{kf.id}.explain", kf.explain)
    for e in m.evidence:
        add(f"evidence.{e.id}.title", e.title)
        add(f"evidence.{e.id}.player_text", e.player_text)
        add(f"evidence.{e.id}.teaching_note", e.teaching_note)
        for f in e.figures:
            add(f"evidence.{e.id}.{f.id}.label", f.label)
            add(f"evidence.{e.id}.{f.id}.period", f.period or "")
    for d in m.documents:
        add(f"documents.{d.id}.title", d.title)
    for c in m.characters:
        for k in ("name", "role"):
            add(f"characters.{c.id}.{k}", getattr(c, k))
        for i, n in enumerate(c.never):
            add(f"characters.{c.id}.never[{i}]", n)
    for en in m.encounters:
        for k in ("title", "skill_flavor", "failure_forward", "teaching_target"):
            add(f"encounters.{en.id}.{k}", getattr(en, k))
    add("news.headline", m.news.headline)
    add("news.summary", m.news.summary)
    for s in m.campaign_location_seeds:
        for k in ("name", "description", "art_subject"):
            add(f"campaign_location_seeds.{s.key}.{k}", getattr(s, k))
    return out


def _leak_hits(text: str, terms: Iterable[str]) -> list[str]:
    hits = []
    for term in terms:
        flags = 0 if len(term) <= SHORT_TERM_LEN else re.IGNORECASE
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags):
            hits.append(term)
    return hits


def _check_text(m: CampaignManifest, r: ValidationReport) -> None:
    terms = [t for t in m.secret.leak_terms if t.strip()]
    if not terms:
        r.errors.append("secret.leak_terms is empty")
    fig_by_evidence = {e.id: {f.id for f in e.figures} for e in m.evidence}
    news_figs = {f for eid in m.news.evidence_ids for f in fig_by_evidence.get(eid, set())}
    for path, text in player_texts(m):
        for term in _leak_hits(text, terms):
            r.errors.append(f"leak term '{term}' in {path}")
        if MAGNITUDE_WORDS.search(text):
            r.errors.append(f"magnitude word (million/billion) in {path}")
        if MONTH_WORDS.search(text):
            r.errors.append(f"{REASON_DATE}: month name in {path}")
        if WEEKDAY_WORDS.search(PLACEHOLDER.sub("", text)):
            r.errors.append(f"{REASON_DATE}: weekday in {path}")
        if YEAR_WORDS.search(PLACEHOLDER.sub("", text)):
            r.errors.append(f"{REASON_DATE}: year in {path}")
        stripped = PLACEHOLDER.sub("", text)
        if re.search(r"\d", stripped):
            r.errors.append(f"raw number in {path}: use a {{figure_id}} placeholder")
        # Placeholders must resolve against the figures available to that text.
        parts = path.split(".")
        allowed: set[str] | None = None
        if parts[0] == "evidence" and parts[2] == "player_text":
            allowed = fig_by_evidence.get(parts[1], set())
        elif path == "news.summary" or path == "news.headline":
            allowed = news_figs
        elif parts[0] == "company_card":
            allowed = {kf.id for kf in m.company_card.key_figures}
        for ph in PLACEHOLDER.findall(text):
            if allowed is None:
                r.errors.append(f"placeholder {{{ph}}} not allowed in {path}")
            elif ph not in allowed:
                r.errors.append(f"placeholder {{{ph}}} in {path} has no matching figure")


def _check_structure(
    m: CampaignManifest, r: ValidationReport, price_dates: list[date] | None
) -> None:
    cps = m.checkpoints
    by_id = {c.id: c for c in cps}
    if len(by_id) != len(cps):
        r.errors.append("duplicate checkpoint ids")
    roles = {c.role: c for c in cps}
    for role in ("intro", "disclosure", "decision"):
        if role not in roles:
            r.errors.append(f"checkpoint role '{role}' missing")
    if {"intro", "disclosure", "decision"} <= roles.keys():
        cp_i, cp_d, cp_c = roles["intro"], roles["disclosure"], roles["decision"]
        if not (cp_i.cutoff_date < cp_d.cutoff_date <= cp_c.cutoff_date):
            r.errors.append("checkpoints intro/disclosure/decision are not in date order")
        if cp_c.cutoff_date != m.prices.decision_date:
            r.errors.append("decision checkpoint date differs from prices.decision_date")
    ordered = sorted(cps, key=lambda c: c.cutoff_date)
    if [c.id for c in ordered] != [c.id for c in cps]:
        r.errors.append("checkpoints are not listed in date order")
    decision = roles.get("decision")
    order = {c.id: n for n, c in enumerate(cps)}

    def after_decision(cp: str) -> bool:
        return decision is None or cp not in order or order[cp] > order[decision.id]

    ev = {e.id: e for e in m.evidence}
    if len(ev) != len(m.evidence):
        r.errors.append("duplicate evidence ids")
    figure_ids = [f.id for e in m.evidence for f in e.figures] + [
        k.id for k in m.company_card.key_figures
    ]
    if len(set(figure_ids)) != len(figure_ids):
        # A key figure may legitimately reuse an evidence figure id only if values agree.
        seen: dict[str, object] = {}
        for f in [f for e in m.evidence for f in e.figures] + m.company_card.key_figures:
            if f.id in seen and seen[f.id] != f.value:
                r.errors.append(f"figure id {f.id} used with different values")
            seen[f.id] = f.value
    for e in m.evidence:
        if e.checkpoint not in by_id:
            r.errors.append(f"evidence {e.id}: unknown checkpoint {e.checkpoint}")
        elif after_decision(e.checkpoint):
            r.errors.append(f"evidence {e.id} is after the decision checkpoint ({e.checkpoint})")
        if e.location.startswith("campaign:"):
            key = e.location.split(":", 1)[1]
            if key not in {s.key for s in m.campaign_location_seeds}:
                r.errors.append(f"evidence {e.id}: unknown campaign location {key}")
    for d in m.documents:
        if after_decision(d.checkpoint):
            r.errors.append(f"document {d.id} is after the decision checkpoint ({d.checkpoint})")
        for eid in d.evidence_ids:
            if eid not in ev:
                r.errors.append(f"document {d.id}: unknown evidence {eid}")
            elif order.get(ev[eid].checkpoint, 99) > order.get(d.checkpoint, -1):
                r.errors.append(f"document {d.id} holds later evidence {eid}")
    for ch in m.characters:
        for cp, ids in ch.may_reveal.items():
            for eid in ids:
                if eid not in ev:
                    r.errors.append(f"character {ch.id}: unknown evidence {eid}")
                elif order.get(ev[eid].checkpoint, 99) > order.get(cp, -1):
                    r.errors.append(f"character {ch.id} reveals {eid} before its checkpoint")
    for cid in m.news.evidence_ids:
        if cid not in ev:
            r.errors.append(f"news: unknown evidence {cid}")
    if m.news.checkpoint not in by_id or after_decision(m.news.checkpoint):
        r.errors.append("news checkpoint must be at or before the decision")
    if m.news.time_skip_days < 1:
        r.errors.append("news.time_skip_days must be positive")

    # Key evidence reachable without dice.
    free: set[str] = {i for d in m.documents for i in d.evidence_ids}
    free |= {i for c in m.characters for ids in c.may_reveal.values() for i in ids}
    free |= {i for en in m.encounters for i in en.evidence_ids}
    keys = [e for e in m.evidence if e.key]
    if not keys:
        r.errors.append("no key evidence")
    for e in keys:
        if e.id not in free:
            r.errors.append(f"key evidence {e.id} is reachable only through dice")

    # Encounters.
    if not 2 <= len(m.encounters) <= 4:
        r.errors.append(f"encounters must number 2-4, found {len(m.encounters)}")
    for en in m.encounters:
        if not 5 <= en.dc <= 20:
            r.errors.append(f"encounter {en.id}: dc {en.dc} outside 5-20")
        if after_decision(en.checkpoint):
            r.errors.append(f"encounter {en.id} is after the decision checkpoint")
        for eid in [*en.evidence_ids, en.success_clue_id]:
            if eid not in ev:
                r.errors.append(f"encounter {en.id}: unknown evidence {eid}")

    # Prices.
    p = m.prices
    if p.horizon_end <= p.decision_date:
        r.errors.append("horizon_end must be after the decision date")
    if price_dates is not None:
        pd_set = set(price_dates)
        intro = roles.get("intro")
        if not price_dates:
            r.errors.append("price table is empty")
        else:
            if intro and min(price_dates) > intro.cutoff_date:
                r.errors.append("price table starts after the intro date")
            if max(price_dates) < p.horizon_end:
                r.errors.append("price table ends before horizon_end")
        if p.decision_date not in pd_set:
            r.errors.append("decision date is not a trading day in the price table")
        if not any(p.decision_date < d <= p.horizon_end for d in pd_set):
            r.errors.append("no trading day after the decision date (no buying day)")

    # Rubric.
    if m.rubric is not None:
        if sum(i.max for i in m.rubric) != 100:
            r.errors.append(f"rubric totals {sum(i.max for i in m.rubric)}, expected 100")
        if not any("reflection" in i.category.lower() for i in m.rubric):
            r.errors.append("rubric has no reflection category")

    if not m.campaign_location_seeds:
        r.warnings.append("no campaign_location_seeds")
    if m.fund is None:
        r.warnings.append("no fund series: Spread will be hidden")


def validate_manifest(
    m: CampaignManifest, price_dates: list[date] | None = None
) -> ValidationReport:
    r = ValidationReport()
    _check_structure(m, r, price_dates)
    _check_text(m, r)
    for e in m.evidence:
        r.evidence_rows.append(
            (e.id, e.checkpoint, e.location, e.key, m.secret.evidence_sources.get(e.id, "?"))
        )
    return r
