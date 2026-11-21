"""``AgentNarration``: the Narration Protocol implemented with the LangGraph graphs."""

from __future__ import annotations

import logging
from typing import Any

from financequest.agents.campaign import context as C
from financequest.agents.campaign import prompts
from financequest.agents.campaign.graphs import (
    DM_WORDS,
    SETUP,
    TURN,
    GuardedSpec,
    default_suggestions,
    make_rules,
    run_guarded,
)
from financequest.agents.campaign.guards import SAFE_FALLBACK, FieldRule, GuardRules
from financequest.agents.campaign.schemas import (
    BuddyOut,
    DebriefOut,
    RouteOut,
    SummaryOut,
    TextOut,
    XpOut,
)
from financequest.campaign.narration import TurnReply
from financequest.campaign.xp import RawScore, excerpt
from financequest.llm import NodeLLM, get_node_llm

log = logging.getLogger("financequest.agents")
BUDDY_WORDS = 120
NEWS_WORDS = 80
HINT_WORDS = 80
PART_WORDS = 70


def _internal(rules: GuardRules) -> GuardRules:
    """Model memory is never shown to the player: the voice rules do not apply."""
    rules.voice = False
    return rules


class AgentNarration:
    def __init__(self, llm: NodeLLM | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> NodeLLM:
        return self._llm if self._llm is not None else get_node_llm()

    # ---- setup ------------------------------------------------------------------------------
    def setup(self, ctx: C.AgentContext) -> dict[str, Any]:
        s = SETUP.invoke({"llm": self.llm, "ctx": ctx})
        return dict(s["result"])

    # ---- turn -------------------------------------------------------------------------------
    def turn(self, ctx: C.AgentContext, text: str, forced_move: str | None = None) -> TurnReply:
        forced = RouteOut(intent="move", location_key=forced_move) if forced_move else None
        s = TURN.invoke({"llm": self.llm, "ctx": ctx, "text": text, "forced": forced})
        reply: TurnReply = s["reply"]
        return reply

    # ---- text nodes ---------------------------------------------------------------------------
    def _text_node(
        self,
        ctx: C.AgentContext,
        *,
        node: str,
        prompt: str,
        user: str,
        extra: str,
        effort: str,
        max_words: int,
        question: bool,
        template: str,
        spoilers: bool = False,
        llm_context: dict[str, Any] | None = None,
    ) -> tuple[str, bool]:
        spec = GuardedSpec(
            llm=self.llm, node=node, schema=TextOut, effort=effort,
            messages=lambda notes: C.build_messages(ctx, prompt, user, corrective=notes, extra=extra),
            texts=lambda o: {"text": o.text},
            rules=make_rules(ctx, user, fields={"text": FieldRule(max_words, question)}, spoilers=spoilers),
            template=lambda: TextOut(text=template), ctx=ctx,
            llm_context={"ctx": ctx, "input": user, "extra": extra, **(llm_context or {})},
        )  # fmt: skip
        res = run_guarded(spec)
        return res.out.text.strip(), res.degraded

    def narrate_roll(self, ctx: C.AgentContext, roll: dict[str, Any]) -> TurnReply:
        """Only ever called with the FINAL result; a rerolled first result is never narrated."""
        clue = roll.get("clue")
        if roll["result"] == "success":
            template = (
                f"You find what you were looking for: {clue['title']}. What would you do next?"
                if clue else "You find what you were looking for. What would you do next?"
            )  # fmt: skip
        else:
            template = (
                f"A complication, but not a dead end. {roll.get('alt_source') or ''} "
                "What would you do next?"
            ).replace("  ", " ")
        extra = (
            f"# Outcome of the attempt\nChallenge: {roll['title']}. Result: {roll['result']}.\n"
            + (f"Clue found: {clue['title']}: {clue['text']}\n" if clue else "")
            + (f"Alternative source for the same information: {roll.get('alt_source')}\n"
               if roll["result"] != "success" else "")
        )  # fmt: skip
        text, degraded = self._text_node(
            ctx, node="campaign_dice", prompt=prompts.DICE, user="Narrate the result.", extra=extra,
            effort="low", max_words=DM_WORDS, question=True, template=template,
            llm_context={"roll": roll},
        )  # fmt: skip
        return TurnReply(text=text, intent="narrate_roll", degraded=degraded,
                         suggestions=default_suggestions(ctx))  # fmt: skip

    def news(self, ctx: C.AgentContext) -> TurnReply:
        n = ctx.content["news"] or {}
        extra = f"# Breaking news card already shown\nHeadline: {n.get('headline')}\nSummary: {n.get('summary')}"
        text, degraded = self._text_node(
            ctx, node="campaign_news", prompt=prompts.NEWS, user="Frame the news.", extra=extra,
            effort="low", max_words=NEWS_WORDS, question=True,
            template="How does this news change your thinking?",
        )  # fmt: skip
        return TurnReply(text=text, degraded=degraded, intent="news")

    def hint(self, ctx: C.AgentContext, target: dict[str, Any]) -> TurnReply:
        where = target["location_name"]
        extra = f"# Hint target \nThe clue the hero has not found is at: {where}."
        text, degraded = self._text_node(
            ctx, node="campaign_hint", prompt=prompts.HINT, user="Give the hint.", extra=extra,
            effort="low", max_words=HINT_WORDS, question=True, spoilers=True, llm_context={"target": target},
            template=f"Try the {where}: something there is worth reading. Will you go?",
        )  # fmt: skip
        sugg = [f"Go to the {where}"]
        for extra_s in default_suggestions(ctx):
            if len(sugg) < 3 and extra_s not in sugg:
                sugg.append(extra_s)
        return TurnReply(text=text, degraded=degraded, intent="hint", suggestions=sugg[:3])

    def summarize(self, ctx: C.AgentContext) -> str:
        found = ", ".join((ctx.evidence_by_id(i) or {}).get("title", i) for i in ctx.found)
        template = (
            f"The hero has taken {ctx.turn_count} turns and found: {found or 'nothing yet'}."
        )
        spec = GuardedSpec(
            llm=self.llm, node="campaign_summary", schema=SummaryOut, effort="low",
            messages=lambda notes: C.build_messages(ctx, prompts.SUMMARY, "Write the summary.", corrective=notes),
            texts=lambda o: {"summary": o.summary},
            rules=_internal(make_rules(ctx, fields={"summary": FieldRule(150, False)})),
            template=lambda: SummaryOut(summary=template), ctx=ctx, llm_context={"ctx": ctx},
        )  # fmt: skip
        return run_guarded(spec).out.summary.strip()

    # ---- buddy ----------------------------------------------------------------------------------
    def buddy(self, ctx: C.AgentContext, text: str) -> TurnReply:
        spec = GuardedSpec(
            llm=self.llm, node="campaign_buddy", schema=BuddyOut, effort="low",
            messages=lambda notes: C.build_messages(ctx, prompts.BUDDY, text, buddy=True, corrective=notes),
            texts=lambda o: {"text": o.text},
            rules=make_rules(ctx, text, fields={"text": FieldRule(BUDDY_WORDS, False)}, spoilers=True),
            template=lambda: BuddyOut(text=SAFE_FALLBACK, intent="other", mood="calm"),
            ctx=ctx, llm_context={"ctx": ctx, "input": text},
        )  # fmt: skip
        res = run_guarded(spec)
        out: BuddyOut = res.out
        return TurnReply(text=out.text.strip(), speaker=C.BUDDY_NAME, intent=out.intent,
                         mood=out.mood, degraded=res.degraded)  # fmt: skip

    # ---- debrief ----------------------------------------------------------------------------------
    def debrief(self, ctx: C.AgentContext) -> dict[str, Any]:
        missed = ctx.overlooked
        question = ctx.question or "What would you check first next time?"
        template = DebriefOut(
            sound_reasoning="You gave reasons in your own words.",
            overlooked=", ".join(missed) if missed else "Nothing important",
            luck="Part of the result depended on events no one could know at the time.",
            reflection_question=question,
        )  # fmt: skip
        extra = (
            f"# Debrief facts \nOverlooked clue titles: {', '.join(missed) or 'none'}.\n"
            f"Player's written evidence: {' | '.join(ctx.player_texts)}\n"
            f"Suggested reflection question: {question}\nResult: {ctx.outcome}"
        )
        fields = {k: FieldRule(PART_WORDS, False) for k in
                  ("sound_reasoning", "overlooked", "luck")}  # fmt: skip
        fields["reflection_question"] = FieldRule(PART_WORDS, True)
        spec = GuardedSpec(
            llm=self.llm, node="campaign_debrief", schema=DebriefOut, effort="high",
            messages=lambda notes: C.build_messages(ctx, prompts.DEBRIEF, "Give the debrief.", corrective=notes, extra=extra),
            texts=lambda o: o.model_dump(), rules=make_rules(ctx, fields=fields),
            template=lambda: template, ctx=ctx, llm_context={"ctx": ctx, "question": question},
        )  # fmt: skip
        out: DebriefOut = run_guarded(spec).out
        return {"sound": out.sound_reasoning, "overlooked": out.overlooked, "luck": out.luck,
                "question": out.reflection_question}  # fmt: skip

    # ---- xp ----------------------------------------------------------------------------------------
    def xp(
        self, rubric: tuple[tuple[str, int], ...], texts: dict[str, str],
        decision: dict[str, Any] | None = None,
    ) -> list[RawScore]:
        """The evaluator sees only the rubric and the player's own words, never P&L, HP or dice;
        the engine clamps, quote-checks and loss-word-scans whatever comes back."""
        from langchain_core.messages import HumanMessage, SystemMessage

        user = (
            "Rubric (category: max): " + "; ".join(f"{n}: {m}" for n, m in rubric)
            + f"\n\nPlayer's written evidence:\n{texts.get('evidence', '')}"
            + f"\n\nPlayer's reflection:\n{texts.get('reflection', '')}"
            + _decision_facts(decision)
        )  # fmt: skip
        try:
            res = self.llm.run(
                "campaign_xp",
                [SystemMessage(content=prompts.XP), HumanMessage(content=user)],
                schema=XpOut, effort="high",
                context={"rubric": rubric, "texts": texts, "decision": decision},
            )
            parsed = res.parsed
            if res.refused or not isinstance(parsed, XpOut):
                raise ValueError("no XP scores")
        except Exception as exc:  # noqa: BLE001
            log.warning("xp evaluator failed, using heuristic scores: %s", exc)
            return heuristic_xp(rubric, texts, decision)
        return [RawScore(s.category, int(s.score), s.rationale, s.quote) for s in parsed.scores]


def _decision_facts(decision: dict[str, Any] | None) -> str:
    if not decision:
        return ""
    pct, conf = decision.get("forecast_pct"), decision.get("confidence")
    return (
        "\n\nCommitted decision (explicit, set by the player on the decision form): "
        f"action {decision.get('action')}; forecast {pct}% chance the price is higher at the "
        f"horizon; confidence {conf}."
    )


def heuristic_xp(
    rubric: tuple[tuple[str, int], ...], texts: dict[str, str], decision: dict[str, Any] | None = None
) -> list[RawScore]:
    """Degraded scoring when the evaluator fails: clarity by length, never outcome."""
    out = []
    pct = (decision or {}).get("forecast_pct")
    for name, mx in rubric:
        if "forecast" in name.lower() and pct is not None:
            conf = (decision or {}).get("confidence")
            out.append(RawScore(
                name, mx,
                f"You committed to a {pct}% forecast"
                + (f" with {conf} confidence." if conf else "."), "",
            ))  # fmt: skip
            continue
        src = texts["reflection"] if "eflection" in name else texts["evidence"]
        quote = excerpt(src, 60)
        score = min(mx, round(mx * min(len(src.strip()), 120) / 120))
        out.append(RawScore(name, score, _heuristic_rationale(name, bool(quote)), quote))
    return out


def _heuristic_rationale(category: str, has_quote: bool) -> str:
    """A rationale specific to the category (neutral wording: no outcome or profit words)."""
    low = category.lower()
    if "evidence" in low:
        what = "You pointed to specific details from the documents"
    elif "risk" in low:
        what = "You named what could go wrong"
    elif "uncertain" in low:
        what = "You admitted what could not be known"
    elif "logic" in low or "consisten" in low:
        what = "Your steps followed from one another"
    elif "eflection" in low:
        what = "You looked back at your own reasoning"
    else:
        what = f"On {category.lower()}, you explained your thinking"
    return what + (", as in your own words." if has_quote else ".")
