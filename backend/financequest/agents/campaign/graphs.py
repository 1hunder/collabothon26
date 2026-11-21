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

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError

from financequest.agents.campaign import context as C
from financequest.agents.campaign import prompts
from financequest.agents.campaign.guards import (
    CHECK_NOTE,
    MECHANICS_NOTE,
    SAFE_FALLBACK,
    THIRD_NOTE,
    FieldRule,
    GuardRules,
    advice_prefilter,
    implies_check,
    leak_violations,
)
from financequest.agents.campaign.schemas import (
    AdviceCheck,
    CheckSpec,
    ExtraChallenge,
    ExtraLocation,
    NewLocationSpec,
    NpcOut,
    RouteOut,
    SetupOut,
    TurnOut,
)
from financequest.campaign import clock, rules
from financequest.llm import LLMResult, NodeLLM, extract_json_object

log = logging.getLogger("financequest.agents")
MIN_RETRY_S = 5.0
DM_WORDS = 150
NPC_WORDS = 120
HP_NOTE = "hp_loss is above 0 but the text does not state the loss (write 'You lose N HP: reason')"
NO_DAMAGE_INTENTS = ("off_topic", "decision_intent")  # everything else may cost HP


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
    checks: Callable[[Any], list[str]] | None = None  # node-specific violations on the parsed output


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
    trail: list[dict[str, Any]]
    gen_ms: int


def guard_results(violations: list[str]) -> dict[str, str]:
    """Pass/fail per guard from violation texts; only categories, never the offending terms."""
    def hit(*keys: str) -> bool:
        return any(k in v for v in violations for k in keys)

    return {
        "number": "pass" if not hit("number ", "millions or billions") else "fail",
        "leak": "pass" if not hit("real identity term") else "fail",
        "advice": "pass" if not hit("recommends", "promises", "predicts the future", "advice check")
        else "fail",
        "word_cap": "pass" if not hit("the cap is", "must end with a question") else "fail",
        "style": "pass" if not hit(MECHANICS_NOTE, THIRD_NOTE, CHECK_NOTE, HP_NOTE) else "fail",
    }


def _parse(res: LLMResult, schema: type[BaseModel]) -> BaseModel | None:
    if res.parsed is not None:
        return res.parsed
    try:
        return schema.model_validate(extract_json_object(res.text))
    except (ValueError, ValidationError):
        return None


def _generate(state: GState) -> dict[str, Any]:
    t_gen = time.monotonic()
    out = _generate_once(state)
    return {**out, "gen_ms": int((time.monotonic() - t_gen) * 1000)}


def _generate_once(state: GState) -> dict[str, Any]:
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
    log.debug("node=%s attempt=%d stop=%s %.1fs", spec.node, attempt, res.stop_reason,
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
    res = _check_once(state)
    viol = res.get("violations", state.get("violations") or [])
    entry = {"attempt": state.get("attempt", 1), "ms": state.get("gen_ms", 0),
             "refused": bool(state.get("refused")), **guard_results(viol)}  # fmt: skip
    if state.get("out") is None:
        entry["call"] = "failed"
    return {**res, "trail": [*(state.get("trail") or []), entry]}


def _check_once(state: GState) -> dict[str, Any]:
    spec, out = state["spec"], state.get("out")
    if out is None:
        return {}
    texts = spec.texts(out)
    bad = spec.rules.static_violations(texts)
    if spec.checks is not None:
        bad += spec.checks(out)
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
    t0 = time.monotonic()
    s = GUARDED.invoke({"spec": spec, "attempt": 0, "violations": [], "degraded": False,
                        "trail": []})  # fmt: skip
    trail = s.get("trail") or []
    # One structured line per guarded call. Guard names and pass/fail only: never the text, the
    # offending terms or the leak list.
    log.info("guarded %s", json.dumps({
        "graph": spec.node, "attempts": int(s.get("attempt", 1)), "trail": trail,
        "retry": len(trail) > 1, "fallback": bool(s.get("degraded")),
        "ms": int((time.monotonic() - t0) * 1000),
    }, separators=(",", ":")))  # fmt: skip
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
        hero_name=ctx.hero_name,
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
        return RouteOut(intent="challenge", challenge_key=r.challenge_key)  # a listed one wins
    if r.intent == "challenge" and r.check is not None:
        return _validate_check(ctx, r)
    if r.intent == "talk" and ctx.character(r.character_id) is not None:
        return r
    if r.intent == "move" and r.location_key in {x["key"] for x in ctx.locations}:
        return r
    if r.intent == "new_location":
        return _validate_new_location(ctx, r)
    if r.intent in ("decision_intent", "off_topic", "free"):
        return r
    return RouteOut(intent="free")


def check_location(ctx: C.AgentContext) -> str:
    return ctx.current["key"] if ctx.current else ""


def check_key(ctx: C.AgentContext, check: CheckSpec) -> str:
    return rules.adhoc_key(check.skill, check.target, check_location(ctx))


def check_repeated(ctx: C.AgentContext, check: CheckSpec) -> bool:
    """One ad-hoc check per skill + target + place: asking again is narrated, never rolled."""
    return check_key(ctx, check) in {c["key"] for c in ctx.challenges}


def _validate_check(ctx: C.AgentContext, r: RouteOut) -> RouteOut:
    """The engine, not the model, decides whether an ad-hoc skill check is allowed: a known
    skill, a clean target (a person must be here), and no second roll for the same attempt."""
    spec = r.check
    here = check_location(ctx)
    if spec is None or spec.skill not in rules.SKILLS or not here:
        return RouteOut(intent="free")
    target = " ".join(spec.target.split())[:80]
    low = target.lower()
    for ch in ctx.content["characters"]:
        names = [ch["name"].lower(), *(w for w in ch["name"].lower().split() if len(w) > 3)]
        if any(n in low for n in names):
            if ch["location"] != here:  # not here: that is a plain talk (they are elsewhere)
                return RouteOut(intent="talk", character_id=ch["id"])
            target = ch["name"]
            break
    if not target or leak_violations(target, ctx.pack.leak_terms):
        target = "the place"
    stakes = " ".join(spec.stakes.split())[:120]
    if leak_violations(stakes, ctx.pack.leak_terms):
        stakes = ""
    clean = CheckSpec(skill=spec.skill, target=target, difficulty=spec.difficulty, stakes=stakes)
    return RouteOut(intent="free" if check_repeated(ctx, clean) else "challenge", check=clean)


_FALLBACK_NPC = ("Brim Ostler", "A local keeper of the place")


def sanitize_new_location(ctx: C.AgentContext, spec: NewLocationSpec) -> NewLocationSpec | None:
    """The engine, not the model, decides whether a created place is acceptable: a
    clean name, and no real identity term anywhere (names fall back, free text is scrubbed)."""
    from financequest.media.art import scrub_subject

    terms = ctx.pack.leak_terms
    name = " ".join(spec.name.split())[:60]
    if not name or len(name) < 3 or re.search(r"\d", name) or leak_violations(name, terms):
        return None
    npc_name = " ".join(spec.npc.name.split())[:40]
    npc_role = " ".join(spec.npc.role.split())[:80]
    if not npc_name or re.search(r"\d", npc_name) or leak_violations(npc_name, terms):
        npc_name = _FALLBACK_NPC[0]
    if not npc_role or leak_violations(npc_role, terms):
        npc_role = _FALLBACK_NPC[1]
    clean = lambda t: " ".join(scrub_subject(t, terms).split())  # noqa: E731
    desc = clean(spec.description) or f"{name}, a place of this story."
    subject = clean(spec.art_subject) or desc
    subject = f"{subject.rstrip('. ')}. No people, no text or lettering, no logos."
    return NewLocationSpec(
        name=name, description=desc, art_subject=subject,
        npc={"name": npc_name, "role": npc_role, "persona": clean(spec.npc.persona)},  # type: ignore[arg-type]
    )


def _validate_new_location(ctx: C.AgentContext, r: RouteOut) -> RouteOut:
    if r.new_location is None:
        return RouteOut(intent="free")
    wanted = r.new_location.name.strip().lower()
    for x in ctx.locations:  # the place already exists: that is a move
        if x["name"].lower() == wanted or x["key"].replace("_", " ") == wanted:
            return RouteOut(intent="move", location_key=x["key"])
    spec = sanitize_new_location(ctx, r.new_location)
    if spec is None:
        return RouteOut(intent="free")
    return RouteOut(intent="new_location", new_location=spec)


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
    here = ctx.current["key"] if ctx.current else ""
    chars = [
        f"{c['id']} ({c['name']}, at {c['location']}{', HERE' if c['location'] == here else ''})"
        for c in ctx.content["characters"]
    ]
    locs = [f"{x['key']} ({x['name']})" for x in ctx.locations]
    chs = [f"{c['key']} ({c['title']}, {c['state']})" for c in ctx.challenges]
    return (
        f"# Ids you may use\nChallenges: {'; '.join(chs) or 'none'}\n"
        f"Characters: {'; '.join(chars) or 'none'}\nLocations: {'; '.join(locs)}\n"
        + f"Created places so far: {ctx.generated_count} (new_location is allowed whenever the story "
          "needs a place that is not listed)."
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
        who = C.people_at(ctx, loc["key"])
        return (
            f"# Intent: arrival\nYou (the hero) go to {loc['name']} ({loc['key']}): {state}. "
            f"Place: {loc['description']}\nFree clues the hero learns on arrival, which you MUST "
            f"mention in clue_ids_given and in the text: {'; '.join(titles) or 'none'}.\n"
            + (f"Characters who can be questioned here: {', '.join(c['name'] for c in who)}. "
               "Offer 'Ask <name> ...' as one of the suggestions.\n" if who else "")
            + "Speaker: chronicler.",
            set(free),
        )
    if r.intent == "new_location" and r.new_location is not None:
        n = r.new_location
        return (
            f"# Intent: arrival at a NEW place\nYou (the hero) walk into {n.name}, a place that "
            f"has only now come into the story, a first visit. Place: {n.description}\n"
            f"Someone is here: {n.npc.name}, {n.npc.role}. Introduce them by name in the text, in "
            f"one or two sentences, and offer 'Ask {n.npc.name} ...' as one of the suggestions. "
            "Reveal no clues and give no clue_ids. Speaker: chronicler.",
            set(),
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
    if r.intent == "challenge" and r.check is None:
        c = next(x for x in ctx.challenges if x["key"] == r.challenge_key)
        if c["state"] != "open":
            alt = c["alt_source"] or "ask around and read the documents"
            return (
                f"# Intent: challenge '{c['title']}' was already rolled ({c['result']}).\n"
                f"Say the information must come from another source: {alt}. Do not mention dice.",
                set(),
            )
        return (
            f"# Intent: challenge '{c['title']}'\nNarrate only the lead-in, to 'you'; a result card "
            "follows on its own. Do not mention dice, rolling, checks or the engine, and do not "
            "reveal what you find. End with a question.",
            set(),
        )
    if r.intent == "free" and r.check is not None:  # the same attempt again: narrated, not rolled
        ck = r.check
        return (
            f"# Intent: the hero repeats an attempt already made here ({rules.SKILLS[ck.skill]} on "
            f"{ck.target}). Say in the story that they have already gone over it and found all there "
            "is to find, reveal nothing new, and suggest doing something else. Do not mention dice.",
            set(),
        )
    if r.intent == "challenge" and r.check is not None:
        ck = r.check
        return (
            f"# Intent: an uncertain attempt, {rules.SKILLS[ck.skill]} aimed at {ck.target}\n"
            "Narrate only the lead-in in the story, to 'you' (what you crouch to study, how you "
            "lean in); a result card follows on its own. Do not mention dice, rolling, checks, "
            "skills or the engine, and do not reveal what you find. End with a question.",
            set(),
        )
    if r.intent == "off_topic":
        return ("# Intent: off-topic\nOne friendly sentence, then steer back to the investigation.",
                set())  # fmt: skip
    return ("# Intent: free action\nAnswer from the reference data.", C.reachable_clue_ids(ctx, None))


def open_challenge_here(ctx: C.AgentContext) -> dict[str, Any] | None:
    here = ctx.current["key"] if ctx.current else ""
    return next((c for c in ctx.challenges if c["state"] == "open" and c["location"] == here), None)


def _turn_texts(o: TurnOut) -> dict[str, str]:
    t = {"text": o.text}
    if o.suggestions:
        t["suggestions"] = " / ".join(o.suggestions)
    if o.hp_loss > 0 and o.hp_reason.strip():
        t["hp_reason"] = o.hp_reason
    return t


def hp_checks(o: Any) -> list[str]:
    """A damage claim must be stated in the text, so the player always sees why HP dropped."""
    if int(getattr(o, "hp_loss", 0) or 0) > 0 and not re.search(r"\bHP\b", o.text):
        return [HP_NOTE]
    return []


def _narrate(state: TurnState) -> dict[str, Any]:
    ctx, text, r = state["ctx"], state["text"], state["route"]
    extra, _ = turn_extra(ctx, r)
    rules_ = make_rules(ctx, text, fields={"text": FieldRule(DM_WORDS, True),
                                           "suggestions": FieldRule()})  # fmt: skip
    rules_.forbid_check = r.intent != "challenge" and open_challenge_here(ctx) is None
    if r.intent == "new_location" and r.new_location is not None:
        n = r.new_location
        arrival = TurnOut(
            text=f"You arrive at {n.name}. {n.npc.name}, {n.npc.role}, looks up from the work "
                 f"at hand. What would you do?",
            speaker=C.CHRONICLER, suggestions=[f"Ask {n.npc.name} what they know",
                                               *default_suggestions(ctx)][:3],
        )  # fmt: skip
    spec = GuardedSpec(
        llm=state["llm"], node="campaign_turn", schema=TurnOut, effort="medium",
        messages=lambda notes: C.build_messages(ctx, prompts.CAMPAIGN_MASTER, text, corrective=notes, extra=extra),
        texts=_turn_texts,
        rules=rules_,
        template=lambda: arrival if r.intent == "new_location" and r.new_location is not None
        else TurnOut(text=SAFE_FALLBACK, speaker=C.CHRONICLER,
                     suggestions=default_suggestions(ctx)),  # fmt: skip
        ctx=ctx, llm_context={"ctx": ctx, "input": text, "route": r, "extra": extra},
        checks=hp_checks,
    )  # fmt: skip
    res = run_guarded(spec)
    return {"out": res.out, "degraded": res.degraded}


def name_who_is_here(
    ctx: C.AgentContext, loc_key: str, text: str, sugg: list[str]
) -> tuple[str, list[str]]:
    """The arrival names who is there and offers "Ask <name> ..." (engine facts, so safe to add)."""
    who = C.people_at(ctx, loc_key)
    for ch in who[:1]:
        if ch["name"] not in text:
            head, sep, last = text.rpartition(". ")
            note = f"{ch['name']} is here, ready to talk."
            text = f"{head}{sep}{note} {last}" if sep else f"{note} {text}"
        if not any(f"Ask {ch['name']}" in s for s in sugg):
            sugg = [*sugg[:2], f"Ask {ch['name']} what they know"][:3]
    return text, sugg


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
    text_out = out.text.strip()
    if r.intent == "move" and r.location_key and not state.get("degraded"):
        text_out, sugg = name_who_is_here(ctx, r.location_key, text_out, sugg)
    spec = r.new_location if r.intent == "new_location" else None
    if spec is not None:
        if spec.npc.name not in text_out:
            head, sep, last = text_out.rpartition(". ")
            note = f"{spec.npc.name}, {spec.npc.role}, is here."
            text_out = f"{head}{sep}{note} {last}" if sep else f"{note} {text_out}"
        if not any(f"Ask {spec.npc.name}" in s_ for s_ in sugg):
            sugg = [*sugg[:2], f"Ask {spec.npc.name} what they know"][:3]
    hp_loss = 0
    if not state.get("degraded") and r.intent not in NO_DAMAGE_INTENTS:
        hp_loss = max(0, min(int(out.hp_loss or 0), 10))
    intent, ch_key = r.intent, r.challenge_key
    promised = None
    if intent not in ("challenge", "decision_intent", "new_location") \
            and not state.get("degraded") and implies_check(out.text):
        promised = open_challenge_here(ctx)  # a promised check always gets its dice card
        if promised is not None:
            intent, ch_key = "challenge", promised["key"]
    check = None
    if intent == "challenge" and r.check is not None:
        check = {"skill": r.check.skill, "target": r.check.target,
                 "difficulty": r.check.difficulty, "stakes": r.check.stakes}  # fmt: skip
    reply = TurnReply(
        text=text_out, speaker=C.speaker_name(ctx, speaker), intent=intent, check=check,
        challenge_id=next((c["id"] for c in ctx.challenges if c["key"] == ch_key), None)
        if intent == "challenge" else None,
        location_key=r.location_key if r.intent == "move" else None,
        clue_ids_given=given, suggestions=sugg,
        nothing_more_to_uncover=bool(out.nothing_more_to_uncover) and not state.get("degraded"),
        degraded=bool(state.get("degraded")), rejected_clue_ids=rejected,
        speaker_id=speaker,
        calls_for_decision=bool(getattr(out, "calls_for_decision", False))
        and not state.get("degraded") and intent not in ("challenge", "move", "new_location"),
        hp_loss=hp_loss, hp_reason=out.hp_reason.strip() if hp_loss else "",
        new_location=spec.model_dump() if spec is not None else None,
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
# NPC graph: the character of a Master-created place answers; the Master takes over on escalation
# =====================================================================================
class NpcState(TypedDict, total=False):
    llm: NodeLLM
    ctx: C.AgentContext
    text: str
    out: NpcOut | None
    escalate_reason: str
    reply: Any


def npc_extra(ctx: C.AgentContext) -> str:
    npc = ctx.npc_here
    assert npc is not None
    loc = next(x for x in ctx.locations if x["key"] == (ctx.current or {}).get("key"))
    may = C.npc_may_reveal(ctx)
    fresh = [i for i in may if i not in set(ctx.found)]
    titles = [f"{i} = {(ctx.evidence_by_id(i) or {}).get('title')}" for i in fresh]
    found = [(ctx.evidence_by_id(i) or {}).get("title", i) for i in ctx.found]
    return (
        f"# You are {npc['name']}, {npc['role']}\nPersona: {npc.get('persona') or 'plain-spoken'}\n"
        f"Place: {loc['name']}: {loc['description']}\n"
        f"Evidence you may reveal (ids; each only if the hero has not found it yet): "
        f"{'; '.join(titles) or 'none left'}.\n"
        f"The hero has already found: {'; '.join(found) or 'nothing yet'}.\n"
        "Reveal at most two clues per reply, and only by naming them clearly in the text."
    )


def _npc_texts(o: NpcOut) -> dict[str, str]:
    t = {"text": o.text}
    if o.suggestions:
        t["suggestions"] = " / ".join(o.suggestions)
    if o.hp_loss > 0 and o.hp_reason.strip():
        t["hp_reason"] = o.hp_reason
    return t


def _npc_answer(state: NpcState) -> dict[str, Any]:
    ctx, text = state["ctx"], state["text"]
    npc = ctx.npc_here
    if npc is None:
        return {"out": None, "escalate_reason": "no npc here"}
    if rules.is_decision_intent(text):  # committing coins is the Master's business, no model call
        return {"out": None, "escalate_reason": "the hero wants to decide"}
    rules_ = make_rules(ctx, text, fields={"text": FieldRule(NPC_WORDS, False),
                                           "suggestions": FieldRule()})  # fmt: skip
    extra = npc_extra(ctx)
    spec = GuardedSpec(
        llm=state["llm"], node="campaign_npc", schema=NpcOut, effort="medium",
        messages=lambda notes: C.build_messages(ctx, prompts.NPC, text, corrective=notes, extra=extra),
        texts=_npc_texts, rules=rules_, checks=hp_checks,
        template=lambda: NpcOut(text=SAFE_FALLBACK, escalate=True, escalate_reason="guards"),
        ctx=ctx, llm_context={"ctx": ctx, "input": text, "extra": extra, "npc": npc},
    )  # fmt: skip
    res = run_guarded(spec)
    out: NpcOut = res.out
    if res.degraded or out.escalate:
        return {"out": None, "escalate_reason": out.escalate_reason or "beyond the npc"}
    return {"out": out}


def _after_npc(state: NpcState) -> str:
    return "reply" if state.get("out") is not None else "master"


def _npc_reply(state: NpcState) -> dict[str, Any]:
    from financequest.campaign.narration import TurnReply

    ctx, out = state["ctx"], state["out"]
    assert out is not None
    npc = ctx.npc_here
    assert npc is not None
    may = set(C.npc_may_reveal(ctx))
    given = [c for c in dict.fromkeys(out.clue_ids_given) if c in may][:2]
    sugg = [s.strip() for s in out.suggestions if s.strip()][:3]
    for extra_s in default_suggestions(ctx):
        if len(sugg) >= 3:
            break
        if extra_s not in sugg:
            sugg.append(extra_s)
    hp_loss = max(0, min(int(out.hp_loss or 0), 10))
    return {"reply": TurnReply(
        text=out.text.strip(), speaker=str(npc["name"]), speaker_id=str(npc["id"]),
        speaker_kind="npc", intent="talk", clue_ids_given=given, suggestions=sugg,
        hp_loss=hp_loss, hp_reason=out.hp_reason.strip() if hp_loss else "",
        rejected_clue_ids=[c for c in out.clue_ids_given if c not in may],
    )}  # fmt: skip


def _npc_master(state: NpcState) -> dict[str, Any]:
    s = TURN.invoke({"llm": state["llm"], "ctx": state["ctx"], "text": state["text"],
                     "forced": None})  # fmt: skip
    reply = s["reply"]
    reply.escalated = True
    log.info("npc escalated: %s", state.get("escalate_reason"))
    return {"reply": reply}


def _build_npc() -> Any:
    g = StateGraph(NpcState)
    g.add_node("npc", _npc_answer)
    g.add_node("reply", _npc_reply)
    g.add_node("master", _npc_master)
    g.add_edge(START, "npc")
    g.add_conditional_edges("npc", _after_npc, {"reply": "reply", "master": "master"})
    g.add_edge("reply", END)
    g.add_edge("master", END)
    return g.compile()


NPC = _build_npc()


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
    who = "; ".join(f"{c['name']} at {the(ctx.location_name(c['location']))}" for c in chars[:5])
    known = [e["title"] for e in ctx.content["evidence"] if e["id"] in set(ctx.found)]
    if not known:  # the opening facts: free clues of the starting place, else of the first
        start = ctx.current["key"] if ctx.current else None
        known = [e["title"] for e in ctx.content["evidence"] if e["location"] == start][:3]
    knows = f"You already know: {'; '.join(known[:3])}. " if known else "You already know only the rumours of the room. "
    text = (
        f"Rain drums on the stained glass of the tavern in {p.setting}. The talk of the room is "
        f"{p.company_name}, {p.trade[:1].lower() + p.trade[1:]}. Your task: investigate, then decide "
        f"what to do with your {ctx.budget} euros. {knows}In this story {clock.horizon_sentence(ctx.pack)}. "
        f"The Library holds {docs}. The {p.market_name} shows the price board and the crowd's "
        f"mood. {who + ' can be questioned. ' if who else ''}"
        "CommerzBuddy can be called at any time. What would you do?"
    )
    return SetupOut(text=text, suggestions=default_suggestions(ctx))


def the(name: str) -> str:
    """"the Library", but "The Golden Guild Hall" already carries its article."""
    return name if name.lower().startswith("the ") else f"the {name}"




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
    "ExtraChallenge", "GUARDED", "NPC", "SETUP", "TURN", "GuardedSpec", "make_rules", "run_guarded",
    "prepared_setup", "default_suggestions",
]  # fmt: skip
