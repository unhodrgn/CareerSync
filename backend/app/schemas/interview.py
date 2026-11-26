"""Schemas of the practice-interview API (M4 S4; docs/DECISIONS.md D58, D65, D67).

Each stage of S4 adds the schemas of the routes it adds: S4.1 the consent text, S4.2 the creation of a session, S4.3 the history, S4.5 the feedback. The responses are built from
the service dataclasses (`from_attributes`), and nothing here imports the interview engine or the models."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.application import AI_NOTICE


class ConsentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    text: str


class ConsentTextOut(BaseModel):
    """The consent to store a transcript (D65): what the client shows, and the version it sends back with a create request. Static text
    with no personal data and no AI result, so there is no `notice`."""

    model_config = ConfigDict(from_attributes=True)

    version: str
    title: str
    retention_days: int
    items: list[ConsentItemOut]


class JoinOut(BaseModel):
    """What the browser needs to join the room of a created session (M5 S4, D80 (4)): the LiveKit URL, a microphone-only token for that one
    room, the room name, and when the token stops being valid. No AI result, so no `notice`."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    token: str
    room: str
    expires_at: datetime


class InterviewCreateIn(BaseModel):
    """The request to create a session. The two consent fields are deliberately not typed: the service decides, with `is True` and an exact
    version, and answers a missing, false, string or old-version consent with its own 409 codes. A typed field would turn `"true"` into
    `true`, and a missing value into a 422. An unknown field is refused (422)."""

    model_config = ConfigDict(extra="forbid")

    consent_transcript: object = Field(default=None, description="Must be exactly `true`: consent to store the masked transcript (D65)")
    consent_version: object = Field(default=None, description="The `version` of `GET /api/interview-consent` that the seeker was shown")
    depth: Literal[1, 2, 3] = Field(default=2, description="Question depth chosen by the seeker: 1 introductory, 2 applied, 3 advanced (D93)")

    @field_validator("depth", mode="before")
    @classmethod
    def _exact_int_depth(cls, value: object) -> object:
        # Reject bool (`True` -> 1) and float (`2.0` -> 2) with a fixed message so D68 error sanitization never leaks input values.
        if type(value) is not int:
            raise ValueError("Input should be 1, 2 or 3")
        return value


class TopicOut(BaseModel):
    """A topic of the plan. `importance` is the label core / important / general, never a weight (AI rule 9)."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: str
    kind: str
    criterion_name: str | None
    importance: str | None
    depth: int | None
    status: str  # the engine's: not_asked, asked, demonstrated, partial, not_shown, skipped


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    kind: str
    text: str  # masked


class SessionOut(BaseModel):
    """A practice-interview session as its owner sees it. The plan and the rubric are AI-generated, so it carries the notice."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    job_title: str
    status: str  # derived from the deadlines: a session past its deadline reads `aborted`
    end_reason: str | None
    plan_method: str | None
    depth: int | None
    max_seconds: int | None
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    active_until: datetime | None
    expires_at: datetime
    joinable: bool
    accepting_turns: bool
    end_grace_open: bool
    feedback_status: str  # none or ready
    topics: list[TopicOut]
    turns: list[TurnOut]
    notice: str = AI_NOTICE


class CreatedSessionOut(BaseModel):
    """`limited`: a model is configured, but the day's planning-model quota stopped the attempt, so the plan is the template."""

    model_config = ConfigDict(from_attributes=True)

    session: SessionOut
    limited: bool


class SessionSummaryOut(BaseModel):
    """A session in the history (D67): its lifecycle and whether a feedback exists, and nothing of the plan, the coverage, the transcript or
    the feedback itself. It has no `topics`, no `turns`, no weight and no `notice` (the page has the notice)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    job_title: str
    status: str  # derived like `SessionOut.status`: a session past its deadline reads `aborted`
    end_reason: str | None
    created_at: datetime
    ended_at: datetime | None
    active_until: datetime | None
    expires_at: datetime
    joinable: bool
    feedback_status: str  # none or ready


class HistoryPageOut(BaseModel):
    """One page of the seeker's history, newest first. `next_before_id`: pass it as `before_id` for the next page; null at the end.
    `active` is the seeker's one planning, created or live session now, in the same shape as an item, or null. It does not depend on
    `job_id`, `limit` or `before_id`, so a client reads it here and never infers it from `items` (D67); when the session is on the page it
    is in `items` too. Every field is always present."""

    model_config = ConfigDict(from_attributes=True)

    items: list[SessionSummaryOut]
    next_before_id: int | None
    active: SessionSummaryOut | None
    notice: str = AI_NOTICE


# ── The feedback of a finished session (D63, D64, D67). `FeedbackReportOut` is the `to_data()` of the report that the feedback service stores or
# makes, field for field: it adds no field, and it drops any key that is not one of these. ──


class FeedbackTopicOut(BaseModel):
    """`importance` is the label core / important / general, never a weight (AI rule 9). `status` is the engine's."""

    topic_id: str
    name: str
    importance: str | None
    status: str  # demonstrated, partial, not_shown, skipped, asked or not_asked


class FeedbackStrengthOut(BaseModel):
    topic_id: str
    text: str
    quotes: list[str]  # each found exactly in a candidate line of the same topic (D63): the only transcript text of the report


class FeedbackGapOut(BaseModel):
    topic_id: str
    text: str


class FeedbackPracticeQuestionOut(BaseModel):
    topic_id: str
    question: str


class FeedbackResourceLinkOut(BaseModel):
    topic_id: str
    skill: str
    title: str
    url: str  # only ever a URL of the learning-resources allow-list


class FeedbackUncoveredOut(BaseModel):
    topic_id: str
    name: str
    importance: str
    reason: str


class FeedbackReportOut(BaseModel):
    """What the report says; no number that scores or ranks, no verdict, no hiring advice. `rubric_notice` says that the rubric points are AI-made."""

    method: str  # "rules" or "llm:<model>"
    topics: list[FeedbackTopicOut]
    strengths: list[FeedbackStrengthOut]
    gaps: list[FeedbackGapOut]
    improvements: list[str]
    practice_questions: list[FeedbackPracticeQuestionOut]
    resources: list[FeedbackResourceLinkOut]
    uncovered: list[FeedbackUncoveredOut]
    notes: list[str]
    rules_sections: list[str]  # with method "llm:...": the sections taken from the rules report
    rubric_notice: str


class FeedbackOut(BaseModel):
    """The answer of the feedback route, 200 for a final and a provisional report alike (D67 (1)). `final`: the report is stored and never changes.
    Provisional (`final` false): made for this request and not stored, and `reason` says why (`quota`, `model_failed`, `plan_invalid`,
    `lease_lost`); `limited`: a model is configured but today's feedback-model quota stopped the attempt. `generated_at` is the time of a stored
    report. There is no prompt version, no attempt count and no second `method` here: the method is `report.method`."""

    report: FeedbackReportOut
    final: bool
    limited: bool
    reason: str | None
    generated_at: datetime | None
    notice: str = AI_NOTICE
