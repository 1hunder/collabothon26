"""The Veteran's guarded node: generate -> guards (numbers, leaks, advice, voice, question) ->
one corrective retry -> templated fallback. Same guards subgraph as the Campaign Master."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from financequest.agents.campaign.graphs import GuardedSpec, run_guarded
from financequest.agents.campaign.guards import FieldRule, GuardRules
from financequest.agents.veteran import prompts
from financequest.agents.veteran.context import (
    VeteranContext,
    allowlist,
    facts_block,
    history_block,
)
from financequest.agents.veteran.schemas import VeteranOut
from financequest.llm import NodeLLM, get_node_llm

VETERAN_WORDS = 130
SUGGESTION_WORDS = 12
FALLBACK = (
    "Let me fill my pipe and take that slower. Which of your decisions shall we look at again?"
)
FALLBACK_SUGGESTIONS = [
    "Walk me through my last quest",
    "What habits do you see?",
    "Tell me a story",
]


@dataclass
class VeteranReply:
    text: str
    mood: str = "listening"
    suggestions: list[str] = field(default_factory=list)
    show_timeline: bool = False
    degraded: bool = False


def _messages(ctx: VeteranContext, text: str, notes: list[str] | None) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    user = facts_block(ctx) + history_block(ctx) + f"\n\n# The hero says\n{text}"
    if notes:
        user += (
            "\n\n# Your previous answer broke these rules; write it again without them\n- "
            + "\n- ".join(notes)
        )
    return [SystemMessage(content=prompts.VETERAN), HumanMessage(content=user)]


def _texts(o: VeteranOut) -> dict[str, str]:
    out = {"text": o.text}
    for i, s in enumerate(o.suggestions[:3]):
        out[f"suggestion_{i}"] = s
    return out


class VeteranNarration:
    def __init__(self, llm: NodeLLM | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> NodeLLM:
        return self._llm if self._llm is not None else get_node_llm()

    def talk(self, ctx: VeteranContext, text: str) -> VeteranReply:
        fields = {"text": FieldRule(VETERAN_WORDS, True)}
        fields |= {f"suggestion_{i}": FieldRule(SUGGESTION_WORDS, False) for i in range(3)}
        rules = GuardRules(
            allowed=allowlist(ctx, text),
            leak_terms=ctx.leak_terms,
            leak_enabled=bool(ctx.leak_terms),
            hero_name="",
            advice=True,
            fields=fields,
        )
        spec = GuardedSpec(
            llm=self.llm,
            node="veteran_talk",
            schema=VeteranOut,
            effort="medium",
            messages=lambda notes: _messages(ctx, text, notes),
            texts=_texts,
            rules=rules,
            template=lambda: VeteranOut(
                text=FALLBACK, mood="listening", suggestions=FALLBACK_SUGGESTIONS
            ),
            ctx=ctx,  # type: ignore[arg-type]  # duck-typed: the subgraph only reads seconds_left()
            llm_context={"ctx": ctx, "input": text},
        )
        res = run_guarded(spec)
        out: VeteranOut = res.out
        sugg = [s.strip() for s in out.suggestions if s.strip()][:3]
        if len(sugg) < 3:
            sugg += [s for s in FALLBACK_SUGGESTIONS if s not in sugg][: 3 - len(sugg)]
        return VeteranReply(
            text=out.text.strip(),
            mood=out.mood,
            suggestions=sugg,
            show_timeline=out.show_timeline,
            degraded=res.degraded,
        )


_current: VeteranNarration | None = None


def get_veteran() -> VeteranNarration:
    global _current
    if _current is None:
        _current = VeteranNarration()
    return _current


def set_veteran(v: VeteranNarration | None) -> None:
    global _current
    _current = v
