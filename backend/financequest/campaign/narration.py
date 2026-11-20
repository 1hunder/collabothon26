"""Narration Protocol: what the engine asks of the agent layer.

The real implementation is ``financequest.agents.campaign.narration.AgentNarration`` (LangGraph
graphs over ``NodeLLM``). With ``FAKE_LLM=1`` the same graphs run over a scripted Campaign Master,
so the whole campaign is playable without keys. Narration never produces a number: code supplies
every figure, and the guards reject any figure that is not in the gated reference data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from financequest.campaign.xp import RawScore

if TYPE_CHECKING:
    from financequest.agents.campaign.context import AgentContext


@dataclass
class TurnReply:
    text: str
    speaker: str = "Campaign Master"  # the name tab
    intent: str = "free"  # free / challenge / talk / decision_intent / off_topic / move
    challenge_id: str | None = None
    location_key: str | None = None
    clue_ids_given: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    nothing_more_to_uncover: bool = False
    mood: str | None = None
    degraded: bool = False  # a guard failed and the templated text was used
    rejected_clue_ids: list[str] = field(default_factory=list)
    speaker_id: str = "chronicler"


class Narration(Protocol):
    def setup(self, ctx: AgentContext) -> dict[str, Any]: ...
    def turn(self, ctx: AgentContext, text: str, forced_move: str | None = None) -> TurnReply: ...
    def narrate_roll(self, ctx: AgentContext, roll: dict[str, Any]) -> TurnReply: ...
    def buddy(self, ctx: AgentContext, text: str) -> TurnReply: ...
    def news(self, ctx: AgentContext) -> TurnReply: ...
    def hint(self, ctx: AgentContext, target: dict[str, Any]) -> TurnReply: ...
    def summarize(self, ctx: AgentContext) -> str: ...
    def debrief(self, ctx: AgentContext) -> dict[str, Any]: ...
    def xp(self, rubric: tuple[tuple[str, int], ...], texts: dict[str, str]) -> list[RawScore]: ...


_current: Narration | None = None


def get_narration() -> Narration:
    """An explicitly set narration (tests), else the agent layer over ``get_node_llm()``: the
    scripted Campaign Master under FAKE_LLM=1, ChatAnthropic otherwise."""
    global _current
    if _current is None:
        from financequest.agents.campaign.narration import AgentNarration

        _current = AgentNarration()
    return _current


def set_narration(n: Narration | None) -> None:
    global _current
    _current = n
