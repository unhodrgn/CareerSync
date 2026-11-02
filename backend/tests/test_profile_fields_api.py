"""Seeker profile (docs/DECISIONS.md D46): display-name changes with the lock after the first CV, and the
self-declared experience level and skills, which are display only and never change any score."""
import re
from pathlib import Path

from sqlalchemy import func, select, text

from ai.scoring.pref import JobFacts, pref_score
from ai.tests.helpers import SAMPLE_CV
from app.models import CvDocument, CvProfile, Evaluation, SeekerPreference, SeekerProfileSkill, User
from app.services import account_service, cv_service, preference_service

from .test_applications_api import job, seeker, upload  # noqa: F401  (job is a fixture)

ROOT = Path(__file__).resolve().parents[2]


def me(client, headers):
    return client.get("/api/users/me", headers=headers).json()


def rename(client, headers, name):
    return client.patch("/api/users/me", json={"display_name": name}, headers=headers)


# ── Display name ──


def test_rename_before_any_cv_and_for_companies(client, db, world):
    h = seeker(db, "kim@seeker.test", "임시 이름")
    r = rename(client, h, "  김지원  ")
    assert r.status_code == 200 and r.json()["display_name"] == "김지원"
    assert me(client, h)["display_name"] == "김지원"
    # Companies are never locked
    assert rename(client, world["recruiter"], "Acme 인사팀").json()["display_name"] == "Acme 인사팀"
    assert rename(client, world["recruiter"], "Acme 채용팀").status_code == 200


def test_rename_validation_like_registration(client, db, world):
    h = seeker(db, "kim@seeker.test", "김지원")
    for body in ({"display_name": ""}, {"display_name": "   "}, {"display_name": "가" * 51}, {}):
        assert client.patch("/api/users/me", json=body, headers=h).status_code == 422
    # The email is the login and cannot be changed here (D36)
    r = client.patch("/api/users/me", json={"display_name": "김지원", "email": "new@seeker.test"}, headers=h)
    assert r.status_code == 422
    assert me(client, h)["email"] == "kim@seeker.test"
    assert client.patch("/api/users/me", json={"display_name": "x"}).status_code == 401


def test_name_is_locked_after_the_first_cv_upload(client, db, world):
    h = seeker(db, "kim@seeker.test", "김지원")
    assert upload(client, h).status_code == 201  # uploaded, not confirmed: already locked
    r = rename(client, h, "박서준")
    assert r.status_code == 409 and r.json()["code"] == "NAME_LOCKED"
    assert me(client, h)["display_name"] == "김지원"


def test_a_failed_upload_does_not_lock_the_name(client, db, world):
    h = seeker(db, "kim@seeker.test", "김지원")
    r = client.post("/api/cv", files={"file": ("cv.pdf", b"not a pdf", "application/pdf")}, headers=h)
    assert r.status_code == 422
    assert rename(client, h, "김지원2").status_code == 200


def test_there_is_no_way_to_delete_a_cv_and_rename(client, db, world):
    """The lock is "has any CV document". No CV deletion exists (D34); when it is added, this test must be revisited
    together with the lock (a seeker without documents has no stored masked text, so renaming is safe again)."""
    h = seeker(db, "kim@seeker.test", "김지원")
    cv = upload(client, h).json()
    assert client.delete(f"/api/cv/{cv['id']}", headers=h).status_code == 405
    assert client.delete("/api/cv/me", headers=h).status_code == 405
    assert rename(client, h, "박서준").json()["code"] == "NAME_LOCKED"


def test_a_rename_during_an_upload_makes_the_upload_fail(client, db, world, monkeypatch):
    """Upload masks with the name it read first, then re-reads it under the row lock renames take; a rename in
    between wins and the upload stores nothing, so no stored text is masked with a stale name."""
    h = seeker(db, "kim@seeker.test", "임시 이름")
    user = db.scalars(select(User).where(User.email == "kim@seeker.test")).one()
    real = cv_service.structure_cv

    def rename_mid_upload(*args, **kwargs):
        account_service.rename(db, user, "김지원")  # a parallel request, while the CV is being analyzed
        return real(*args, **kwargs)

    monkeypatch.setattr(cv_service, "structure_cv", rename_mid_upload)
    r = upload(client, h)
    assert r.status_code == 409 and r.json()["code"] == "NAME_CHANGED"
    assert db.scalar(select(func.count()).select_from(CvDocument)) == 0
    monkeypatch.setattr(cv_service, "structure_cv", real)

    # The next upload masks the new name, and from then on the name is locked
    cv = upload(client, h).json()
    masked = db.get(CvProfile, cv["id"]).document.masked_text
    assert "김지원" in SAMPLE_CV and "김지원" not in masked and "name" in cv["masked_kinds"]
    assert rename(client, h, "임시 이름").json()["code"] == "NAME_LOCKED"


# ── Self-declared experience level and skills ──


def put_prefs(client, headers, **body):
    return client.put("/api/preferences/me", json=body, headers=headers)


def test_profile_fields_default_empty_and_are_normalized(client, db, world):
    h = world["seeker"]
    before = client.get("/api/preferences/me", headers=h).json()
    assert before["experience_level"] is None and before["skills"] == []
    r = put_prefs(client, h, locations=["서울"], experience_level="junior", skills=["react", "리액트", "spring boot", " FooLang ", "", "SQL"])
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["experience_level"] == "junior"
    assert body["skills"] == ["React", "Spring", "FooLang", "SQL"]  # canonical names, duplicates merged, order kept
    assert client.get("/api/preferences/me", headers=h).json()["skills"] == body["skills"]


def test_profile_fields_validation(client, db, world):
    h = world["seeker"]
    assert put_prefs(client, h, experience_level="expert").status_code == 422
    assert put_prefs(client, h, skills=[f"skill{i}" for i in range(21)]).status_code == 422
    assert put_prefs(client, h, skills=["x" * 101]).status_code == 422
    assert put_prefs(client, h, skills=[f"skill{i}" for i in range(20)]).status_code == 200


def test_old_clients_that_leave_the_fields_out_change_nothing(client, db, world):
    h = world["seeker"]
    put_prefs(client, h, experience_level="senior", skills=["Java"])
    r = put_prefs(client, h, locations=["경기"], job_keywords=["백엔드"])  # a client that does not know the new fields
    assert r.status_code == 200
    assert r.json()["experience_level"] == "senior" and r.json()["skills"] == ["Java"]
    assert r.json()["locations"] == ["경기"]
    cleared = put_prefs(client, h, experience_level=None, skills=[]).json()
    assert cleared["experience_level"] is None and cleared["skills"] == []


def test_profile_skills_go_with_the_preferences_and_the_user(client, db, world):
    h = world["seeker"]
    put_prefs(client, h, skills=["Java", "Python"])
    seeker_id = db.scalar(select(User.id).where(User.email == "me@seeker.test"))
    db.commit()
    if db.bind.dialect.name == "sqlite":
        db.execute(text("PRAGMA foreign_keys=ON"))  # SQLite enforces ON DELETE CASCADE only with this
    assert db.scalar(select(func.count()).select_from(SeekerProfileSkill)) == 2
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": seeker_id})
    db.commit()
    assert db.scalar(select(func.count()).select_from(SeekerPreference)) == 0
    assert db.scalar(select(func.count()).select_from(SeekerProfileSkill)) == 0


# ── Display only: no score may change (D46, AI rule 14) ──


def _apply_with_prefs(client, db, job_id, email, prefs):
    h = seeker(db, email, "김지원")  # same name: same masking
    assert put_prefs(client, h, **prefs).status_code == 200
    cv = upload(client, h).json()
    client.put(f"/api/cv/{cv['id']}", json={"profile": cv["profile"], "confirm": True}, headers=h)
    app_id = client.post(f"/api/jobs/{job_id}/applications", headers=h).json()["id"]
    return h, cv["id"], app_id


def test_experience_level_and_skills_change_no_score(client, db, world, job):
    base = {"locations": ["서울"], "employment_types": ["full_time"], "job_keywords": ["백엔드"]}
    _, plain_cv, plain_app = _apply_with_prefs(client, db, job, "plain@seeker.test", base)
    _, extra_cv, extra_app = _apply_with_prefs(
        client, db, job, "extra@seeker.test", {**base, "experience_level": "senior", "skills": ["Java", "Spring", "Kubernetes", "Rust"]}
    )

    # Fit and every criterion score are identical
    rows = {r["application_id"]: r for r in client.get(f"/api/jobs/{job}/applications", headers=world["recruiter"]).json()["items"]}
    assert rows[extra_app]["fit"] == rows[plain_app]["fit"] is not None
    assert rows[extra_app]["experience_months"] == rows[plain_app]["experience_months"]
    scores = {ev.cv_profile_id: sorted((s.job_criteria_id, s.score, s.level) for s in ev.scores) for ev in db.query(Evaluation)}
    confirmed = {p.seeker_id: p.id for p in db.query(CvProfile).filter(CvProfile.confirmed_at.isnot(None))}
    ids = {u.email: u.id for u in db.query(User)}
    assert scores[confirmed[ids["extra@seeker.test"]]] == scores[confirmed[ids["plain@seeker.test"]]]

    # Pref sees exactly the same preferences, so it gives the same score
    prefs = {email: preference_service.to_preferences(preference_service._find(db, ids[email])) for email in ("plain@seeker.test", "extra@seeker.test")}
    assert prefs["plain@seeker.test"] == prefs["extra@seeker.test"]
    facts = JobFacts(title="백엔드 개발자", description="Java", location="서울 강남구", employment_type="full_time")
    assert pref_score(prefs["plain@seeker.test"], facts) == pref_score(prefs["extra@seeker.test"], facts)


def test_no_scoring_code_reads_the_display_only_fields():
    """Static guard: the scorers and the services that compute Fit, Pref, recommendations and talent never name
    the self-declared fields."""
    files = [*sorted((ROOT / "ai").rglob("*.py"))] + [
        ROOT / "backend/app/services" / f
        for f in ("evaluation_service.py", "recommendation_service.py", "talent_service.py", "application_service.py", "career_service.py")
    ]
    pattern = re.compile(r"experience_level|profile_skills|SeekerProfileSkill")
    hits = [f"{p.relative_to(ROOT)}" for p in files if "tests" not in p.parts and pattern.search(p.read_text(encoding="utf-8"))]
    assert hits == []
