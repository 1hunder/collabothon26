"""Pydantic structured outputs of the campaign nodes.

Kept free of numeric/length constraints on purpose: the json_schema output mode does not support
them, so the engine validates counts, caps and ids after parsing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["free", "challenge", "talk", "decision_intent", "off_topic", "move"]
BuddyIntent = Literal["concept", "advice_request", "future_request", "identity_request", "other"]
Mood = Literal["calm", "curious", "thinking", "cheerful", "concerned"]
ChallengeKind = Literal["public_report", "unusual_figure", "cross_check", "obscure_lead"]


class RouteOut(BaseModel):
    """The router's judgment of one player action. The engine validates every id."""

    intent: Intent
    challenge_key: str | None = Field(default=None, description="Challenge key, intent=challenge")
    character_id: str | None = Field(default=None, description="Character id, intent=talk")
    location_key: str | None = Field(default=None, description="Location key, intent=move")


class TurnOut(BaseModel):
    text: str = Field(description="At most 150 words, ends with a question")
    speaker: str = Field(default="chronicler", description="'chronicler' or a character id")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short actions")
    clue_ids_given: list[str] = Field(default_factory=list)
    nothing_more_to_uncover: bool = False
    calls_for_decision: bool = Field(
        default=False, description="True when this scene puts an investment choice to the hero"
    )


class DecideOut(BaseModel):
    """The player's written answer in a decision scene. The engine clamps every amount."""

    kind: Literal["decision", "question"] = "decision"
    action: Literal["buy", "sell", "hold"] | None = None
    amount_eur: int | None = Field(default=None, description="Euro amount named, whole number")
    portion: Literal["all", "most", "half", "some"] | None = None
    text: str = Field(default="", description="At most 120 words, ends with a question")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short actions")


class TextOut(BaseModel):
    text: str


class SummaryOut(BaseModel):
    summary: str


class BuddyOut(BaseModel):
    text: str = Field(description="At most 120 words")
    intent: BuddyIntent = "other"
    mood: Mood = "calm"


class AdviceCheck(BaseModel):
    contains_recommendation: bool = False
    promises_profit: bool = False
    predicts_future: bool = False

    @property
    def flagged(self) -> bool:
        return self.contains_recommendation or self.promises_profit or self.predicts_future


class ExtraLocation(BaseModel):
    key: str = Field(description="A key from the campaign location seeds")
    description: str = ""


class ExtraChallenge(BaseModel):
    title: str
    kind: ChallengeKind
    location_key: str
    clue_id: str


class SetupOut(BaseModel):
    text: str = Field(description="The Tavern briefing, at most 150 words, ends with a question")
    suggestions: list[str] = Field(default_factory=list)
    extra_locations: list[ExtraLocation] = Field(default_factory=list)
    extra_challenges: list[ExtraChallenge] = Field(default_factory=list)


class DebriefOut(BaseModel):
    sound_reasoning: str
    overlooked: str
    luck: str
    reflection_question: str


class XpScore(BaseModel):
    category: str
    score: int
    rationale: str
    quote: str = ""


class XpOut(BaseModel):
    scores: list[XpScore]
