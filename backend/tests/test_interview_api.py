"""The practice-interview API, route by route (M4 S4; docs/DECISIONS.md D58, D65, D67).

Each route has the cases that can happen to it and no others: a route with no id has no bad-id case, a route that any logged-in user may call
has no 403, and only the routes that can produce a 409 or a 429 are tested for one. Every status asserted on an interview route is asserted
together with `Cache-Control: no-store`; only the control rows at the end must not have it. `COVERED_ROUTES` lists the routes that have
their cases here, and test_interview_api_contract.py fails if it differs from the routes the application registers.

The cases of the consent route are here; those of the create route are in test_interview_api_create.py, those of the history route in test_interview_api_history.py, those of the routes of one session in test_interview_api_detail.py,
test_interview_api_end.py, test_interview_api_delete.py, test_interview_api_feedback.py, test_interview_api_feedback_model.py and test_interview_api_session_common.py,
and the mechanisms (no-store,
validation errors) are in test_interview_api_no_store.py and test_interview_api_validation_errors.py. Stage S4.5 registers the consent text, the creation of
a session, the history, and the detail, the end, the delete and the feedback of a session."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.services import ai_runtime, career_service, interview_consent_service

COVERED_ROUTES = {
    ("GET", "/api/interview-consent"),
    ("POST", "/api/jobs/{job_id}/interview-sessions"),
    ("GET", "/api/interview-sessions"),
    ("GET", "/api/interview-sessions/{session_id}"),
    ("POST", "/api/interview-sessions/{session_id}/end"),
    ("DELETE", "/api/interview-sessions/{session_id}"),
    ("POST", "/api/interview-sessions/{session_id}/feedback"),
}  # grows with each stage

CONSENT = "/api/interview-consent"
SECRET = "SECRET-MARKER-답변-내용"


@pytest.fixture
def quiet(db):
    """A client that answers an unexpected error with the 500 response, instead of raising it into the test."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def no_store(response) -> bool:
    return response.headers.get_list("cache-control") == ["no-store"]


# ── GET /api/interview-consent ──


def test_consent_no_token_is_401(client):
    response = client.get(CONSENT)
    assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer" and no_store(response)


@pytest.mark.parametrize("headers", [{"Authorization": "Bearer not-a-token"}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}])
def test_consent_a_malformed_token_is_401(client, headers):
    response = client.get(CONSENT, headers=headers)
    assert response.status_code == 401 and no_store(response)


def test_consent_a_seeker_gets_the_text_and_version_the_service_has(client, world):
    response = client.get(CONSENT, headers=world["seeker"])
    assert response.status_code == 200 and no_store(response) and response.headers["content-type"] == "application/json"
    current = interview_consent_service.current()
    assert response.json() == {
        "version": current.version,
        "title": current.title,
        "retention_days": current.retention_days,
        "items": [{"key": item.key, "text": item.text} for item in current.items],
    }
    body = response.json()
    assert body["version"] == settings.INTERVIEW_CONSENT_VERSION and body["retention_days"] == settings.INTERVIEW_RETENTION_DAYS
    assert [item["key"] for item in body["items"]] == ["processing", "purpose", "retention", "access", "deletion", "separate"]
    assert "notice" not in body  # static text, no AI result


def test_consent_a_company_user_gets_it_too_and_not_a_403(client, world):
    """Any logged-in user may read the text: it is static and holds no data (D67). The seeker-only rule is the services', and this route
    calls none of them."""
    seeker, company = client.get(CONSENT, headers=world["seeker"]), client.get(CONSENT, headers=world["recruiter"])
    assert company.status_code == 200 and no_store(company) and company.json() == seeker.json()


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_consent_other_methods_are_405(client, world, method):
    response = getattr(client, method)(CONSENT, headers=world["seeker"])
    assert response.status_code == 405 and "GET" in response.headers["allow"] and no_store(response)


def test_consent_an_unknown_subpath_is_404(client, world):
    response = client.get(CONSENT + "/x", headers=world["seeker"])
    assert response.status_code == 404 and no_store(response)


def test_consent_the_trailing_slash_redirects(client):
    response = client.get(CONSENT + "/", follow_redirects=False)  # the router redirects before any dependency runs: no token needed
    assert response.status_code == 307 and response.headers["location"].endswith(CONSENT) and no_store(response)


def test_consent_has_no_query_or_body_to_validate(client, world):
    response = client.get(CONSENT, headers=world["seeker"], params={"anything": "1"})
    assert response.status_code == 200 and no_store(response)  # an unknown query parameter is ignored


def test_consent_an_unexpected_error_is_a_plain_500_with_the_header_and_nothing_of_the_error(quiet, world, monkeypatch):
    def broken():
        raise RuntimeError(SECRET)

    monkeypatch.setattr(interview_consent_service, "current", broken)
    response = quiet.get(CONSENT, headers=world["seeker"])
    assert (response.status_code, response.text) == (500, "Internal Server Error") and no_store(response)
    assert SECRET not in response.text and SECRET not in str(dict(response.headers))


def test_consent_changes_nothing_reserves_nothing_and_calls_no_model(client, world, db, monkeypatch):
    def forbidden():
        raise AssertionError("the consent text must not reach a model")

    monkeypatch.setattr(ai_runtime, "llm", forbidden)
    for headers in (world["seeker"], world["recruiter"]):
        assert client.get(CONSENT, headers=headers).status_code == 200
    db.rollback()
    assert [db.query(model).count() for model in (InterviewSession, InterviewTurn, InterviewQuota)] == [0, 0, 0]


# ── Control rows: what is not an interview path has no `no-store` ──


def test_control_another_route_does_not_have_it(client, world):
    response = client.get("/api/users/me", headers=world["seeker"])
    assert response.status_code == 200 and response.headers.get_list("cache-control") == []


def test_control_the_d21_questions_route_is_not_an_interview_path(client, world):
    unauthenticated = client.post(f"/api/jobs/{world['job'].id}/interview-questions")
    assert unauthenticated.status_code == 401 and unauthenticated.headers.get_list("cache-control") == []


def test_control_an_unexpected_error_elsewhere_is_the_plain_500_it_always_was(quiet, world, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(career_service, "interview_questions", broken)
    response = quiet.post(f"/api/jobs/{world['job'].id}/interview-questions", headers=world["seeker"])
    assert (response.status_code, response.text, response.headers["content-type"]) == (500, "Internal Server Error", "text/plain; charset=utf-8")
    assert response.headers.get_list("cache-control") == []
