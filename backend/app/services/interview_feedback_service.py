"""The final feedback of a practice interview: get it, or make it once (M4 S3b; docs/DECISIONS.md D63, D64, D17, D53, D54, D57).

The seeker API (`POST /api/interview-sessions/{session_id}/feedback`, M4 S4.5) calls `ensure` and adds nothing to it but the `Retry-After`
header of the busy 409; nothing here changes an interview, its turns or its plan. The report is made by
`ai.interview.make_feedback` (M3) from the two sanitized views and nothing else, and is stored in `interview_sessions.feedback`.
`AI_NOTICE` is added by the response schema (`FeedbackOut`), not here.

**Who and when.** `stored` and `ensure` start with the seeker check (`SEEKER_ONLY`, 403) and find the session as the lifecycle service
does (`interview_service.load_own`: another seeker's, an expired and a deleted session are one 404). A stored report is returned before
anything else, so it stays readable after the AI consent is withdrawn (D17). Everything that makes a report is a *new generation*, rules
and provisional reports included, and needs the current global AI consent (409 `AI_CONSENT_REQUIRED`) but not a confirmed newest CV:
an old interview keeps its feedback after a new CV is uploaded. The interview must be over (`completed` or `aborted`, derived: a
`live` session past its deadline and grace is `aborted` for the reader), otherwise 409 `INTERVIEW_NOT_ENDED`. An aborted session whose
last coverage still says `listening` (stale live, or ended by the seeker mid-interview) gets the engine's own interruption note: the
view is made with the phase `aborted`, and no topic status is changed.

**What the model sees.** Only `ModelInput`s that `make_feedback` composes from `SafeText`: the views come from `plan_view_from` and
`transcript_view_from`. No CV text, no raw state, no raw turn is read, and no raw serialization is done here. The topic of a turn is
looked up in the *original* plan order (`InterviewPlan.from_dict` of the digest-checked stored plan), because `item_index` points into
that list and the validated plan may have dropped items. A plan whose original topic ids are empty or repeat has no faithful mapping
(409 `INTERVIEW_PLAN_INVALID`). A plan whose digest does not match, or that `validate_plan` still changes, is not trusted: no model, no
quota, no attempt, and a provisional rules report that is not stored.

**Transactions.** R0 reads (and ends); the model is called with no transaction open; T1 and T3 are one short transaction each.

- R0: seeker, session, stored report, consent, status, the plan, the coverage and the turns, copied to plain values; then `rollback`.
- Local work, no database: digest, views, the request. Anything that can fail locally fails here, before a reservation is taken.
- T1, one transaction, one commit: one conditional UPDATE takes the session's lease (`feedback_lease_token`, 120 seconds) and one
  model attempt, only for a session with no report, an attempt left and no valid lease; then one feedback-model reservation of the
  daily ledger. A refused reservation rolls the whole transaction back, lease and attempt included, so it takes nothing. Attempts and
  reservations are never refunded: not after a model failure, not after a crash, not after a deleted session (the ledger has no link to one).
- The model call (`make_feedback`): one request at most, no transaction, no row lock, no database access.
- T3, one compare-and-set: it stores only for the token that holds the lease and only while there is no report, so a worker whose lease
  was taken over (or whose session was deleted) changes nothing. A failed attempt below the cap releases the lease with the same token
  fence; a stale release is a no-op and never clears a newer lease. The lease fences by token, not by time: an expired lease only lets
  another request take over, and a slow worker that nobody replaced can still store.

**Fallbacks (D54, D64)**: see `ensure`. The attempt cap is the last resort: a third failed attempt stores the rules report, and a
session whose third worker died (attempts at the cap, no valid lease) gets the rules report stored by the next request, with no model call.
"""
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai.career.resources import Resources
from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.interview import (
    FeedbackReport,
    InterviewPlan,
    SafePlan,
    SafeTurn,
    feedback_request,
    make_feedback,
    plan_view_from,
    rules_feedback,
    transcript_view_from,
)
from ai.interview.types import Turn
from ai.llm.client import LLMClient
from ai.parsing.extract import PROMPT_VERSION
from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn, User
from app.models.interview import InterviewStatus, QuotaKind
from app.services import ai_runtime, career_service, interview_quota_service, interview_service
from app.services.interview_plan_service import has_nul, has_surrogate, plan_digest
from app.services.interview_time import Clock, as_utc, now_from, utcnow

log = logging.getLogger(__name__)

_S = InterviewSession.__table__
_T = InterviewTurn.__table__
FINAL_STATUSES = (InterviewStatus.COMPLETED, InterviewStatus.ABORTED)

BUSY = "INTERVIEW_FEEDBACK_BUSY"
NOT_ENDED = "INTERVIEW_NOT_ENDED"
PLAN_INVALID = "INTERVIEW_PLAN_INVALID"  # the existing code of the ingest service, reused for "no safe view" (D64)
CONSENT_REQUIRED = "AI_CONSENT_REQUIRED"

# Why a report is provisional (a code, never text)
REASON_QUOTA = "quota"
REASON_MODEL_FAILED = "model_failed"
REASON_PLAN_INVALID = "plan_invalid"
REASON_LEASE_LOST = "lease_lost"


# ── What the service returns (the route maps it to `FeedbackOut`, which adds AI_NOTICE and leaves out `prompt_version` and `attempts_used`) ──


@dataclass(frozen=True)
class FeedbackResult:
    data: dict  # `FeedbackReport.to_data()`, or the stored JSON
    final: bool  # True: stored, and never changed again. False: provisional, made for this request and not stored
    limited: bool  # a model is configured, but today's feedback-model quota stopped the attempt
    reason: str | None  # provisional only: quota, model_failed, plan_invalid or lease_lost
    method: str  # "rules" or "llm:<model>"
    prompt_version: str | None  # of a stored report
    generated_at: datetime | None  # of a stored report (aware UTC)
    attempts_used: int  # model attempts this session has used so far


@dataclass(frozen=True)
class _Source:
    """What the database held, copied to plain values so that no ORM object is touched after R0."""

    session_id: int
    seeker_id: int
    plan_data: object
    plan_sha256: str | None
    coverage: dict | None
    interrupted: bool  # aborted, and the last coverage the agent posted says it was still listening (D64)
    attempts: int
    turns: tuple[Turn, ...]


@dataclass(frozen=True)
class _Views:
    safe_plan: SafePlan
    safe_turns: tuple[SafeTurn, ...]
    trusted: bool  # digest verified, no validation issue, and the original topic order is the plan view's


@dataclass(frozen=True)
class _Kit:
    resources: Resources
    skills: SkillDictionary
    blocklists: tuple[Blocklist, ...]


@dataclass(frozen=True)
class _Latest:
    """A fresh read of the feedback columns of one session."""

    feedback: object
    method: str | None
    prompt_version: str | None
    generated_at: datetime | None
    attempts: int
    lease_until: datetime | None


@dataclass(frozen=True)
class _Claimed:
    token: str
    attempt: int  # this worker's attempt number, 1 to the cap


_LIMITED = "limited"  # T1: the day's quota refused, nothing was taken
_SPENT = "spent"  # T1: the attempts are used up and no lease is valid


# ── Errors: codes in `extra`, never any text of the interview ──


def _plan_invalid() -> AppError:
    return AppError(409, PLAN_INVALID, "면접 계획을 확인할 수 없습니다.")


def _not_found() -> AppError:
    return AppError(404, interview_service.NOT_FOUND, "모의 면접을 찾을 수 없습니다.")


def _busy(retry_after: int) -> AppError:
    return AppError(409, BUSY, "피드백을 만드는 중입니다. 잠시 후 다시 시도해 주세요.", retry_after_seconds=retry_after)


def _retry_after(lease_until: datetime | None, now: datetime) -> int:
    """Seconds until the lease that is held now ends, at least 1 and at most the lease itself."""
    if lease_until is None:
        return 1
    return max(1, min(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS, math.ceil((lease_until - now).total_seconds())))


# ── Read ──


def stored(db: Session, user: User, session_id: int, *, clock: Clock = utcnow) -> FeedbackResult | None:
    """The stored report of the seeker's own session, or None when there is none. Never generates, and does not ask for the AI
    consent: a report that was made stays readable after the consent is withdrawn (D17)."""
    interview_service.seeker_only(user)
    row, _title = interview_service.load_own(db, user.id, session_id, now_from(clock))
    return _stored_result(row.feedback, row.feedback_method, row.feedback_prompt_version, row.feedback_at, row.feedback_attempts)


def _stored_result(feedback: object, method: str | None, prompt_version: str | None, at: datetime | None, attempts: int) -> FeedbackResult | None:
    if feedback is None:
        return None
    if not isinstance(feedback, dict):  # not something this service wrote
        raise _plan_invalid()
    return FeedbackResult(dict(feedback), True, False, None, method or str(feedback.get("method", "rules")), prompt_version, as_utc(at), int(attempts or 0))


def _latest(db: Session, session_id: int, seeker_id: int, now: datetime) -> _Latest | None:
    """A fresh read (its own transaction, ended here). None: the session is gone, expired or not this seeker's."""
    found = db.execute(
        select(
            _S.c.feedback, _S.c.feedback_method, _S.c.feedback_prompt_version, _S.c.feedback_at, _S.c.feedback_attempts, _S.c.feedback_lease_until
        ).where(_S.c.id == session_id, _S.c.seeker_id == seeker_id, _S.c.expires_at > now)
    ).first()
    db.rollback()
    if found is None:
        return None
    return _Latest(found.feedback, found.feedback_method, found.feedback_prompt_version, found.feedback_at, int(found.feedback_attempts or 0), as_utc(found.feedback_lease_until))


# ── Get or create ──


def ensure(db: Session, user: User, session_id: int, *, clock: Clock = utcnow) -> FeedbackResult:
    """The feedback of the seeker's own, finished session: the stored report, or a new one. In the order of the checks:

    1. a stored report: returned, no model, no quota (readable after the consent is withdrawn);
    2. no AI consent: 409 `AI_CONSENT_REQUIRED`; the interview is not over: 409 `INTERVIEW_NOT_ENDED`;
    3. no safe view of the plan (none, unreadable, no items, a topic id that is empty or repeats): 409 `INTERVIEW_PLAN_INVALID`;
    4. a digest that does not match, or validation issues left: a provisional rules report (`plan_invalid`), no model, no quota;
    5. rules mode, or nothing for a model to work with (no answers): the rules report, stored as final, no quota;
    6. the attempts are used up (the third worker died): the rules report, stored as final, no model;
    7. a valid lease held by another request: 409 `INTERVIEW_FEEDBACK_BUSY` with `retry_after_seconds`;
    8. the day's quota is used up: a provisional rules report with `limited` (the lease and the attempt are not kept);
    9. the model is asked once: a usable report is stored (`llm:<model>`); a failure on attempt 1 or 2 gives a provisional rules report and
       frees the lease; a failure on the last attempt stores the rules report as final.
    """
    interview_service.seeker_only(user)
    seeker_id = user.id
    now = now_from(clock)
    try:
        read = _read(db, user, seeker_id, session_id, now)  # R0
    finally:
        db.rollback()  # nothing of the session is touched after this point
    if isinstance(read, FeedbackResult):
        return read
    source = read

    blocklists = tuple(career_service.interview_blocklists())
    views = _build_views(source, blocklists)
    kit = _Kit(ai_runtime.resources(), ai_runtime.skills(), blocklists)
    llm = ai_runtime.llm()  # None in rules mode

    if not views.trusted:
        return _provisional(_rules_report(views, kit), REASON_PLAN_INVALID, source.attempts)
    if llm is None or not _would_ask(views, kit):
        return _store_rules(db, source, views, kit, clock)
    if source.attempts >= settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS:
        return _store_rules(db, source, views, kit, clock)  # recovery: the last attempt never finished

    t1 = now_from(clock)
    taken = _claim(db, source.session_id, source.seeker_id, t1)  # T1
    if isinstance(taken, FeedbackResult):
        return taken
    if taken == _LIMITED:
        return _provisional(_rules_report(views, kit), REASON_QUOTA, source.attempts, limited=True)
    if taken == _SPENT:  # the attempts were used up since the read
        return _store_rules(db, source, views, kit, clock, attempts=settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS)
    return _finish(db, source, views, kit, llm, taken, clock)


def _read(db: Session, user: User, seeker_id: int, session_id: int, now: datetime) -> FeedbackResult | _Source:
    """R0: everything the generation needs from the database, as plain values; or the stored report."""
    row, _title = interview_service.load_own(db, seeker_id, session_id, now)
    done = _stored_result(row.feedback, row.feedback_method, row.feedback_prompt_version, row.feedback_at, row.feedback_attempts)
    if done is not None:
        return done
    if not interview_service.has_ai_consent(user):
        raise AppError(409, CONSENT_REQUIRED, "모의 면접 피드백을 만들려면 최신 AI 분석 동의가 필요합니다.")
    eff = interview_service.effective(row, now)
    if eff.status not in FINAL_STATUSES:
        raise AppError(409, NOT_ENDED, "아직 끝나지 않은 면접입니다.", status=eff.status)
    coverage = row.coverage if isinstance(row.coverage, dict) else None
    turns = tuple(
        Turn(r.seq, r.role, r.kind, r.item_index, r.text, analysis=r.analysis if isinstance(r.analysis, dict) else None)
        for r in db.execute(
            select(_T.c.seq, _T.c.role, _T.c.kind, _T.c.item_index, _T.c.text, _T.c.analysis).where(_T.c.session_id == row.id).order_by(_T.c.seq)
        )
    )
    interrupted = eff.status == InterviewStatus.ABORTED and coverage is not None and coverage.get("phase") == "listening"
    return _Source(row.id, seeker_id, row.plan, row.plan_sha256, coverage, interrupted, int(row.feedback_attempts or 0), turns)


# ── The views ──


def _build_views(source: _Source, blocklists: tuple[Blocklist, ...]) -> _Views:
    """The two safe views, through `plan_view_from` and `transcript_view_from` only.

    The plan is read twice, on purpose: once as stored (`InterviewPlan.from_dict`), for the digest and for the topic ids in their original
    order, which is what a turn's item index points into; once validated again by `plan_view_from`, which may drop or deduplicate items and
    so is not a mapping source. The model gets a request only when the digest matches, validation changed nothing, and the two orders are
    the same list."""
    data = source.plan_data
    if not isinstance(data, dict):
        raise _plan_invalid()
    try:
        stored_plan = InterviewPlan.from_dict(data)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _plan_invalid() from None
    order = tuple(item.topic_id for item in stored_plan.items)
    if not order or any(not isinstance(topic, str) or not topic for topic in order) or len(set(order)) != len(order):
        raise _plan_invalid()  # an empty or ambiguous mapping: no safe view of the transcript either
    try:
        digest_ok = bool(source.plan_sha256) and plan_digest(data) == source.plan_sha256
    except (TypeError, ValueError):
        digest_ok = False
    coverage = source.coverage
    if source.interrupted and coverage is not None:
        coverage = {**coverage, "phase": "aborted"}  # a copy, for the view only: the report then says the practice was interrupted
    try:
        safe_plan = plan_view_from(stored_plan, coverage, blocklists=blocklists)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _plan_invalid() from None
    safe_turns = transcript_view_from(source.turns, order)
    return _Views(safe_plan, safe_turns, digest_ok and not safe_plan.issues and safe_plan.topic_ids == order)


def _rules_report(views: _Views, kit: _Kit) -> FeedbackReport:
    return rules_feedback(views.safe_turns, views.safe_plan, resources=kit.resources, skills=kit.skills, blocklists=kit.blocklists)


def _would_ask(views: _Views, kit: _Kit) -> bool:
    """True when `make_feedback` would send a request: the exact test it applies itself (no questions, no answers or a seam that matches
    the vocabulary give None). It is asked before anything is reserved, so a reservation is never spent on a call that cannot happen."""
    return feedback_request(views.safe_turns, views.safe_plan, blocklists=kit.blocklists, skills=kit.skills) is not None


def _model_report(safe_turns: tuple[SafeTurn, ...], safe_plan: SafePlan, kit: _Kit, llm: LLMClient) -> FeedbackReport:
    """The one model call of a lease: `make_feedback` composes the request from the two views and sends it. It never raises on a model
    problem: a failed call, an invalid answer or nothing usable gives the rules report, whose method is "rules"."""
    return make_feedback(safe_turns, safe_plan, resources=kit.resources, skills=kit.skills, blocklists=kit.blocklists, llm=llm)


# ── T1: the lease, the attempt and the reservation ──


def _claim(db: Session, session_id: int, seeker_id: int, now: datetime) -> FeedbackResult | _Claimed | str:
    """T1. One transaction: the lease and the attempt, then the day's reservation; all of it or none of it.

    Returns `_Claimed`; `_LIMITED` (the quota is used up, nothing is kept); `_SPENT` (attempts used up, no valid lease); or the report that
    another request stored meanwhile. Raises 409 `INTERVIEW_FEEDBACK_BUSY` or 404."""
    token = secrets.token_hex(16)
    lease_until = now + timedelta(seconds=settings.INTERVIEW_FEEDBACK_LEASE_SECONDS)
    try:
        taken = db.execute(
            update(_S)
            .where(
                _S.c.id == session_id,
                _S.c.seeker_id == seeker_id,
                _S.c.expires_at > now,
                _S.c.feedback.is_(None),  # nobody stored a report meanwhile
                _S.c.feedback_attempts < settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS,
                or_(_S.c.feedback_lease_until.is_(None), _S.c.feedback_lease_until <= now),  # no valid lease: free, released or expired
            )
            .values(feedback_attempts=_S.c.feedback_attempts + 1, feedback_lease_until=lease_until, feedback_lease_token=token)
        ).rowcount
        if taken != 1:
            db.rollback()
            return _why_not(db, session_id, seeker_id, now)
        attempt = int(db.scalar(select(_S.c.feedback_attempts).where(_S.c.id == session_id)) or 0)  # our own row, under its lock
        if not interview_quota_service.claim(db, seeker_id, QuotaKind.FEEDBACK_MODEL, now=now):
            db.rollback()  # the lease and the attempt go with it
            return _LIMITED
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return _Claimed(token, attempt)


def _why_not(db: Session, session_id: int, seeker_id: int, now: datetime) -> FeedbackResult | str:
    """The lease was not taken: say why, from a fresh read."""
    latest = _latest(db, session_id, seeker_id, now)
    if latest is None:
        raise _not_found()
    done = _stored_result(latest.feedback, latest.method, latest.prompt_version, latest.generated_at, latest.attempts)
    if done is not None:
        return done
    if latest.lease_until is not None and latest.lease_until > now:
        raise _busy(_retry_after(latest.lease_until, now))
    if latest.attempts >= settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS:
        return _SPENT
    raise _busy(1)  # the holder let go between our statement and this read: try again


# ── The model, then T3 ──


def _finish(db: Session, source: _Source, views: _Views, kit: _Kit, llm: LLMClient, held: _Claimed, clock: Clock) -> FeedbackResult:
    """Ask the model once, with no transaction open, and settle the lease: store, or release, or find that it is no longer ours."""
    try:
        report = _model_report(views.safe_turns, views.safe_plan, kit, llm)
        data = report.to_data()
        if report.method != "rules" and (has_nul(data) or has_surrogate(data)):
            # U+0000 or a surrogate code point in what the model wrote (or in its name): PostgreSQL cannot store either, and the screens of
            # `make_feedback` do not look for them. The whole model report is dropped, never cleaned and never stored in part, and the
            # request goes on as a failed model call: the rules report, provisional, or final on the last attempt (D65, D73). The rules
            # report is made of stored values, which PostgreSQL could not have held with either in them.
            log.warning("interview feedback by the model rejected (nul_or_surrogate_character); using the rules")
            report = _rules_report(views, kit)
        used = held.attempt
        if report.method == "rules" and used < settings.INTERVIEW_FEEDBACK_MAX_ATTEMPTS:
            _release(db, source.session_id, held.token)  # attempts are left: free the lease so the seeker can ask again
            return _provisional(report, REASON_MODEL_FAILED, used)
        t3 = now_from(clock)
        won = _store(db, source.session_id, source.seeker_id, report, t3, token=held.token)  # T3 (the last attempt's rules report too)
    except BaseException:
        _release(db, source.session_id, held.token)
        raise
    if won:
        return FeedbackResult(report.to_data(), True, False, None, report.method, PROMPT_VERSION, t3, used)
    return _lost(db, source, report, used, now_from(clock))


def _lost(db: Session, source: _Source, report: FeedbackReport, used: int, now: datetime) -> FeedbackResult:
    """T3 stored nothing: the lease is another worker's now, or the session is gone. Never overwrite, never release."""
    latest = _latest(db, source.session_id, source.seeker_id, now)
    if latest is None:
        raise _not_found()
    done = _stored_result(latest.feedback, latest.method, latest.prompt_version, latest.generated_at, latest.attempts)
    return done if done is not None else _provisional(report, REASON_LEASE_LOST, used)


def _store_rules(db: Session, source: _Source, views: _Views, kit: _Kit, clock: Clock, *, attempts: int | None = None) -> FeedbackResult:
    """Store the rules report as the final one, with no lease: allowed only while no valid lease is held (rules mode, no answers, spent)."""
    report = _rules_report(views, kit)
    now = now_from(clock)
    if _store(db, source.session_id, source.seeker_id, report, now, token=None):
        return FeedbackResult(report.to_data(), True, False, None, report.method, PROMPT_VERSION, now, source.attempts if attempts is None else attempts)
    again = now_from(clock)
    latest = _latest(db, source.session_id, source.seeker_id, again)
    if latest is None:
        raise _not_found()
    done = _stored_result(latest.feedback, latest.method, latest.prompt_version, latest.generated_at, latest.attempts)
    if done is not None:
        return done  # another request stored it first: that one is the report
    raise _busy(_retry_after(latest.lease_until, again))  # a valid lease is held: wait for it (1 second when it was just freed)


def _store(db: Session, session_id: int, seeker_id: int, report: FeedbackReport, now: datetime, *, token: str | None) -> bool:
    """T3: one compare-and-set. With a token: only the holder of that lease. Without: only while no lease is valid. Either way only while
    there is no report, so a stored report is never overwritten."""
    guard = [_S.c.id == session_id, _S.c.seeker_id == seeker_id, _S.c.feedback.is_(None), _S.c.expires_at > now]
    if token is not None:
        guard.append(_S.c.feedback_lease_token == token)
    else:
        guard.append(or_(_S.c.feedback_lease_until.is_(None), _S.c.feedback_lease_until <= now))
    try:
        changed = db.execute(
            update(_S)
            .where(*guard)
            .values(
                feedback=report.to_data(),
                feedback_method=report.method,
                feedback_prompt_version=PROMPT_VERSION,
                feedback_at=now,
                feedback_lease_until=None,
                feedback_lease_token=None,
            )
        ).rowcount
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return changed == 1


def _release(db: Session, session_id: int, token: str) -> None:
    """Free the lease of this token. Fenced: a lease that another worker holds now (another token) is not touched. Best effort: if it
    fails the lease ends by itself, and the log has the error type only."""
    try:
        db.execute(
            update(_S)
            .where(_S.c.id == session_id, _S.c.feedback_lease_token == token, _S.c.feedback.is_(None))
            .values(feedback_lease_until=None, feedback_lease_token=None)
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        log.warning("interview feedback lease release failed: %s", type(error).__name__)


def _provisional(report: FeedbackReport, reason: str, attempts: int, *, limited: bool = False) -> FeedbackResult:
    return FeedbackResult(report.to_data(), False, limited, reason, report.method, None, None, attempts)
