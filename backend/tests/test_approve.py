import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session, select
from typer.testing import CliRunner

from financequest.cli import app
from financequest.db.models import Scenario, ScenarioSecret
from financequest.db.session import get_engine
from financequest.refpack.approve import approve_pack

PACK = Path(__file__).parent.parent / "financequest" / "fixtures" / "reference" / "fq-av-001"
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _strings(o: Any) -> list[str]:
    if isinstance(o, str):
        return [o]
    if isinstance(o, list):
        return [s for x in o for s in _strings(x)]
    if isinstance(o, dict):
        return [s for v in o.values() for s in _strings(v)]
    return []


def _shown_numbers(o: Any) -> list[float]:
    """Numbers in rendered texts (not ids) plus numeric figure values."""
    out: list[float] = []
    if isinstance(o, dict):
        if "family" in o and "value" in o:
            out.append(abs(float(o["value"])))
        for k, v in o.items():
            if k in ("player_text", "summary", "headline", "explain", "label", "title"):
                out += [float(n) for n in NUMBER.findall(v)] if isinstance(v, str) else []
            else:
                out += _shown_numbers(v)
    elif isinstance(o, list):
        for x in o:
            out += _shown_numbers(x)
    return out


@pytest.fixture
def approved(test_db_url: str) -> tuple[Session, Any]:
    with Session(get_engine()) as s:
        res = approve_pack(PACK, s)
        assert res.ok, res.reasons
        sc = s.get(Scenario, res.scenario_id and __import__("uuid").UUID(res.scenario_id))
        assert sc is not None
        s.expunge_all()
        return s, sc


def test_enron_is_playable_and_clean(approved: tuple[Session, Scenario]) -> None:
    _, sc = approved
    assert sc.status == "playable" and sc.source == "reference_pack" and sc.case_id is None
    blob = json.dumps(
        [sc.invented_name, sc.industry_shown, sc.story_days, sc.beats, sc.chart_series,
         sc.company_card, sc.manifest]
    )  # fmt: skip
    raw = json.loads((PACK / "manifest.json").read_text())
    for term in raw["secret"]["leak_terms"]:
        if term[0].isdigit():  # years and dates: checked below (prices have decimals)
            continue
        pat = re.escape(term)
        assert not re.search(rf"(?<!\w){pat}(?!\w)", blob, re.I if len(term) > 3 else 0), term
    assert not re.search(r"\b(million|billion)s?\b", blob, re.I)
    text = " ".join(_strings([sc.beats, sc.company_card, sc.manifest]))
    assert not re.search(r"(?<![\w.])(?:19|20)\d{2}(?![\w.])", text)
    assert not re.search(r"\b(19|20)\d{2}-\d{2}", blob)
    assert "secret" not in sc.manifest and "Enron" not in blob
    assert sc.story_days[0] >= 0 and sc.story_days == sorted(sc.story_days)
    assert all((d - sc.story_days[0]) % 7 == 0 for d in sc.story_days[1:])
    assert "{" not in blob.replace('{"', "").replace("{}", "")  # no unfilled placeholders


def test_all_shown_numbers_at_most_10000(approved: tuple[Session, Scenario]) -> None:
    _, sc = approved
    nums = _shown_numbers(sc.manifest) + _shown_numbers(sc.company_card)
    assert nums and max(nums) <= 10_000
    for p in sc.chart_series:
        assert float(p["high"]) <= 10_000


def test_money_ratio_preserved(approved: tuple[Session, Scenario]) -> None:
    _, sc = approved
    raw = json.loads((PACK / "manifest.json").read_text())
    real = {f["id"]: float(f["value"]) for e in raw["evidence"] for f in e["figures"]}
    shown = {f["id"]: float(f["value"]) for e in sc.manifest["evidence"] for f in e["figures"]}
    a, b = "FIG-NI-FY00", "FIG-CFO-FY00"
    assert shown[a] / shown[b] == pytest.approx(real[a] / real[b], rel=0.06)


def test_secret_holds_real_data(approved: tuple[Session, Scenario]) -> None:
    s, sc = approved
    sec = s.get(ScenarioSecret, sc.id)
    assert sec is not None
    assert sec.real_name == "Enron Corporation" and sec.n_guessers == 0
    assert "Enron" in sec.leak_terms and sec.price_series_ref.endswith("prices.csv")
    assert "money" in sec.amount_factors and sec.price_factor
    assert sec.real_beats["buy_date"] == "2001-10-18"
    assert sec.real_beats["day_map"]["2001-10-17"] == sec.real_beats["decision_story_day"]
    assert sec.what_changed


def test_reapprove_idempotent(approved: tuple[Session, Scenario]) -> None:
    s, sc = approved
    res = approve_pack(PACK, s)
    assert res.ok and res.scenario_id == str(sc.id)
    rows = [r for r in s.exec(select(Scenario)) if r.source == "reference_pack"]
    assert len([r for r in rows if r.manifest.get("pack_id") == "FQ-AV-001"]) == 1


def test_tampered_pack_not_playable(test_db_url: str, tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    shutil.copytree(PACK, pack)
    raw = json.loads((pack / "manifest.json").read_text())
    raw["checkpoints"][0]["label"] = "Skilling takes the stage"
    (pack / "manifest.json").write_text(json.dumps(raw))
    with Session(get_engine()) as s:
        res = approve_pack(pack, s)
    assert not res.ok and any("Skilling" in r for r in res.reasons)


def test_cli_approve(test_db_url: str) -> None:
    r = CliRunner().invoke(app, ["refpack", "approve", str(PACK)])
    assert r.exit_code == 0 and "status=playable" in r.output


def test_story_days_are_never_negative(approved: tuple[Session, Scenario]) -> None:
    """Player-facing story days start at 0 and every source of days shares one offset."""
    _, sc = approved
    chart_days = [p["day"] for p in sc.chart_series]
    assert min(chart_days) == 0
    assert all(b["day"] >= 0 for b in sc.beats)
    assert all(d >= 0 for d in sc.story_days)
    assert all(c["story_day"] >= 0 for c in sc.manifest["checkpoints"])
    assert sc.manifest["prices"]["decision_story_day"] >= max(chart_days)
    with Session(get_engine()) as s:
        secret = s.get(ScenarioSecret, sc.id)
        assert secret is not None
        dm = secret.real_beats["day_map"]
        assert min(dm.values()) == 0
        for p in sc.chart_series:
            assert p["day"] in dm.values()
        assert all(v >= 0 for v in secret.real_beats["checkpoint_days"].values())
