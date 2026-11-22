"""Recruiter-only on-demand verification; authorizes before accessing CV contents."""
from sqlalchemy.orm import Session

from ai.career.interview import CriterionInfo
from ai.career.verification import generate_questions
from app.core.errors import AppError
from app.models import JobPosting, User
from app.schemas.verification import VerificationOut, VerificationQuestionOut
from app.services import ai_runtime, application_service, career_service, criteria_service


def generate(db: Session, user: User, application_id: int) -> VerificationOut:
    application = application_service.get_owned(db, user, application_id)
    if application.seeker.consent_ai_at is None:
        raise AppError(409, "AI_CONSENT_WITHDRAWN", "지원자가 AI 분석 동의를 철회했습니다.")
    job = db.get(JobPosting, application.job_id)
    criteria = [
        CriterionInfo(c.id, c.name, c.category, c.description)
        for c in criteria_service.load_for_scoring(db, job.id).items
    ]
    questions, method = generate_questions(
        job.title, job.description, criteria, application.cv_profile.document.masked_text,
        career_service.interview_blocklists(), ai_runtime.llm(),
    )
    return VerificationOut(
        application_id=application.id,
        cv_profile_id=application.cv_profile_id,
        method=method,
        questions=[
            VerificationQuestionOut(
                question=q.question, criterion_id=q.criterion_id, criterion_name=q.criterion_name,
                cv_quote=q.cv_quote, reason=q.reason, check_points=list(q.check_points),
            ) for q in questions
        ],
    )
