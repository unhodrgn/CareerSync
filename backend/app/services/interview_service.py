"""The practice interview session: create, read, end, delete, and the maintenance that keeps retention
(docs/DECISIONS.md D51–D58, D61–D63, D65, D67, D69). The seeker API (`app/api/v1/interview_sessions.py`, M4 S4) calls `create_session`,
`history`, `detail`, `end` and `delete` and adds nothing to them: seeker, ownership, expiry, lifecycle and quota are decided here and not in
the router. The feedback of a session is `interview_feedback_service`, which reuses `seeker_only`, `load_own`, `effective` and
`has_ai_consent` below (its route is `POST /api/interview-sessions/{session_id}/feedback`, M4 S4.5). Nothing here ingests a turn: that is `interview_ingest_service`, which no
route calls until the Interview Agent (M5) exists.

Every function starts with the seeker check (`SEEKER_ONLY`, 403: a company user never gets as far as a query). A session is
found by `id AND seeker_id AND expires_at > now`, so another seeker's session, a deleted one and an expired one are the same
404. Time is one UTC strategy (`interview_time`); the clock is a parameter.

**Create** (`create_session`) keeps every database transaction short and calls the model outside all of them:

1. Checks that read no interview data: seeker, global AI consent, confirmed CV (`check_seeker`: it reads `cv_profiles`, not the
   CV text), an open job, then the transcript consent. Then the criteria (the job's own public text, weights turned into
   importance labels here and nowhere else).
2. `settle` (mandatory) frees a stale session, then best-effort retention purge.
3. T1, one transaction, one commit: insert the session as `planning` with a lease (`INTERVIEW_PLAN_LEASE_SECONDS`), claim one
   session reservation and, when a model is configured, one planning-model reservation. Another active session or a used-up
   session quota rolls everything back, claims included. The claims are committed here, before the CV text is read or any model
   is called, so a failure or a crash after this point never gives one back.
4. Read the stored CV (`_read_stored_cv`, the one place), end that read transaction, and make the plan
   (`interview_plan_service.build_canonical_plan`, which calls the model if a reservation was taken, with no transaction open).
5. T3, one compare-and-set: `planning -> created` only for this seeker's session that is still `planning`, whose lease has not
   run out and that has not expired. A deleted, expired or superseded reservation is not brought back (409/404), and nothing is
   refunded.

`limited` in the result means a model is configured but the day's planning-model quota stopped the attempt; the plan is then the
template. A model that fails gives the same plan with `limited` False: the attempt was made and consumed.

**Reads** (`detail`, `history`) never change a lifecycle status: they show `interview_time.derive` of the row, so a session past
its deadline is `aborted` for the reader while its row still says `created`. They may delete the seeker's own expired sessions
(`history`), which is retention maintenance and not settlement. `create_session`, `end` and the purge script settle: `settle`
makes the row say what `derive` says, and never touches the quota.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ai.interview import InterviewPlan, PlanCriterion, plan_view_from
from ai.parsing.extract import PROMPT_VERSION
from app.core.config import settings
from app.core.errors import AppError
from app.models import CvDocument, InterviewQuota, InterviewSession, InterviewTurn, JobPosting, User
from app.models.interview import InterviewStatus, QuotaKind
from app.models.job import JobStatus
from app.services import (
    ai_runtime,
    career_service,
    criteria_service,
    interview_consent_service,
    interview_quota_service,
    recommendation_service,
)
from app.services.interview_plan_service import PlanRefused, build_canonical_plan, limits_data, limits_from_settings
from app.services.interview_time import Clock, as_utc, derive, now_from, utcnow

log = logging.getLogger(__name__)

_S = InterviewSession.__table__
_T = InterviewTurn.__table__
_ACTIVE = InterviewStatus.ACTIVE

NOT_FOUND = "INTERVIEW_NOT_FOUND"
CONSENT_WITHDRAWN = "consent_withdrawn"  # the end reason of a session that ended because the seeker withdrew the AI consent (D81)
CONSENT_REQUIRED = "AI_CONSENT_REQUIRED"


def consent_required_error() -> AppError:
    """A practice interview without the current AI consent (D17, D65 (5), D81): one error for every place that refuses it by name, the join
    route (M5 S4) and a session whose planning a withdrawal ended. Its code is the one of the other AI features."""
    return AppError(409, CONSENT_REQUIRED, "모의 면접을 하려면 최신 AI 분석 동의가 필요합니다.")


# ── What the service returns (the router returns these, and the response models of `app/schemas/interview.py` shape them) ──


@dataclass(frozen=True)
class TopicView:
    topic_id: str
    kind: str
    criterion_name: str | None
    importance: str | None
    depth: int | None
    status: str  # the engine's: not_asked, asked, demonstrated, partial, not_shown, skipped


@dataclass(frozen=True)
class TurnView:
    seq: int
    role: str
    kind: str
    text: str  # masked


@dataclass(frozen=True)
class SessionView:
    id: int
    job_id: int
    job_title: str
    status: str
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
    feedback_status: str  # "none" or "ready"
    topics: tuple[TopicView, ...]
    turns: tuple[TurnView, ...]


@dataclass(frozen=True)
class SessionSummary:
    id: int
    job_id: int
    job_title: str
    status: str
    end_reason: str | None
    created_at: datetime
    ended_at: datetime | None
    active_until: datetime | None
    expires_at: datetime
    joinable: bool
    feedback_status: str


@dataclass(frozen=True)
class HistoryPage:
    items: tuple[SessionSummary, ...]
    next_before_id: int | None  # pass it as `before_id` for the next page; None at the end
    active: SessionSummary | None  # the seeker's one planning, created or live session now; independent of job_id, limit and before_id


@dataclass(frozen=True)
class CreatedSession:
    view: SessionView
    limited: bool  # a model is configured, but the day's planning-model quota stopped the attempt


@dataclass(frozen=True)
class MaintenanceReport:
    settled: int
    purged_sessions: int
    purged_quota_rows: int
    dry_run: bool


# ── Checks ──


def _seeker_only(user: User) -> None:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")


def _open_job(db: Session, job_id: int) -> JobPosting:
    """Published and not past its deadline. (`job_service.get_visible_job` also shows expired jobs to a logged-in user.)"""
    job = db.get(JobPosting, job_id)
    if job is None or job.status != JobStatus.PUBLISHED or (job.deadline is not None and job.deadline < date.today()):
        raise AppError(404, "JOB_NOT_FOUND", "채용공고를 찾을 수 없습니다.")
    return job


def _plan_criteria(db: Session, job_id: int) -> list[PlanCriterion]:
    """The job's usable criteria with their importance label. A weight is read here to make the label and goes no further."""
    scoring = criteria_service.load_for_scoring(db, job_id)
    out = [
        PlanCriterion(c.id, c.name, c.category, c.description, criteria_service.importance_level(c.weight), index)  # type: ignore[arg-type]
        for index, c in enumerate(scoring.items)
    ]
    if not out:
        raise AppError(422, "INTERVIEW_NOT_AVAILABLE", "이 공고로는 모의 면접을 준비할 수 없습니다.")
    return out


# ── Create ──


def create_session(
    db: Session,
    user: User,
    job_id: int,
    *,
    consent_transcript: object,
    consent_version: object,
    depth: int = 2,
    clock: Clock = utcnow,
) -> CreatedSession:
    if type(depth) is not int or depth not in (1, 2, 3):
        raise ValueError("depth must be 1, 2, or 3")
    _seeker_only(user)
    profile = recommendation_service.check_seeker(db, user)
    job = _open_job(db, job_id)
    interview_consent_service.require(consent_transcript, consent_version)  # nothing of the interview is read before this
    criteria = _plan_criteria(db, job.id)
    seeker_id, profile_id, cv_document_id = user.id, profile.id, profile.cv_document_id
    job_pk, job_title, job_text = job.id, job.title, job.description

    now = now_from(clock)
    settle(db, seeker_id, now)  # a stale session must not keep the seeker from starting a new one
    _best_effort(db, lambda: purge_expired(db, now=now, seeker_id=seeker_id, batch=settings.INTERVIEW_LAZY_PURGE_BATCH))
    _best_effort(db, lambda: purge_expired(db, now=now, seeker_id=None, batch=settings.INTERVIEW_LAZY_PURGE_BATCH))

    llm = ai_runtime.llm()  # None in rules mode
    session_id, plan_claimed = _reserve(db, seeker_id, job_pk, profile_id, llm is not None, now)  # T1, committed
    limited = llm is not None and not plan_claimed

    stored_cv = _read_stored_cv(db, cv_document_id)
    db.commit()  # the read ends here: no transaction is open while the model is called
    try:
        sealed = build_canonical_plan(
            stored_cv=stored_cv,
            job_title=job_title,
            job_text=job_text,
            criteria=criteria,
            blocklists=career_service.interview_blocklists(),
            embedder=ai_runtime.embedder(),
            skills=ai_runtime.skills(),
            limits=limits_from_settings(),
            llm=llm if plan_claimed else None,
            depth=depth,
        )
    except PlanRefused as refused:
        _abort_planning(db, session_id, "plan_unavailable", clock)
        raise AppError(422, "INTERVIEW_NOT_AVAILABLE", "이 공고로는 모의 면접을 준비할 수 없습니다.") from refused
    except Exception:
        _abort_planning(db, session_id, "internal_error", clock, best_effort=True)
        raise

    t3 = now_from(clock)
    changed = db.execute(
        sql_update(_S)
        .where(
            _S.c.id == session_id,
            _S.c.seeker_id == seeker_id,
            _S.c.status == InterviewStatus.PLANNING,  # still this reservation: not deleted, not settled by a later create
            _S.c.active_until >= t3,  # its lease has not run out
            _S.c.expires_at > t3,
        )
        .values(
            status=InterviewStatus.CREATED,
            plan=sealed.data,
            plan_method=sealed.method,
            plan_sha256=sealed.sha256,
            active_until=t3 + timedelta(seconds=settings.INTERVIEW_JOIN_SECONDS),
        )
    ).rowcount
    db.commit()
    if changed != 1:  # nothing is brought back, and nothing is refunded
        found = db.execute(select(_S.c.status, _S.c.end_reason).where(_S.c.id == session_id, _S.c.seeker_id == seeker_id)).first()
        if found is None:
            raise AppError(404, NOT_FOUND, "모의 면접을 찾을 수 없습니다.")
        if found.status == InterviewStatus.ABORTED and found.end_reason == CONSENT_WITHDRAWN:
            db.refresh(user)  # another request withdrew the consent: read what the seeker has now
            if not has_ai_consent(user):  # a seeker who consented again is told to start again, as for any lost reservation
                raise consent_required_error()
        raise AppError(409, "INTERVIEW_PLANNING_EXPIRED", "면접 준비 시간이 지났습니다. 다시 시작해 주세요.", session_id=session_id)
    row, title = _load_own(db, seeker_id, session_id, t3)
    return CreatedSession(_view(db, row, title, t3), limited)


def _reserve(db: Session, seeker_id: int, job_id: int, cv_profile_id: int, model_configured: bool, now: datetime) -> tuple[int, bool]:
    """T1: the planning session and its reservations, in one transaction. (session id, whether a planning-model attempt was
    reserved.) A refusal rolls the whole transaction back, so it takes nothing."""
    row = InterviewSession(
        seeker_id=seeker_id,
        job_id=job_id,
        cv_profile_id=cv_profile_id,
        status=InterviewStatus.PLANNING,
        prompt_version=PROMPT_VERSION,
        limits=limits_data(limits_from_settings()),
        consent_version=settings.INTERVIEW_CONSENT_VERSION,
        consent_at=now,
        created_at=now,
        active_until=now + timedelta(seconds=settings.INTERVIEW_PLAN_LEASE_SECONDS),
        expires_at=now + timedelta(days=settings.INTERVIEW_RETENTION_DAYS),
    )
    try:
        db.add(row)
        db.flush()
    except IntegrityError:
        db.rollback()
        active = db.execute(
            select(_S.c.id, _S.c.status).where(_S.c.seeker_id == seeker_id, _S.c.status.in_(_ACTIVE))
        ).first()
        if active is None:  # not the one-active-session index: nothing to explain, so nothing to hide
            raise
        raise AppError(409, "INTERVIEW_SESSION_ACTIVE", "진행 중인 모의 면접이 있습니다.", session_id=active.id, status=active.status) from None
    session_id = row.id
    if not interview_quota_service.claim(db, seeker_id, QuotaKind.SESSION, now=now):
        db.rollback()
        raise AppError(
            429,
            "INTERVIEW_DAILY_LIMIT",
            "오늘 만들 수 있는 모의 면접 횟수를 모두 사용했습니다.",
            quota="sessions",
            limit=interview_quota_service.limit_for(QuotaKind.SESSION),
            resets_at=_resets_at(now),
        )
    plan_claimed = model_configured and interview_quota_service.claim(db, seeker_id, QuotaKind.PLAN_MODEL, now=now)
    db.commit()
    return session_id, plan_claimed


def _read_stored_cv(db: Session, cv_document_id: int) -> str:
    """The one place the stored masked CV text is read. It is handed to `build_canonical_plan` and to nothing else."""
    document = db.get(CvDocument, cv_document_id)
    return document.masked_text if document is not None else ""


def _abort_planning(db: Session, session_id: int, reason: str, clock: Clock, *, best_effort: bool = False) -> None:
    """Close a planning reservation that cannot finish. Quota is not refunded. A reservation already settled or deleted is left."""
    try:
        t = now_from(clock)
        db.execute(
            sql_update(_S)
            .where(_S.c.id == session_id, _S.c.status == InterviewStatus.PLANNING)
            .values(status=InterviewStatus.ABORTED, end_reason=reason, ended_at=t, active_until=None)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if not best_effort:
            raise
        log.warning("interview planning abort failed for a session: the lease will end it")


def _resets_at(now: datetime) -> str:
    local = now.astimezone(interview_quota_service.KST)
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


# ── Read ──


def detail(db: Session, user: User, session_id: int, *, clock: Clock = utcnow) -> SessionView:
    _seeker_only(user)
    now = now_from(clock)
    row, title = _load_own(db, user.id, session_id, now)
    return _view(db, row, title, now)


def history(
    db: Session,
    user: User,
    *,
    job_id: int | None = None,
    limit: int | None = None,
    before_id: int | None = None,
    clock: Clock = utcnow,
) -> HistoryPage:
    """The seeker's sessions, newest first, with the status they have now. `job_id` narrows it to one job (the job need not
    be open any more). `active` is the seeker's one planning, created or live session as it is at the same `now`, whatever `job_id`,
    `limit` and `before_id` say (`_active_summary`). Nothing is settled; the seeker's own expired sessions are deleted first, best effort."""
    _seeker_only(user)
    now = now_from(clock)
    _best_effort(db, lambda: purge_expired(db, now=now, seeker_id=user.id, batch=settings.INTERVIEW_LAZY_PURGE_BATCH))
    size = settings.INTERVIEW_HISTORY_DEFAULT_LIMIT if limit is None else min(max(int(limit), 1), settings.INTERVIEW_HISTORY_MAX_LIMIT)
    query = (
        select(InterviewSession, JobPosting.title)
        .join(JobPosting, JobPosting.id == InterviewSession.job_id)
        .where(InterviewSession.seeker_id == user.id, InterviewSession.expires_at > now)
        .order_by(InterviewSession.id.desc())
        .limit(size)
        .execution_options(populate_existing=True)
    )
    if job_id is not None:
        query = query.where(InterviewSession.job_id == job_id)
    if before_id is not None:
        query = query.where(InterviewSession.id < before_id)
    rows = db.execute(query).all()
    items = tuple(_summary(row, title, now) for row, title in rows)
    return HistoryPage(items, items[-1].id if len(items) == size else None, _active_summary(db, user.id, now))


def _active_summary(db: Session, seeker_id: int, now: datetime) -> SessionSummary | None:
    """The seeker's one session whose derived status is planning, created or live, or None. Read-only: a row past its deadline is still
    stored as active until something settles it, but `derive` reads it as `aborted`, so it is not active here, and nothing is written. The
    partial unique index allows one stored-active row per seeker at most, so there is nothing to filter or page."""
    rows = db.execute(
        select(InterviewSession, JobPosting.title)
        .join(JobPosting, JobPosting.id == InterviewSession.job_id)
        .where(InterviewSession.seeker_id == seeker_id, InterviewSession.status.in_(_ACTIVE), InterviewSession.expires_at > now)
        .order_by(InterviewSession.id.desc())
        .execution_options(populate_existing=True)
    ).all()
    for row, title in rows:
        summary = _summary(row, title, now)
        if summary.status in _ACTIVE:
            return summary
    return None


def _load_own(db: Session, seeker_id: int, session_id: int, now: datetime) -> tuple[InterviewSession, str]:
    found = db.execute(
        select(InterviewSession, JobPosting.title)
        .join(JobPosting, JobPosting.id == InterviewSession.job_id)
        .where(InterviewSession.id == session_id, InterviewSession.seeker_id == seeker_id, InterviewSession.expires_at > now)
        .execution_options(populate_existing=True)
    ).first()
    if found is None:
        raise AppError(404, NOT_FOUND, "모의 면접을 찾을 수 없습니다.")
    return found[0], found[1]


def _effective(row: InterviewSession, now: datetime):
    return derive(row.status, row.end_reason, row.ended_at, row.active_until, now, settings.INTERVIEW_END_GRACE_SECONDS)


# The checks of this module under public names, for the feedback service (M4 S3b): one definition of "the seeker's own, unexpired
# session" and of the effective status, so a second service cannot drift from them. Nothing else of this module is shared.
seeker_only = _seeker_only
load_own = _load_own
effective = _effective


def has_ai_consent(user: User) -> bool:
    """Current global AI consent (D17): the predicate of `recommendation_service.check_seeker`, without its confirmed-CV gate."""
    return recommendation_service._has_ai_consent(user)


def _summary(row: InterviewSession, title: str, now: datetime) -> SessionSummary:
    eff = _effective(row, now)
    return SessionSummary(
        row.id, row.job_id, title, eff.status, eff.end_reason, as_utc(row.created_at), eff.ended_at, eff.active_until,  # type: ignore[arg-type]
        as_utc(row.expires_at), eff.joinable, "ready" if row.feedback is not None else "none",
    )


def _view(db: Session, row: InterviewSession, title: str, now: datetime) -> SessionView:
    eff = _effective(row, now)
    turns = tuple(
        TurnView(t.seq, t.role, t.kind, t.text)
        for t in db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == row.id).order_by(InterviewTurn.seq).execution_options(populate_existing=True))
    )
    limits = row.limits if isinstance(row.limits, dict) else {}
    topics, depth = _plan_details(row)
    return SessionView(
        id=row.id,
        job_id=row.job_id,
        job_title=title,
        status=eff.status,
        end_reason=eff.end_reason,
        plan_method=row.plan_method,
        depth=depth,
        max_seconds=limits.get("max_seconds"),
        created_at=as_utc(row.created_at),  # type: ignore[arg-type]
        started_at=as_utc(row.started_at),
        ended_at=eff.ended_at,
        active_until=eff.active_until,
        expires_at=as_utc(row.expires_at),  # type: ignore[arg-type]
        joinable=eff.joinable,
        accepting_turns=eff.accepting_turns,
        end_grace_open=eff.end_grace_open,
        feedback_status="ready" if row.feedback is not None else "none",
        topics=topics,
        turns=turns,
    )


def _plan_details(row: InterviewSession) -> tuple[tuple[TopicView, ...], int | None]:
    """The topics with the engine's statuses and requested depth, from the stored plan and coverage (`plan_view_from`: the plan is
    validated again and every text leaves as SafeText). A plan that cannot be read shows no topics and no depth; the log has a code,
    never the content."""
    if not row.plan:
        return (), None
    try:
        plan = InterviewPlan.from_dict(row.plan)
        view = plan_view_from(plan, row.coverage if isinstance(row.coverage, dict) else None, blocklists=career_service.interview_blocklists())
    except (KeyError, TypeError, ValueError, AttributeError):
        log.warning("interview plan of a session cannot be read: stored data invalid")
        return (), None
    topics = tuple(
        TopicView(item.topic_id, item.kind, item.criterion_name.value or None, item.importance, item.depth, item.status)
        for item in view.items
    )
    return topics, view.depth


# ── End and delete ──


def end(db: Session, user: User, session_id: int, *, clock: Clock = utcnow) -> SessionView:
    """The seeker ends the session: `aborted`, reason `seeker_ended`. Idempotent: an ended or stale session is returned as it is
    (a stale one keeps its own reason). A session that is still being planned cannot be ended (409)."""
    _seeker_only(user)
    now = now_from(clock)
    settle(db, user.id, now)
    row, title = _load_own(db, user.id, session_id, now)
    if row.status == InterviewStatus.PLANNING:
        raise AppError(409, "INTERVIEW_PLANNING", "면접을 준비하는 중입니다. 잠시 후 다시 시도해 주세요.")
    if row.status in (InterviewStatus.CREATED, InterviewStatus.LIVE):
        grace = timedelta(seconds=settings.INTERVIEW_END_GRACE_SECONDS)
        db.execute(
            sql_update(_S)
            .where(
                _S.c.id == session_id,
                _S.c.seeker_id == user.id,
                or_(
                    (_S.c.status == InterviewStatus.CREATED) & (_S.c.active_until >= now),
                    (_S.c.status == InterviewStatus.LIVE) & (_S.c.active_until >= now - grace),
                ),
            )
            .values(status=InterviewStatus.ABORTED, end_reason="seeker_ended", ended_at=now, active_until=None)
        )
        db.commit()
        row, title = _load_own(db, user.id, session_id, now)  # whoever changed it first decided; return what it is now
    return _view(db, row, title, now)


def delete(db: Session, user: User, session_id: int, *, clock: Clock = utcnow) -> None:
    """Delete the session and its turns, in any status. The quota is not touched."""
    _seeker_only(user)
    now = now_from(clock)
    _best_effort(db, lambda: purge_expired(db, now=now, seeker_id=user.id, batch=settings.INTERVIEW_LAZY_PURGE_BATCH))
    _load_own(db, user.id, session_id, now)
    db.execute(sql_delete(_T).where(_T.c.session_id == session_id))
    removed = db.execute(sql_delete(_S).where(_S.c.id == session_id, _S.c.seeker_id == user.id)).rowcount
    db.commit()
    if removed != 1:
        raise AppError(404, NOT_FOUND, "모의 면접을 찾을 수 없습니다.")


def abort_for_consent_withdrawal(db: Session, seeker_id: int, now: datetime) -> int:
    """The seeker withdrew the global AI consent (D17, D65 (5), D81): every planning, created or live session of theirs that is still inside
    its time becomes `aborted` with the reason `consent_withdrawn`, `ended_at` now. The number of sessions ended.

    The rules are those of the seeker's own End: a session past its deadline (a live one: past the end grace) is not claimed here and keeps
    the reason that `settle` gives it; a completed or an aborted session is not touched; another seeker's sessions never are. The ingestion
    then refuses every further turn of an ended session by its existing status check, and the planning of a session that was ended while its
    model call ran cannot seal it (the compare-and-set of `create_session` needs `planning`). The quota is not touched and no model is called.

    It does NOT commit: `consent_service.withdraw_ai` commits it with the withdrawal itself, so a seeker never has a withdrawn consent and a
    session that goes on, or the other way round. It is the one place outside the interview services that this module is used from, and the
    architecture guard names that use."""
    grace = timedelta(seconds=settings.INTERVIEW_END_GRACE_SECONDS)
    return db.execute(
        sql_update(_S)
        .where(
            _S.c.seeker_id == seeker_id,
            or_(
                _S.c.status.in_((InterviewStatus.PLANNING, InterviewStatus.CREATED)) & (_S.c.active_until >= now),
                (_S.c.status == InterviewStatus.LIVE) & (_S.c.active_until >= now - grace),
            ),
        )
        .values(status=InterviewStatus.ABORTED, end_reason=CONSENT_WITHDRAWN, ended_at=now, active_until=None)
    ).rowcount


# ── Settlement and retention ──


def _stale_rules(now: datetime):
    """(status, reason, the cutoff `active_until` must be before) for each status that can go stale. The same thresholds as
    `interview_time.derive`."""
    grace = timedelta(seconds=settings.INTERVIEW_END_GRACE_SECONDS)
    return (
        (InterviewStatus.PLANNING, "planning_lost", now),
        (InterviewStatus.CREATED, "not_joined", now),
        (InterviewStatus.LIVE, "stale_live", now - grace),
    )


def settle(db: Session, seeker_id: int | None, now: datetime) -> int:
    """Make the rows past their deadline say `aborted`, with the deadline as `ended_at`: one seeker's, or everyone's (the purge
    script) when `seeker_id` is None. Idempotent, one transaction, and it never touches the quota ledger."""
    total = 0
    for status, reason, cutoff in _stale_rules(now):
        statement = (
            sql_update(_S)
            .where(_S.c.status == status, or_(_S.c.active_until.is_(None), _S.c.active_until < cutoff))
            .values(status=InterviewStatus.ABORTED, end_reason=reason, ended_at=func.coalesce(_S.c.active_until, now), active_until=None)
        )
        if seeker_id is not None:
            statement = statement.where(_S.c.seeker_id == seeker_id)
        total += db.execute(statement).rowcount
    db.commit()
    return total


def purge_expired(db: Session, *, now: datetime, seeker_id: int | None, batch: int) -> int:
    """Delete up to `batch` sessions with `expires_at <= now` and their turns (the seeker's own, or anyone's). Count back."""
    query = select(_S.c.id).where(_S.c.expires_at <= now).order_by(_S.c.id).limit(batch)
    if seeker_id is not None:
        query = query.where(_S.c.seeker_id == seeker_id)
    ids = list(db.scalars(query))
    if not ids:
        return 0
    db.execute(sql_delete(_T).where(_T.c.session_id.in_(ids)))
    db.execute(sql_delete(_S).where(_S.c.id.in_(ids)))
    db.commit()
    return len(ids)


def purge_old_quota(db: Session, *, now: datetime, dry_run: bool = False) -> int:
    """Delete the quota rows of days before today (KST). A row of today is never touched: that is the reservation."""
    today = interview_quota_service.kst_day(now)
    quota = InterviewQuota.__table__
    if dry_run:
        return db.scalar(select(func.count()).select_from(quota).where(quota.c.kst_day < today)) or 0
    removed = db.execute(sql_delete(quota).where(quota.c.kst_day < today)).rowcount
    db.commit()
    return removed


def maintenance(db: Session, *, clock: Clock = utcnow, batch: int = 500, dry_run: bool = False) -> MaintenanceReport:
    """What `scripts/purge_interviews.py` runs: settle every stale session, delete every expired one, delete the quota rows of
    past days. A scheduler has to run it; nothing in the app does. `dry_run` only counts."""
    now = now_from(clock)
    if dry_run:
        settled = 0
        for status, _reason, cutoff in _stale_rules(now):
            settled += db.scalar(select(func.count()).select_from(_S).where(_S.c.status == status, or_(_S.c.active_until.is_(None), _S.c.active_until < cutoff))) or 0
        purged = db.scalar(select(func.count()).select_from(_S).where(_S.c.expires_at <= now)) or 0
        report = MaintenanceReport(settled, purged, purge_old_quota(db, now=now, dry_run=True), True)
        db.rollback()
    else:
        settled = settle(db, None, now)
        purged = 0
        while count := purge_expired(db, now=now, seeker_id=None, batch=batch):
            purged += count
        report = MaintenanceReport(settled, purged, purge_old_quota(db, now=now), False)
    log.info(
        "interview maintenance: settled=%d purged_sessions=%d purged_quota_rows=%d dry_run=%s",
        report.settled, report.purged_sessions, report.purged_quota_rows, report.dry_run,
    )
    return report


def _best_effort(db: Session, work) -> int:
    """Retention maintenance on a request: a database failure never fails the request, and the log has the error type only."""
    try:
        return work()
    except SQLAlchemyError as error:
        db.rollback()
        log.warning("interview retention maintenance failed: %s", type(error).__name__)
        return 0
