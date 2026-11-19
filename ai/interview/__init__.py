"""The seeker practice-interview engine (docs/DECISIONS.md D51–D54, D57): pure Python, no model, no network, no database.

`build_plan` makes a deterministic plan from the job's criteria, the D21 question bank and the masked CV;
`InterviewEngine` runs it one answer at a time and tracks which criteria were covered. The CV enters only through
`clean_cv` (D62), every plan is checked by `validate_plan`, and everything sent to a model is a `ModelInput` made by
`compose` from `SafeText` (D61, D62). The final feedback is `make_feedback` over the two views (D63). See
PROJECT_DOCUMENTATION.md §6.2.
"""
from ai.interview.boundary import GatedClient, ModelInput, ask, compose
from ai.interview.cv_context import CleanCv, clean_cv, make_bank
from ai.interview.engine import InterviewEngine, InterviewStateError
from ai.interview.feedback import (
    FeedbackReport,
    FeedbackRequest,
    ParsedFeedback,
    feedback_request,
    make_feedback,
    parse_feedback,
    rules_feedback,
    screen_feedback,
)
from ai.interview.guards import is_duplicate, sanitize_analysis, screen_spoken, verified_quotes
from ai.interview.llm import LlmTurn, TurnLlmOut, TurnRequest, analyze_turn, parse_rubric, parse_turn, prepare_turn, rubric_request
from ai.interview.plan import build_plan, evidence_lines
from ai.interview.sensitive import SafeText, cut_sensitive, for_model, for_model_block, is_sensitive, safe_text, strip_sensitive
from ai.interview.spoken_pii import SpokenMaskResult, mask_spoken
from ai.interview.validate import PlanReport, validate_plan
from ai.interview.views import (
    SafeItem,
    SafePlan,
    SafeTurn,
    SafeUncovered,
    coverage_snapshot,
    plan_view,
    plan_view_from,
    transcript_view,
    transcript_view_from,
)
from ai.interview.types import (
    DEFAULT_LIMITS,
    Action,
    ActionKind,
    AnswerType,
    InterviewLimits,
    InterviewPlan,
    PlanCriterion,
    PlanItem,
    RubricPoint,
    TopicStatus,
    TurnAnalysis,
    TurnContext,
)

__all__ = [
    "DEFAULT_LIMITS",
    "Action",
    "ActionKind",
    "AnswerType",
    "CleanCv",
    "FeedbackReport",
    "FeedbackRequest",
    "GatedClient",
    "InterviewEngine",
    "InterviewLimits",
    "InterviewPlan",
    "InterviewStateError",
    "LlmTurn",
    "ModelInput",
    "ParsedFeedback",
    "PlanReport",
    "PlanCriterion",
    "PlanItem",
    "RubricPoint",
    "SafeItem",
    "SafePlan",
    "SafeText",
    "SafeTurn",
    "SafeUncovered",
    "SpokenMaskResult",
    "TopicStatus",
    "TurnAnalysis",
    "TurnContext",
    "TurnLlmOut",
    "TurnRequest",
    "analyze_turn",
    "ask",
    "build_plan",
    "clean_cv",
    "compose",
    "coverage_snapshot",
    "cut_sensitive",
    "evidence_lines",
    "feedback_request",
    "for_model",
    "for_model_block",
    "is_duplicate",
    "is_sensitive",
    "make_bank",
    "make_feedback",
    "mask_spoken",
    "parse_feedback",
    "parse_rubric",
    "parse_turn",
    "plan_view",
    "plan_view_from",
    "prepare_turn",
    "rubric_request",
    "rules_feedback",
    "safe_text",
    "sanitize_analysis",
    "screen_feedback",
    "screen_spoken",
    "strip_sensitive",
    "transcript_view",
    "transcript_view_from",
    "validate_plan",
    "verified_quotes",
]
