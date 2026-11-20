import copy
import csv
import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from financequest.cli import app
from financequest.refpack.importer import import_pack, parse_pack
from financequest.refpack.manifest import CampaignManifest
from financequest.refpack.validate import validate_manifest

PACK = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"


def _prices() -> list[date]:
    with (PACK / "prices.csv").open() as fh:
        return [date.fromisoformat(r["date"]) for r in csv.DictReader(fh)]


def _raw() -> dict:
    return json.loads((PACK / "manifest.json").read_text())


def _errors(raw: dict, prices: list[date] | None = None) -> list[str]:
    m = CampaignManifest.model_validate(raw)
    return validate_manifest(m, _prices() if prices is None else prices).errors


def test_enron_manifest_validates() -> None:
    m = CampaignManifest.model_validate(_raw())
    report = validate_manifest(m, _prices())
    assert report.errors == []
    assert len(m.evidence) >= 15 and len(m.encounters) == 4
    assert [e.dc for e in m.encounters] == [12, 14, 14, 12]
    assert "secret" not in m.public_dict()


def test_g3_evidence_before_decision_fails() -> None:
    raw = _raw()
    raw["checkpoints"] += [
        {"id": "G3", "role": "outcome", "cutoff_date": "2001-12-31", "label": "Outcome"}
    ]
    raw["evidence"][0]["checkpoint"] = "G3"
    assert any("after the decision checkpoint" in e for e in _errors(raw))


def test_leak_term_in_player_text_fails() -> None:
    raw = _raw()
    raw["evidence"][0]["player_text"] += " Enron said so."
    assert any("leak term 'Enron'" in e for e in _errors(raw))


def test_raw_number_and_magnitude_fail() -> None:
    raw = _raw()
    raw["evidence"][1]["player_text"] += " Sales hit 100 million."
    errs = _errors(raw)
    assert any("raw number" in e for e in errs) and any("magnitude" in e for e in errs)


def test_no_trading_day_after_decision_fails() -> None:
    prices = [d for d in _prices() if d <= date(2001, 10, 17)]
    errs = _errors(_raw(), prices)
    assert any("no trading day after" in e for e in errs)


def test_decision_not_trading_day_fails() -> None:
    prices = [d for d in _prices() if d != date(2001, 10, 17)]
    assert any("not a trading day" in e for e in _errors(_raw(), prices))


def test_rubric_not_100_fails() -> None:
    raw = _raw()
    raw["rubric"][0]["max"] = 30
    assert any("rubric totals 105" in e for e in _errors(raw))


def test_too_few_encounters_fails() -> None:
    raw = _raw()
    raw["encounters"] = raw["encounters"][:1]
    assert any("encounters must number 2-4" in e for e in _errors(raw))


def test_key_evidence_only_behind_dice_fails() -> None:
    raw = _raw()
    raw["evidence"].append({**copy.deepcopy(raw["evidence"][0]), "id": "F-GATED", "key": True})
    raw["encounters"][0]["success_clue_id"] = "F-GATED"
    assert any("reachable only through dice" in e for e in _errors(raw))


def test_dc_out_of_range_fails() -> None:
    raw = _raw()
    raw["encounters"][0]["dc"] = 25
    assert any("dc 25" in e for e in _errors(raw))


def test_importer_round_trip_with_fake_llm(tmp_path: Path) -> None:
    raw = _raw()
    result = import_pack(PACK / "case.md", PACK / "prices.csv", tmp_path, [raw])
    assert result.report.ok
    drafted = json.loads(result.manifest_path.read_text())
    assert CampaignManifest.model_validate(drafted) == CampaignManifest.model_validate(raw)
    assert "PASS" in result.report_path.read_text()
    assert "F-Q3-LOSS-001" in result.report_path.read_text()


def test_importer_reports_schema_failure(tmp_path: Path) -> None:
    result = import_pack(PACK / "case.md", PACK / "prices.csv", tmp_path, [{"meta": {}}])
    assert not result.report.ok


def test_parse_pack_sections() -> None:
    pack = parse_pack(PACK / "case.md", PACK / "prices.csv")
    assert pack.frontmatter["case_id"] == "FQ-AV-001"
    assert any(t.startswith("11.") for t in pack.sections)
    assert len(pack.price_rows) == 102


def test_cli_import_with_fake_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from financequest.config import get_settings

    monkeypatch.setenv("FAKE_LLM", "1")
    get_settings.cache_clear()
    try:
        res = CliRunner().invoke(
            app,
            [
                "refpack",
                "import",
                str(PACK / "case.md"),
                str(PACK / "prices.csv"),
                "--out",
                str(tmp_path),
            ],
        )
    finally:
        monkeypatch.delenv("FAKE_LLM")
        get_settings.cache_clear()
    assert res.exit_code == 0, res.output
    assert (tmp_path / "manifest.draft.json").exists()
