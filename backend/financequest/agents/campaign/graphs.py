"""The LangGraph graphs of the campaign agent layer.

* ``GUARDED``: the shared guards subgraph. generate -> check -> (one corrective retry while more
  than 5 s remain) -> templated fallback. Every narrating node runs through it.
* ``TURN``: route -> (decision template | narrate) -> validate.
* ``SETUP``: plan (guarded, prepared setup as template) -> validate extras.

Model calls go through ``NodeLLM`` (ChatAnthropic with ``effort`` and ``cache_control`` blocks,
verified by a request-capture test). A refusal stop reason counts as a failed guard; the corrective
retry after a refusal runs with ``fallback=True``. No node needs the raw ``anthropic`` SDK.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError

from financequest.agents.campaign import context as C
from financequest.agents.campaign import prompts
from financequest.agents.campaign.guards import (
    SAFE_FALLBACK,
    FieldRule,
    GuardRules,
    advice_prefilter,
)
from financequest.agents.campaign.schemas import (
    AdviceCheck,
    ExtraChallenge,
    ExtraLocation,
    RouteOut,
    SetupOut,
    TurnOut,
)
from financequest.campaign import rules
from financequest.llm import LLMResult, NodeLLM, extract_json_object

log = logging.getLogger("financequest.agents")
MIN_RETRY_S = 5.0
DM_WORDS = 150


# =====================================================================================
# Guards subgraph
# =====================================================================================
@dataclass
class GuardedSpec:
    llm: NodeLLM
    node: str
    schema: type[BaseModel]
    effort: str
    messages: Callable[[list[str] | None], list[Any]]
    texts: Callable[[Any], dict[str, str]]
    rules: GuardRules
    template: Callable[[], Any]
    ctx: C.AgentContext
    llm_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardedResult:
    out: Any
    degraded: bool
    attempts: int
    violations: list[str]


class GState(TypedDict, total=False):
    spec: GuardedSpec
    attempt: int
    out: Any
    violations: list[str]
    refused: bool
    degraded: bool


def _parse(res: LLMResult, schema: type[BaseModel]) -> BaseModel | None:
    if res.parsed is not None:
        return res.parsed
    try:
        return schema.model_validate(extract_json_object(res.text))
    except (ValueError, ValidationError):
        return None


def _generate(state: GState) -> dict[str, Any]:
    spec, attempt = state["spec"], state.get("attempt", 0)
    notes = state.get("violations") or None
    t0 = time.monotonic()
    try:
        res = spec.llm.run(
            spec.node,
            spec.messages(notes if attempt else None),
            schema=spec.schema,
            effort=spec.effort,
            context={**spec.llm_context, "attempt": attempt, "corrective": notes},
            fallback=bool(state.get("refused")),
        )
    except Exception as exc:  # noqa: BLE001 - network, overload, parse errors: all a failed call
        log.warning("node=%s call failed: %s", spec.node, exc)
        return {"attempt": attempt + 1, "out": None, "refused": False,
                "violations": [f"the model call failed ({type(exc).__name__})"]}  # fmt: skip
    log.info("node=%s attempt=%d stop=%s %.1fs", spec.node, attempt, res.stop_reason,
             time.monotonic() - t0)  # fmt: skip
    if res.refused:
        return {"attempt": attempt + 1, "out": None, "refused": True,
                "violations": ["the model refused to answer"]}  # fmt: skip
    if res.stop_reason == "max_tokens":
        return {"attempt": attempt + 1, "out": None, "refused": False,
                "violations": ["the answer was cut off; be shorter"]}  # fmt: skip
    parsed = _parse(res, spec.schema)
    if parsed is None:
        return {"attempt": attempt + 1, "out": None, "refused": False,
                "violations": ["the answer was not valid for the required schema"]}  # fmt: skip
    return {"attempt": attempt + 1, "out": parsed, "refused": False, "violations": []}


def classify_advice(spec: GuardedSpec, text: str) -> AdviceCheck | None:
    """Low-effort classifier; None when the call itself failed (the caller fails closed)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        res = spec.llm.run(
            "campaign_advice",
            [SystemMessage(content=prompts.ADVICE), HumanMessage(content=text)],
            schema=AdviceCheck,
            effort="low",
            context={"text": text},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("advice check failed: %s", exc)
        return None
    if res.refused:
        return None
    parsed = _parse(res, AdviceCheck)
    return parsed if isinstance(parsed, AdviceCheck) else None


def _check(state: GState) -> dict[str, Any]:
    spec, out = state["spec"], state.get("out")
    if out is None:
        return {}
    texts = spec.texts(out)
    bad = spec.rules.static_violations(texts)
    if not bad and spec.rules.advice:
        joined = "\n".join(texts.values())
        if advice_prefilter(joined):
            verdict = classify_advice(spec, joined)
            if verdict is None:
                bad.append("the advice check could not run")
            else:
                if verdict.contains_recommendation:
                    bad.append("recommends buying, selling or investing")
                if verdict.promises_profit:
                    bad.append("promises or implies profit")
                if verdict.predicts_future:
                    bad.append("predicts the future price or direction")
    return {"violations": bad}


def _after_check(state: GState) -> str:
    if not state.get("violations"):
        return "done"
    if state.get("attempt", 0) < 2 and state["spec"].ctx.seconds_left() > MIN_RETRY_S:
        return "retry"
    return "template"


def _template(state: GState) -> dict[str, Any]:
    return {"out": state["spec"].template(), "degraded": True}


def _build_guarded() -> Any:
    g = StateGraph(GState)
    g.add_node("generate", _generate)
    g.add_node("check", _check)
    g.add_node("template", _template)
    g.add_edge(START, "generate")
    g.add_edge("generate", "check")
    g.add_conditional_edges("check", _after_check, {"done": END, "retry": "generate",
                                                    "template": "template"})  # fmt: skip
    g.add_edge("template", END)
    return g.compile()


GUARDED = _build_guarded()


def run_guarded(spec: GuardedSpec) -> GuardedResult:
    s = GUARDED.invoke({"spec": spec, "attempt": 0, "violations": [], "degraded": False})
    return GuardedResult(
        out=s["out"], degraded=bool(s.get("degraded")), attempts=int(s.get("attempt", 1)),
        violations=list(s.get("violations") or []),
    )  # fmt: skip


# =====================================================================================
# Shared helpers
# =====================================================================================
def make_rules(
    ctx: C.AgentContext,
    typed: str = "",
    *,
    fields: dict[str, FieldRule] | None = None,
    spoilers: bool = False,
) -> GuardRules:
    unfound = tuple(e["text"] for e in ctx.unfound()) if spoilers and not ctx.locked else ()
    return GuardRules(
        allowed=C.allowlist(ctx, typed),
        leak_terms=ctx.pack.leak_terms,
        leak_enabled=not ctx.company_revealed,
        advice=True,
        unfound_texts=unfound,
        fields=fields or {},
    )


def default_suggestions(ctx: C.AgentContext) -> list[str]:
    out = [f"Go to the {x['name']}" for x in ctx.locations if not x["visited"]][:2]
    for c in ctx.challenges:
        if c["state"] == "open" and len(out) < 2:
            out.append(f"Examine {c['title']}")
    out.append("Ask CommerzBuddy what to look at")
    for extra in ("Look around the room", "Review what you have found"):
        if len(out) < 3:
            out.append(extra)
    return out[:3]


# =====================================================================================
# Turn graph
# =====================================================================================
class TurnState(TypedDict, total=False):
    llm: NodeLLM
    ctx: C.AgentContext
    text: str
    forced: RouteOut | None
    route: RouteOut
    out: TurnOut
    degraded: bool
    reply: Any


def validate_route(ctx: C.AgentContext, r: RouteOut) -> RouteOut:
    """The engine, not the model, decides which ids exist."""
    if r.intent == "challenge" and r.challenge_key in {c["key"] for c in ctx.challenges}:
        return r
    if r.intent == "talk" and ctx.character(r.character_id) is not None:
        return r
    if r.intent == "move" and r.location_key in {x["key"] for x in ctx.locations}:
        return r
    if r.intent in ("decision_intent", "off_topic", "free"):
        return r
    return RouteOut(intent="free")


def _route(state: TurnState) -> dict[str, Any]:
    ctx, text = state["ctx"], state["text"]
    if state.get("forced") is not None:
        return {"route": state["forced"]}
    if rules.is_decision_intent(text):
        return {"route": RouteOut(intent="decision_intent")}
    try:
        res = state["llm"].run(
            "campaign_route",
            C.build_messages(ctx, prompts.ROUTER, text, extra=_route_facts(ctx)),
            schema=RouteOut,
            effort="low",
            context={"ctx": ctx, "input": text},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("route failed: %s", exc)
        return {"route": RouteOut(intent="free")}
    parsed = None if res.refused else _parse(res, RouteOut)
    return {"route": validate_route(ctx, parsed) if isinstance(parsed, RouteOut)
            else RouteOut(intent="free")}  # fmt: skip


def _route_facts(ctx: C.AgentContext) -> str:
    chars = [f"{c['id']} ({c['name']}, at {c['location']})" for c in ctx.content["characters"]]
    locs = [f"{x['key']} ({x['name']})" for x in ctx.locations]
    chs = [f"{c['key']} ({c['title']}, {c['state']})" for c in ctx.challenges]
    return (
        f"# Ids you may use\nChallenges: {'; '.join(chs) or 'none'}\n"
        f"Characters: {'; '.join(chars) or 'none'}\nLocations: {'; '.join(locs)}"
    )


def _after_route(state: TurnState) -> str:
    return "decision" if state["route"].intent == "decision_intent" else "narrate"


def _decision(state: TurnState) -> dict[str, Any]:
    from financequest.campaign.narration import TurnReply

    return {"reply": TurnReply(text="Ready to make your decision?", intent="decision_intent")}


def turn_extra(ctx: C.AgentContext, r: RouteOut) -> tuple[str, set[str]]:
    """Per-intent instructions for the narrator, and the clue ids the engine will accept."""
    here = ctx.current["key"] if ctx.current else ""
    if r.intent == "move" and r.location_key:
        loc = next(x for x in ctx.locations if x["key"] == r.location_key)
        free = C.free_clues_at(ctx, loc["key"])
        titles = [f"{i} = {(ctx.evidence_by_id(i) or {}).get('title')}" for i in free]
        state = "back again (do not re-describe it)" if loc["visited"] else "a first visit"
        return (
            f"# Intent: arrival\nThe hero goes to {loc['name']} ({loc['key']}): {state}. "
            f"Place: {loc['description']}\nFree clues the hero learns on arrival, which you MUST "
            f"mention in clue_ids_given and in the text: {'; '.join(titles) or 'none'}.\n"
            "Speaker: chronicler.",
            set(free),
        )
    if r.intent == "talk":
        ch = ctx.character(r.character_id)
        assert ch is not None
        if ch["location"] != here:
            where = ctx.location_name(ch["location"])
            return (
                f"# Intent: talk with {ch['name']}\n{ch['name']} is not here; they are at "
                f"{where}. Say so briefly and suggest going there. Reveal nothing.",
                set(),
            )
        return (
            f"# Intent: talk with {ch['name']} (id {ch['id']}, {ch['role']})\nSet speaker to "
            f"'{ch['id']}'. They may reveal only: {', '.join(ch['may_reveal'])}. They never: "
            f"{'; '.join(ch['never'])}. Voice the character in first person.",
            set(ch["may_reveal"]),
        )
    if r.intent == "challenge":
        c = next(x for x in ctx.challenges if x["key"] == r.challenge_key)
        if c["state"] != "open":
            alt = c["alt_source"] or "ask around and read the documents"
            return (
                f"# Intent: challenge '{c['title']}' was already rolled ({c['result']}).\n"
                f"Say the information must come from another source: {alt}. No dice.",
                set(),
            )
        return (
            f"# Intent: challenge '{c['title']}'\nNarrate only the lead-in; the engine rolls the "
            "dice next. Do not reveal what the check finds. End with a question.",
            set(),
        )
    if r.intent == "off_topic":
        return ("# Intent: off-topic\nOne friendly sentence, then steer back to the investigation.",
                set())  # fmt: skip
    return ("# Intent: free action\nAnswer from the reference data.", C.reachable_clue_ids(ctx, None))


def _turn_texts(o: TurnOut) -> dict[str, str]:
    t = {"text": o.text}
    if o.suggestions:
        t["suggestions"] = " / ".join(o.suggestions)
    return t


def _narrate(state: TurnState) -> dict[str, Any]:
    ctx, text, r = state["ctx"], state["text"], state["route"]
    extra, _ = turn_extra(ctx, r)
    spec = GuardedSpec(
        llm=state["llm"], node="campaign_turn", schema=TurnOut, effort="medium",
        messages=lambda notes: C.build_messages(ctx, prompts.CAMPAIGN_MASTER, text, corrective=notes, extra=extra),
        texts=_turn_texts,
        rules=make_rules(ctx, text, fields={"text": FieldRule(DM_WORDS, True),
                                            "suggestions": FieldRule()}),  # fmt: skip
        template=lambda: TurnOut(text=SAFE_FALLBACK, speaker=C.CHRONICLER,
                                 suggestions=default_suggestions(ctx)),  # fmt: skip
        ctx=ctx, llm_context={"ctx": ctx, "input": text, "route": r, "extra": extra},
    )  # fmt: skip
    res = run_guarded(spec)
    return {"out": res.out, "degraded": res.degraded}


def _validate(state: TurnState) -> dict[str, Any]:
    from financequest.campaign.narration import TurnReply

    ctx, r, out = state["ctx"], state["route"], state["out"]
    _, allowed = turn_extra(ctx, r)
    here = ctx.current["key"] if ctx.current else ""
    ch = ctx.character(r.character_id) if r.intent == "talk" else None
    speaker = ch["id"] if ch and ch["location"] == here and not state.get("degraded") else C.CHRONICLER
    if state.get("degraded"):
        proposed: list[str] = []
    elif r.intent == "move" and r.location_key:  # arrival grants exactly the engine's free clues
        proposed = sorted(allowed)
    else:
        proposed = list(out.clue_ids_given)
    given = list(dict.fromkeys(c for c in proposed if c in allowed))
    rejected = [c for c in out.clue_ids_given if c not in allowed]
    sugg = [s.strip() for s in out.suggestions if s.strip()][:3]
    for extra_s in default_suggestions(ctx):
        if len(sugg) >= 3:
            break
        if extra_s not in sugg:
            sugg.append(extra_s)
    reply = TurnReply(
        text=out.text.strip(), speaker=C.speaker_name(ctx, speaker), intent=r.intent,
        challenge_id=next((c["id"] for c in ctx.challenges if c["key"] == r.challenge_key), None)
        if r.intent == "challenge" else None,
        location_key=r.location_key if r.intent == "move" else None,
        clue_ids_given=given, suggestions=sugg,
        nothing_more_to_uncover=bool(out.nothing_more_to_uncover) and not state.get("degraded"),
        degraded=bool(state.get("degraded")), rejected_clue_ids=rejected,
        speaker_id=speaker,
    )  # fmt: skip
    return {"reply": reply}


def _build_turn() -> Any:
    g = StateGraph(TurnState)
    g.add_node("route", _route)
    g.add_node("decision", _decision)
    g.add_node("narrate", _narrate)
    g.add_node("validate", _validate)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", _after_route, {"decision": "decision", "narrate": "narrate"})
    g.add_edge("narrate", "validate")
    g.add_edge("decision", END)
    g.add_edge("validate", END)
    return g.compile()


TURN = _build_turn()


# =====================================================================================
# Setup graph
# =====================================================================================
class SetupState(TypedDict, total=False):
    llm: NodeLLM
    ctx: C.AgentContext
    out: SetupOut
    degraded: bool
    result: dict[str, Any]


def prepared_setup(ctx: C.AgentContext) -> SetupOut:
    """Deterministic Tavern briefing: the fallback, and the FAKE_LLM script."""
    p = ctx.pack
    docs = ", ".join(d["title"] for d in ctx.content["documents"]) or "the archives"
    chars = [c for c in ctx.content["characters"] if ctx.location_name(c["location"]) != c["location"]]
    who = "; ".join(f"{c['name']} at {the(ctx.location_name(c['location']))}" for c in chars[:3])
    text = (
        f"Rain drums on the stained glass of the tavern in {p.setting}. The talk of the room is "
        f"{p.company_name}, {p.trade[:1].lower() + p.trade[1:]}. Your task: investigate, then decide "
        f"what to do with your {ctx.budget} euros. The story runs {clock_label(ctx)}. "
        f"The Library holds {docs}. The {p.market_name} shows the price board and the crowd's "
        f"mood. {who + ' can be questioned. ' if who else ''}"
        "CommerzBuddy can be called at any time. Where will you start?"
    )
    return SetupOut(text=text, suggestions=default_suggestions(ctx))


def the(name: str) -> str:
    """"the Library", but "The Golden Guild Hall" already carries its article."""
    return name if name.lower().startswith("the ") else f"the {name}"


def clock_label(ctx: C.AgentContext) -> str:
    from financequest.campaign import clock

    return clock.horizon_label(ctx.pack)


def _plan(state: SetupState) -> dict[str, Any]:
    ctx = state["ctx"]
    seeds = [f"{s['key']}: {s['name']}" for s in ctx.pack.seeds]
    have = {x["key"] for x in ctx.locations}
    extra = (
        f"# Setup facts\nLocation seeds not yet in play: "
        f"{'; '.join(s for s in seeds if s.split(':')[0] not in have) or 'none'}\n"
        f"Encounters in the reference data: {len(ctx.pack.encounters)} "
        f"({'enough' if len(ctx.pack.encounters) >= 2 else 'fewer than 2: add challenges'})."
    )
    spec = GuardedSpec(
        llm=state["llm"], node="campaign_setup", schema=SetupOut, effort="high",
        messages=lambda notes: C.build_messages(ctx, prompts.SETUP, "Open the campaign.", corrective=notes, extra=extra),
        texts=lambda o: {"text": o.text, "suggestions": " / ".join(o.suggestions)},
        rules=make_rules(ctx, fields={"text": FieldRule(DM_WORDS, True)}),
        template=lambda: prepared_setup(ctx), ctx=ctx, llm_context={"ctx": ctx},
    )  # fmt: skip
    res = run_guarded(spec)
    return {"out": res.out, "degraded": res.degraded}


def validate_setup(ctx: C.AgentContext, out: SetupOut) -> dict[str, Any]:
    """Engine validation of the plan. Locations only from the manifest seeds (their art subject
    comes from the seed, never from the model); extra challenges only when fewer than 2 encounters
    exist, with a difficulty from the rule table."""
    seed_keys = {s["key"] for s in ctx.pack.seeds}
    have = {x["key"] for x in ctx.locations}
    locs: list[ExtraLocation] = []
    for loc in out.extra_locations:
        if loc.key in seed_keys and loc.key not in have and loc.key not in {x.key for x in locs}:
            locs.append(loc)
    challenges: list[dict[str, Any]] = []
    if len(ctx.pack.encounters) < 2:
        all_keys = have | {x.key for x in locs}
        for ch in out.extra_challenges[: 2 - len(ctx.pack.encounters) + 1]:
            ev = ctx.evidence_by_id(ch.clue_id)
            taken = {c["key"] for c in ctx.challenges}
            if ev is None or ch.location_key not in all_keys or f"EXTRA-{ch.clue_id}" in taken:
                continue
            challenges.append({
                "key": f"EXTRA-{ch.clue_id}", "title": ch.title, "kind": ch.kind,
                "dc": rules.DC_TABLE[ch.kind], "location_key": ch.location_key,
                "clue_id": ch.clue_id, "checkpoint": ev["checkpoint"],
            })  # fmt: skip
    sugg = [s.strip() for s in out.suggestions if s.strip()][:3]
    for s in default_suggestions(ctx):
        if len(sugg) >= 3:
            break
        if s not in sugg:
            sugg.append(s)
    return {"locations": [x.model_dump() for x in locs], "challenges": challenges,
            "suggestions": sugg}  # fmt: skip


def _validate_setup(state: SetupState) -> dict[str, Any]:
    ctx, out = state["ctx"], state["out"]
    v = validate_setup(ctx, out)
    return {"result": {"text": out.text.strip(), "speaker": C.DM_NAME, "degraded": state.get("degraded", False), **v}}  # fmt: skip


def _build_setup() -> Any:
    g = StateGraph(SetupState)
    g.add_node("plan_campaign", _plan)
    g.add_node("validate", _validate_setup)
    g.add_edge(START, "plan_campaign")
    g.add_edge("plan_campaign", "validate")
    g.add_edge("validate", END)
    return g.compile()


SETUP = _build_setup()

__all__ = [
    "ExtraChallenge", "GUARDED", "SETUP", "TURN", "GuardedSpec", "make_rules", "run_guarded",
    "prepared_setup", "default_suggestions",
]  # fmt: skip
