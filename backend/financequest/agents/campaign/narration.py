"""``AgentNarration``: the Narration Protocol implemented with the LangGraph graphs."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from financequest.agents.campaign import context as C
from financequest.agents.campaign import prompts
from financequest.agents.campaign.edu_lessons import prepared_lesson
from financequest.agents.campaign.graphs import (
    DM_WORDS,
    NPC,
    SETUP,
    TURN,
    GuardedSpec,
    default_suggestions,
    hp_checks,
    make_rules,
    run_guarded,
)
from financequest.agents.campaign.guards import (
    SAFE_FALLBACK,
    FieldRule,
    GuardRules,
    lesson_advice_violations,
    round_numbers,
    whole,
)
from financequest.agents.campaign.schemas import (
    BuddyOut,
    DebriefOut,
    DecideOut,
    DiceOut,
    LessonOut,
    OfferOut,
    RouteOut,
    SummaryOut,
    SupportOut,
    TextOut,
    XpOut,
)
from financequest.campaign import reasoning as reasoning_mod
from financequest.campaign import rules
from financequest.campaign.narration import DecisionReply, OfferReply, TurnReply
from financequest.campaign.xp import RawScore, excerpt
from financequest.llm import NodeLLM, get_node_llm

log = logging.getLogger("financequest.agents")
SCENE_WORDS = 100
DECIDE_WORDS = 120
SCENE_BEATS = {
    "opening": "the first chance to put coins in, before the hero has learned much",
    "news": "the market reacts to the breaking news; the hero may change course",
    "decision": "the day of decision: the last chance to set the purse before the long wait",
    "story": "a moment in the story that asks the hero to commit coins or not",
}
SCENE_TEMPLATES = {
    "opening": "A guild broker leans over the counter: shares are on offer today, for anyone "
               "brave enough. Do you put coins in now, or keep them while you look around?",
    "news": "The square is loud with the news, and traders crowd the brokers' stalls. Your coins "
            "are where you left them. Do you change anything now?",
    "decision": "The bell for the last trading of the season rings. Whatever you choose now, you "
                "will live with until the horizon. What do you do with your coins?",
    "story": "Someone is waiting for your answer about your coins. What do you do with them now?",
}  # fmt: skip


def decisions_block(ctx: C.AgentContext) -> str:
    """Every decision the player wrote, in order, with what it did to the result (engine
    computed). The debrief weighs the reasoning at each step, not just the final number."""
    if not ctx.decisions:
        return "Decisions during the campaign: none."
    lines = ["# Decisions during the campaign (engine computed effects, gold pieces)"]
    for d in ctx.decisions:
        eff = d.get("effect_eur")
        lines.append(
            f"{d['day_label']} ({d['beat']}): {d['action']} {whole(d['amount_eur'])}"
            + (f"; effect on the result {whole(eff)}" if eff is not None else "")
            + f". Their words: \"{d['text']}\""
            + ("" if d["beat"] == "damage" else
               f". Reasoning given ({d.get('reasoning_source')}): \"{d['reasoning']}\""
               if d.get("reasoning") else ". Reasoning given: none")
        )
    if ctx.final_reasoning:
        lines.append(f"Reasoning given at the seal: \"{ctx.final_reasoning}\"")
    return "\n".join(lines)


def decision_suggestions(ctx: C.AgentContext) -> list[str]:
    if ctx.holds_shares:
        return ["Hold what I have", "Sell half my shares", "Buy more with my cash"]
    return ["Invest a quarter of my coins", "Invest half of my coins", "Keep my coins for now"]


_OFFER_SUGGESTIONS = {
    "buyback": ["Sell half of my coins", "No, I keep them all", "I look around instead"],
    "loan": ["I take the loan", "No, I decline", "I look around instead"],
}


def _offer_template(kind: str, facts: dict[str, Any]) -> dict[str, Any]:
    """The prepared offer used when the model's fails the guards: engine terms only."""
    if kind == "buyback":
        return {
            "name": "Harrel Voss", "role": "Guild broker", "suggestions": _OFFER_SUGGESTIONS["buyback"],
            "text": "A guild broker draws you aside: he will buy back part of your coins in the "
                    f"company at today's board price, up to {whole(facts['buyback']['max_eur'])} gold pieces "
                    "worth. How do you answer?",
        }  # fmt: skip
    if kind == "loan":
        t = facts["loan"]
        return {
            "name": "Ismene Dray", "role": "Moneylender", "suggestions": _OFFER_SUGGESTIONS["loan"],
            "text": f"A moneylender offers you up to {whole(t['principal_eur'])} gold pieces now, at flat "
                    f"interest of {whole(t['interest_pct'])} percent: {whole(t['repay_eur'])} gold pieces repaid "
                    f"{t['due']}. How do you answer?",
        }  # fmt: skip
    return {"name": "", "role": "", "suggestions": [],
            "text": "With everything committed, the days begin to pass. Are you ready to wait?"}  # fmt: skip


_SUPPORT_REASONS = {
    "low_hp": "their HP (the purse bar) is low after the damage they took",
    "position_down": "the coins they hold in the company are worth much less than they paid",
    "loss_sale": "they sold coins at a loss",
    "broke": "their purse bar is empty",
}
_SUPPORT_SUGGESTIONS = {
    "loan": ["I take the loan", "No, thank you", "I look around instead"],
    "patron_grant": ["I accept the help", "No, thank you", "I look around instead"],
    "rescue_buyback": ["Sell half of my coins", "No, I keep them", "I look around instead"],
    "second_look": ["Yes, show me", "No, thank you", "I look around instead"],
}
_SUPPORT_HELPERS = {
    "loan": ("Ismene Dray", "Moneylender"), "patron_grant": ("Edda Wren", "Guild patron"),
    "rescue_buyback": ("Cato Brindle", "Sympathetic broker"), "second_look": ("Old Marek", "Mentor"),
}  # fmt: skip


def _support_template(kind: str, terms: dict[str, Any]) -> dict[str, Any]:
    """The prepared supporting hand used when the model's fails the guards: engine terms only."""
    name, role = _SUPPORT_HELPERS[kind]
    if kind == "patron_grant":
        body = (f"A guild patron presses a purse into your hands: {whole(terms['gift_eur'])} gold pieces "
                f"to restore part of what you lost, a gift with no repayment. Do you accept?")
    elif kind == "loan":
        body = (f"A moneylender offers you up to {whole(terms['principal_eur'])} gold pieces now, at flat "
                f"interest of {whole(terms['interest_pct'])} percent: {whole(terms['repay_eur'])} gold pieces "
                f"repaid {terms['due']}. How do you answer?")
    elif kind == "rescue_buyback":
        body = ("A broker offers to buy part of your coins in the company at today's board price, up to "
                f"{whole(terms['max_eur'])} gold pieces worth. How do you answer?")
    else:
        body = ("An old mentor offers you a free look: one clue shared at no cost to you. Do you accept?"
                if terms.get("gives") == "one clue" else
                "An old mentor offers you a quiet hour to gather your thoughts, restoring one Focus at no cost. "
                "Do you accept?")
    return {"name": name, "role": role, "text": body, "suggestions": _SUPPORT_SUGGESTIONS[kind]}


SUPPORT_CLOSING = ("This was a hard path, and it is no failure to feel it. Stepping back from a loss "
                   "and asking what it taught you is exactly how a trader grows.")
BUDDY_WORDS = 120
EDU_FIELDS = {
    "what_happened": FieldRule(45, False), "idea": FieldRule(60, False), "example": FieldRule(55, False),
    "takeaway": FieldRule(25, False), "check_question": FieldRule(30, False),
    **{f"option_{i}": FieldRule(12, False) for i in range(3)},
}  # fmt: skip
EDU_HYPOTHETICAL = ("example", "check_question", "option_0", "option_1", "option_2")
LESSON_SENTENCE_WORDS = 25


def lesson_rules(ctx: C.AgentContext, facts: dict[str, Any]) -> GuardRules:
    """The guards of a lesson. The moment's snapshot figures are allowed everywhere; small round
    numbers (an imaginary case) only in the example and the quiz."""
    rules_ = make_rules(ctx, json.dumps(facts), fields=EDU_FIELDS)
    rules_.field_allowed = {k: rules_.allowed | round_numbers() for k in EDU_HYPOTHETICAL}
    return rules_


def lesson_violations(ctx: C.AgentContext, out: LessonOut, facts: dict[str, Any]) -> list[str]:
    return lesson_rules(ctx, facts).static_violations(_lesson_texts(out)) + _lesson_checks(out)


def _lesson_out(d: dict[str, Any]) -> LessonOut:
    c = d["check"]
    return LessonOut(
        what_happened=d["what_happened"], idea=d["idea"], example=d["example"], takeaway=d["takeaway"],
        check_question=c["question"], check_options=c["options"], answer_index=c["answer_index"],
    )


def _lesson_texts(o: LessonOut) -> dict[str, str]:
    return {"what_happened": o.what_happened, "idea": o.idea, "example": o.example,
            "takeaway": o.takeaway, "check_question": o.check_question,
            **{f"option_{i}": t for i, t in enumerate(o.check_options)}}  # fmt: skip


def _lesson_checks(o: LessonOut) -> list[str]:
    """Reading level (short sentences), at most two sentences about the game, three distinct
    options, and never advice."""
    out: list[str] = []
    for name, text in _lesson_texts(o).items():
        if any(len(s.split()) > LESSON_SENTENCE_WORDS for s in re.split(r"(?<=[.!?])\s+", text)):
            out.append(f"{name} has a sentence over {LESSON_SENTENCE_WORDS} words; use short sentences")
        out += lesson_advice_violations(text)
        if re.search(r"[$£]|\b(dollars?|pounds?|usd)\b", text, re.I):
            out.append("uses real-world currency; the quest's money is gold pieces (gp)")
    if len(re.findall(r"[.!?](?:\s|$)", o.what_happened)) > 2:
        out.append("what_happened must be one or two sentences")
    if len({t.strip().lower() for t in o.check_options}) < 3:
        out.append("the three answer options must differ")
    return list(dict.fromkeys(out))
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

    def npc_turn(self, ctx: C.AgentContext, text: str) -> TurnReply:
        """The NPC of the current Master-created place answers; escalation runs the Master turn."""
        s = NPC.invoke({"llm": self.llm, "ctx": ctx, "text": text})
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
        schema: type[BaseModel] = TextOut,
    ) -> tuple[str, bool, Any]:
        spec = GuardedSpec(
            llm=self.llm, node=node, schema=schema, effort=effort,
            messages=lambda notes: C.build_messages(ctx, prompt, user, corrective=notes, extra=extra),
            texts=lambda o: {"text": o.text, **({"hp_reason": o.hp_reason}
                                                 if getattr(o, "hp_loss", 0) > 0
                                                 and getattr(o, "hp_reason", "").strip() else {})},
            checks=hp_checks,
            rules=make_rules(ctx, user, fields={"text": FieldRule(max_words, question)}, spoilers=spoilers),
            template=lambda: TextOut(text=template), ctx=ctx,
            llm_context={"ctx": ctx, "input": user, "extra": extra, **(llm_context or {})},
        )  # fmt: skip
        res = run_guarded(spec)
        return res.out.text.strip(), res.degraded, res.out

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
        adhoc = bool(roll.get("skill"))
        if adhoc and roll["result"] != "success":
            template = ("You find nothing you can use, and the attempt costs you a moment you "
                        "cannot spare. What would you do next?")
        elif adhoc and not clue:
            template = "You notice a small thing worth remembering. What would you do next?"
        extra = (
            f"# Outcome of the attempt\nChallenge: {roll['title']}. Result: {roll['result']}.\n"
            + (f"Clue found: {clue['title']}: {clue['text']}\n" if clue else "")
            + (f"Alternative source for the same information: {roll.get('alt_source')}\n"
               if roll["result"] != "success" else "")
        )  # fmt: skip
        if adhoc:
            extra += (
                f"This was an unplanned attempt ({roll['skill']}) aimed at {roll['title']}"
                + (f"; success could reveal: {roll['stakes']}" if roll.get("stakes") else "")
                + ". It is not one of the listed challenges, so there is no alternative source to "
                "name. On success reveal ONLY the clue above"
                + ("" if clue else " (none is left here: give one small useful detail of the "
                   "place or person instead, never new evidence, figures or what happens next)")
                + ("; a natural 20 earns one extra small, safe detail" if roll.get("used") == 20
                   else "")
                + ". On a setback tell what goes wrong and what it costs the hero, then move on.\n"
            )
        nat1 = roll.get("used") == 1
        extra += (f"Natural 1 (a disastrous attempt): {'yes' if nat1 else 'no'}. "
                  "You may take HP on any result (a setback, or a success that costs something) "
                  "when you judge it right, and always say why.\n")
        text, degraded, out = self._text_node(
            ctx, node="campaign_dice", prompt=prompts.DICE, user="Narrate the result.", extra=extra,
            effort="low", max_words=DM_WORDS, question=True, template=template,
            llm_context={"roll": roll}, schema=DiceOut,
        )  # fmt: skip
        loss = 0 if degraded else max(0, min(int(getattr(out, "hp_loss", 0)), 10))  # any result may cost
        return TurnReply(text=text, intent="narrate_roll", degraded=degraded,
                         suggestions=default_suggestions(ctx), hp_loss=loss,
                         hp_reason=getattr(out, "hp_reason", "").strip() if loss else "")  # fmt: skip

    def news(self, ctx: C.AgentContext) -> TurnReply:
        n = ctx.content["news"] or {}
        extra = f"# Breaking news card already shown\nHeadline: {n.get('headline')}\nSummary: {n.get('summary')}"
        text, degraded, _ = self._text_node(
            ctx, node="campaign_news", prompt=prompts.NEWS, user="Frame the news.", extra=extra,
            effort="low", max_words=NEWS_WORDS, question=True,
            template="How does this news change your thinking?",
        )  # fmt: skip
        return TurnReply(text=text, degraded=degraded, intent="news")

    # ---- decisions throughout the campaign --------------------------------------------------------
    def market_scene(self, ctx: C.AgentContext, beat: str) -> TurnReply:
        """Sets a scene that puts an investment choice to the hero; the purse card has the figures."""
        extra = (
            f"# Decision scene\nBeat: {beat} ({SCENE_BEATS.get(beat, SCENE_BEATS['story'])}).\n"
            + "\n".join(C.purse_lines(ctx))
        )
        text, degraded, _ = self._text_node(
            ctx, node="campaign_scene", prompt=prompts.MARKET_SCENE, user="Set the scene.",
            extra=extra, effort="low", max_words=SCENE_WORDS, question=True,
            template=SCENE_TEMPLATES.get(beat, SCENE_TEMPLATES["story"]),
            llm_context={"beat": beat},
        )  # fmt: skip
        return TurnReply(text=text, degraded=degraded, intent="market_scene",
                         suggestions=decision_suggestions(ctx))  # fmt: skip

    def decide(self, ctx: C.AgentContext, text: str) -> DecisionReply:
        """Reads the player's written decision. The engine clamps and executes it; the model only
        reads the words and narrates the world's reaction. A failed reading falls back to a plain
        parse of the same words."""
        action, amount, portion = rules.parse_decision(text)
        fallback = DecideOut(
            kind="decision" if action else "question", action=action, amount_eur=amount,  # type: ignore[arg-type]
            portion=portion, suggestions=decision_suggestions(ctx),  # type: ignore[arg-type]
            text=("It is done, and the hall takes note of it. What do you do next?" if action
                  else "Tell me plainly what you do with your coins: put some in, take some out, "
                       "or wait?"),
        )  # fmt: skip
        spec = GuardedSpec(
            llm=self.llm, node="campaign_decide", schema=DecideOut, effort="medium",
            messages=lambda notes: C.build_messages(ctx, prompts.DECIDE, text, corrective=notes),
            texts=lambda o: {"text": o.text, **({"hp_reason": o.hp_reason}
                                                 if o.hp_loss > 0 and o.hp_reason.strip() else {})},
            checks=hp_checks,
            rules=make_rules(ctx, text, fields={"text": FieldRule(DECIDE_WORDS, True)}),
            template=lambda: fallback, ctx=ctx, llm_context={"ctx": ctx, "input": text},
        )  # fmt: skip
        res = run_guarded(spec)
        out: DecideOut = res.out
        kind = out.kind if out.kind in ("decision", "question", "other") else "question"
        if kind == "other":
            return DecisionReply(kind="other", action=None, amount_eur=None, portion=None,
                                 text="", degraded=res.degraded)  # fmt: skip
        reasoning = (out.reasoning or "").strip() or None
        if kind == "decision" and reasoning is None:  # the model missed it: read it from the words
            reasoning = reasoning_mod.extract_inline(text)
        sufficient = bool(reasoning) and bool(out.reasoning_sufficient) and not res.degraded
        if res.degraded and reasoning:
            sufficient = reasoning_mod.is_sufficient(reasoning)
        act = out.action if kind == "decision" else None
        if kind == "decision" and act is None:  # a decision with no action reads as a question
            kind = "question"
        sugg = [s.strip() for s in out.suggestions if s.strip()][:3] or decision_suggestions(ctx)
        loss = max(0, min(int(out.hp_loss or 0), 10)) if kind == "decision" and not res.degraded else 0
        return DecisionReply(hp_loss=loss, hp_reason=out.hp_reason.strip() if loss else "",
            reasoning=reasoning if kind == "decision" else None,
            reasoning_sufficient=sufficient if kind == "decision" else False,
            kind=kind, action=act, amount_eur=out.amount_eur if kind == "decision" else None,
            portion=out.portion if kind == "decision" else None, text=out.text.strip(),
            suggestions=sugg, degraded=res.degraded,
        )  # fmt: skip

    # ---- the all-in plot: nothing left at stake ----------------------------------------------------
    def offer(self, ctx: C.AgentContext, allowed: list[str]) -> OfferReply:
        """The Master chooses one in-world opportunity (or the days passing) for a hero with every
        coin committed. The engine supplies the terms and validates the kind."""
        facts = ctx.offer_facts or {}
        kinds = [k for k in allowed if k == "fast_forward" or k in facts] or ["fast_forward"]
        first = kinds[0]
        extra = (
            "# Offer facts (engine computed, gold pieces)\n"
            f"Allowed kinds: {', '.join(kinds)}.\n"
            + (f"buyback terms: a broker takes back up to {whole(facts['buyback']['max_eur'])} gold pieces of their "
               "coins at today's board price.\n" if "buyback" in kinds and "buyback" in facts else "")
            + (f"loan terms: lends up to {whole(facts['loan']['principal_eur'])} gold pieces, flat interest "
               f"{whole(facts['loan']['interest_pct'])} percent, {whole(facts['loan']['repay_eur'])} gold pieces repaid "
               f"{facts['loan']['due']}.\n" if "loan" in kinds and "loan" in facts else "")
            + "\n".join(C.purse_lines(ctx))
        )  # fmt: skip
        template = OfferOut(kind=first, **_offer_template(first, facts))  # type: ignore[arg-type]
        spec = GuardedSpec(
            llm=self.llm, node="campaign_offer", schema=OfferOut, effort="medium",
            messages=lambda notes: C.build_messages(
                ctx, prompts.OFFER, "Make the offer.", corrective=notes, extra=extra),
            texts=lambda o: {"text": o.text},
            rules=make_rules(ctx, fields={"text": FieldRule(SCENE_WORDS, True)}),
            template=lambda: template, ctx=ctx,
            llm_context={"ctx": ctx, "input": "Make the offer.", "allowed": kinds},
        )  # fmt: skip
        res = run_guarded(spec)
        out: OfferOut = res.out
        kind = out.kind if out.kind in kinds else first
        name = " ".join(out.name.split())[:40] or template.name
        role = " ".join(out.role.split())[:40] or template.role
        sugg = [s.strip() for s in out.suggestions if s.strip()][:3] or _OFFER_SUGGESTIONS.get(kind, [])
        return OfferReply(kind=kind, name=name if kind != "fast_forward" else "",
                          role=role if kind != "fast_forward" else "", text=out.text.strip(),
                          suggestions=sugg, degraded=res.degraded)  # fmt: skip

    # ---- the supporting hand: the story offers help to a hero in trouble ----------------------------
    def support(self, ctx: C.AgentContext, reason: str, allowed: list[str]) -> OfferReply:
        """The Master picks one engine-allowed kind of help and voices a helper. The engine supplies
        the terms and validates the kind; a refused or failed model gets the prepared offer."""
        facts = ctx.offer_facts or {}
        kinds = [k for k in allowed if k in facts] or allowed[:1]
        first = rules.support_pick(reason, kinds)
        ctx.support_reason = reason
        lines = [
            "# Supporting hand (engine computed, gold pieces)",
            f"Why the hero is in trouble: {_SUPPORT_REASONS[reason]}.",
            f"Allowed kinds: {', '.join(kinds)}.",
        ]
        for k in kinds:
            t = facts[k]
            lines.append(f"{k} terms: " + ", ".join(
                f"{key} {whole(v) if isinstance(v, int | float) else v}" for key, v in t.items()) + ".")
        extra = "\n".join([*lines, *C.purse_lines(ctx)])
        template = SupportOut(kind=first, **_support_template(first, facts[first]))  # type: ignore[arg-type]
        spec = GuardedSpec(
            llm=self.llm, node="campaign_support", schema=SupportOut, effort="medium",
            messages=lambda notes: C.build_messages(
                ctx, prompts.SUPPORT, "Offer the supporting hand.", corrective=notes, extra=extra),
            texts=lambda o: {"text": o.text},
            rules=make_rules(ctx, fields={"text": FieldRule(SCENE_WORDS, True)}),
            template=lambda: template, ctx=ctx,
            llm_context={"ctx": ctx, "input": "Offer the supporting hand.", "allowed": kinds,
                         "reason": reason},
        )  # fmt: skip
        res = run_guarded(spec)
        out: SupportOut = res.out
        kind = out.kind if out.kind in kinds else first
        name = " ".join(out.name.split())[:40] or _SUPPORT_HELPERS[kind][0]
        role = " ".join(out.role.split())[:40] or _SUPPORT_HELPERS[kind][1]
        text = out.text.strip() if kind == out.kind else _support_template(kind, facts[kind])["text"]
        sugg = [x.strip() for x in out.suggestions if x.strip()][:3] or _SUPPORT_SUGGESTIONS[kind]
        return OfferReply(kind=kind, name=name, role=role, text=text, suggestions=sugg,
                          degraded=res.degraded)  # fmt: skip

    def support_answer(self, ctx: C.AgentContext, kind: str, taken: bool) -> TurnReply:
        """The hero answered the supporting hand: narrated in the world, no figure repeated."""
        verdict = "taken" if taken else "declined"
        text, degraded, _ = self._text_node(
            ctx, node="campaign_support_answer", prompt=prompts.SUPPORT_ANSWER,
            user="Narrate the answer to the supporting hand.",
            extra=f"# The answer\nKind of help: {kind}. The hero {verdict} it.\n" + "\n".join(C.purse_lines(ctx)),
            effort="low", max_words=PART_WORDS + 10, question=True,
            template=("The helper's kindness settles over the room, and the moment passes. What do you do next?"
                      if taken else
                      "The helper nods kindly and steps back; the offer rests there should you want it. "
                      "What do you do next?"),
            llm_context={"kind": kind, "taken": taken},
        )  # fmt: skip
        return TurnReply(text=text, degraded=degraded, intent="offer_answer",
                         suggestions=decision_suggestions(ctx))  # fmt: skip

    def offer_answer(self, ctx: C.AgentContext) -> TurnReply:
        """The hero took the loan: the coins change hands (a card shows the terms)."""
        text, degraded, _ = self._text_node(
            ctx, node="campaign_offer_answer", prompt=prompts.OFFER_ANSWER, user="Narrate the loan.",
            extra="\n".join(C.purse_lines(ctx)), effort="low", max_words=PART_WORDS + 10, question=True,
            template="The lender counts the coins into your purse and the room goes back to its own "
                     "business. What do you do next?",
        )  # fmt: skip
        return TurnReply(text=text, degraded=degraded, intent="offer_answer",
                         suggestions=decision_suggestions(ctx))  # fmt: skip

    def fast_forward(self, ctx: C.AgentContext, why: str) -> TurnReply:
        """With nothing left at stake the days pass and the plot moves to its finish. Describes
        the passage of time only: no result, no figure, no prediction."""
        text, degraded, _ = self._text_node(
            ctx, node="campaign_forward", prompt=prompts.FAST_FORWARD, user="Narrate the days passing.",
            extra=f"# Why the plot moves on\n{why}\n" + "\n".join(C.purse_lines(ctx)),
            effort="low", max_words=SCENE_WORDS, question=False,
            template="With everything committed, there is nothing left for you to decide. The days "
                     "pass over the guild's halls, and the horizon draws near.",
            llm_context={"why": why},
        )  # fmt: skip
        return TurnReply(text=text, degraded=degraded, intent="fast_forward")

    def hint(self, ctx: C.AgentContext, target: dict[str, Any]) -> TurnReply:
        where = target["location_name"]
        extra = f"# Hint target \nThe clue the hero has not found is at: {where}."
        text, degraded, _ = self._text_node(
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

    # ---- educational lesson ---------------------------------------------------------------------------
    def edu_lesson(self, ctx: C.AgentContext, moment: dict[str, Any]) -> dict[str, Any]:
        """CommerzBuddy's lesson for one moment. The same guards as every narrating node; the
        example and the quiz may use small round numbers of an imaginary case, nothing else new.
        A failed guard (or a failed call) gives the prepared lesson of the concept."""
        facts = dict(moment["facts"])
        key = str(moment["concept_key"])
        base = lesson_rules(ctx, facts)
        extra = (
            f"# Moment to teach\nConcept: {moment['title']}. Moment facts (the only figures about the "
            f"player's game; whole numbers, gold pieces): {json.dumps(facts)}"
        )
        spec = GuardedSpec(
            llm=self.llm, node="campaign_edu_lesson", schema=LessonOut, effort="low",
            messages=lambda notes: C.build_messages(
                ctx, prompts.EDU_LESSON, f"Write the lesson: {moment['title']}.", corrective=notes, extra=extra),
            texts=_lesson_texts, rules=base, checks=_lesson_checks,
            template=lambda: _lesson_out(prepared_lesson(key, facts)),
            ctx=ctx, llm_context={"ctx": ctx, "moment": moment},
        )  # fmt: skip
        out: LessonOut = run_guarded(spec).out
        return {
            "what_happened": out.what_happened.strip(), "idea": out.idea.strip(),
            "example": out.example.strip(), "takeaway": out.takeaway.strip(),
            "check": {"question": out.check_question.strip(),
                      "options": [o.strip() for o in out.check_options], "answer_index": out.answer_index},
        }

    # ---- debrief ----------------------------------------------------------------------------------
    def debrief(self, ctx: C.AgentContext) -> dict[str, Any]:
        missed = ctx.overlooked
        question = ctx.question or "What would you check first next time?"
        template = DebriefOut(
            sound_reasoning="You gave reasons in your own words.",
            how_you_reasoned=(
                "You gave reasons for some of your decisions, and left others without one."
                if any(d.get("reasoning") for d in ctx.decisions)
                else "You gave no reasoning for your decisions along the way."
            ),
            overlooked=", ".join(missed) if missed else "Nothing important",
            luck="Part of the result depended on events no one could know at the time.",
            reflection_question=question,
            closing=SUPPORT_CLOSING if ctx.support_closing else "",
        )  # fmt: skip
        extra = (
            f"# Debrief facts \nOverlooked clue titles: {', '.join(missed) or 'none'}.\n"
            f"Player's written evidence: {' | '.join(ctx.player_texts)}\n"
            + ("Closing line: required. The result was a big loss and no supporting hand was taken.\n"
               if ctx.support_closing else "Closing line: leave empty.\n")
            + f"Suggested reflection question: {question}\n{C.render_outcome(ctx.outcome) if ctx.outcome else ''}\n"
            + decisions_block(ctx)
        )
        fields = {k: FieldRule(PART_WORDS, False) for k in
                  ("sound_reasoning", "how_you_reasoned", "overlooked", "luck")}  # fmt: skip
        fields["reflection_question"] = FieldRule(PART_WORDS, True)
        fields["closing"] = FieldRule(45, False)
        spec = GuardedSpec(
            llm=self.llm, node="campaign_debrief", schema=DebriefOut, effort="high",
            messages=lambda notes: C.build_messages(ctx, prompts.DEBRIEF, "Give the debrief.", corrective=notes, extra=extra),
            texts=lambda o: o.model_dump(), rules=make_rules(ctx, fields=fields),
            template=lambda: template, ctx=ctx, llm_context={"ctx": ctx, "question": question},
        )  # fmt: skip
        out: DebriefOut = run_guarded(spec).out
        closing = (out.closing.strip() or SUPPORT_CLOSING) if ctx.support_closing else ""
        return {"sound": out.sound_reasoning, "reasoning": out.how_you_reasoned, "overlooked": out.overlooked, "luck": out.luck,
                "question": out.reflection_question, **({"closing": closing} if closing else {})}  # fmt: skip

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
            + f"\n\nReasoning given:\n{texts.get('reasoning') or 'none'}"
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
        src = texts["reflection"] if "eflection" in name else (
            texts["evidence"] + "\n" + texts.get("reasoning", "")
        ).strip()
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
