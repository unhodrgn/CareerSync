"""Practice interview, seeker API (M4 S4; docs/DECISIONS.md D58, D65, D67).

Stage S4.1 registered the consent text and stage S4.2 the creation of a session; stage S4.3 adds the history, and stage S4.4 the routes of one
session (the detail, the end and the delete), and stage S4.5 the feedback. Each further route is added in the stage where its service
integration is implemented; no placeholder and no 501 route is registered (a test lists the routes of the stage). The router parses the
request, calls one service function and returns its result: seeker-only, ownership, consent, quota and lifecycle are the services' business,
not repeated here. A wrong method on a path that has more than one route is a 405 whose `Allow` lists them all: the route class of this router
(`app/core/allowed_methods.py`). The feedback route adds one thing to the service's answer: the `Retry-After` header of the busy 409 (D67 (6)),
made with the application's own AppError handler, so the body is the handler's."""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.core.allowed_methods import all_methods_route_class
from app.core.deps import CurrentUser, DbSession, get_current_user
from app.core.errors import AppError
from app.schemas.interview import ConsentTextOut, CreatedSessionOut, FeedbackOut, HistoryPageOut, InterviewCreateIn, JoinOut, SessionOut
from app.services import interview_consent_service, interview_feedback_service, interview_join_service, interview_service
from app.services.interview_time import Clock, utcnow

router = APIRouter(tags=["interview"], route_class=all_methods_route_class())


def get_clock() -> Clock:
    """The clock the services use for this request: the real one. A test replaces it (`app.dependency_overrides[get_clock]`), so that no
    API test depends on the real date."""
    return utcnow


ClockDep = Annotated[Clock, Depends(get_clock)]

# The id columns are 32-bit integers (`Integer`, migrations 0001 and 0012), so an id outside this range cannot name a row: it is a 422 here and
# not an empty page, and it keeps a value that SQLite cannot bind (a driver error, so a 500) away from the database. `limit` has no bound.
IdQuery = Annotated[int | None, Query(ge=-(2**31), le=2**31 - 1)]

# The same range for the id of a session in the path, for every route of one session: outside it, or not an integer, is a 422 and no service is
# called; inside it, an id that names no session of the seeker is the service's 404.
SessionIdPath = Annotated[int, Path(ge=-(2**31), le=2**31 - 1)]


@router.get(
    "/interview-consent",
    response_model=ConsentTextOut,
    dependencies=[Depends(get_current_user)],
    summary="Text and version of the consent to store a practice-interview transcript (any logged-in user; static, no personal data)",
)
def interview_consent():
    return interview_consent_service.current()


@router.post(
    "/jobs/{job_id}/interview-sessions",
    response_model=CreatedSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a practice-interview session for an open job (seeker): the plan is made inside the request; uses the daily quota",
)
def create_interview_session(job_id: int, body: InterviewCreateIn, db: DbSession, user: CurrentUser, clock: ClockDep):
    created = interview_service.create_session(
        db,
        user,
        job_id,
        consent_transcript=body.consent_transcript,
        consent_version=body.consent_version,
        depth=body.depth,
        clock=clock,
    )
    return {"session": created.view, "limited": created.limited}


@router.get(
    "/interview-sessions",
    response_model=HistoryPageOut,
    summary="The seeker's practice-interview history, newest first, and the one active session (seeker; read-only)",
)
def interview_history(
    db: DbSession, user: CurrentUser, clock: ClockDep, job_id: IdQuery = None, limit: int | None = None, before_id: IdQuery = None
):
    return interview_service.history(db, user, job_id=job_id, limit=limit, before_id=before_id, clock=clock)


@router.get(
    "/interview-sessions/{session_id}",
    response_model=SessionOut,
    summary="One of the seeker's practice-interview sessions, with its topics and masked transcript (seeker; read-only)",
)
def interview_session(session_id: SessionIdPath, db: DbSession, user: CurrentUser, clock: ClockDep):
    return interview_service.detail(db, user, session_id, clock=clock)


@router.post(
    "/interview-sessions/{session_id}/end",
    response_model=SessionOut,
    summary="The seeker ends a practice-interview session: aborted, reason seeker_ended; idempotent; no closing line is written (seeker)",
)
def end_interview_session(session_id: SessionIdPath, db: DbSession, user: CurrentUser, clock: ClockDep):
    return interview_service.end(db, user, session_id, clock=clock)


@router.delete(
    "/interview-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a practice-interview session with its turns and feedback, in any status; final; no quota is refunded (seeker)",
)
def delete_interview_session(session_id: SessionIdPath, db: DbSession, user: CurrentUser, clock: ClockDep):
    interview_service.delete(db, user, session_id, clock=clock)


@router.post(
    "/interview-sessions/{session_id}/join",
    response_model=JoinOut,
    summary="A microphone-only LiveKit token for the room of a created session, which dispatches the Interview Agent; needs the current AI consent (seeker)",
)
def join_interview_session(session_id: SessionIdPath, db: DbSession, user: CurrentUser, clock: ClockDep):
    return interview_join_service.issue(db, user, session_id, clock=clock)


@router.post(
    "/interview-sessions/{session_id}/feedback",
    response_model=FeedbackOut,
    summary="The feedback of a finished practice interview: the stored report, or a new one; 200 for a final and a provisional report alike (seeker)",
)
def interview_feedback(session_id: SessionIdPath, request: Request, db: DbSession, user: CurrentUser, clock: ClockDep):
    try:
        result = interview_feedback_service.ensure(db, user, session_id, clock=clock)
    except AppError as error:
        if error.code != interview_feedback_service.BUSY:
            raise  # every other error is the application handler's, as everywhere
        response = request.app.exception_handlers[AppError](request, error)  # the handler's own status and body
        response.headers["Retry-After"] = str(error.extra["retry_after_seconds"])  # D67 (6): the same number as the body's
        return response
    return {"report": result.data, "final": result.final, "limited": result.limited, "reason": result.reason, "generated_at": result.generated_at}
