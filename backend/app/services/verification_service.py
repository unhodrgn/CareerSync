"""Recruiter-only on-demand verification; authorizes before accessing CV contents."""
import threading
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ai.career.interview import CriterionInfo
from ai.career.verification import generate_questions
from app.core.config import settings
from app.core.errors import AppError
from app.models import JobPosting, User
from app.schemas.verification import VerificationOut, VerificationQuestionOut
from app.services import ai_runtime, application_service, career_service, criteria_service

KST = timezone(timedelta(hours=9))
_lock = threading.Lock()
_counts: dict[tuple[int, date], int] = {}


def take_llm_slot(company_id: int) -> bool:
    """Count one LLM verification generation for today (KST); False when the daily limit is reached."""
    today = datetime.now(KST).date()
    with _lock:
        for key in [k for k in _counts if k[1] != today]:
            del _counts[key]
        used = _counts.get((company_id, today), 0)
        if used >= settings.COMPANY_DAILY_LLM_VERIFICATIONS:
            return False
        _counts[(company_id, today)] = used + 1
        return True


def reset_counts() -> None:
    with _lock:
        _counts.clear()


def generate(db: Session, user: User, application_id: int) -> VerificationOut:
    application = application_service.get_owned(db, user, application_id)
    if application.seeker.consent_ai_at is None:
        raise AppError(409, "AI_CONSENT_WITHDRAWN", "지원자가 AI 분석 동의를 철회했습니다.")
    job = db.get(JobPosting, application.job_id)
    criteria = [
        CriterionInfo(c.id, c.name, c.category, c.description)
        for c in criteria_service.load_for_scoring(db, job.id).items
    ]
    llm, limited = ai_runtime.llm(), False
    if llm is not None and not take_llm_slot(user.company_id):
        llm, limited = None, True
    questions, method = generate_questions(
        job.title, job.description, criteria, application.cv_profile.document.masked_text,
        career_service.interview_blocklists(), llm,
    )
    return VerificationOut(
        application_id=application.id,
        cv_profile_id=application.cv_profile_id,
        method=method,
        limited=limited,
        questions=[
            VerificationQuestionOut(
                question=q.question, criterion_id=q.criterion_id, criterion_name=q.criterion_name,
                cv_quote=q.cv_quote, reason=q.reason, check_points=list(q.check_points),
            ) for q in questions
        ],
    )
