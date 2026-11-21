"""Per-company quest agent: one LangGraph run per company, on its own thread (see jobs.py).

find_windows -> research -> draft_manifest -> disguise -> (publish | redraft | fail)

- find_windows (code): price history -> candidate shock windows (market.py)
- research (Claude + web search): picks one window, writes a reference-pack case document
- draft_manifest (Claude, structured): case -> campaign manifest, validated; repaired up to twice
- disguise (code): ``refpack approve`` (numbers, story days, deterministic final scan). The scan
  is the leak safety: no real name or date may appear in player text. If it fails, its reasons go
  back to draft_manifest for one rewrite (MAX_DRAFTS drafts in all), then the quest fails.

There is no recognisability check here: famous companies are fine. (Spec 002's batch gate in
``reid/`` stays for the curated pipeline.) The pack's documents (case.md, prices.csv,
manifest.json) are saved to durable storage (storage.py) under ``storage_prefix``.

FAKE_LLM=1 runs the same graph without keys or network: the research and manifest steps reuse the
sample reference pack.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from financequest.config import Settings, get_settings
from financequest.db.models import Scenario
from financequest.db.session import get_engine
from financequest.llm import AnthropicNodeLLM, DefaultFakeNodeLLM, NodeLLM, get_chat_model
from financequest.personal import market, prompts
from financequest.personal.transactions import Category, Company
from financequest.refpack.approve import approve_pack
from financequest.refpack.importer import SYSTEM_PROMPT as MANIFEST_SYSTEM
from financequest.refpack.manifest import CampaignManifest
from financequest.refpack.validate import validate_manifest
from financequest.reid.schemas import GuesserReport
from financequest.storage import materialise, put_many

SAMPLE_PACK = Path(__file__).resolve().parent.parent / "fixtures" / "reference" / "fq-av-001"
MAX_DRAFTS = 2  # first draft + one rewrite when the final scan finds a leak
PACK_FILES = ("case.md", "prices.csv", "manifest.json")
MANIFEST_REPAIRS = 2
FAKE_STEP_DELAY_S = 1.5

Progress = Callable[[str, dict[str, Any]], None]

_log = logging.getLogger(__name__)


class QuestState(TypedDict, total=False):
    pack_id: str
    pack_dir: str
    windows: list[dict[str, Any]]
    window: dict[str, Any]
    attempt: int  # draft number, 1..MAX_DRAFTS
    scenario_id: str | None
    outcome: str  # checking / scan / approved
    reasons: list[str]  # final-scan findings fed back to the next draft


class QuestFailed(Exception):
    """A step could not complete (no price history, unusable research, invalid manifest)."""


# ---- helpers ----------------------------------------------------------------------------------


def _window_dict(w: market.Window) -> dict[str, Any]:
    d = asdict(w)
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in d.items()}


def parse_research(text: str, n_windows: int) -> tuple[int, str]:
    """``CHOSEN_WINDOW: n`` then the Markdown case (fences tolerated)."""
    m = re.search(r"CHOSEN_WINDOW:\s*(\d+)", text)
    idx = int(m.group(1)) if m else 0
    if not 0 <= idx < max(1, n_windows):
        idx = 0
    body = text[m.end() :] if m else text
    body = re.sub(r"^\s*```(?:markdown|md)?\s*\n", "", body)
    body = re.sub(r"\n```\s*$", "", body.rstrip())
    start = body.find("---")
    case = body[start:].strip() if start != -1 else body.strip()
    if "## " not in case or len(case) < 1500:
        raise QuestFailed("research did not return a usable case document")
    return idx, case + "\n"


# ---- the graph --------------------------------------------------------------------------------


def build_quest_graph(
    company: Company,
    category: Category,
    pack_dir: Path,
    pack_id: str,
    progress: Progress,
    *,
    settings: Settings | None = None,
    node_llm: NodeLLM | None = None,
    chat_model_factory: Callable[[], Any] | None = None,
    downloader: market.OhlcDownloader | None = None,
    journal: list[dict[str, Any]] | None = None,
    storage_prefix: str | None = None,
) -> Any:
    """``journal`` collects the job log as the run goes, so it survives a crash (the caller
    persists it); ``storage_prefix`` is where the pack's documents are saved for good."""
    cfg = settings or get_settings()
    jr = journal if journal is not None else []

    def save_docs() -> None:
        if storage_prefix:
            files = {n: pack_dir / n for n in PACK_FILES if (pack_dir / n).is_file()}
            put_many(storage_prefix, files)

    fake = cfg.fake_llm
    llm: NodeLLM = node_llm or (DefaultFakeNodeLLM() if fake else AnthropicNodeLLM(32000))

    def pause() -> None:
        if fake and node_llm is None:
            time.sleep(FAKE_STEP_DELAY_S)

    def find_windows(state: QuestState) -> dict[str, Any]:
        progress("Reading the market history", {})
        pause()
        if fake and downloader is None:
            return {"windows": [], "attempt": 1}
        frame = market.load_history(company.ticker, Path(cfg.cache_dir), downloader)
        windows = market.find_windows(frame)
        if not windows:
            raise QuestFailed(f"no usable price history for {company.ticker}")
        jr.append({"step": "windows", "windows": [w.describe() for w in windows]})
        return {"windows": [_window_dict(w) for w in windows], "attempt": 1}

    def research(state: QuestState) -> dict[str, Any]:
        progress("Researching the story", {})
        pause()
        pack_dir.mkdir(parents=True, exist_ok=True)
        if fake and downloader is None:
            shutil.copy(SAMPLE_PACK / "case.md", pack_dir / "case.md")
            shutil.copy(SAMPLE_PACK / "prices.csv", pack_dir / "prices.csv")
            save_docs()
            return {"window": {"fake": True}, "pack_dir": str(pack_dir)}
        date_keys = ("intro", "shock", "decision", "buy", "horizon")
        windows = []
        for w in state["windows"]:
            kwargs: dict[str, Any] = {
                k: (date.fromisoformat(v) if k in date_keys else v) for k, v in w.items()
            }
            windows.append(market.Window(**kwargs))
        frame = market.load_history(company.ticker, Path(cfg.cache_dir), downloader)
        human = prompts.RESEARCH_HUMAN.format(
            company=company.name,
            ticker=company.ticker,
            aliases=", ".join(company.aliases) or "none",
            windows="\n".join(w.describe() for w in windows),
            first_index=windows[0].index,
            summary=market.price_summary(frame, windows[0]),
        )
        messages = [
            SystemMessage(content=prompts.RESEARCH_SYSTEM.format(case_id=pack_id)),
            HumanMessage(content=human),
        ]
        res = None
        for fallback in (False, True):  # a refusal is retried once, as in the gate graph
            res = llm.run("research_company", messages, schema=GuesserReport, effort="high",
                          web_search_max_uses=cfg.web_search_max_uses, fallback=fallback)  # fmt: skip  # noqa: E501
            if not res.refused:
                break
        if res is None or res.refused or res.stop_reason not in (None, "end_turn"):
            raise QuestFailed(f"research call ended with {res.stop_reason if res else None}")
        idx, case = parse_research(res.text, len(windows))
        win = next((w for w in windows if w.index == idx), windows[0])
        (pack_dir / "case.md").write_text(case, encoding="utf-8")
        market.write_prices_csv(frame, win, pack_dir / "prices.csv", company.ticker)
        jr.append({"step": "research", "window": win.describe(), "usage": res.usage})
        save_docs()
        return {"window": _window_dict(win), "pack_dir": str(pack_dir)}

    def draft_manifest(state: QuestState) -> dict[str, Any]:
        n = state.get("attempt", 1)
        progress("Writing the campaign" if n == 1 else "Polishing the campaign", {})
        if state.get("reasons"):
            jr.append({"step": "redraft", "draft": n, "scan_findings": len(state["reasons"])})
        pause()
        if fake and downloader is None:
            data = json.loads((SAMPLE_PACK / "manifest.json").read_text(encoding="utf-8"))
            data["meta"]["case_id"] = pack_id
            (pack_dir / "manifest.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            save_docs()
            return {}
        from financequest.refpack.importer import parse_pack

        pack = parse_pack(pack_dir / "case.md", pack_dir / "prices.csv")
        w = state["window"]
        extra = (
            f"\n\nFixed values for this pack: meta.case_id = {pack_id}; prices.path = prices.csv; "
            f"checkpoints G0 intro {w['intro']}, G1 disclosure {w['shock']}, G2 decision "
            f"{w['decision']}; prices.decision_date = {w['decision']}; prices.horizon_end = "
            f"{w['horizon']}; news.checkpoint = G1. Give 2-4 encounters with dc 10-15 and at "
            "least one key evidence item reachable without dice. If you give a rubric it must "
            "total 100 and include a reflection category."
        )
        if state.get("reasons"):
            extra += "\n\n" + prompts.MANIFEST_REWRITE.format(
                reasons="\n".join(f"- {c}" for c in state["reasons"][:10])
            )
        model = (chat_model_factory or get_chat_model)()
        human = (
            f"Case id: {pack_id}\nPrice table: {pack.price_dates[0]} to {pack.price_dates[-1]}, "
            f"{len(pack.price_rows)} rows.{extra}\n\n--- CASE MARKDOWN ---\n{pack.markdown}"
        )
        convo: list[Any] = [("system", MANIFEST_SYSTEM), ("human", human)]
        errors: list[str] = []
        for _ in range(MANIFEST_REPAIRS + 1):
            try:
                # The structured-output parser itself raises on an invalid value (e.g. a figure
                # written as "low 30s"), so the call belongs inside the repair loop.
                # json_schema: forced tool calling is not supported on this model / with thinking
                raw = model.with_structured_output(
                    CampaignManifest, method="json_schema"
                ).invoke(convo)
                m = raw if isinstance(raw, CampaignManifest) else CampaignManifest.model_validate(raw)  # noqa: E501
            except Exception as exc:  # noqa: BLE001 - schema problems are repaired below
                errors = [f"schema: {exc}"[:2000]]
                jr.append({"step": "draft_error", "draft": n, "errors": errors})
            else:
                report = validate_manifest(m, pack.price_dates)
                errors = report.errors
                if not report.ok:
                    jr.append({"step": "draft_invalid", "draft": n, "errors": errors[:10]})
                if report.ok:
                    (pack_dir / "manifest.json").write_text(
                        json.dumps(m.model_dump(mode="json"), indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    save_docs()
                    return {}
            convo = [*convo, ("human", "The manifest failed validation. Fix every error and "
                              "return the full manifest again:\n- " + "\n- ".join(errors))]  # fmt: skip  # noqa: E501
        raise QuestFailed("manifest invalid after repairs: " + "; ".join(errors[:5]))

    def disguise(state: QuestState) -> dict[str, Any]:
        progress("Disguising names, dates and numbers", {})
        pause()
        n = state.get("attempt", 1)
        work, price_ref = pack_dir, None
        if storage_prefix:  # approve reads the pack back from durable storage
            work = materialise(storage_prefix, list(PACK_FILES))
            price_ref = f"{storage_prefix}/prices.csv"
        try:
            with Session(get_engine()) as s:
                res = approve_pack(work, s, status="checking", price_ref=price_ref)
        finally:
            if work != pack_dir:
                shutil.rmtree(work, ignore_errors=True)
        if not res.ok:
            _log.info("quest %s draft %s: final scan failed %s", pack_id, n, list(res.reasons)[:5])
            jr.append({"step": "scan", "draft": n, "reasons": list(res.reasons)[:20]})
            return {"scenario_id": res.scenario_id, "reasons": res.reasons, "outcome": "scan"}
        return {"scenario_id": res.scenario_id, "reasons": [], "outcome": "checking"}

    def route(state: QuestState) -> str:
        if state.get("outcome") != "scan":
            return "publish"
        return "retry" if state.get("attempt", 1) < MAX_DRAFTS else "fail"

    def retry(state: QuestState) -> dict[str, Any]:
        return {"attempt": state.get("attempt", 1) + 1}

    def publish(state: QuestState) -> dict[str, Any]:
        _set_status(state.get("scenario_id"), "playable")
        progress("Ready", {})
        return {"outcome": "approved"}

    def fail(state: QuestState) -> dict[str, Any]:
        found = "; ".join(state.get("reasons", [])[:5])
        raise QuestFailed(f"final leak scan failed after {state.get('attempt', 1)} drafts: {found}")

    g = StateGraph(QuestState)
    for name, fn in (("find_windows", find_windows), ("research", research),
                     ("draft_manifest", draft_manifest), ("disguise", disguise),
                     ("retry", retry), ("publish", publish), ("fail", fail)):  # fmt: skip
        g.add_node(name, fn)
    g.add_edge(START, "find_windows")
    g.add_edge("find_windows", "research")
    g.add_edge("research", "draft_manifest")
    g.add_edge("draft_manifest", "disguise")
    g.add_conditional_edges("disguise", route, {"publish": "publish", "retry": "retry",
                                                "fail": "fail"})  # fmt: skip
    g.add_edge("retry", "draft_manifest")
    g.add_edge("publish", END)
    g.add_edge("fail", END)
    return g.compile()


def _set_status(scenario_id: str | None, status: str) -> None:
    if not scenario_id:
        return
    with Session(get_engine()) as s:
        sc = s.get(Scenario, uuid.UUID(str(scenario_id)))
        if sc is not None:
            sc.status = status
            s.add(sc)
            s.commit()


__all__ = ["QuestFailed", "build_quest_graph", "parse_research"]
