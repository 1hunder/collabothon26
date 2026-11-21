"""Per-company quest agent: one LangGraph run per company, on its own thread (see jobs.py).

find_windows -> research -> draft_manifest -> disguise -> guess -> (publish | retry | reject)

- find_windows (code): price history -> candidate shock windows (market.py)
- research (Claude + web search): picks one window, writes a reference-pack case document
- draft_manifest (Claude, structured): case -> campaign manifest, validated; repaired up to twice
- disguise (code): ``refpack approve`` with status ``checking`` (numbers, story days, final scan)
- guess (Claude): the recognition gate of spec 002 on the player-visible campaign, memory round
  then web round, 3 personas each
- on recognition the manifest is redrafted with the guessers' clues, up to MAX_ATTEMPTS; then the
  company is rejected and the scenario retired

FAKE_LLM=1 runs the same graph without keys or network: the research and manifest steps reuse the
sample reference pack, and the default fake guessers never recognise anything.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
from financequest.reid import rules
from financequest.reid.graph import call_node
from financequest.reid.match import MatchTargets
from financequest.reid.prompts.guesser import (
    DISGUISE_RULES_DESCRIPTION,
    GUESSER_SYSTEM,
    PERSONA_SUFFIX,
    WEB_INSTRUCTIONS,
)
from financequest.reid.schemas import GuesserReport

SAMPLE_PACK = Path(__file__).resolve().parent.parent / "fixtures" / "reference" / "fq-av-001"
PERSONAS = ("generalist", "forensic", "industry")
MANIFEST_REPAIRS = 2
FAKE_STEP_DELAY_S = 1.5

FANTASY_NOTE = (
    "\n- The story is told as a fantasy re-skin: the company, its shares, the market, people and "
    "places carry invented fantasy names; the trade may be generalised or moved to a similar one."
)

Progress = Callable[[str, dict[str, Any]], None]

_log = logging.getLogger(__name__)


class QuestState(TypedDict, total=False):
    pack_id: str
    pack_dir: str
    windows: list[dict[str, Any]]
    window: dict[str, Any]
    attempt: int
    clues: list[str]
    scenario_id: str | None
    outcome: str  # approved / rejected / failed
    reasons: list[str]
    log: list[dict[str, Any]]


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


def player_view_text(sc: Scenario) -> str:
    """Everything a player can see before the company reveal, as one plain text for guessers."""
    m = sc.manifest if isinstance(sc.manifest, dict) else {}
    world, card = m.get("world", {}), m.get("company_card", {})
    lines = [
        f"Setting: {world.get('setting_name', '')}. Company: {world.get('company_name', '')} "
        f"({card.get('trade', '')}; {card.get('size', '')}). Shares: {world.get('shares_name', '')}"
        f"; market: {world.get('market_name', '')}.",
        "Key figures (disguised scale):",
        *[f"- {k.get('label')}: {k.get('value')} ({k.get('period') or ''})"
          for k in card.get("key_figures", [])],  # fmt: skip
        "Story timeline (story days):",
        *[f"- Day {c.get('story_day')}: {c.get('label')}" for c in m.get("checkpoints", [])],
        "Evidence the player can find:",
        *[f"- [{e.get('checkpoint')}] {e.get('title')}: {e.get('player_text')}"
          for e in m.get("evidence", [])],  # fmt: skip
    ]
    news = m.get("news") or {}
    if news:
        lines += [f"Breaking news after {news.get('time_skip_days')} days: "
                  f"{news.get('headline')} - {news.get('summary')}"]  # fmt: skip
    lines += ["People: " + "; ".join(f"{c.get('name')} ({c.get('role')})"
                                     for c in m.get("characters", []))]  # fmt: skip
    series = sc.chart_series or []
    if len(series) >= 2:
        step = max(1, len(series) // 10)
        pts = series[::step] + ([series[-1]] if series[-1] is not series[::step][-1] else [])
        lines += ["Share price (disguised level, real % moves), by story day: "
                  + ", ".join(f"day {p['day']}: {p['close']}" for p in pts)]  # fmt: skip
    return "\n".join(lines)


def _clue_lines(reports: list[GuesserReport]) -> list[str]:
    out: list[str] = []
    for r in reports:
        out += [f"{c.category}: {c.text}" for c in r.clues]
        out += [f"named: {g.company}" for g in r.top3[:1]]
    return list(dict.fromkeys(out))


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
) -> Any:
    cfg = settings or get_settings()
    fake = cfg.fake_llm
    llm: NodeLLM = node_llm or (DefaultFakeNodeLLM() if fake else AnthropicNodeLLM(32000))

    def pause() -> None:
        if fake and node_llm is None:
            time.sleep(FAKE_STEP_DELAY_S)

    def find_windows(state: QuestState) -> dict[str, Any]:
        progress("Reading the market history", {})
        pause()
        if fake and downloader is None:
            return {"windows": [], "attempt": 1, "clues": [], "log": []}
        frame = market.load_history(company.ticker, Path(cfg.cache_dir), downloader)
        windows = market.find_windows(frame)
        if not windows:
            raise QuestFailed(f"no usable price history for {company.ticker}")
        return {
            "windows": [_window_dict(w) for w in windows],
            "attempt": 1,
            "clues": [],
            "log": [{"step": "windows", "windows": [w.describe() for w in windows]}],
        }

    def research(state: QuestState) -> dict[str, Any]:
        progress("Researching the story", {})
        pause()
        pack_dir.mkdir(parents=True, exist_ok=True)
        if fake and downloader is None:
            shutil.copy(SAMPLE_PACK / "case.md", pack_dir / "case.md")
            shutil.copy(SAMPLE_PACK / "prices.csv", pack_dir / "prices.csv")
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
        return {
            "window": _window_dict(win),
            "pack_dir": str(pack_dir),
            "log": [*state.get("log", []), {"step": "research", "window": win.describe(),
                                             "usage": res.usage}],  # fmt: skip
        }

    def draft_manifest(state: QuestState) -> dict[str, Any]:
        n = state.get("attempt", 1)
        progress("Writing the campaign" if n == 1 else f"Rewriting the disguise (try {n})", {})
        pause()
        if fake and downloader is None:
            data = json.loads((SAMPLE_PACK / "manifest.json").read_text(encoding="utf-8"))
            data["meta"]["case_id"] = pack_id
            (pack_dir / "manifest.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
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
        if state.get("clues"):
            extra += "\n\n" + prompts.MANIFEST_REWRITE.format(
                clues="\n".join(f"- {c}" for c in state["clues"])
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
                raw = model.with_structured_output(CampaignManifest).invoke(convo)
                m = raw if isinstance(raw, CampaignManifest) else CampaignManifest.model_validate(raw)  # noqa: E501
            except Exception as exc:  # noqa: BLE001 - schema problems are repaired below
                errors = [f"schema: {exc}"[:2000]]
            else:
                report = validate_manifest(m, pack.price_dates)
                errors = report.errors
                if report.ok:
                    (pack_dir / "manifest.json").write_text(
                        json.dumps(m.model_dump(mode="json"), indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    return {}
            convo = [*convo, ("human", "The manifest failed validation. Fix every error and "
                              "return the full manifest again:\n- " + "\n- ".join(errors))]  # fmt: skip  # noqa: E501
        raise QuestFailed("manifest invalid after repairs: " + "; ".join(errors[:5]))

    def disguise(state: QuestState) -> dict[str, Any]:
        progress("Disguising names, dates and numbers", {})
        pause()
        with Session(get_engine()) as s:
            res = approve_pack(
                pack_dir, s, status="checking", n_guessers=len(PERSONAS)
            )
        if not res.ok:
            _log.info("quest %s attempt %s: final scan failed %s", pack_id,
                      state.get("attempt", 1), list(res.reasons)[:5])  # fmt: skip
            return {"scenario_id": res.scenario_id, "reasons": res.reasons, "outcome": "scan"}
        return {"scenario_id": res.scenario_id, "reasons": [], "outcome": "checking"}

    def guess(state: QuestState) -> dict[str, Any]:
        n = state.get("attempt", 1)
        log = list(state.get("log", []))
        if state.get("outcome") == "scan":
            reasons = state.get("reasons", [])
            log.append({"step": "scan", "attempt": n, "reasons": reasons})
            return {"outcome": "failed_attempt", "clues": reasons[:10], "log": log}
        progress("Testing if AI investigators recognise it", {})
        with Session(get_engine()) as s:
            sc = s.get(Scenario, uuid.UUID(str(state["scenario_id"])))
            text = player_view_text(sc) if sc else ""
        if not text:
            raise QuestFailed("disguised scenario not found")
        m = CampaignManifest.model_validate_json((pack_dir / "manifest.json").read_text("utf-8"))
        real_start = date.fromisoformat(str(m.checkpoints[0].cutoff_date))
        targets = MatchTargets(
            company=m.secret.real_entity or company.name,
            ticker=company.ticker.split(".")[0],
            former_names=tuple(company.aliases),
        )

        def run_round(web: bool) -> list[tuple[GuesserReport | None, str | None]]:
            def one(persona: str) -> tuple[GuesserReport | None, str | None]:
                parts = [GUESSER_SYSTEM, PERSONA_SUFFIX[persona]]
                if web:
                    parts.append(WEB_INSTRUCTIONS + "\nJSON schema:\n"
                                 + json.dumps(GuesserReport.model_json_schema()))  # fmt: skip
                out = call_node(
                    llm,
                    case_id=pack_id,
                    attempt=n,
                    node="guess_web" if web else "guess_memory",
                    messages=[
                        SystemMessage(content="\n\n".join(parts)),
                        HumanMessage(content=DISGUISE_RULES_DESCRIPTION + FANTASY_NOTE
                                     + "\n\nThe disguised story:\n" + text),  # fmt: skip
                    ],
                    schema=GuesserReport,
                    effort="high" if web else "medium",
                    persona=persona,
                    web_search_max_uses=cfg.web_search_max_uses if web else None,
                )
                return out.parsed, out.error  # type: ignore[return-value]

            with ThreadPoolExecutor(len(PERSONAS)) as pool:
                return list(pool.map(one, PERSONAS))

        def results(rnd: list[tuple[GuesserReport | None, str | None]]) -> list[rules.GuesserResult]:  # noqa: E501
            out: list[rules.GuesserResult] = []
            for rep, err in rnd:
                if err or rep is None:
                    out.append(rules.GuesserResult(error=True))
                    continue
                out.append(rules.GuesserResult(
                    top3=tuple(g.company for g in rep.top3) + tuple(g.ticker for g in rep.top3
                                                                     if g.ticker),
                    start_year=rep.start_year, start_month=rep.start_month,
                    start_confidence=rep.start_confidence, readability=rep.readability,
                ))  # fmt: skip
            return out

        rs = (real_start.year, real_start.month)
        memory = run_round(False)
        mem_res = results(memory)
        web: list[tuple[GuesserReport | None, str | None]] | None = None
        try:
            verdict = rules.evaluate_attempt(scan_passed=True, memory_round=mem_res,
                                             web_round=None, targets=targets, real_start=rs,
                                             settings=cfg)  # fmt: skip
        except ValueError:  # memory round passed: the web round decides
            progress("Investigators are searching the web", {})
            web = run_round(True)
            verdict = rules.evaluate_attempt(scan_passed=True, memory_round=mem_res,
                                             web_round=results(web), targets=targets,
                                             real_start=rs, settings=cfg)  # fmt: skip
        reports = [r for r, _ in memory + (web or []) if r is not None]
        log.append({
            "step": "guess", "attempt": n, "verdict": verdict.status,
            "reasons": list(verdict.reasons),
            "guesses": [[g.company for g in r.top3] for r in reports],
        })  # fmt: skip
        _log.info(
            "quest %s attempt %s: %s %s; top guesses %s",
            pack_id, n, verdict.status, list(verdict.reasons),
            [[g.company for g in r.top3][:1] for r in reports],
        )
        if verdict.passed:
            return {"outcome": "approved", "log": log}
        if verdict.status == "error":
            raise QuestFailed("guesser calls failed")
        return {"outcome": "failed_attempt", "clues": _clue_lines(reports), "log": log}

    def route(state: QuestState) -> str:
        if state.get("outcome") == "approved":
            return "publish"
        return "retry" if state.get("attempt", 1) < cfg.max_attempts else "reject"

    def retry(state: QuestState) -> dict[str, Any]:
        return {"attempt": state.get("attempt", 1) + 1}

    def publish(state: QuestState) -> dict[str, Any]:
        _set_status(state.get("scenario_id"), "playable")
        progress("Ready", {})
        return {"outcome": "approved"}

    def reject(state: QuestState) -> dict[str, Any]:
        _set_status(state.get("scenario_id"), "retired")
        return {"outcome": "rejected"}

    g = StateGraph(QuestState)
    for name, fn in (("find_windows", find_windows), ("research", research),
                     ("draft_manifest", draft_manifest), ("disguise", disguise), ("guess", guess),
                     ("retry", retry), ("publish", publish), ("reject", reject)):  # fmt: skip
        g.add_node(name, fn)
    g.add_edge(START, "find_windows")
    g.add_edge("find_windows", "research")
    g.add_edge("research", "draft_manifest")
    g.add_edge("draft_manifest", "disguise")
    g.add_edge("disguise", "guess")
    g.add_conditional_edges("guess", route, {"publish": "publish", "retry": "retry",
                                             "reject": "reject"})  # fmt: skip
    g.add_edge("retry", "draft_manifest")
    g.add_edge("publish", END)
    g.add_edge("reject", END)
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


__all__ = ["QuestFailed", "build_quest_graph", "parse_research", "player_view_text"]
