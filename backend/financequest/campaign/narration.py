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
    calls_for_decision: bool = False  # the scene puts an investment choice to the hero
    speaker_kind: str = "master"  # master / npc / buddy
    escalated: bool = False  # an NPC handed the action to the Campaign Master
    hp_loss: int = 0  # what the Master asked for; the engine clamps it
    hp_reason: str = ""
    new_location: dict[str, Any] | None = None  # validated spec, intent == new_location
    check: dict[str, Any] | None = None  # ad-hoc skill check the engine opens (intent == challenge)


@dataclass
class DecisionReply:
    """The player's answer in a decision scene, read by the agent layer; the engine executes it."""

    kind: str  # decision / question / other (not about the scene: run a normal turn)
    action: str | None  # buy / sell / hold
    amount_eur: int | None
    portion: str | None  # all / most / half / some
    text: str
    suggestions: list[str] = field(default_factory=list)
    degraded: bool = False
    hp_loss: int = 0  # a decision's costly consequence in the scene; the engine clamps it
    hp_reason: str = ""
    reasoning: str | None = None  # the reasons the player wrote inside the decision message
    reasoning_sufficient: bool = False  # concrete enough to proceed without asking


class Narration(Protocol):
    def market_scene(self, ctx: AgentContext, beat: str) -> TurnReply: ...
    def decide(self, ctx: AgentContext, text: str) -> DecisionReply: ...
    def setup(self, ctx: AgentContext) -> dict[str, Any]: ...
    def turn(self, ctx: AgentContext, text: str, forced_move: str | None = None) -> TurnReply: ...
    def npc_turn(self, ctx: AgentContext, text: str) -> TurnReply: ...
    def narrate_roll(self, ctx: AgentContext, roll: dict[str, Any]) -> TurnReply: ...
    def buddy(self, ctx: AgentContext, text: str) -> TurnReply: ...
    def news(self, ctx: AgentContext) -> TurnReply: ...
    def hint(self, ctx: AgentContext, target: dict[str, Any]) -> TurnReply: ...
    def summarize(self, ctx: AgentContext) -> str: ...
    def debrief(self, ctx: AgentContext) -> dict[str, Any]: ...
    def xp(
        self, rubric: tuple[tuple[str, int], ...], texts: dict[str, str],
        decision: dict[str, Any] | None = None,
    ) -> list[RawScore]: ...


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
