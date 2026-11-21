from typing import Literal

from pydantic import BaseModel, Field

VeteranMood = Literal["listening", "pondering", "approving", "stern"]


class VeteranOut(BaseModel):
    text: str = Field(description="At most 130 words; the last sentence is a question")
    mood: VeteranMood = "listening"
    suggestions: list[str] = Field(
        default_factory=list, description="Exactly 3 short replies the player could give"
    )
    show_timeline: bool = Field(
        default=False, description="True when the decision timeline card helps this reply"
    )
