"""Shared data models. Pitch is 105 x 68 metres; NOR attacks +x, HAR attacks -x."""
from typing import Literal

from pydantic import BaseModel, Field

PITCH_X = 105.0
PITCH_Y = 68.0


class Player(BaseModel):
    id: str
    name: str
    team: str
    number: int
    position: str


class Event(BaseModel):
    id: int
    t: float
    type: str
    team: str
    player_id: str | None
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None
    outcome: str | None = None
    speed_kmh: float | None = None
    under_pressure: bool = False
    meta: dict = Field(default_factory=dict)


MomentKind = Literal["pressing_surge", "momentum_swing", "milestone", "speed",
                     "big_chance", "goal", "tactical_shift"]


class Moment(BaseModel):
    kind: MomentKind
    t: float
    team: str | None
    player_id: str | None
    evidence_event_ids: list[int]
    stats: dict
    priority: int


class Claim(BaseModel):
    text: str
    metric: str
    value: float | str
    subject: str  # team code or player id


class Insight(BaseModel):
    headline: str
    why_it_matters: str
    claims: list[Claim] = Field(default_factory=list)
    evidence_event_ids: list[int] = Field(default_factory=list)


class Overlay(BaseModel):
    kind: Literal["lower_third", "stat_card", "player_tag"]
    title: str
    body: str
    stats: list[tuple[str, str]] = Field(default_factory=list)
    t_start: float
    duration_s: float


class Proposal(BaseModel):
    id: str
    moment: Moment
    insight: Insight
    overlay: Overlay
    source: Literal["agent", "template"]
    verified: bool
    status: Literal["pending", "approved", "rejected", "expired", "aired"] = "pending"
    expires_at: float
    variants: dict[str, str] = Field(default_factory=dict)
    trace: list[dict] = Field(default_factory=list)
