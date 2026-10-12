"""D4: GET /api/jobs and GET /api/jobs/{job_id} work without login; everything else still needs a token."""
from datetime import date, timedelta

from app.core.security import create_access_token
from app.models import JobPosting

from .test_jobs_api import create, make_published


def _jobs(client, world, db):
    """Published, expired-published, closed and draft jobs of Acme."""
    h = world["recruiter"]
    live = make_published(client, h, title="게시 중")
    expired = make_published(client, h, title="마감 지남")
    closed = make_published(client, h, title="마감됨")
    assert client.post(f"/api/jobs/{closed['id']}/close", headers=h).status_code == 200
    db.get(JobPosting, expired["id"]).deadline = date.today() - timedelta(days=1)
    db.commit()
    return {"live": live["id"], "expired": expired["id"], "closed": closed["id"], "draft": world["job"].id}


def test_guest_list_shows_only_published_unexpired_jobs(client, world, db):
    jobs = _jobs(client, world, db)
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert [j["id"] for j in r.json()["items"]] == [jobs["live"]]
    assert r.json() == client.get("/api/jobs", headers=world["seeker"]).json()  # same body as logged in


def test_guest_detail(client, world, db):
    jobs = _jobs(client, world, db)
    r = client.get(f"/api/jobs/{jobs['live']}")
    assert r.status_code == 200
    assert r.json() == client.get(f"/api/jobs/{jobs['live']}", headers=world["seeker"]).json()
    for key in ("expired", "closed", "draft"):
        r = client.get(f"/api/jobs/{jobs[key]}")
        assert (r.status_code, r.json()["code"]) == (404, "JOB_NOT_FOUND"), key
    assert client.get("/api/jobs/999999").status_code == 404


def test_logged_in_detail_unchanged(client, world, db):
    jobs = _jobs(client, world, db)
    seeker, rival, owner = world["seeker"], world["rival"], world["recruiter"]
    expired = client.get(f"/api/jobs/{jobs['expired']}", headers=seeker)
    assert expired.status_code == 200 and expired.json()["expired"] is True
    for headers in (seeker, rival):
        assert client.get(f"/api/jobs/{jobs['draft']}", headers=headers).status_code == 404
        assert client.get(f"/api/jobs/{jobs['closed']}", headers=headers).status_code == 404
    for key in ("draft", "closed", "expired", "live"):
        assert client.get(f"/api/jobs/{jobs[key]}", headers=owner).status_code == 200, key


def test_bad_token_is_401_not_guest(client, world, db):
    jobs = _jobs(client, world, db)
    good = world["seeker"]["Authorization"]
    bad_tokens = [
        f"Bearer {create_access_token(1, expires_minutes=-1)}",  # expired
        good[:-2] + ("aa" if not good.endswith("aa") else "bb"),  # tampered
        f"Bearer {create_access_token(999999)}",  # user does not exist
    ]
    for token in bad_tokens:
        for url in ("/api/jobs", f"/api/jobs/{jobs['live']}"):
            assert client.get(url, headers={"Authorization": token}).status_code == 401, (url, token)


def test_other_endpoints_still_need_login(client, world):
    job_id = world["job"].id
    calls = [
        ("POST", "/api/jobs"),
        ("GET", "/api/jobs/mine"),
        ("PATCH", f"/api/jobs/{job_id}"),
        ("DELETE", f"/api/jobs/{job_id}"),
        ("POST", f"/api/jobs/{job_id}/publish"),
        ("POST", f"/api/jobs/{job_id}/close"),
        ("POST", f"/api/jobs/{job_id}/analyze"),
        ("GET", f"/api/jobs/{job_id}/criteria"),
        ("PUT", f"/api/jobs/{job_id}/criteria"),
        ("GET", f"/api/jobs/{job_id}/applications"),
        ("POST", f"/api/jobs/{job_id}/applications"),
        ("GET", "/api/cv/me"),
        ("GET", "/api/users/me"),
    ]
    for method, url in calls:
        assert client.request(method, url).status_code == 401, (method, url)
