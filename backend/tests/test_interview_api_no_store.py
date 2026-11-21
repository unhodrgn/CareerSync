"""`Cache-Control: no-store` on the interview paths, and nothing else changed (M4 S4.1; docs/DECISIONS.md D67): `app/core/no_store.py`.

These are the general mechanism tests, on throwaway FastAPI apps, so that they do not depend on which interview routes exist yet: every kind
of response on an interview path has the header; a path outside the pattern never has it; and the handler for unexpected errors changes
nothing for any other path (the response is the one the application gave before, handler or default), keeps Starlette's re-raise, runs a
synchronous handler off the event loop, and delegates to the handler the framework itself would have chosen. The routes of the real
application are checked, route by route, in test_interview_api.py and test_interview_api_contract.py."""
import asyncio
import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.core.no_store import INTERVIEW_PATH, NO_STORE, NoStoreMiddleware, install, is_interview_path

SECRET = "SECRET-MARKER-답변-내용"
INTERVIEW_URLS = [
    "/api/interview-consent",
    "/api/interview-sessions",
    "/api/interview-sessions/1",
    "/api/interview-sessions/probe/ok",
]
ELSEWHERE_URLS = ["/api/elsewhere/ok", "/api/jobs/1/interview-questions"]


# ── Throwaway applications ──


def build(*, pre=(), with_install=True) -> FastAPI:
    """An application with routes of every kind on interview paths and on other paths. `pre`: (key, handler) pairs registered before
    `install`, the application's own error handlers."""
    app = FastAPI()
    for key, handler in pre:
        app.add_exception_handler(key, handler)

    @app.exception_handler(AppError)
    def app_error(_request, exc):  # as main.py does
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, **exc.extra})

    def ok():
        return {"ok": True}

    for path in ("/api/interview-consent", "/api/interview-sessions", "/api/interview-sessions/probe/ok", "/api/elsewhere/ok"):
        app.add_api_route(path, ok, methods=["GET"])
    app.add_api_route("/api/jobs/{job_id}/interview-sessions", ok, methods=["POST"])

    @app.get("/api/interview-sessions/probe/http-error")
    def http_error():
        raise HTTPException(401, "not logged in", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/api/interview-sessions/probe/app-error")
    def raises_app_error():
        raise AppError(409, "SOME_CODE", "a business rule", detail_id=7)

    @app.get("/api/interview-sessions/probe/boom")
    def boom():
        raise RuntimeError(SECRET)

    @app.get("/api/interview-sessions/probe/header")
    def own_header():
        return Response(content="x", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/interview-sessions/probe/stream")
    def stream():
        def chunks():
            yield b"first"
            raise RuntimeError(SECRET)

        return StreamingResponse(chunks())

    @app.get("/api/interview-sessions/{session_id}")
    def one(session_id: int):
        return {"id": session_id}

    @app.get("/api/elsewhere/boom")
    def elsewhere_boom():
        raise RuntimeError(SECRET)

    @app.get("/api/jobs/{job_id}/interview-questions")  # the D21 route: another feature, not matched
    def questions(job_id: int):
        if job_id == 13:
            raise RuntimeError(SECRET)
        return {"ok": True}

    if with_install:
        install(app)
    return app


def quiet(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def cache(response) -> list[str]:
    return response.headers.get_list("cache-control")


# ── Every kind of response on an interview path has the header ──


@pytest.mark.parametrize("url", INTERVIEW_URLS)
def test_a_success_has_it(url):
    response = quiet(build()).get(url)
    assert response.status_code == 200 and cache(response) == [NO_STORE]


def test_a_post_under_a_job_has_it():
    response = quiet(build()).post("/api/jobs/5/interview-sessions")
    assert response.status_code == 200 and cache(response) == [NO_STORE]


def test_an_authentication_failure_raised_by_a_dependency_style_http_exception_has_it_and_keeps_its_own_headers():
    response = quiet(build()).get("/api/interview-sessions/probe/http-error")
    assert response.status_code == 401 and response.json() == {"detail": "not logged in"}
    assert response.headers["www-authenticate"] == "Bearer" and cache(response) == [NO_STORE]


def test_an_app_error_has_it_and_keeps_its_body():
    response = quiet(build()).get("/api/interview-sessions/probe/app-error")
    assert response.status_code == 409 and response.json() == {"code": "SOME_CODE", "message": "a business rule", "detail_id": 7}
    assert cache(response) == [NO_STORE]


def test_a_validation_error_has_it():
    response = quiet(build()).get("/api/interview-sessions/abc")
    assert response.status_code == 422 and cache(response) == [NO_STORE]


@pytest.mark.parametrize("url", ["/api/interview-consent/x", "/api/interview-sessions/probe/missing", "/api/interview-sessions/1/unknown"])
def test_a_404_on_an_interview_path_has_it(url):
    response = quiet(build()).get(url)
    assert response.status_code == 404 and cache(response) == [NO_STORE]


def test_a_405_has_it():
    response = quiet(build()).post("/api/interview-consent")
    assert response.status_code == 405 and "GET" in response.headers["allow"] and cache(response) == [NO_STORE]


@pytest.mark.parametrize("url", ["/api/interview-consent/", "/api/interview-sessions/"])
def test_a_trailing_slash_redirect_has_it(url):
    response = quiet(build()).get(url, follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"].endswith(url.rstrip("/")) and cache(response) == [NO_STORE]


def test_an_unexpected_error_has_it_and_says_nothing_about_the_error():
    response = quiet(build()).get("/api/interview-sessions/probe/boom")
    assert (response.status_code, response.text, response.headers["content-type"]) == (500, "Internal Server Error", "text/plain; charset=utf-8")
    assert cache(response) == [NO_STORE] and SECRET not in response.text and SECRET not in str(dict(response.headers))


def test_a_value_the_route_set_is_replaced_not_added_to():
    response = quiet(build()).get("/api/interview-sessions/probe/header")
    assert cache(response) == [NO_STORE]


async def _call(app, path):
    """The raw messages the application sends, and the error it raises, for a GET of `path`."""
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # the client stays connected: wait to be cancelled (a streaming response listens here)

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "path": path, "raw_path": path.encode(),
        "root_path": "", "scheme": "http", "query_string": b"", "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    try:
        await app(scope, receive, send)
    except Exception as error:  # noqa: BLE001  (returned to the test)
        return messages, error
    return messages, None


def test_a_response_that_already_started_has_it_and_the_error_still_reaches_the_server():
    messages, error = asyncio.run(_call(build(), "/api/interview-sessions/probe/stream"))
    start = next(m for m in messages if m["type"] == "http.response.start")
    assert (start["status"], dict(start["headers"])[b"cache-control"]) == (200, b"no-store")
    assert isinstance(error, RuntimeError)  # re-raised by Starlette, as before; no 500 body could be sent after the start


# ── Nothing outside the interview paths has it ──


@pytest.mark.parametrize("url", ELSEWHERE_URLS)
def test_other_paths_do_not_have_it(url):
    response = quiet(build()).get(url)
    assert response.status_code == 200 and cache(response) == []


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/api/interview-consent", True),
        ("/api/interview-consent/", True),
        ("/api/interview-sessions", True),
        ("/api/interview-sessions/", True),
        ("/api/interview-sessions/12", True),
        ("/api/interview-sessions/12/feedback", True),
        ("/api/jobs/5/interview-sessions", True),
        ("/api/jobs/5/interview-sessions/", True),
        ("/api/jobs/5/interview-questions", False),  # D21
        ("/api/jobs/5/roadmap", False),
        ("/api/jobs/interview-sessions", False),
        ("/api/jobs/5/6/interview-sessions", False),
        ("/api/interview-sessionsX", False),
        ("/api/interview-consentX", False),
        ("/api/interview-sessions-old", False),
        ("/xapi/interview-sessions", False),
        ("/api/users/me", False),
        ("/health", False),
        ("/API/INTERVIEW-SESSIONS", False),  # routing is case-sensitive: nothing is served there
        ("", False),
    ],
)
def test_the_path_pattern_matches_exactly_the_interview_paths(path, expected):
    assert (INTERVIEW_PATH.match(path) is not None) is expected
    assert is_interview_path({"type": "http", "path": path, "root_path": ""}) is expected


def test_the_pattern_reads_the_path_the_router_reads_when_there_is_a_root_path():
    assert is_interview_path({"type": "http", "path": "/prefix/api/interview-sessions/1", "root_path": "/prefix"}) is True
    assert is_interview_path({"type": "http", "path": "/api/interview-sessions/1", "root_path": "/prefix"}) is True
    assert is_interview_path({"type": "http", "path": "/prefix/api/users/me", "root_path": "/prefix"}) is False


def test_a_non_http_scope_is_passed_through_with_its_own_send():
    """Only an HTTP request for an interview path gets a wrapped `send`: a lifespan scope, a websocket scope (even on an interview path)
    and an HTTP request for another path are handed the original one."""
    seen = []

    async def inner(scope, receive, send):
        seen.append(send)

    async def original(message):
        pass

    for scope in (
        {"type": "lifespan"},
        {"type": "websocket", "path": "/api/interview-sessions/1", "root_path": ""},
        {"type": "http", "path": "/api/users/me", "root_path": ""},
    ):
        asyncio.run(NoStoreMiddleware(inner)(scope, None, original))
    assert seen == [original, original, original]
    asyncio.run(NoStoreMiddleware(inner)({"type": "http", "path": "/api/interview-sessions/1", "root_path": ""}, None, original))
    assert seen[-1] is not original  # the one case that is wrapped


# ── The handler for unexpected errors: nothing changes outside the interview paths ──


def snapshot(response, *, without_cache=True):
    headers = tuple(sorted((k.lower(), v) for k, v in response.headers.items() if not (without_cache and k.lower() == "cache-control")))
    return response.status_code, response.content, headers


def test_without_a_handler_the_response_outside_the_interview_paths_is_the_one_starlette_gives():
    installed, control = quiet(build()), quiet(build(with_install=False))
    a, b = installed.get("/api/elsewhere/boom"), control.get("/api/elsewhere/boom")
    assert snapshot(a, without_cache=False) == snapshot(b, without_cache=False)  # identical, header set included
    assert (a.status_code, a.text, a.headers["content-type"]) == (500, "Internal Server Error", "text/plain; charset=utf-8")
    assert cache(a) == [] and cache(b) == []


def test_on_an_interview_path_the_only_difference_is_the_header():
    a = quiet(build()).get("/api/interview-sessions/probe/boom")
    b = quiet(build(with_install=False)).get("/api/interview-sessions/probe/boom")
    assert snapshot(a) == snapshot(b) and cache(a) == [NO_STORE] and cache(b) == []


ON_LOOP: list[bool] = []


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def handler(name, status, *, sync, header=None):
    headers = {"X-Handled": name, **({"Cache-Control": header} if header else {})}

    def respond(request, exc):
        return JSONResponse({"handler": name}, status_code=status, headers=headers)

    if sync:
        def sync_handler(request, exc):
            ON_LOOP.append(_on_event_loop())
            return respond(request, exc)

        return sync_handler

    async def async_handler(request, exc):
        return respond(request, exc)

    return async_handler


PRE = {
    "a sync handler under 500": [(500, handler("sync-500", 500, sync=True))],
    "an async handler under 500": [(500, handler("async-500", 500, sync=False))],
    "a sync handler under Exception": [(Exception, handler("sync-exception", 502, sync=True))],
    "an async handler under Exception": [(Exception, handler("async-exception", 503, sync=False))],
    "both keys, Exception registered last": [(500, handler("sync-500", 500, sync=True)), (Exception, handler("async-exception", 503, sync=False))],
    "both keys, 500 registered last": [(Exception, handler("async-exception", 503, sync=False)), (500, handler("sync-500", 500, sync=True))],
}


@pytest.mark.parametrize("name", list(PRE), ids=list(PRE))
def test_an_existing_generic_handler_is_delegated_to_and_is_the_one_the_framework_would_have_used(name):
    pre = PRE[name]
    installed, control = quiet(build(pre=pre)), quiet(build(pre=pre, with_install=False))
    outside_a, outside_b = installed.get("/api/elsewhere/boom"), control.get("/api/elsewhere/boom")
    assert snapshot(outside_a, without_cache=False) == snapshot(outside_b, without_cache=False)  # outside the interview paths: identical
    assert outside_a.json()["handler"] in {"sync-500", "async-500", "sync-exception", "async-exception"}
    inside_a, inside_b = installed.get("/api/interview-sessions/probe/boom"), control.get("/api/interview-sessions/probe/boom")
    assert snapshot(inside_a) == snapshot(inside_b)  # the same handler, so the same response ...
    assert cache(inside_a) == [NO_STORE] and cache(inside_b) == []  # ... and the header is all that was added
    assert SECRET not in inside_a.text


def test_the_last_registered_of_the_two_keys_wins_as_it_does_in_the_framework():
    last_is_exception = quiet(build(pre=PRE["both keys, Exception registered last"])).get("/api/elsewhere/boom")
    last_is_500 = quiet(build(pre=PRE["both keys, 500 registered last"])).get("/api/elsewhere/boom")
    assert (last_is_exception.json(), last_is_exception.status_code) == ({"handler": "async-exception"}, 503)
    assert (last_is_500.json(), last_is_500.status_code) == ({"handler": "sync-500"}, 500)


@pytest.mark.parametrize("with_install", [True, False], ids=["installed", "control"])
def test_a_synchronous_handler_does_not_run_on_the_event_loop(with_install):
    ON_LOOP.clear()
    pre = [(Exception, handler("sync", 500, sync=True))]
    quiet(build(pre=pre, with_install=with_install)).get("/api/interview-sessions/probe/boom")
    assert ON_LOOP == [False]


def test_a_cache_control_value_of_the_existing_handler_is_replaced_on_interview_paths_and_kept_elsewhere():
    pre = [(Exception, handler("own", 500, sync=False, header="public, max-age=60"))]
    client = quiet(build(pre=pre))
    assert cache(client.get("/api/interview-sessions/probe/boom")) == [NO_STORE]
    assert cache(client.get("/api/elsewhere/boom")) == ["public, max-age=60"]


@pytest.mark.parametrize("with_install", [True, False], ids=["installed", "control"])
def test_the_exception_still_reaches_the_server_and_the_handler_logs_nothing(with_install, caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(RuntimeError, match=SECRET):
        TestClient(build(with_install=with_install)).get("/api/interview-sessions/probe/boom")  # raise_server_exceptions: Starlette re-raised it
    assert [r for r in caplog.records if r.name.startswith("app")] == []


# ── Installation ──


def test_install_is_idempotent_and_leaves_one_generic_handler_that_is_the_new_one():
    app = build(pre=[(500, handler("old", 500, sync=False))])
    install(app)
    assert sum(1 for m in app.user_middleware if m.cls is NoStoreMiddleware) == 1
    assert [k for k in app.exception_handlers if k in (500, Exception)] == [Exception]
    before = quiet(app).get("/api/elsewhere/boom").json()
    install(app)  # a second call changes nothing: the handler does not delegate to itself
    assert [k for k in app.exception_handlers if k in (500, Exception)] == [Exception]
    assert sum(1 for m in app.user_middleware if m.cls is NoStoreMiddleware) == 1
    assert quiet(app).get("/api/elsewhere/boom").json() == before == {"handler": "old"}


def test_the_middleware_is_the_outermost_user_middleware_after_install():
    app = build()
    assert app.user_middleware[0].cls is NoStoreMiddleware  # the last added is the outermost: nothing may be added after it
