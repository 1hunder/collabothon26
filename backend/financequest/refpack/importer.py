"""Offline import: case.md + prices.csv -> draft manifest + validation report."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from financequest.llm import get_chat_model
from financequest.refpack.manifest import CampaignManifest
from financequest.refpack.validate import ValidationReport, validate_manifest

SYSTEM_PROMPT = """You draft a campaign manifest for a finance-education game from a historical \
case reference. Rules:
- Player-facing fields are fantasy-mapped: no real names, tickers, places, dates, years, months, \
and never the words million or billion.
- Amounts are never written in text. Put the REAL reported value in figures[] with a family and \
refer to it as {figure_id} in player_text.
- Only information available at or before the decision checkpoint is evidence. Later events go \
into debrief and secret.later_events.
- Every real name, ticker, person, place and real date string goes into secret.leak_terms.
- Every key evidence item must be reachable without dice. Return the full manifest."""


@dataclass
class ParsedPack:
    frontmatter: dict[str, str]
    sections: dict[str, str]
    markdown: str
    price_rows: list[dict[str, str]]

    @property
    def price_dates(self) -> list[date]:
        return [date.fromisoformat(r["date"]) for r in self.price_rows]


def parse_frontmatter(md: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n", md, re.DOTALL)
    if not m:
        return {}, md
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm, md[m.end() :]


def parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    title: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if title is not None:
                sections[title] = "\n".join(buf).strip()
            title, buf = line[3:].strip(), []
        elif title is not None:
            buf.append(line)
    if title is not None:
        sections[title] = "\n".join(buf).strip()
    return sections


def parse_pack(case_md: Path, prices_csv: Path) -> ParsedPack:
    md = case_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(md)
    with prices_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return ParsedPack(fm, parse_sections(body), md, rows)


@dataclass
class ImportResult:
    manifest_path: Path
    report_path: Path
    report: ValidationReport


def import_pack(
    case_md: Path, prices_csv: Path, out_dir: Path, fake_responses: list[Any] | None = None
) -> ImportResult:
    pack = parse_pack(case_md, prices_csv)
    out_dir.mkdir(parents=True, exist_ok=True)
    llm = get_chat_model(fake_responses)
    prompt = (
        f"Case id: {pack.frontmatter.get('case_id', '?')}\n"
        f"Price table: {pack.price_dates[0]} to {pack.price_dates[-1]}, "
        f"{len(pack.price_rows)} rows.\n\n--- CASE MARKDOWN ---\n{pack.markdown}"
    )
    raw = llm.with_structured_output(CampaignManifest).invoke(
        [("system", SYSTEM_PROMPT), ("human", prompt)]
    )
    manifest_path = out_dir / "manifest.draft.json"
    report_path = out_dir / "validation-report.md"
    try:
        manifest = (
            raw if isinstance(raw, CampaignManifest) else CampaignManifest.model_validate(raw)
        )
    except ValidationError as exc:
        report = ValidationReport(errors=[f"draft does not match the manifest schema: {exc}"])
        manifest_path.write_text(json.dumps(raw, default=str, indent=2), encoding="utf-8")
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        return ImportResult(manifest_path, report_path, report)
    report = validate_manifest(manifest, pack.price_dates)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(report.to_markdown(), encoding="utf-8")
    return ImportResult(manifest_path, report_path, report)
