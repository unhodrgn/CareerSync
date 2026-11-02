"""Saved jobs (공고 저장, docs/DECISIONS.md D45): seeker only, idempotent, never an evaluation, never shown to companies."""
from datetime import date, timedelta

from sqlalchemy import func, select, text

from app.models import Evaluation, JobPosting, SavedJob, User
from app.services import evaluation_service

from .test_applications_api import seeker
from .test_jobs_api import make_published


def save(client, job_id, headers):
    return client.put(f"/api/jobs/{job_id}/save", headers=headers)


def unsave(client, job_id, headers):
    return client.delete(f"/api/jobs/{job_id}/save", headers=headers)


def mine(client, headers):
    r = client.get("/api/saved-jobs/mine", headers=headers)
    assert r.status_code == 200, r.json()
    return r.json()


def test_seeker_only(client, world):
    job = make_published(client, world["recruiter"])
    for headers in (world["recruiter"], world["rival"]):
        for r in (save(client, job["id"], headers), unsave(client, job["id"], headers), client.get("/api/saved-jobs/mine", headers=headers)):
            assert r.status_code == 403 and r.json()["code"] == "SEEKER_ONLY"
    for r in (save(client, job["id"], {}), unsave(client, job["id"], {}), client.get("/api/saved-jobs/mine")):
        assert r.status_code == 401


def test_save_and_remove_are_idempotent(client, world):
    s, job = world["seeker"], make_published(client, world["recruiter"])
    assert save(client, job["id"], s).status_code == 204
    assert save(client, job["id"], s).status_code == 204
    saved = mine(client, s)
    assert [j["id"] for j in saved] == [job["id"]]
    assert saved[0]["title"] == job["title"] and saved[0]["category"] == "dev" and saved[0]["tags"]
    assert unsave(client, job["id"], s).status_code == 204
    assert unsave(client, job["id"], s).status_code == 204
    assert unsave(client, 9999, s).status_code == 204
    assert mine(client, s) == []


def test_saving_needs_a_job_the_seeker_can_see(client, world, db):
    s = world["seeker"]
    draft = world["job"].id  # never published
    assert save(client, draft, s).json()["code"] == "JOB_NOT_FOUND"
    assert save(client, 9999, s).status_code == 404
    closed = make_published(client, world["recruiter"], title="마감된 공고")
    client.post(f"/api/jobs/{closed['id']}/close", headers=world["recruiter"])
    assert save(client, closed["id"], s).status_code == 404
    # A published job past its deadline is still visible to signed-in users, so it can be saved
    expired = make_published(client, world["recruiter"], title="기한 지난 공고", deadline=str(date.today() + timedelta(days=1)))
    db.query(JobPosting).filter_by(id=expired["id"]).update({"deadline": date.today() - timedelta(days=1)})
    db.commit()
    assert save(client, expired["id"], s).status_code == 204


def test_closed_and_expired_jobs_stay_in_the_list_newest_saved_first(client, world, db):
    s, h = world["seeker"], world["recruiter"]
    first = make_published(client, h, title="첫 번째")
    second = make_published(client, h, title="두 번째", deadline=str(date.today() + timedelta(days=1)))
    save(client, first["id"], s)
    save(client, second["id"], s)
    assert [j["id"] for j in mine(client, s)] == [second["id"], first["id"]]
    client.post(f"/api/jobs/{first['id']}/close", headers=h)
    db.query(JobPosting).filter_by(id=second["id"]).update({"deadline": date.today() - timedelta(days=1)})
    db.commit()
    saved = {j["id"]: j for j in mine(client, s)}
    assert saved[first["id"]]["status"] == "closed"
    assert saved[second["id"]]["status"] == "published" and saved[second["id"]]["expired"] is True
    # Removing still works for a job the seeker can no longer open
    assert unsave(client, first["id"], s).status_code == 204
    assert [j["id"] for j in mine(client, s)] == [second["id"]]


def test_saved_jobs_are_per_seeker(client, world, db):
    other = seeker(db, "other@seeker.test", "박다른")
    job = make_published(client, world["recruiter"])
    save(client, job["id"], world["seeker"])
    assert mine(client, other) == []


def test_rows_go_with_the_user_or_the_job(client, world, db):
    s = world["seeker"]
    a = make_published(client, world["recruiter"], title="A")
    b = make_published(client, world["recruiter"], title="B")
    save(client, a["id"], s)
    save(client, b["id"], s)
    seeker_id = db.scalar(select(User.id).where(User.email == "me@seeker.test"))
    db.commit()
    if db.bind.dialect.name == "sqlite":
        db.execute(text("PRAGMA foreign_keys=ON"))  # SQLite enforces ON DELETE CASCADE only with this
    db.execute(text("DELETE FROM job_postings WHERE id = :id"), {"id": a["id"]})
    db.commit()
    assert db.scalars(select(SavedJob.job_id).where(SavedJob.user_id == seeker_id)).all() == [b["id"]]
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": seeker_id})
    db.commit()
    assert db.scalar(select(func.count()).select_from(SavedJob)) == 0


def test_saving_never_creates_or_queues_an_evaluation(client, world, db, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("saving a job must not touch evaluations")

    for name in ("ensure", "claim", "queue"):
        monkeypatch.setattr(evaluation_service, name, forbidden)
    job = make_published(client, world["recruiter"])
    assert save(client, job["id"], world["seeker"]).status_code == 204
    mine(client, world["seeker"])
    assert unsave(client, job["id"], world["seeker"]).status_code == 204
    assert db.scalar(select(func.count()).select_from(Evaluation)) == 0


def test_companies_cannot_see_who_saved_their_jobs(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    save(client, job["id"], world["seeker"])
    bodies = [
        client.get(f"/api/jobs/{job['id']}", headers=h).text,
        client.get("/api/jobs/mine", headers=h).text,
        client.get("/api/jobs", headers=h).text,
        client.get(f"/api/jobs/{job['id']}/applications", headers=h).text,
        client.get(f"/api/jobs/{job['id']}/criteria", headers=h).text,
        client.get("/api/companies/me", headers=h).text,
    ]
    for body in bodies:
        assert "saved" not in body.lower() and "me@seeker.test" not in body
