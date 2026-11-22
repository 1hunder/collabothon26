"""Pydantic structured outputs of the campaign nodes.

Kept free of numeric/length constraints on purpose: the json_schema output mode does not support
them, so the engine validates counts, caps and ids after parsing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal[
    "free", "challenge", "talk", "decision_intent", "off_topic", "move", "new_location"
]
BuddyIntent = Literal["concept", "advice_request", "future_request", "identity_request", "other"]
Mood = Literal["calm", "curious", "thinking", "cheerful", "concerned"]
ChallengeKind = Literal["public_report", "unusual_figure", "cross_check", "obscure_lead"]


class NpcSpec(BaseModel):
    name: str = Field(description="A generated fantasy name, never a real person")
    role: str = Field(description="Short role, e.g. 'Dockmaster of the guild fleet'")
    persona: str = Field(default="", description="Two sentences: manner of speaking and attitude")


class NewLocationSpec(BaseModel):
    """A place the Campaign Master adds because the story needs it. The engine validates it."""

    name: str = Field(description="Place name, 2 to 5 words")
    description: str = Field(default="", description="One or two sentences, fictional world")
    art_subject: str = Field(
        default="", description="Scene for the painter: no text, lettering, logos, people or faces"
    )
    npc: NpcSpec


Skill = Literal["investigation", "insight", "persuasion", "stealth", "knowledge"]
Difficulty = Literal["easy", "medium", "hard"]


class CheckSpec(BaseModel):
    """An uncertain, skill-based action with no predefined challenge. The engine rolls the dice."""

    skill: Skill
    target: str = Field(description="What or who the attempt is aimed at, 2 to 8 words")
    difficulty: Difficulty = "medium"
    stakes: str = Field(default="", description="What success could reveal, one short phrase")


class RouteOut(BaseModel):
    """The router's judgment of one player action. The engine validates every id."""

    intent: Intent
    challenge_key: str | None = Field(default=None, description="Challenge key, intent=challenge")
    check: CheckSpec | None = Field(
        default=None,
        description="intent=challenge with no fitting challenge_key: an ad-hoc skill check",
    )
    character_id: str | None = Field(default=None, description="Character id, intent=talk")
    location_key: str | None = Field(default=None, description="Location key, intent=move")
    new_location: NewLocationSpec | None = Field(
        default=None, description="intent=new_location: the place to create, with its NPC"
    )


class TurnOut(BaseModel):
    text: str = Field(description="At most 150 words, ends with a question")
    speaker: str = Field(default="chronicler", description="'chronicler' or a character id")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short actions")
    clue_ids_given: list[str] = Field(default_factory=list)
    nothing_more_to_uncover: bool = False
    calls_for_decision: bool = Field(
        default=False, description="True when this scene puts an investment choice to the hero"
    )
    hp_loss: int = Field(default=0, description="HP the hero loses in this scene, 0 to 10")
    hp_reason: str = Field(default="", description="Why, in one short phrase, when hp_loss > 0")


class DecideOut(BaseModel):
    """The player's written answer in a decision scene. The engine clamps every amount."""

    kind: Literal["decision", "question", "other"] = "decision"
    action: Literal["buy", "sell", "hold"] | None = None
    amount_eur: int | None = Field(default=None, description="Euro amount named, whole number")
    portion: Literal["all", "most", "half", "some"] | None = None
    text: str = Field(default="", description="At most 120 words, ends with a question")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short actions")
    hp_loss: int = Field(default=0, description="HP lost to this decision's scene, 0 to 10; usually 0")
    hp_reason: str = Field(default="", description="Why, in one short phrase, when hp_loss > 0")
    reasoning: str | None = Field(
        default=None, description="The player's own reasons for the decision, copied from their words; null if none"
    )
    reasoning_sufficient: bool = Field(
        default=False,
        description="True only when the reasons name at least one concrete reason tied to the "
        "evidence or situation (a figure, a clue, the news, a risk)",
    )


class TextOut(BaseModel):
    text: str


class DiceOut(BaseModel):
    text: str
    hp_loss: int = Field(default=0, description="HP the hero loses, 0 to 10; usually 0")
    hp_reason: str = Field(default="", description="Why, in one short phrase, when hp_loss > 0")


class NpcOut(BaseModel):
    """The reply of the NPC at a Master-created place."""

    text: str = Field(description="At most 120 words, in the NPC's own voice, to 'you'")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short actions")
    clue_ids_given: list[str] = Field(default_factory=list)
    hp_loss: int = Field(default=0, description="HP the hero loses, 0 to 10; usually 0")
    hp_reason: str = Field(default="", description="Why, in one short phrase, when hp_loss > 0")
    escalate: bool = Field(default=False, description="True when the Campaign Master must answer")
    escalate_reason: str = ""


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
    how_you_reasoned: str = ""
    overlooked: str
    luck: str
    reflection_question: str
    closing: str = Field(default="", description="A short supportive closing line, only when asked")


class XpScore(BaseModel):
    category: str
    score: int
    rationale: str
    quote: str = ""


class XpOut(BaseModel):
    scores: list[XpScore]


class OfferOut(BaseModel):
    """The Master's answer to a hero with nothing left at stake: one in-world opportunity, or the
    days passing. The engine picks the figures and validates the kind."""

    kind: Literal["buyback", "loan", "fast_forward"]
    name: str = Field(default="", description="The offerer's generated fantasy name")
    role: str = Field(default="", description="Short role, e.g. 'Moneylender'")
    text: str = Field(description="At most 100 words, ends with a question")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short replies")


class SupportOut(BaseModel):
    """The Master's supporting hand for a hero in trouble: one in-world helper and one kind of help.
    The engine lists the allowed kinds, picks every figure and validates the kind."""

    kind: Literal["loan", "patron_grant", "rescue_buyback", "second_look"]
    name: str = Field(default="", description="The helper's generated fantasy name")
    role: str = Field(default="", description="Short role, e.g. 'Guild patron'")
    text: str = Field(description="At most 100 words, ends with a question")
    suggestions: list[str] = Field(default_factory=list, description="Exactly 3 short replies")


class LessonOut(BaseModel):
    """A CommerzBuddy lesson on one educational moment. Plain words, about age 16."""

    what_happened: str = Field(description="1-2 short sentences about the player's own game moment")
    idea: str = Field(description="The concept in plain words, at most 60 words")
    example: str = Field(description="A tiny hypothetical worked example with small round numbers in gp")
    takeaway: str = Field(description="One sentence")
    check_question: str
    check_options: list[str] = Field(min_length=3, max_length=3)
    answer_index: int = Field(ge=0, le=2)
