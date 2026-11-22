"""Schemas of the internal agent API of the practice interview (M5 S1; docs/DECISIONS.md D58, D79).

Only the Interview Agent calls these routes. The fields of an event are deliberately untyped (`object`): `interview_ingest_service`
checks every type strictly (an integer that is not a bool, a string, a mapping) and answers with its own codes, so a typed field here
would coerce `"1"` into `1` or turn a wrong type into a generic 422. An unknown field is refused (422, sanitized as on every interview
path, D68). No response carries an AI result for a person to read, so there is no `notice`.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AgentContextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    status: str
    end_reason: str | None
    joinable: bool
    accepting_turns: bool
    end_grace_open: bool
    active_until: datetime | None
    plan: dict | None
    plan_sha256: str | None
    limits: dict
    last_seq: int
    ai_consent: bool
    mask_names: list[str]


class TurnEventIn(BaseModel):
    """One turn as `interview_ingest_service.TurnEvent` takes it."""

    model_config = ConfigDict(extra="forbid")

    seq: object = None
    role: object = None
    kind: object = None
    item_index: object = None
    topic_id: object = None
    text: object = None
    method: object = "rules"
    analysis: object = None
    masked_kinds: object = None
    coverage: object = None


class AgentEventIn(BaseModel):
    """`{"type": "turn", "turn": {...}}`, or `{"type": "end", "coverage": {...}, "closing": {...} | null}`."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["turn", "end"]
    turn: TurnEventIn | None = None
    coverage: object = None
    closing: TurnEventIn | None = None


class AgentEventOut(BaseModel):
    """A turn: `outcome` (`stored` or `duplicate`), `seq`, `started`, `dropped_quotes`. An end: `outcome` (`ended` or `duplicate`), `status`,
    `end_reason`."""

    type: Literal["turn", "end"]
    outcome: str
    seq: int | None = None
    started: bool | None = None
    dropped_quotes: int | None = None
    status: str | None = None
    end_reason: str | None = None
