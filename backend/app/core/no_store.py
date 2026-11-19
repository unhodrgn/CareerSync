"""`Cache-Control: no-store` on every response of the practice-interview API (M4 S4.1; docs/DECISIONS.md D67).

The responses of this API carry a masked transcript, a feedback report and the seeker's own history, so no browser or proxy may keep
them, whatever the response is: a success, an authentication or authorization failure, a business error, a validation error, a 404, a 405,
a redirect, a 429 or an unexpected error. Setting the header in the routers would cover the successes only, and a middleware alone would
miss one response, so there are two parts, installed together by `install(app)`:

1. `NoStoreMiddleware`, a pure ASGI middleware. It wraps `send` and sets the header on `http.response.start` of an HTTP request whose path
   is one of the interview paths. Every response made inside the application stack passes through it: the routes, the dependencies
   (`get_current_user` raises a 401), the `AppError` handler, FastAPI's validation handler, the router's 404, 405 and trailing-slash
   redirect. A response that has already started when an error occurs has the header too, because its first message passed through.
2. A handler for unexpected errors. An exception that nothing handles is turned into the 500 response by Starlette's
   `ServerErrorMiddleware`, which is outside every user middleware and writes with its own `send`, so the middleware above never sees that
   response. The handler returns what the application would have returned without it and adds the header on the interview paths:
   - the handler that the framework would have used, if the application has one. `build_middleware_stack` keeps the last entry of
     `app.exception_handlers` whose key is `500` or `Exception`, and so does `install`; a synchronous handler is run in the thread pool,
     as Starlette runs it, and not on the event loop;
   - otherwise Starlette's own default response (`ServerErrorMiddleware.error_response`: the text `Internal Server Error`, status 500).
   Outside the interview paths the response is untouched. The handler logs nothing and swallows nothing: Starlette re-raises after it, so
   the server logs the error as it always did.

Nothing else is outside the middleware. The layers in front of it in FastAPI's stack are `ServerErrorMiddleware` (the 500, above) and an
exception-telemetry layer that only observes and re-raises; a test walks the real stack and fails if a library upgrade adds another one, or
if a middleware is added after this one (the last added is the outermost). Debug mode would show a traceback page before any handler, so a
test asserts that the application is not in debug mode.
"""
import functools
import inspect
import re

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "Cache-Control"
NO_STORE = "no-store"

# The interview API: the consent text, the sessions and what hangs off them, and the create route under a job. The D21 route
# `/api/jobs/{id}/interview-questions` is another feature and is not matched. A route that is outside this pattern is not covered,
# which a test checks for every route of the interview router.
INTERVIEW_PATH = re.compile(r"^/api/(?:interview-consent|interview-sessions|jobs/[^/]+/interview-sessions)(?:/|\Z)")


def route_path(scope: Scope) -> str:
    """The path the router matches: `scope["path"]` without the `root_path` prefix, as Starlette's router reads it."""
    path = scope.get("path", "")
    root = scope.get("root_path", "")
    if not root or not path.startswith(root):
        return path
    if path == root:
        return ""
    return path[len(root) :] if path[len(root)] == "/" else path


def is_interview_path(scope: Scope) -> bool:
    return INTERVIEW_PATH.match(route_path(scope)) is not None


class NoStoreMiddleware:
    """Sets `Cache-Control: no-store` on every response to a request for an interview path, replacing a value that was already there."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_interview_path(scope):
            await self.app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[HEADER] = NO_STORE
            await send(message)

        await self.app(scope, receive, send_no_store)


def _is_async(handler) -> bool:
    """Whether Starlette would await the handler: a coroutine function, a partial of one, or an object with an async `__call__`."""
    while isinstance(handler, functools.partial):
        handler = handler.func
    return inspect.iscoroutinefunction(handler) or (callable(handler) and inspect.iscoroutinefunction(handler.__call__))


async def call_handler(handler, request: Request, exc: Exception) -> Response:
    """Call an exception handler as Starlette does: await an async one, run a synchronous one in the thread pool and not on the event loop."""
    if _is_async(handler):
        return await handler(request, exc)
    return await run_in_threadpool(handler, request, exc)


def _effective_error_handler(app: Starlette):
    """The generic error handler the framework would use: the last entry whose key is `500` or `Exception` (the loop of
    `build_middleware_stack`, which gives neither key priority). None when the application has none."""
    found = None
    for key, handler in app.exception_handlers.items():
        if key in (500, Exception):
            found = handler
    return found


def _make_handler(previous):
    default = ServerErrorMiddleware(app=None)  # type: ignore[arg-type]  (only `error_response` is used, and it needs no application)

    async def unexpected_error(request: Request, exc: Exception) -> Response:
        if previous is None:
            response = default.error_response(request, exc)  # Starlette's own default, whatever it is in this version
        else:
            response = await call_handler(previous, request, exc)
        if is_interview_path(request.scope):
            response.headers[HEADER] = NO_STORE
        return response

    return unexpected_error


def install(app: Starlette) -> None:
    """Add the middleware and the handler. Call it after every other handler is registered, and before the application starts.

    An existing generic handler is kept and delegated to; both keys (`500` and `Exception`) are then removed and the new handler is
    registered under `Exception`, so no key is ambiguous. Calling it twice changes nothing the second time."""
    if any(m.cls is NoStoreMiddleware for m in app.user_middleware):
        return
    previous = _effective_error_handler(app)
    app.exception_handlers.pop(500, None)
    app.exception_handlers.pop(Exception, None)
    app.add_exception_handler(Exception, _make_handler(previous))
    app.add_middleware(NoStoreMiddleware)
