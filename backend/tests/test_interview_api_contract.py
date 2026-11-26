"""Contract guards of the practice-interview API (M4 S4; docs/DECISIONS.md D67), on the real application.

They fail when the registered routes differ from the stage's list (so a route cannot appear early, as a placeholder, or be forgotten), when a
route falls outside the `no-store` path pattern, and when something in the application stack could let a response bypass the header.
`EXPECTED_INTERVIEW_ROUTES` grows with each stage and `test_interview_api.COVERED_ROUTES` must equal it."""
import inspect
import re
from unittest.mock import patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Router

try:
    from starlette.middleware.body_limit import RequestBodyLimitMiddleware  # Starlette 1.6+, which FastAPI 0.164+ needs
except ImportError:  # an older Starlette has no request body limit, so none can be configured
    RequestBodyLimitMiddleware = None

from app.api.v1 import interview_sessions
from app.core.no_store import AGENT_PATH, INTERVIEW_PATH, NoStoreMiddleware
from app.main import app

from .docs.test_doc_api import code_routes
from .test_interview_api import COVERED_ROUTES

EXPECTED_INTERVIEW_ROUTES = {
    ("GET", "/api/interview-consent"),
    ("POST", "/api/jobs/{job_id}/interview-sessions"),
    ("GET", "/api/interview-sessions"),
    ("GET", "/api/interview-sessions/{session_id}"),
    ("POST", "/api/interview-sessions/{session_id}/end"),
    ("DELETE", "/api/interview-sessions/{session_id}"),
    ("POST", "/api/interview-sessions/{session_id}/feedback"),
    ("POST", "/api/interview-sessions/{session_id}/join"),
}  # stage S4.5 (the feedback joins the detail, the end and the delete), and M5 S4 (the join token, D80 (4))
ROUTER_FILE = "backend/app/api/v1/interview_sessions.py"

# FastAPI keeps an included router as one lazy object in `app.routes`, so the routes are read the way the API documentation guard reads
# them (each router module's own routes, under the /api prefix); that guard checks the walk against what OpenAPI serves.


def on_interview_paths():
    return {op: route for op, route in code_routes().items() if INTERVIEW_PATH.match(op[1])}


def test_the_application_registers_exactly_the_routes_of_the_stage():
    assert set(on_interview_paths()) == EXPECTED_INTERVIEW_ROUTES


def test_the_openapi_document_serves_the_same_interview_operations():
    served = {(method.upper(), path) for path, item in app.openapi()["paths"].items() for method in item if INTERVIEW_PATH.match(path)}
    assert served == EXPECTED_INTERVIEW_ROUTES


def test_the_interview_router_serves_only_interview_paths_and_no_other_module_serves_one():
    mine = {op for op, route in code_routes().items() if ROUTER_FILE in route.place.replace(chr(92), '/')}
    assert mine == EXPECTED_INTERVIEW_ROUTES
    assert all(INTERVIEW_PATH.match(path) for _method, path in mine), "a route outside the no-store pattern would not get the header"
    assert {op for op, route in on_interview_paths().items() if not ROUTER_FILE in route.place.replace(chr(92), '/')} == set()


def test_every_registered_interview_route_has_its_cases_in_the_route_tests():
    assert COVERED_ROUTES == EXPECTED_INTERVIEW_ROUTES


EXPECTED_AGENT_ROUTES = {
    ("GET", "/api/internal/interview-sessions/{session_id}/context"),
    ("POST", "/api/internal/interview-sessions/{session_id}/events"),
}  # M5 S1 (D80): the Interview Agent's two internal routes, and no other
AGENT_ROUTER_FILE = "backend/app/api/v1/internal_interview.py"


def test_the_only_agent_routes_are_the_two_internal_ones_of_their_own_module_and_no_route_is_a_placeholder():
    agent = {op: route for op, route in code_routes().items() if "/internal" in op[1] or "agent" in op[1].lower()}
    assert set(agent) == EXPECTED_AGENT_ROUTES
    assert all(AGENT_ROUTER_FILE in route.place.replace(chr(92), "/") for route in agent.values())
    assert all(AGENT_PATH.match(path) and not INTERVIEW_PATH.match(path) for _method, path in agent), "agent paths get no-store through AGENT_PATH"
    assert {route.kind for route in agent.values()} == {"public"}, "the agent routes take the agent secret, never a JWT"
    for route in interview_sessions.router.routes:
        assert route.status_code != 501 and "501" not in (route.responses or {}), route.path


def test_every_interview_route_needs_a_logged_in_user():
    assert {route.kind for route in on_interview_paths().values()} == {"login"}


# ── Nothing can bypass the header ──


def stack_layers() -> list[str]:
    """The class names of the layers of the real application, outermost first, down to the router."""
    layer, names = app.build_middleware_stack(), []
    while not isinstance(layer, Router):
        names.append(type(layer).__name__)
        layer = layer.app
    return names


BODY_LIMIT_LAYER = "AppBodyLimitMiddleware"  # FastAPI 0.164+ puts it in front of every user middleware (docs/DECISIONS.md D78)
ALWAYS_IN_FRONT = ["ServerErrorMiddleware", "ExceptionTelemetryMiddleware"]


def test_the_only_layers_in_front_of_the_middleware_cannot_make_a_response_it_would_miss():
    """`ServerErrorMiddleware` makes the 500, which the registered handler covers; the telemetry layer only observes and re-raises. FastAPI
    0.164+ adds `AppBodyLimitMiddleware` right after them: it answers (a 413, outside `NoStoreMiddleware`) only when a request body limit
    is set on the application, so it is accepted only while there is none (D78). The stack is also accepted without it, on an older
    FastAPI. A limit on a router or a route is refused by the probe below. A library upgrade or a middleware added after `install` that
    puts any other layer in front, or changes the order, fails here and has to be reviewed."""
    names = stack_layers()
    in_front = names[: names.index("NoStoreMiddleware")]
    if BODY_LIMIT_LAYER in in_front:  # checked first: with a limit the layer also puts the limiter itself in front, and this says why
        assert app.max_body_size is None, "a limit on the application makes the layer send its 413 outside NoStoreMiddleware (D78)"
    assert in_front in (ALWAYS_IN_FRONT, [*ALWAYS_IN_FRONT, BODY_LIMIT_LAYER])
    assert names.index("ExceptionMiddleware") > names.index("NoStoreMiddleware")  # the handlers of 401, 404, 405, 422 and AppError are inside


# ── No request body limit anywhere (D78) ──
# A configured limit (FastAPI 0.164+) would put a 413 in front of the middleware: with a limit on the application, a declared
# Content-Length over it is answered by the layer above, without `Cache-Control: no-store` and in Starlette's plain-text shape. A limit
# on a router, an `include_router` call or a route is answered inside the stack and is covered, but it is refused too: one rule, no case
# to reason about. Setting a limit needs a new decision that also puts its 413 behind no-store (D67 (4)), and then this guard changes.

# The probe self-tests set the limit through FastAPI's `max_body_size` (0.164+); the pinned FastAPI (D82) has no such parameter.
needs_limiter = pytest.mark.skipif(
    RequestBodyLimitMiddleware is None or "max_body_size" not in inspect.signature(FastAPI).parameters,
    reason="this FastAPI or Starlette has no request body limit",
)
FEEDBACK = [("POST", "/api/interview-sessions/{session_id}/feedback")]


def limited_operations(application: FastAPI, operations) -> list[tuple[str, str]]:
    """The operations whose requests pass through a request body limiter, wherever the limit is set: the application, a router, an
    `include_router` call or a route. Each of them is Starlette's `RequestBodyLimitMiddleware`, so one empty, unauthenticated request
    is sent to every operation and the calls to that class are counted."""
    if RequestBodyLimitMiddleware is None:
        return []
    calls, found, original = [], [], RequestBodyLimitMiddleware.__call__

    async def counting(self, scope, receive, send):
        calls.append(scope["path"])
        await original(self, scope, receive, send)

    with patch.object(RequestBodyLimitMiddleware, "__call__", counting):
        client = TestClient(application, raise_server_exceptions=False)  # no `with`: the lifespan (model warm-up) does not run
        for method, path in operations:
            before = len(calls)
            client.request(method, re.sub(r"\{[^}]*\}", "1", path))
            if len(calls) > before:
                found.append((method, path))
    return found


@pytest.mark.usefixtures("client")  # only for its database override: the public routes read the database
def test_no_request_body_limit_is_configured_on_any_route_of_the_application():
    assert limited_operations(app, code_routes()) == [], "a request body limit is set; its 413 would bypass the no-store header (D78)"


def probe_app(level: str | None) -> FastAPI:
    """A throwaway application with one route and a body limit at `level` (app, router, include or route), or none."""
    limit = {"max_body_size": 1000}
    application = FastAPI(**(limit if level == "app" else {}))
    router = APIRouter(**(limit if level == "router" else {}))

    def feedback(session_id: int):
        return {}

    router.post(FEEDBACK[0][1], **(limit if level == "route" else {}))(feedback)
    application.include_router(router, **(limit if level == "include" else {}))
    return application


@needs_limiter
@pytest.mark.parametrize("level", ["app", "router", "include", "route"])
def test_the_probe_finds_a_body_limit_wherever_it_is_set(level):
    """If this fails, the guard above has gone blind: it would pass with a limit set."""
    assert limited_operations(probe_app(level), FEEDBACK) == FEEDBACK


@needs_limiter
def test_the_probe_finds_nothing_in_an_application_without_a_body_limit():
    assert limited_operations(probe_app(None), FEEDBACK) == []


def test_the_middleware_is_the_outermost_user_middleware():
    assert app.user_middleware[0].cls is NoStoreMiddleware


def test_the_generic_error_handler_is_the_no_store_one_and_the_only_one():
    keys = [k for k in app.exception_handlers if k in (500, Exception)]
    assert keys == [Exception]
    assert app.exception_handlers[Exception].__qualname__.startswith("_make_handler.")  # a handler registered after `install` would replace it


def test_the_application_is_not_in_debug_mode():
    assert app.debug is False  # debug mode shows a traceback page before any handler


def test_the_validation_error_handler_is_the_sanitizing_one():
    """A 422 on an interview path carries no submitted value (D68); a handler registered after `install` would replace it and fail here."""
    assert getattr(app.exception_handlers[RequestValidationError], "interview_sanitizer", False) is True


# ── The OpenAPI contract ──

INTERVIEW_SCHEMAS = (
    "ConsentTextOut", "ConsentItemOut", "InterviewCreateIn", "TopicOut", "TurnOut", "SessionOut", "CreatedSessionOut", "SessionSummaryOut", "HistoryPageOut",
    "FeedbackOut", "FeedbackReportOut", "FeedbackTopicOut", "FeedbackStrengthOut", "FeedbackGapOut", "FeedbackPracticeQuestionOut", "FeedbackResourceLinkOut", "FeedbackUncoveredOut",
)


def test_no_interview_schema_has_a_weight_field_and_the_ones_with_ai_content_carry_the_notice():
    schemas = app.openapi()["components"]["schemas"]
    for name in INTERVIEW_SCHEMAS:
        assert not [p for p in schemas[name]["properties"] if "weight" in p.lower()], name  # importance labels only (AI rule 9)
    assert schemas["SessionOut"]["properties"]["notice"]["default"] == "AI 분석은 참고용입니다. 채용 여부는 기업이 최종 판단합니다."
    assert "notice" not in schemas["ConsentTextOut"]["properties"]  # static text, no AI result


def test_the_create_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/jobs/{job_id}/interview-sessions"]
    assert set(operation) == {"post"}
    post = operation["post"]
    assert post["tags"] == ["interview"] and post["security"] == [{"HTTPBearer": []}]
    assert post["parameters"] == [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "integer", "title": "Job Id"}}]
    assert post["requestBody"] == {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/InterviewCreateIn"}}}}
    assert set(post["responses"]) == {"201", "422"}  # 201 on success; the business errors are not declared, like the other routes
    assert post["responses"]["201"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/CreatedSessionOut"}
    schemas = spec["components"]["schemas"]
    body = schemas["InterviewCreateIn"]
    assert set(body["properties"]) == {"consent_transcript", "consent_version", "depth"} and body["additionalProperties"] is False
    assert "required" not in body  # all optional: a missing consent is the service's 409, depth defaults to 2
    for consent_field in ("consent_transcript", "consent_version"):
        prop = body["properties"][consent_field]
        assert "type" not in prop and "anyOf" not in prop  # untyped: nothing is coerced
    assert body["properties"]["depth"] == {
        "default": 2,
        "description": "Question depth chosen by the seeker: 1 기초, 2 적용, 3 심화 (D93)",
        "enum": [1, 2, 3],
        "title": "Depth",
        "type": "integer",
    }
    created = schemas["CreatedSessionOut"]
    assert set(created["properties"]) == {"session", "limited"} and set(created["required"]) == {"session", "limited"}
    assert created["properties"]["session"] == {"$ref": "#/components/schemas/SessionOut"}
    session = schemas["SessionOut"]
    assert set(session["properties"]) == {
        "id", "job_id", "job_title", "status", "end_reason", "plan_method", "depth", "max_seconds", "created_at", "started_at", "ended_at", "active_until",
        "expires_at", "joinable", "accepting_turns", "end_grace_open", "feedback_status", "topics", "turns", "notice",
    }
    assert set(session["required"]) == set(session["properties"]) - {"notice"}
    assert set(schemas["TopicOut"]["properties"]) == {"topic_id", "kind", "criterion_name", "importance", "depth", "status"}
    assert set(schemas["TurnOut"]["properties"]) == {"seq", "role", "kind", "text"}


# The consent route


def test_the_consent_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-consent"]
    assert set(operation) == {"get"}
    get = operation["get"]
    assert get["tags"] == ["interview"] and get.get("security"), "the route needs the bearer token"
    assert "parameters" not in get and "requestBody" not in get
    assert get["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ConsentTextOut"}
    schemas = spec["components"]["schemas"]
    out, item = schemas["ConsentTextOut"], schemas["ConsentItemOut"]
    assert set(out["properties"]) == {"version", "title", "retention_days", "items"} and set(out["required"]) == set(out["properties"])
    assert out["properties"]["items"]["items"] == {"$ref": "#/components/schemas/ConsentItemOut"}
    assert set(item["properties"]) == {"key", "text"} and set(item["required"]) == {"key", "text"}


# The history route


SUMMARY_FIELDS = {"id", "job_id", "job_title", "status", "end_reason", "created_at", "ended_at", "active_until", "expires_at", "joinable", "feedback_status"}


def test_the_history_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-sessions"]
    assert set(operation) == {"get"}
    get = operation["get"]
    assert get["tags"] == ["interview"] and get["security"] == [{"HTTPBearer": []}]
    assert "requestBody" not in get
    assert len(get["parameters"]) == 3 and {p["name"] for p in get["parameters"]} == {"job_id", "limit", "before_id"}
    int32 = {"type": "integer", "maximum": 2**31 - 1, "minimum": -(2**31)}  # the range of the id columns (`Integer`)
    for parameter in get["parameters"]:
        assert parameter["in"] == "query" and parameter["required"] is False, parameter["name"]
        integer = int32 if parameter["name"] in {"job_id", "before_id"} else {"type": "integer"}  # `limit` has no bound: the service clamps it
        assert parameter["schema"]["anyOf"] == [integer, {"type": "null"}], parameter["name"]
        assert not set(parameter["schema"]) & {"exclusiveMinimum", "exclusiveMaximum", "enum"}, parameter["name"]
    assert set(get["responses"]) == {"200", "422"}  # the route has no business error
    assert get["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/HistoryPageOut"}
    schemas = spec["components"]["schemas"]
    page, summary = schemas["HistoryPageOut"], schemas["SessionSummaryOut"]
    assert set(page["properties"]) == {"items", "next_before_id", "active", "notice"}
    assert set(page["required"]) == {"items", "next_before_id", "active"}  # `active` is always present, null when there is none
    assert page["properties"]["items"]["items"] == {"$ref": "#/components/schemas/SessionSummaryOut"}
    assert page["properties"]["active"]["anyOf"] == [{"$ref": "#/components/schemas/SessionSummaryOut"}, {"type": "null"}]
    assert page["properties"]["next_before_id"]["anyOf"] == [{"type": "integer"}, {"type": "null"}]
    assert page["properties"]["notice"]["default"] == "AI 분석은 참고용입니다. 채용 여부는 기업이 최종 판단합니다."
    assert set(summary["properties"]) == SUMMARY_FIELDS and set(summary["required"]) == SUMMARY_FIELDS
    assert "notice" not in summary["properties"]  # one notice for the page, none per item
    assert not {"topics", "turns", "plan_method", "plan", "coverage", "feedback"} & set(summary["properties"])


# The detail route


def test_the_detail_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-sessions/{session_id}"]
    assert set(operation) == {"get", "delete"}  # the detail is the get; the delete has its own contract below
    get = operation["get"]
    assert get["tags"] == ["interview"] and get["security"] == [{"HTTPBearer": []}]
    assert "requestBody" not in get
    assert get["parameters"] == [
        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "integer", "maximum": 2**31 - 1, "minimum": -(2**31), "title": "Session Id"}}
    ]  # the range of the id column, and nothing else is a parameter
    assert set(get["responses"]) == {"200", "422"}  # the business error (404) is not declared, like the other routes
    assert get["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/SessionOut"}


# The end route


def test_the_end_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-sessions/{session_id}/end"]
    assert set(operation) == {"post"}
    post = operation["post"]
    assert post["tags"] == ["interview"] and post["security"] == [{"HTTPBearer": []}]
    assert "requestBody" not in post  # no body: whatever is sent is ignored
    assert post["parameters"] == [
        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "integer", "maximum": 2**31 - 1, "minimum": -(2**31), "title": "Session Id"}}
    ]  # the range of the id column, and nothing else is a parameter
    assert set(post["responses"]) == {"200", "422"}  # 200 with the session; the business errors (404, 409) are not declared, like the other routes
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/SessionOut"}
    assert set(spec["paths"]["/api/interview-sessions/{session_id}"]) == {"get", "delete"}  # the end is not at the detail path


# The delete route


def test_the_delete_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-sessions/{session_id}"]
    assert set(operation) == {"get", "delete"}
    delete = operation["delete"]
    assert delete["tags"] == ["interview"] and delete["security"] == [{"HTTPBearer": []}]
    assert "requestBody" not in delete  # no body: whatever is sent is ignored
    assert delete["parameters"] == [
        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "integer", "maximum": 2**31 - 1, "minimum": -(2**31), "title": "Session Id"}}
    ]  # the range of the id column, and nothing else is a parameter
    assert set(delete["responses"]) == {"204", "422"}  # 204 with no body; the business error (404) is not declared, like the other routes
    assert "content" not in delete["responses"]["204"]
    assert operation["get"]["parameters"] == delete["parameters"]  # the detail and the delete read the id the same way


# The 405 of the interview paths


def test_every_interview_path_advertises_exactly_its_openapi_methods_in_allow():
    """A 405 is answered before any dependency runs, so this needs no login and no database."""
    spec = app.openapi()
    paths = {path: item for path, item in spec["paths"].items() if INTERVIEW_PATH.match(path)}
    assert len(paths) == 7  # the consent, the history, the create, the detail with the delete, the end, the feedback, and the join
    web = TestClient(app, raise_server_exceptions=False)
    for path, item in paths.items():
        supported = {method.upper() for method in item}
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            if method in supported:
                continue
            response = web.request(method, re.sub(r"\{[a-z_]+\}", "1", path))
            assert response.status_code == 405 and response.headers.get_list("cache-control") == ["no-store"], (method, path)
            assert response.headers["allow"] == ", ".join(sorted(supported)), (method, path, response.headers["allow"])


def test_every_route_of_the_interview_router_uses_the_all_methods_route_class():
    router = interview_sessions.router
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert len(routes) == 8 and issubclass(router.route_class, APIRoute) and router.route_class is not APIRoute
    assert all(type(route) is router.route_class for route in routes)  # a route that is added with another class would advertise one method again


# The feedback route

FEEDBACK_REPORT_FIELDS = {
    "method", "topics", "strengths", "gaps", "improvements", "practice_questions", "resources", "uncovered", "notes", "rules_sections", "rubric_notice",
}
FEEDBACK_NESTED = {
    "FeedbackTopicOut": {"topic_id", "name", "importance", "status"}, "FeedbackStrengthOut": {"topic_id", "text", "quotes"},
    "FeedbackGapOut": {"topic_id", "text"}, "FeedbackPracticeQuestionOut": {"topic_id", "question"},
    "FeedbackResourceLinkOut": {"topic_id", "skill", "title", "url"}, "FeedbackUncoveredOut": {"topic_id", "name", "importance", "reason"},
}


def test_the_feedback_route_contract():
    spec = app.openapi()
    operation = spec["paths"]["/api/interview-sessions/{session_id}/feedback"]
    assert set(operation) == {"post"}  # get-or-create: there is no separate GET (D67 (1))
    post = operation["post"]
    assert post["tags"] == ["interview"] and post["security"] == [{"HTTPBearer": []}]
    assert "requestBody" not in post  # no body: whatever is sent is ignored
    assert post["parameters"] == [
        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "integer", "maximum": 2**31 - 1, "minimum": -(2**31), "title": "Session Id"}}
    ]  # the range of the id column, and nothing else is a parameter
    assert set(post["responses"]) == {"200", "422"}  # 200 for a final and a provisional report alike; the business errors are not declared, like the other routes
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/FeedbackOut"}
    schemas = spec["components"]["schemas"]
    out = schemas["FeedbackOut"]
    assert set(out["properties"]) == {"report", "final", "limited", "reason", "generated_at", "notice"}
    assert set(out["required"]) == {"report", "final", "limited", "reason", "generated_at"}  # every field is always present; only `notice` has a default
    assert out["properties"]["report"] == {"$ref": "#/components/schemas/FeedbackReportOut"}
    assert out["properties"]["reason"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert out["properties"]["generated_at"]["anyOf"] == [{"type": "string", "format": "date-time"}, {"type": "null"}]
    assert out["properties"]["notice"]["default"] == "AI 분석은 참고용입니다. 채용 여부는 기업이 최종 판단합니다."
    assert not {"prompt_version", "attempts_used", "method", "score", "rank", "verdict"} & set(out["properties"])  # nothing internal, no second method
    report = schemas["FeedbackReportOut"]
    assert set(report["properties"]) == FEEDBACK_REPORT_FIELDS and set(report["required"]) == FEEDBACK_REPORT_FIELDS  # the `to_data()` of the report, exactly
    for field, model in (
        ("topics", "FeedbackTopicOut"), ("strengths", "FeedbackStrengthOut"), ("gaps", "FeedbackGapOut"), ("practice_questions", "FeedbackPracticeQuestionOut"),
        ("resources", "FeedbackResourceLinkOut"), ("uncovered", "FeedbackUncoveredOut"),
    ):
        assert report["properties"][field]["items"] == {"$ref": f"#/components/schemas/{model}"}, field
    for model, fields in FEEDBACK_NESTED.items():
        assert set(schemas[model]["properties"]) == fields and set(schemas[model]["required"]) == fields, model
