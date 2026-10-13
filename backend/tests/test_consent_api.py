"""Re-consent and AI-consent withdrawal (D17); CV upload needs AI consent."""
from sqlalchemy import select

from ai.tests.helpers import SAMPLE_CV
from app.core.config import settings
from app.models import Evaluation, User
from app.models.application import EvaluationStatus
from app.services import evaluation_service

from .test_applications_api import confirm, job, ready_seeker, upload  # noqa: F401  (job is a fixture)
from .test_jobs_api import make_published

ME = "/api/users/me"
CONSENT = "/api/users/me/consent"
WITHDRAW = "/api/users/me/consent/ai"
OLD_VERSION = "2026-10-01"
REAL_RUN = evaluation_service.run_in_background


def _body(version=None, **flags):
    return {"version": version or settings.CONSENT_VERSION, "consent_privacy": True, "consent_ai": True, **flags}


def _user(db, email) -> User:
    return db.scalars(select(User).where(User.email == email)).one()


def _seeker(client, db, email="kim@seeker.test", version=None):
    h = ready_seeker(client, db, email, "김지원")
    _user(db, email).consent_version = version or settings.CONSENT_VERSION
    db.commit()
    return h


def test_old_version_reconsents_and_gets_recommendations(client, db, world):
    h = _seeker(client, db, version=OLD_VERSION)
    me = client.get(ME, headers=h).json()
    assert me["consent_required"] is True and me["current_consent_version"] == settings.CONSENT_VERSION
    assert me["consent_version"] == OLD_VERSION and "consent_ai_at" not in me
    assert client.get("/api/recommendations/jobs", headers=h).json()["code"] == "AI_CONSENT_REQUIRED"

    r = client.post(CONSENT, json=_body(), headers=h)
    assert r.status_code == 200, r.json()
    assert (r.json()["consent_version"], r.json()["consent_required"]) == (settings.CONSENT_VERSION, False)
    assert client.get("/api/recommendations/jobs", headers=h).status_code == 200


def test_reconsent_validation(client, db, world):
    h = _seeker(client, db, version=OLD_VERSION)
    r = client.post(CONSENT, json=_body(version=OLD_VERSION), headers=h)  # the page showed an older text
    assert (r.status_code, r.json()["code"], r.json()["current_version"]) == (409, "CONSENT_VERSION_OUTDATED", settings.CONSENT_VERSION)
    assert client.post(CONSENT, json=_body(consent_ai=False), headers=h).status_code == 422
    assert client.post(CONSENT, json=_body(consent_privacy=False), headers=h).status_code == 422
    assert client.post(CONSENT, json=_body()).status_code == 401
    assert _user(db, "kim@seeker.test").consent_version == OLD_VERSION  # nothing saved
    assert client.post(CONSENT, json=_body(), headers=world["recruiter"]).status_code == 200  # companies consent too


def test_old_version_still_uploads_and_applies(client, db, world, job):
    h = _seeker(client, db, version=OLD_VERSION)
    cv = upload(client, h)
    assert cv.status_code == 201
    assert confirm(client, h, cv.json()).status_code == 200
    assert client.post(f"/api/jobs/{job}/applications", headers=h).status_code == 201


def test_register_response_has_the_consent_fields(client):
    body = {"email": "new@seeker.test", "password": "pass1234", "role": "seeker", "display_name": "신규",
            "consent_privacy": True, "consent_ai": True}
    r = client.post("/api/auth/register", json=body).json()
    assert (r["consent_version"], r["current_consent_version"], r["consent_required"]) == (
        settings.CONSENT_VERSION, settings.CONSENT_VERSION, False
    )


def test_withdrawal_stops_new_ai_use_and_keeps_data(client, db, world, job):
    h = _seeker(client, db)
    client.put("/api/preferences/me", json={"profile_public": True}, headers=h)
    app_id = client.post(f"/api/jobs/{job}/applications", headers=h).json()["id"]

    r = client.delete(WITHDRAW, headers=h)
    assert r.status_code == 200
    assert (r.json()["consent_required"], r.json()["consent_version"]) == (True, settings.CONSENT_VERSION)

    # No new AI use of the seeker's data
    assert client.post("/api/cv", files={"file": ("cv.pdf", b"%PDF", "application/pdf")}, headers=h).json()["code"] == "AI_CONSENT_REQUIRED"
    other = make_published(client, world["recruiter"], title="다른 공고")["id"]
    assert client.post(f"/api/jobs/{other}/applications", headers=h).json()["code"] == "AI_CONSENT_REQUIRED"
    assert client.get("/api/recommendations/jobs", headers=h).json()["code"] == "AI_CONSENT_REQUIRED"
    prefs = client.get("/api/preferences/me", headers=h).json()
    assert (prefs["profile_public"], prefs["profile_public_at"]) == (False, None)  # out of the talent pool

    # Data already stored stays; the company still sees the application but cannot re-score it
    rows = client.get(f"/api/jobs/{job}/applications", headers=world["recruiter"]).json()["items"]
    assert [row["application_id"] for row in rows] == [app_id]
    ev = db.scalars(select(Evaluation)).one()
    ev.status = EvaluationStatus.FAILED
    db.commit()
    r = client.post(f"/api/applications/{app_id}/evaluation/retry", headers=world["recruiter"])
    assert (r.status_code, r.json()["code"]) == (409, "AI_CONSENT_WITHDRAWN")
    assert client.get("/api/cv/me", headers=h).status_code == 200

    # Consenting again restores it
    assert client.post(CONSENT, json=_body(), headers=h).json()["consent_required"] is False
    assert upload(client, h, SAMPLE_CV).status_code == 201


def test_a_run_queued_before_withdrawal_finishes(client, db, world, job, monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation_service, "run_in_background", lambda *args: calls.append(args))
    h = _seeker(client, db)
    assert client.post(f"/api/jobs/{job}/applications", headers=h).status_code == 201
    assert client.delete(WITHDRAW, headers=h).status_code == 200
    (factory, evaluation_id, token), = calls
    REAL_RUN(factory, evaluation_id, token)  # the queued run is not cancelled
    db.expire_all()
    assert db.get(Evaluation, evaluation_id).status == EvaluationStatus.DONE


def test_only_seekers_withdraw(client, world):
    r = client.delete(WITHDRAW, headers=world["recruiter"])
    assert (r.status_code, r.json()["code"]) == (403, "SEEKER_ONLY")
    assert client.delete(WITHDRAW).status_code == 401
