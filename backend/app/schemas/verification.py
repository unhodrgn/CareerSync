"""Company-only questions used to verify claimed professional experience."""
from pydantic import BaseModel
from app.schemas.application import AI_NOTICE


class VerificationQuestionOut(BaseModel):
    question: str
    criterion_id: int
    criterion_name: str
    cv_quote: str
    reason: str
    check_points: list[str]


class VerificationOut(BaseModel):
    application_id: int
    cv_profile_id: int
    method: str
    limited: bool = False
    questions: list[VerificationQuestionOut]
    notice: str = AI_NOTICE
