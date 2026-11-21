"""LangGraph graphs for spec 002: ``intake_graph`` (offline extraction) and ``gate_graph``
(disguise + recognition check for one case).

Principles enforced here
- Code owns every number, date and verdict (NumberPlan, scan, rules.evaluate_attempt). Models only
  write text (the disguise) and give guesses (the guessers).
- ``GateState.case`` is server-only. Guessers are dispatched with ``Send`` and receive only the
  disguised scenario and a plain description of the disguise rules; the writer receives the case
  with the real name, ticker and identifying terms scrubbed, and in rewrite mode only tagged
  clues (never the company a guesser named).
- The event of record is the ``attempts`` list (what a batch runner persists), never a checkpoint.

Models: every call goes through ``financequest.llm.NodeLLM`` (ChatAnthropic, effort per node,
``max_retries=5``, cache_control on the shared system prefix). langchain-anthropic forwards
``effort`` and the ``server_tool_use`` / ``web_search_tool_result`` blocks, so there is no direct
``anthropic`` SDK exception. ``guess_web`` cannot force structured output while a server tool is
bound, so it asks for the JSON report in the final text block and validates it with Pydantic (the
spike's documented fallback). ``stop_reason`` is checked before content is used; a refusal is
retried once through ``run(..., fallback=True)`` and then recorded as an error, never a pass.
Live access (web search enabled for the org key) is not verifiable offline; see the live smoke test.
"""

from __future__ import annotations

import json
import operator
import random
import re
import time
from collections.abc import Callable, Sequence
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, ValidationError

from financequest.config import Settings, get_settings
from financequest.engine.disguise import (
    AmountFact,
    NumberPlan,
    fill_placeholders,
)
from financequest.llm import LLMResult, NodeLLM, extract_json_object, get_node_llm
from financequest.reid import rules
from financequest.reid.match import MatchTargets
from financequest.reid.prompts import (
    DISGUISE_RULES_DESCRIPTION,
    EXTRACT_SYSTEM,
    GUESSER_SYSTEM,
    PERSONA_SUFFIX,
    REWRITE_CHECKLIST,
    WRITER_SYSTEM,
)
from financequest.reid.prompts.guesser import WEB_INSTRUCTIONS
from financequest.reid.scan import Finding, ScanContext, ScanResult, scan_case
from financequest.reid.schemas import (
    PERSONAS,
    AttemptRecord,
    CaseChunk,
    Clue,
    DisguiseDraft,
    DisguisedScenario,
    FailReason,
    GateCase,
    GateStatus,
    GuesserReport,
    GuessRecord,
    IntakeResult,
    Persona,
    ScenarioBeat,
    SourceCaseDraft,
)

CACHE = {"type": "ephemeral"}
REDACTED = "[a company]"
REASON_BEAT_COUNT = "Beat count differs from the source case"
REASON_UNKNOWN_TOKEN = "Unknown placeholder in text"

_sleep: Callable[[float], None] = time.sleep  # patched in tests


# ======================================================================
# LLM call wrapper: stop_reason check, refusal retry, 429/529 backoff, telemetry
# ======================================================================
class CallOutcome(BaseModel):
    parsed: Any = None
    result: Any = None
    error: str | None = None
    telemetry: dict[str, Any]


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def call_node(
    llm: NodeLLM,
    *,
    case_id: str,
    attempt: int,
    node: str,
    messages: Sequence[BaseMessage],
    schema: type[BaseModel],
    effort: str,
    persona: str | None = None,
    web_search_max_uses: int | None = None,
    context: dict[str, Any] | None = None,
    backoff_tries: int = 3,
) -> CallOutcome:
    t0 = time.monotonic()
    retries = 0
    res: LLMResult | None = None
    error: str | None = None
    fallback = False
    outcome = "ok"
    while True:
        try:
            res = llm.run(
                node,
                messages,
                schema=schema,
                effort=effort,
                persona=persona,
                web_search_max_uses=web_search_max_uses,
                context=context,
                fallback=fallback,
            )
        except Exception as exc:  # noqa: BLE001 - provider errors are data for the verdict
            if _status_code(exc) in (429, 529) and retries < backoff_tries:
                retries += 1
                _sleep(random.uniform(0.5, 1.5) * 2**retries)
                continue
            error, outcome = f"{type(exc).__name__}: {exc}", "error"
            break
        if res.refused:
            if not fallback:
                fallback, retries = True, retries + 1
                continue
            error, outcome = "refusal", "refusal"
            break
        if res.stop_reason not in (None, "end_turn", "stop_sequence", "tool_use"):
            error, outcome = f"unusable stop_reason {res.stop_reason}", "error"
            break
        break

    parsed: BaseModel | None = None
    if error is None and res is not None:
        parsed = res.parsed
        if parsed is None:
            try:
                parsed = schema.model_validate(extract_json_object(res.text))
            except (ValueError, ValidationError) as exc:
                error, outcome = f"unparseable output: {type(exc).__name__}", "error"
    usage = res.usage if res else {}
    tel = {
        "case": case_id,
        "attempt": attempt,
        "node": node,
        "persona": persona,
        "effort": effort,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_tokens", 0),
        "cache_creation_tokens": usage.get("cache_creation_tokens", 0),
        "web_searches": usage.get("web_search_requests", 0),
        "latency_s": round(time.monotonic() - t0, 3),
        "stop_reason": res.stop_reason if res else None,
        "retries": retries,
        "outcome": outcome,
    }
    return CallOutcome(parsed=parsed, result=res, error=error, telemetry=tel)


# ======================================================================
# Web-round parsing (server_tool_use / web_search_tool_result blocks)
# ======================================================================
class WebTrace(BaseModel):
    queries: list[str]
    citations: list[dict[str, str]]
    searches_used: int
    usage_mismatch: bool = False


def parse_web_blocks(
    content: Sequence[dict[str, Any]], usage_searches: int | None = None
) -> WebTrace:
    queries: list[str] = []
    cites: dict[str, dict[str, str]] = {}
    for b in content:
        kind = b.get("type")
        if kind == "server_tool_use" and b.get("name", "web_search") == "web_search":
            q = (b.get("input") or {}).get("query")
            queries.append(str(q) if q else "")
        elif kind == "web_search_tool_result":
            body = b.get("content")
            for r in body if isinstance(body, list) else []:
                if isinstance(r, dict) and r.get("url"):
                    cites.setdefault(
                        r["url"], {"url": str(r["url"]), "title": str(r.get("title", ""))}
                    )
        elif kind == "text":
            for c in b.get("citations") or []:
                if isinstance(c, dict) and c.get("url"):
                    cites.setdefault(
                        c["url"], {"url": str(c["url"]), "title": str(c.get("title", ""))}
                    )
    used = len(queries)
    mismatch = usage_searches is not None and usage_searches > 0 and usage_searches != used
    return WebTrace(
        queries=queries,
        citations=list(cites.values()),
        searches_used=max(used, usage_searches or 0),
        usage_mismatch=mismatch,
    )


# ======================================================================
# Helpers shared by nodes
# ======================================================================
def _real_terms(case: GateCase) -> list[str]:
    raw = [
        case.company,
        case.ticker,
        case.parent,
        *case.subsidiaries,
        *case.former_names,
        *case.aliases,
        *case.identifying_terms,
        *case.executives,
    ]
    return sorted({t.strip() for t in raw if t and len(t.strip()) >= 2}, key=len, reverse=True)


def scrub(text: str, terms: Sequence[str]) -> str:
    for t in terms:
        text = re.sub(rf"(?<!\w){re.escape(t)}(?!\w)", REDACTED, text, flags=re.I)
    return text


def _move_word(prev: float, cur: float) -> str:
    pct = (cur / prev - 1) * 100 if prev else 0.0
    size = abs(pct)
    mag = "flat" if size < 3 else "small" if size < 10 else "moderate" if size < 25 else "large"
    if mag == "flat":
        return "flat"
    return f"{'up' if pct > 0 else 'down'}, {mag}"


def _facts(case: GateCase) -> list[AmountFact]:
    return [AmountFact(a.token, a.family, a.value, a.is_ratio) for a in case.amounts]


def _scan_ctx(case: GateCase) -> ScanContext:
    return ScanContext(
        real_name=case.company,
        ticker=case.ticker,
        aliases=[*case.aliases, case.parent, *case.subsidiaries, *case.former_names],
        identifying_terms=case.identifying_terms,
        executives=case.executives,
    )


def _scan_dict(res: ScanResult, extra: Sequence[Finding] = ()) -> dict[str, Any]:
    findings = [*res.findings, *extra]
    return {
        "passed": not findings,
        "reasons": list(dict.fromkeys(f.reason for f in findings)),
        "findings": [
            {"reason": f.reason, "field": f.field, "excerpt": f.excerpt} for f in findings
        ],
    }


def _targets(case: GateCase) -> MatchTargets:
    return MatchTargets(
        company=case.company,
        ticker=case.ticker,
        parent=case.parent,
        subsidiaries=tuple(case.subsidiaries),
        former_names=tuple(case.former_names),
    )


def _to_result(rec: GuessRecord) -> rules.GuesserResult:
    if rec.error or rec.report is None:
        return rules.GuesserResult(error=True)
    r = rec.report
    return rules.GuesserResult(
        top3=tuple(g.company for g in r.top3) + tuple(g.ticker for g in r.top3 if g.ticker),
        start_year=r.start_year,
        start_month=r.start_month,
        start_confidence=r.start_confidence,
        readability=r.readability,
    )


def _round(recs: Sequence[GuessRecord], rnd: str) -> list[rules.GuesserResult]:
    return [_to_result(r) for r in recs if r.round == rnd]


def render_scenario(s: DisguisedScenario) -> str:
    lines = [
        f"Company: {s.invented_name}",
        f"Sector: {s.sector}",
        f"Industry: {s.industry}",
    ]
    if s.transplant_note:
        lines.append(f"Note: {s.transplant_note}")
    for b in s.beats:
        lines.append(f"\nDay {b.story_day} (share price {b.price}): {b.headline}")
        lines += [f"- {f}" for f in b.facts]
    return "\n".join(lines)


def _cached_system(*parts: str) -> SystemMessage:
    """Shared prefix first with the cache breakpoint on it, persona suffix after."""
    blocks: list[str | dict[str, Any]] = [
        {"type": "text", "text": parts[0], "cache_control": CACHE}
    ]
    blocks += [{"type": "text", "text": p} for p in parts[1:]]
    return SystemMessage(content=blocks)


def tag_clues(existing: Sequence[Clue], new: Sequence[Clue], terms: Sequence[str]) -> list[Clue]:
    seen = {(c.category, c.text.casefold()) for c in existing}
    out = list(existing)
    for c in new:
        text = scrub(c.text, terms).strip()
        key = (c.category, text.casefold())
        if text and key not in seen:
            seen.add(key)
            out.append(Clue(category=c.category, text=text))
    return out


# ======================================================================
# gate_graph
# ======================================================================
def _reset_or_add(old: list[Any] | None, new: list[Any] | None) -> list[Any]:
    if new is None:  # explicit reset at the start of an attempt
        return []
    return [*(old or []), *new]


class GateState(TypedDict, total=False):
    case: GateCase  # server-only, never put into the guessers' input
    run_salt: int
    attempt: int
    numbers: NumberPlan
    fills: dict[str, str]
    real_beat_prices: list[float]
    draft: DisguiseDraft | None
    scenario: DisguisedScenario | None
    scan_result: dict[str, Any] | None
    guesses: Annotated[list[GuessRecord], _reset_or_add]
    memory_ok: bool
    clues: list[Clue]  # deduplicated, tagged by category
    feedback: list[str]  # scan reasons from the previous attempt (never excerpts)
    error: str | None
    attempts: Annotated[list[AttemptRecord], operator.add]  # the history that gets persisted
    status: GateStatus
    telemetry: Annotated[list[dict[str, Any]], operator.add]


def build_gate_graph(llm: NodeLLM | None = None, settings: Settings | None = None) -> Any:
    model: NodeLLM = llm or get_node_llm()
    cfg = settings or get_settings()
    max_attempts = cfg.max_attempts

    def plan_numbers(state: GateState) -> dict[str, Any]:
        case = state["case"]
        lookup = dict(case.series)
        beat_days = [b.real_day for b in case.beats]
        plan = NumberPlan.build(
            case.case_id, state.get("run_salt", 0), case.series, beat_days, _facts(case)
        )
        return {
            "numbers": plan,
            "fills": plan.fill_values(_facts(case)),
            "real_beat_prices": [lookup[d] for d in beat_days],
            "attempt": 0,
            "clues": [],
            "feedback": [],
            "status": "running",
            "guesses": None,
        }

    def write_disguise(state: GateState) -> dict[str, Any]:
        case, plan = state["case"], state["numbers"]
        n = state.get("attempt", 0) + 1
        terms = _real_terms(case)
        prices = state["real_beat_prices"]
        beats = []
        for i, b in enumerate(case.beats):
            beats.append(
                {
                    "index": i,
                    "story_day": plan.story_days[i],
                    "move_vs_previous": "start" if i == 0 else _move_word(prices[i - 1], prices[i]),
                    "headline": scrub(b.headline, terms),
                    "facts": [scrub(f, terms) for f in b.facts],
                }
            )
        brief: dict[str, Any] = {
            "industry": scrub(case.industry, terms),
            "lesson": scrub(case.lesson, terms),
            "beats": beats,
            "tokens": [{"token": a.token, "family": a.family} for a in case.amounts],
        }
        user = ["Source case (names removed):", json.dumps(brief, indent=2)]
        previous = state.get("scenario") if n > 1 else None
        if n > 1:
            prev_scn = (
                previous.model_dump(mode="json", exclude={"changes_vs_previous"})
                if previous
                else None
            )
            user += [
                "\nThis is a REWRITE. Your previous disguised scenario:",
                json.dumps(prev_scn, indent=2),
                "\nClues that made it recognisable (tagged by category):",
                json.dumps([c.model_dump() for c in state.get("clues", [])], indent=2),
            ]
            if state.get("feedback"):
                user += ["\nAutomatic checks flagged:", json.dumps(state["feedback"])]
            user += ["\n" + "\n".join(REWRITE_CHECKLIST)]
        messages = [_cached_system(WRITER_SYSTEM), HumanMessage(content="\n".join(user))]
        out = call_node(
            model,
            case_id=case.case_id,
            attempt=n,
            node="write_disguise",
            messages=messages,
            schema=DisguiseDraft,
            effort="medium",
            context={
                "n_beats": len(case.beats),
                "tokens": [a.token for a in case.amounts],
                "rewrite": n > 1,
            },
        )
        return {
            "attempt": n,
            "draft": out.parsed,
            "scenario": None,
            "scan_result": None,
            "memory_ok": False,
            "error": out.error and f"write_disguise: {out.error}",
            "guesses": None,
            "telemetry": [out.telemetry],
        }

    def after_write(state: GateState) -> str:
        return "record_attempt" if state.get("error") else "fill_and_scan"

    def fill_and_scan(state: GateState) -> dict[str, Any]:
        case, plan, draft = state["case"], state["numbers"], state["draft"]
        assert draft is not None
        extra: list[Finding] = []
        if len(draft.beats) != len(case.beats):
            extra.append(Finding(REASON_BEAT_COUNT, "beats", str(len(draft.beats))))
        fills = state["fills"]

        def fill(text: str, where: str) -> str:
            try:
                return fill_placeholders(text, fills)
            except KeyError as exc:
                extra.append(Finding(REASON_UNKNOWN_TOKEN, where, str(exc)))
                return text

        shown = plan.beat_prices([(d, p) for d, p in case.series])
        beats = [
            ScenarioBeat(
                story_day=plan.story_days[i],
                price=f"{shown[i]:.2f}",
                headline=fill(b.headline, f"beat{i}.headline"),
                facts=[fill(f, f"beat{i}.fact{j}") for j, f in enumerate(b.facts)],
            )
            for i, b in enumerate(draft.beats[: len(case.beats)])
        ]
        scenario = DisguisedScenario(
            invented_name=draft.company_name,
            sector=draft.sector,
            industry=draft.industry,
            industry_moved=draft.industry_moved,
            transplant_note=draft.transplant_note,
            beats=beats,
            changes_vs_previous=draft.changes_vs_previous,
        )
        ctx = _scan_ctx(case)
        # Unfilled text catches stray digits exactly (tokens are masked); the filled text then
        # checks units, caps and dates with the plan's own values allowed.
        raw_prose = {
            "invented_name": draft.company_name,
            "sector": draft.sector,
            "industry": draft.industry,
            "transplant_note": draft.transplant_note,
        }
        for i, b in enumerate(draft.beats):
            raw_prose[f"beat{i}.headline"] = b.headline
            for j, f in enumerate(b.facts):
                raw_prose[f"beat{i}.fact{j}"] = f
        raw_scan = scan_case(raw_prose, ctx)
        filled_scan = scan_case(
            scenario.prose(),
            ctx,
            real_prices=[float(p) for p in state["real_beat_prices"]],
            shown_prices=[float(p) for p in shown],
            allowed_numbers=list(fills.values()),
        )
        # a stray-digit finding on filled text is expected only if raw text already had it
        merged = ScanResult(
            passed=False,
            findings=(
                *raw_scan.findings,
                *[f for f in filled_scan.findings if f.reason != "Stray digits in text"],
            ),
        )
        return {
            "scenario": scenario,
            "scan_result": _scan_dict(merged, extra),
        }

    def route_after_scan(state: GateState) -> str | list[Send]:
        sr = state.get("scan_result") or {}
        if not sr.get("passed"):
            return "record_attempt"
        return [
            Send(
                "guess_memory",
                {
                    "scenario": state["scenario"],
                    "persona": p,
                    "round": "memory",
                    "attempt": state["attempt"],
                    "case_id": state["case"].case_id,
                },
            )
            for p in PERSONAS[: cfg.guessers_per_attempt]
        ]

    def make_guesser(rnd: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def guesser(arg: dict[str, Any]) -> dict[str, Any]:
            persona: Persona = arg["persona"]
            scenario: DisguisedScenario = arg["scenario"]
            web = rnd == "web"
            system_parts = [GUESSER_SYSTEM, PERSONA_SUFFIX[persona]]
            if web:
                system_parts.append(
                    WEB_INSTRUCTIONS
                    + "\nJSON schema:\n"
                    + json.dumps(GuesserReport.model_json_schema())
                )
            messages = [
                _cached_system(*system_parts),
                HumanMessage(
                    content=DISGUISE_RULES_DESCRIPTION
                    + "\n\nThe disguised story:\n"
                    + render_scenario(scenario)
                ),
            ]
            out = call_node(
                model,
                case_id=arg["case_id"],
                attempt=arg["attempt"],
                node=f"guess_{rnd}",
                messages=messages,
                schema=GuesserReport,
                effort="high" if web else "medium",
                persona=persona,
                web_search_max_uses=cfg.web_search_max_uses if web else None,
            )
            rec = GuessRecord(persona=persona, round=rnd, error=out.error)  # type: ignore[arg-type]
            if out.parsed is not None:
                rec.report = out.parsed
            if web and out.result is not None:
                trace = parse_web_blocks(
                    out.result.content, out.result.usage.get("web_search_requests")
                )
                rec.queries, rec.citations = trace.queries, trace.citations
                rec.searches_used = trace.searches_used
                out.telemetry["web_searches"] = trace.searches_used
                out.telemetry["usage_mismatch"] = trace.usage_mismatch
            return {"guesses": [rec], "telemetry": [out.telemetry]}

        return guesser

    def judge_memory(state: GateState) -> dict[str, Any]:
        case = state["case"]
        try:
            rules.evaluate_attempt(
                scan_passed=True,
                memory_round=_round(state["guesses"], "memory"),
                web_round=None,
                targets=_targets(case),
                real_start=case.real_start,
                settings=cfg,
            )
            ok = False
        except ValueError:  # "web round required before a case can pass": nobody failed it
            ok = True
        return {"memory_ok": ok}

    def route_after_memory(state: GateState) -> str | list[Send]:
        if not state.get("memory_ok"):
            return "record_attempt"  # web round skipped after a memory fail
        return [
            Send(
                "guess_web",
                {
                    "scenario": state["scenario"],
                    "persona": p,
                    "round": "web",
                    "attempt": state["attempt"],
                    "case_id": state["case"].case_id,
                },
            )
            for p in PERSONAS[: cfg.guessers_per_attempt]
        ]

    def judge_web(state: GateState) -> dict[str, Any]:
        return {}  # verdict is computed once, in record_attempt, over both rounds

    def record_attempt(state: GateState) -> dict[str, Any]:
        case, n = state["case"], state["attempt"]
        recs = list(state.get("guesses") or [])
        scan = state.get("scan_result") or {"passed": False, "reasons": [], "findings": []}
        targets = _targets(case)
        mem, web = _round(recs, "memory"), _round(recs, "web")
        if state.get("error"):
            verdict = rules.AttemptVerdict("error", (rules.REASON_ERROR,))
        elif not scan["passed"]:
            verdict = rules.evaluate_attempt(
                scan_passed=False,
                memory_round=[],
                web_round=None,
                targets=targets,
                real_start=case.real_start,
                settings=cfg,
            )
        else:
            try:
                verdict = rules.evaluate_attempt(
                    scan_passed=True,
                    memory_round=mem,
                    web_round=web if web else None,
                    targets=targets,
                    real_start=case.real_start,
                    settings=cfg,
                )
            except ValueError:  # defensive: passed memory but the web round never ran
                verdict = rules.AttemptVerdict("error", (rules.REASON_ERROR,))
        for rec in recs:
            if rec.report is not None:
                hit = rules.guesser_recognises(
                    _to_result(rec),
                    targets,
                    case.real_start,
                    window_months=cfg.start_window_months,
                    confidence_pct=cfg.start_confidence_pct,
                )
                rec.recognised, rec.reasons = bool(hit), hit
        ratings = [r.report.readability for r in recs if r.report is not None]
        avg = round(sum(ratings) / len(ratings), 2) if ratings else None
        fail: FailReason | None = None
        if verdict.status != "passed":
            rs = set(verdict.reasons)
            fail = (
                "error"
                if verdict.status == "error"
                else "real_date_found"
                if rules.REASON_SCAN in rs
                else "recognised_name"
                if rules.REASON_NAME_HIT in rs
                else "recognised_date"
                if rules.REASON_START_HIT in rs
                else "unreadable"
            )
        record = AttemptRecord(
            n=n,
            number_plan=state["numbers"].to_dict(),
            scenario=state.get("scenario"),
            scan_result=scan,
            guesses=recs,
            avg_readability=avg,
            verdict=verdict.status,
            reasons=list(verdict.reasons),
            fail_reason=fail,
        )
        route = rules.route_attempt(n, verdict, max_attempts)
        status: GateStatus = (
            "approved"
            if route == "approved"
            else "rejected"
            if route == "rejected"
            else "error"
            if route == "error"
            else "running"
        )
        terms = _real_terms(case)
        guessed = [
            x
            for r in recs
            if r.report is not None
            for g in r.report.top3
            for x in (g.company, g.ticker)
            if x
        ]
        new_clues = [c for r in recs if r.report is not None for c in r.report.clues]
        clues = tag_clues(state.get("clues", []), new_clues, [*terms, *guessed])
        return {
            "attempts": [record],
            "status": status,
            "clues": clues,
            "feedback": list(scan.get("reasons", [])),
        }

    def route_after_record(state: GateState) -> str:
        return "write_disguise" if state["status"] == "running" else END

    g: Any = StateGraph(GateState)
    g.add_node("plan_numbers", plan_numbers)
    g.add_node("write_disguise", write_disguise)
    g.add_node("fill_and_scan", fill_and_scan)
    g.add_node("guess_memory", make_guesser("memory"))
    g.add_node("judge_memory", judge_memory)
    g.add_node("guess_web", make_guesser("web"))
    g.add_node("judge_web", judge_web)
    g.add_node("record_attempt", record_attempt)
    g.add_edge(START, "plan_numbers")
    g.add_edge("plan_numbers", "write_disguise")
    g.add_conditional_edges("write_disguise", after_write, ["record_attempt", "fill_and_scan"])
    g.add_conditional_edges("fill_and_scan", route_after_scan, ["record_attempt", "guess_memory"])
    g.add_edge("guess_memory", "judge_memory")
    g.add_conditional_edges("judge_memory", route_after_memory, ["record_attempt", "guess_web"])
    g.add_edge("guess_web", "judge_web")
    g.add_edge("judge_web", "record_attempt")
    g.add_conditional_edges("record_attempt", route_after_record, ["write_disguise", END])
    return g.compile()


def run_gate(
    case: GateCase,
    *,
    run_salt: int = 0,
    llm: NodeLLM | None = None,
    settings: Settings | None = None,
) -> GateState:
    graph = build_gate_graph(llm, settings)
    out: GateState = graph.invoke(
        {"case": case, "run_salt": run_salt}, config={"recursion_limit": 80}
    )
    return out


# ======================================================================
# intake_graph
# ======================================================================
def split_case_chunks(text: str, heading_level: int = 2) -> list[CaseChunk]:
    """One chunk per case heading (``## `` by default); text before the first heading is dropped."""
    pat = re.compile(rf"^{'#' * heading_level} +(.+?)\s*$", re.M)
    stops = re.compile(rf"^#{{1,{heading_level}}} +\S", re.M)
    chunks: list[CaseChunk] = []
    matches = list(pat.finditer(text))
    for m in matches:
        nxt = stops.search(text, m.end())
        body = text[m.end() : nxt.start() if nxt else len(text)].strip()
        chunks.append(CaseChunk(title=m.group(1), body=body))
    return chunks


class IntakeState(TypedDict, total=False):
    text: str
    heading_level: int
    chunks: list[CaseChunk]
    extracted: Annotated[list[tuple[int, str, SourceCaseDraft | None, str | None]], operator.add]
    results: list[IntakeResult]
    telemetry: Annotated[list[dict[str, Any]], operator.add]


def build_intake_graph(llm: NodeLLM | None = None) -> Any:
    model: NodeLLM = llm or get_node_llm()

    def split_cases(state: IntakeState) -> dict[str, Any]:
        return {"chunks": split_case_chunks(state["text"], state.get("heading_level", 2))}

    def fan_out(state: IntakeState) -> list[Send] | str:
        sends = [
            Send("extract_case", {"idx": i, "chunk": c}) for i, c in enumerate(state["chunks"])
        ]
        return sends or "validate_case"

    def extract_case(arg: dict[str, Any]) -> dict[str, Any]:
        chunk: CaseChunk = arg["chunk"]
        out = call_node(
            model,
            case_id=chunk.title,
            attempt=0,
            node="extract_case",
            messages=[
                _cached_system(EXTRACT_SYSTEM),
                HumanMessage(content=f"## {chunk.title}\n\n{chunk.body}"),
            ],
            schema=SourceCaseDraft,
            effort="low",
            context={"title": chunk.title},
        )
        return {
            "extracted": [(arg["idx"], chunk.title, out.parsed, out.error)],
            "telemetry": [out.telemetry],
        }

    def validate_case(state: IntakeState) -> dict[str, Any]:
        results: list[IntakeResult] = []
        for _, title, draft, err in sorted(state.get("extracted", []), key=lambda t: t[0]):
            if draft is None:
                results.append(IntakeResult(title=title, status="error", error=err))
                continue
            facts = rules.CaseFacts(
                lesson=draft.lesson or "",
                identifying_terms=tuple(draft.identifying_terms),
                # Prices are not extracted; they come from the cache and the missing-price skip
                # is applied by the prices pipeline. Placeholders keep the beat-count rule.
                beat_prices=tuple(0.0 for _ in draft.beats),
                market_cap_eur=draft.market_cap_eur,
                is_us_listed=draft.is_us_listed,
                country=draft.country or "",
                story_year=draft.story_year,
            )
            skip = rules.skip_reason(facts)
            if skip:
                results.append(
                    IntakeResult(title=title, draft=draft, status="skipped", skip_reason=skip)
                )
            else:
                status = "untagged" if rules.is_untagged(facts) else "ok"
                results.append(IntakeResult(title=title, draft=draft, status=status))
        return {"results": results}

    g: Any = StateGraph(IntakeState)
    g.add_node("split_cases", split_cases)
    g.add_node("extract_case", extract_case)
    g.add_node("validate_case", validate_case)
    g.add_edge(START, "split_cases")
    g.add_conditional_edges("split_cases", fan_out, ["extract_case", "validate_case"])
    g.add_edge("extract_case", "validate_case")
    g.add_edge("validate_case", END)
    return g.compile()


def run_intake(
    text: str, *, heading_level: int = 2, llm: NodeLLM | None = None
) -> list[IntakeResult]:
    out = build_intake_graph(llm).invoke({"text": text, "heading_level": heading_level})
    results: list[IntakeResult] = out["results"]
    return results


__all__ = [
    "GateState",
    "IntakeState",
    "build_gate_graph",
    "build_intake_graph",
    "parse_web_blocks",
    "run_gate",
    "run_intake",
    "split_case_chunks",
]
