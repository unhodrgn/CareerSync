"""A validation error on an interview path carries no submitted value, and no other path changes (M4 S4.2; docs/DECISIONS.md D68):
`app/core/validation_errors.py`.

General mechanism tests on throwaway FastAPI apps, so that they do not depend on which routes exist: on an interview path the 422 is cut
down to `type`, `loc` and `msg` (and an unknown field is not named); on every other path the response is exactly the one the application gave
before, FastAPI's default or the handler the application registered; the no-store header still covers the sanitized response. The create
route of the real application is checked in test_interview_api_create.py."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.core import no_store, validation_errors
from app.core.validation_errors import install, sanitized_errors

SECRET = "SECRET-MARKER-답변-내용"


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: object = None
    n: int | None = None


def build(*, install_it=True, with_no_store=False, pre=None) -> FastAPI:
    app = FastAPI()
    if pre is not None:
        app.add_exception_handler(RequestValidationError, pre)

    @app.post("/api/interview-sessions/{sid}")
    def inside(sid: int, body: In):
        return {}

    @app.post("/api/jobs/{job_id}/interview-sessions")
    def create(job_id: int, body: In):
        return {}

    @app.post("/api/elsewhere/{sid}")
    def outside(sid: int, body: In):
        return {}

    if install_it:
        install(app)
    if with_no_store:
        no_store.install(app)
    return app


def client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


INTERVIEW = "/api/interview-sessions/1"
CASES = {
    "an unknown field": dict(json={"a": 1, SECRET: SECRET}),
    "a body that is not an object": dict(json=[SECRET]),
    "a body sent as text": dict(content=SECRET.encode(), headers={"content-type": "text/plain"}),
    "a body that is not JSON": dict(content=b"{" + SECRET.encode(), headers={"content-type": "application/json"}),
    "a field of the wrong type": dict(json={"n": SECRET}),
    "no body": dict(),
}


@pytest.mark.parametrize("name", list(CASES), ids=list(CASES))
def test_on_an_interview_path_only_type_loc_and_msg_are_left_and_nothing_submitted(name):
    response = client(build()).post(INTERVIEW, **CASES[name])
    assert response.status_code == 422 and set(response.json()) == {"detail"} and response.json()["detail"]
    for error in response.json()["detail"]:
        assert set(error) == {"type", "loc", "msg"}
    assert SECRET not in response.text


def test_a_bad_id_in_the_path_is_not_echoed_but_its_location_stays():
    response = client(build()).post("/api/jobs/" + SECRET + "/interview-sessions", json={})
    (error,) = response.json()["detail"]
    assert response.status_code == 422 and error["loc"] == ["path", "job_id"] and error["type"] == "int_parsing" and SECRET not in response.text


def test_the_location_of_an_ordinary_error_is_kept_so_the_client_can_fix_it_and_an_unknown_field_is_not_named():
    typed = client(build()).post(INTERVIEW, json={"n": "x"}).json()["detail"]
    unknown = client(build()).post(INTERVIEW, json={"zzz": 1}).json()["detail"]
    assert typed == [{"type": "int_parsing", "loc": ["body", "n"], "msg": "Input should be a valid integer, unable to parse string as an integer"}]
    assert unknown == [{"type": "extra_forbidden", "loc": ["body"], "msg": "Extra inputs are not permitted"}]


def test_the_sanitizer_keeps_only_three_keys_and_tolerates_a_missing_one():
    errors = [{"type": "t", "loc": ("body", 3), "msg": "m", "input": SECRET, "ctx": {"error": SECRET}, "url": "u"}, {"type": "x"}]
    assert sanitized_errors(errors) == [{"type": "t", "loc": ["body", 3], "msg": "m"}, {"type": "x", "loc": [], "msg": None}]


# ── Nothing else changes ──


def snapshot(response):
    return response.status_code, response.content, tuple(sorted((k.lower(), v) for k, v in response.headers.items()))


@pytest.mark.parametrize("name", list(CASES), ids=list(CASES))
def test_on_any_other_path_the_response_is_exactly_the_one_without_the_sanitizer(name):
    installed, control = client(build()), client(build(install_it=False))
    a, b = installed.post("/api/elsewhere/1", **CASES[name]), control.post("/api/elsewhere/1", **CASES[name])
    assert snapshot(a) == snapshot(b)
    assert any("input" in error for error in a.json()["detail"])  # FastAPI's own response still echoes: proof that nothing was changed there


def test_a_bad_path_id_elsewhere_is_unchanged_too():
    a, b = client(build()).post("/api/elsewhere/abc", json={}), client(build(install_it=False)).post("/api/elsewhere/abc", json={})
    assert snapshot(a) == snapshot(b)


def custom_sync(request, exc):
    return JSONResponse({"handler": "sync"}, status_code=400, headers={"X-Handled": "sync"})


async def custom_async(request, exc):
    return JSONResponse({"handler": "async"}, status_code=418, headers={"X-Handled": "async"})


@pytest.mark.parametrize("handler", [custom_sync, custom_async], ids=["sync", "async"])
def test_an_existing_handler_is_still_the_one_used_outside_the_interview_paths(handler):
    installed, control = client(build(pre=handler)), client(build(pre=handler, install_it=False))
    a, b = installed.post("/api/elsewhere/1", json=[1]), control.post("/api/elsewhere/1", json=[1])
    assert snapshot(a) == snapshot(b) and a.json()["handler"] in {"sync", "async"}
    inside = installed.post(INTERVIEW, json=[SECRET])
    assert inside.status_code == 422 and SECRET not in inside.text  # on the interview paths the sanitized response is the one that is sent


def test_a_synchronous_existing_handler_is_not_run_on_the_event_loop():
    ran = []

    def handler(request, exc):
        try:
            asyncio.get_running_loop()
            ran.append(True)
        except RuntimeError:
            ran.append(False)
        return JSONResponse({}, status_code=400)

    client(build(pre=handler)).post("/api/elsewhere/1", json=[1])
    assert ran == [False]


# ── Installation, and the header ──


def test_install_is_idempotent():
    app = build()
    first = app.exception_handlers[RequestValidationError]
    install(app)
    assert app.exception_handlers[RequestValidationError] is first and first.interview_sanitizer is True
    assert client(app).post(INTERVIEW, json=[SECRET]).status_code == 422


def test_the_sanitized_response_still_has_the_no_store_header():
    response = client(build(with_no_store=True)).post(INTERVIEW, json=[SECRET])
    assert response.status_code == 422 and response.headers.get_list("cache-control") == ["no-store"] and SECRET not in response.text
    other = client(build(with_no_store=True)).post("/api/elsewhere/1", json=[SECRET])
    assert other.status_code == 422 and other.headers.get_list("cache-control") == []


def test_the_module_logs_nothing(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    client(build()).post(INTERVIEW, json={SECRET: SECRET})
    assert [r for r in caplog.records if r.name.startswith("app")] == [] and SECRET not in " ".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore", "asyncio"))
    )
    assert validation_errors.__doc__
