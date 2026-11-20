"""Campaign manifest (spec 003 tech section 2.4).

Player-facing amounts are the REAL reported values, tagged with a ``family``. The disguise
(shared money factor, rounding, <= 10,000) is applied later, at approve time, by NumberPlan.
Player text never contains raw numbers: it uses ``{figure_id}`` placeholders (``{id:abs}`` to
print the magnitude of a negative value).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckpointId = Literal["G0", "G1", "G2", "G3", "G4"]
CheckpointRole = Literal["intro", "disclosure", "decision", "outcome", "reflection"]
EvidenceKind = Literal["ledger", "announcement", "figure", "market", "opinion"]
FigureFamily = Literal["money", "per_share", "users", "headcount", "percent", "ratio"]

LOCATION_PATTERN = r"^(library|market_square|tavern|campaign:[a-z0-9_-]+)$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(_Model):
    case_id: str
    version: str
    campaign_title: str
    learning_objectives: list[str]
    currency: str = "USD"


class World(_Model):
    setting_name: str
    company_name: str
    shares_name: str
    market_name: str
    annual_report_name: str
    quarterly_report_name: str
    tone_notes: str = ""


class Checkpoint(_Model):
    id: CheckpointId
    role: CheckpointRole
    cutoff_date: date
    label: str


class Figure(_Model):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    label: str
    value: Decimal  # the real reported value; signed
    family: FigureFamily
    period: str | None = None


class KeyFigure(Figure):
    checkpoint: CheckpointId
    explain: str


class CompanyCard(_Model):
    name: str
    trade: str
    size: str
    key_figures: list[KeyFigure] = []


class Evidence(_Model):
    id: str
    checkpoint: CheckpointId
    location: str = Field(pattern=LOCATION_PATTERN)
    kind: EvidenceKind
    title: str
    player_text: str
    figures: list[Figure] = []
    key: bool = False
    teaching_note: str = ""


class Document(_Model):
    id: str
    checkpoint: CheckpointId
    title: str
    evidence_ids: list[str]


class Character(_Model):
    id: str
    name: str
    role: str
    location: str = Field(pattern=LOCATION_PATTERN)
    may_reveal: dict[CheckpointId, list[str]]
    never: list[str] = []


class Encounter(_Model):
    id: str
    title: str
    checkpoint: CheckpointId
    location: str = Field(pattern=LOCATION_PATTERN)
    dc: int
    skill_flavor: str
    evidence_ids: list[str]
    success_clue_id: str
    failure_forward: str
    teaching_target: str


class News(_Model):
    checkpoint: CheckpointId
    time_skip_days: int  # real day gap; the engine applies jitter later
    headline: str
    summary: str
    evidence_ids: list[str]


class Prices(_Model):
    path: str = "prices.csv"
    decision_date: date
    horizon_end: date


class FundSeries(_Model):
    name: str
    path: str


class RubricItem(_Model):
    category: str
    max: int


class LocationSeed(_Model):
    key: str = Field(pattern=r"^[a-z0-9_-]+$")
    name: str
    description: str
    art_subject: str


class Debrief(_Model):
    questions: list[str]
    post_reveal_facts: list[dict[str, str]] = []  # {checkpoint: G3|G4, text}


class LaterEvent(_Model):
    checkpoint: CheckpointId
    real_date: str
    text: str


class Secret(_Model):
    """Server-only. Never sent to a client or agent before the reveal."""

    real_entity: str
    ticker: str
    actors: list[str]
    city: str
    real_dates: dict[str, str]
    alias_map: dict[str, str]
    leak_terms: list[str]
    later_events: list[LaterEvent] = []
    evidence_sources: dict[str, str] = {}  # evidence id -> "section / source ids"


class CampaignManifest(_Model):
    meta: Meta
    world: World
    checkpoints: list[Checkpoint]
    company_card: CompanyCard
    evidence: list[Evidence]
    documents: list[Document]
    characters: list[Character]
    encounters: list[Encounter]
    news: News
    prices: Prices
    fund: FundSeries | None = None
    rubric: list[RubricItem] | None = None
    campaign_location_seeds: list[LocationSeed] = []
    debrief: Debrief
    secret: Secret

    def public_dict(self) -> dict[str, object]:
        """The part that may be stored in ``scenario.manifest`` (no ``secret``)."""
        return self.model_dump(mode="json", exclude={"secret"})
