"""AI self-check of a seeker's own CV version (docs/DECISIONS.md D25).

Any own version, confirmed or not. Needs AI consent (`consent_ai_at`; the version is not checked, as for
upload, D17). The LLM sees only the masked CV text, so its part is cached per CV document × PROMPT_VERSION ×
method in `cv_reviews`; rule findings that depend on the edited profile are computed on every request.

AI_MODE=rules: the rules review, not stored. AI_MODE=llm: a cached LLM review if any; otherwise one new LLM call
under a lock on the seeker's `users` row, within CAREER_DAILY_LLM_GENERATIONS per day (KST), shared with the
roadmap and interview questions. Over the limit the rules review comes back with `limited: true`; an LLM failure
returns the rules review and stores nothing, so the next call retries.
"""
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai.career.cv_review import CvReview, combine, make_llm_review, review_rules
from ai.parsing.extract import PROMPT_VERSION
from app.core.config import settings
from app.core.errors import AppError
from app.models import CvProfile, User
from app.models import CvReview as CvReviewRow
from app.schemas.cv import CvReviewItem, CvReviewOut
from app.services import ai_runtime, career_service, cv_service


def _out(profile: CvProfile, review: CvReview, method: str, limited: bool) -> CvReviewOut:
    def items(xs):
        return [CvReviewItem(title=i.title, detail=i.detail, cv_quote=i.cv_quote, affects_scoring=i.affects_scoring) for i in xs]

    return CvReviewOut(
        profile_id=profile.id,
        strengths=items(review.strengths),
        improvements=items(review.improvements),
        method=method,
        limited=limited,
    )


def _cached(db: Session, document_id: int) -> CvReviewRow | None:
    q = select(CvReviewRow).where(
        CvReviewRow.cv_document_id == document_id,
        CvReviewRow.prompt_version == PROMPT_VERSION,
        CvReviewRow.method.like("llm:%"),
    )
    return db.scalars(q.order_by(CvReviewRow.created_at.desc(), CvReviewRow.id.desc())).first()


def _store(db: Session, profile: CvProfile, method: str, content: dict) -> None:
    try:
        with db.begin_nested():
            db.add(
                CvReviewRow(
                    cv_document_id=profile.cv_document_id,
                    seeker_id=profile.seeker_id,
                    prompt_version=PROMPT_VERSION,
                    method=method,
                    content=content,
                    created_at=datetime.now(UTC),
                )
            )
    except IntegrityError:
        pass  # stored by a concurrent request


def review(db: Session, user: User, profile_id: int) -> CvReviewOut:
    profile = cv_service.get_own(db, user, profile_id)
    if user.consent_ai_at is None:
        raise AppError(409, "AI_CONSENT_REQUIRED", "AI 분석 동의 후 이력서 점검을 받을 수 있습니다.")
    text = profile.document.masked_text
    data = cv_service.to_profile_data(profile)
    skills = ai_runtime.skills()

    def rules() -> CvReview:
        return review_rules(text, data, skills, date.today().strftime("%Y-%m"))

    if ai_runtime.mode() != "llm":
        return _out(profile, rules(), "rules", False)
    if (hit := _cached(db, profile.cv_document_id)) is not None:
        return _out(profile, combine(CvReview.from_dict(hit.content), text, data, skills), hit.method, False)

    # One generation per seeker at a time, so the shared daily limit holds (the lock covers the LLM call, issue 29)
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    if (hit := _cached(db, profile.cv_document_id)) is not None:
        db.commit()
        return _out(profile, combine(CvReview.from_dict(hit.content), text, data, skills), hit.method, False)
    if career_service.llm_generations_today(db, user.id) >= settings.CAREER_DAILY_LLM_GENERATIONS:
        db.commit()
        return _out(profile, rules(), "rules", True)
    llm_part, method = make_llm_review(text, career_service.interview_blocklists(), ai_runtime.llm())
    if llm_part is None:
        db.commit()
        return _out(profile, rules(), "rules", False)
    _store(db, profile, method, llm_part.to_dict())
    db.commit()
    return _out(profile, combine(llm_part, text, data, skills), method, False)
