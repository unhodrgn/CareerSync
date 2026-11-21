"""A validation error on an interview path carries no submitted value (M4 S4.2; docs/DECISIONS.md D68).

FastAPI answers a request that fails validation with a 422 whose errors repeat what was sent: the offending value (`input`, which for a
body that is not an object is the whole body), the context (`ctx`), and, for an unknown field, the field's own name in `loc`. An interview
request can carry a consent, and later routes carry an id, so on an interview path the response is cut down to what the client needs to
fix its request: for each error the `type`, the `loc` and the `msg`, and for an unknown field a `loc` that stops at the body (the name of
the field is the client's text). The messages of the errors that these routes can produce are fixed sentences ("Field required",
"Extra inputs are not permitted", "JSON decode error", "Input should be a valid integer, ..."); a validator that formatted the input into
its message would have to be checked here before it is added. The body is never logged: nothing here or in FastAPI logs it.

Every other path keeps the handler it had: `install` captures the existing handler for `RequestValidationError` (FastAPI's own default
unless the application registered another), and calls it, as Starlette would, for any path outside the interview paths. The response
status is 422 in both cases, and the no-store header of `no_store.py` covers the interview responses because the handler runs inside the
middleware stack.
"""
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from app.core.no_store import call_handler, is_interview_path


def sanitized_errors(errors) -> list[dict]:
    """The errors of a `RequestValidationError` without the submitted values: `type`, `loc`, `msg` only."""
    out = []
    for error in errors:
        loc = list(error.get("loc", ()))
        if error.get("type") == "extra_forbidden" and loc:
            loc = loc[:-1]  # the name of an unknown field is submitted text
        out.append({"type": error.get("type"), "loc": loc, "msg": error.get("msg")})
    return out


def _make_handler(previous):
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        if not is_interview_path(request.scope):
            return await call_handler(previous, request, exc)
        return JSONResponse(status_code=422, content={"detail": sanitized_errors(exc.errors())})

    validation_error.interview_sanitizer = True  # lets `install` and the tests recognize it
    return validation_error


def install(app: Starlette) -> None:
    """Replace the application's handler for `RequestValidationError` by one that sanitizes the interview paths and delegates for the rest.
    Calling it twice changes nothing the second time."""
    previous = app.exception_handlers.get(RequestValidationError, request_validation_exception_handler)
    if getattr(previous, "interview_sanitizer", False):
        return
    app.add_exception_handler(RequestValidationError, _make_handler(previous))
