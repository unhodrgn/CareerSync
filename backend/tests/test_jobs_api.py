from datetime import date, timedelta

from .test_criteria_api import PLAN_EXAMPLE

NEW_JOB = {
    "title": "백엔드 개발자",
    "description": "Java/Spring 기반 API 개발",
    "employment_type": "full_time",
    "min_experience_years": 2,
    "location": "서울 강남구",
    "salary_note": "회사 내규",
}


def create(client, headers, **overrides):
    return client.post("/api/jobs", json={**NEW_JOB, **overrides}, headers=headers)


def make_published(client, headers, **overrides):
    job = create(client, headers, **overrides).json()
    client.put(f"/api/jobs/{job['id']}/criteria", json={"items": PLAN_EXAMPLE}, headers=headers)
    r = client.post(f"/api/jobs/{job['id']}/publish", headers=headers)
    assert r.status_code == 200, r.json()
    return r.json()


def test_create_draft(client, world):
    r = create(client, world["recruiter"])
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "draft" and job["company_name"] == "Acme"
    assert job["criteria_count"] == 0 and job["published_at"] is None
    assert create(client, world["seeker"]).status_code == 403


def test_lifecycle(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    assert job["status"] == "published" and job["published_at"] and job["criteria_count"] == 5
    r = client.post(f"/api/jobs/{job['id']}/close", headers=h)
    assert r.json()["status"] == "closed" and r.json()["closed_at"]
    assert client.post(f"/api/jobs/{job['id']}/close", headers=h).status_code == 409
    assert client.post(f"/api/jobs/{job['id']}/publish", headers=h).status_code == 409
    assert client.patch(f"/api/jobs/{job['id']}", json={"location": "판교"}, headers=h).json()["code"] == "JOB_CLOSED"


def test_publish_needs_description(client, world):
    job = create(client, world["recruiter"], description="").json()
    client.put(f"/api/jobs/{job['id']}/criteria", json={"items": PLAN_EXAMPLE}, headers=world["recruiter"])
    r = client.post(f"/api/jobs/{job['id']}/publish", headers=world["recruiter"])
    assert r.status_code == 422 and r.json()["code"] == "JOB_INCOMPLETE"


def test_draft_edit_any_field(client, world):
    job = create(client, world["recruiter"]).json()
    patch = {"title": "시니어 백엔드 개발자", "min_experience_years": None, "employment_type": "contract"}
    r = client.patch(f"/api/jobs/{job['id']}", json=patch, headers=world["recruiter"])
    assert r.status_code == 200
    assert {k: r.json()[k] for k in patch} == patch
    assert r.json()["location"] == NEW_JOB["location"]  # untouched


def test_published_locks_scored_fields(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    url = f"/api/jobs/{job['id']}"
    r = client.patch(url, json={"title": "변경", "description": "변경", "location": "판교"}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "JOB_FIELD_LOCKED" and r.json()["fields"] == ["description", "title"]
    assert client.get(url, headers=h).json()["location"] == NEW_JOB["location"]  # nothing applied

    deadline = (date.today() + timedelta(days=14)).isoformat()
    r = client.patch(url, json={"location": "판교", "salary_note": "5000만원 이상", "deadline": deadline}, headers=h)
    assert r.status_code == 200
    assert (r.json()["location"], r.json()["deadline"]) == ("판교", deadline)


def test_required_fields_cannot_be_nulled(client, world):
    job = create(client, world["recruiter"]).json()
    r = client.patch(f"/api/jobs/{job['id']}", json={"title": None}, headers=world["recruiter"])
    assert r.status_code == 422


def test_deadline_cannot_be_past(client, world):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    r = create(client, world["recruiter"], deadline=yesterday)
    assert r.status_code == 422 and r.json()["code"] == "DEADLINE_IN_PAST"


def test_delete_only_drafts(client, world):
    h = world["recruiter"]
    draft = create(client, h).json()
    assert client.delete(f"/api/jobs/{draft['id']}", headers=h).status_code == 204
    assert client.get(f"/api/jobs/{draft['id']}", headers=h).status_code == 404
    published = make_published(client, h)
    assert client.delete(f"/api/jobs/{published['id']}", headers=h).status_code == 409


def test_visibility(client, world):
    h = world["recruiter"]
    draft = create(client, h).json()
    published = make_published(client, h)
    assert client.get(f"/api/jobs/{draft['id']}", headers=world["seeker"]).status_code == 404
    assert client.get(f"/api/jobs/{draft['id']}", headers=world["rival"]).status_code == 404
    assert client.get(f"/api/jobs/{draft['id']}", headers=h).status_code == 200
    assert client.get(f"/api/jobs/{published['id']}", headers=world["seeker"]).status_code == 200
    client.post(f"/api/jobs/{published['id']}/close", headers=h)
    assert client.get(f"/api/jobs/{published['id']}", headers=world["seeker"]).status_code == 404
    assert client.get(f"/api/jobs/{published['id']}", headers=h).status_code == 200


def test_other_company_cannot_write(client, world):
    job = create(client, world["recruiter"]).json()
    url = f"/api/jobs/{job['id']}"
    r = world["rival"]
    assert client.patch(url, json={"title": "x"}, headers=r).status_code == 404
    assert client.delete(url, headers=r).status_code == 404
    assert client.post(f"{url}/publish", headers=r).status_code == 404
    assert client.post(f"{url}/close", headers=r).status_code == 404


def test_public_list(client, world, db):
    h = world["recruiter"]
    a = make_published(client, h, title="백엔드 개발자")
    b = make_published(client, h, title="프론트엔드 개발자")
    create(client, h, title="작성 중인 공고")
    expiring = make_published(client, h, title="곧 마감", deadline=date.today().isoformat())

    page = client.get("/api/jobs", headers=world["seeker"]).json()
    assert [j["id"] for j in page["items"]] == [expiring["id"], b["id"], a["id"]]  # newest first, no draft
    assert page["total"] == 3 and page["items"][0]["criteria_count"] == 5

    assert [j["id"] for j in client.get("/api/jobs?q=프론트", headers=world["seeker"]).json()["items"]] == [b["id"]]
    paged = client.get("/api/jobs?limit=1&offset=1", headers=world["seeker"]).json()
    assert paged["total"] == 3 and [j["id"] for j in paged["items"]] == [b["id"]]

    # A passed deadline hides the job but keeps its status
    from app.models import JobPosting

    db.get(JobPosting, expiring["id"]).deadline = date.today() - timedelta(days=1)
    db.commit()
    assert expiring["id"] not in [j["id"] for j in client.get("/api/jobs", headers=world["seeker"]).json()["items"]]
    mine = {j["id"]: j for j in client.get("/api/jobs/mine", headers=h).json()}
    assert mine[expiring["id"]]["status"] == "published" and mine[expiring["id"]]["expired"] is True


def test_mine(client, world):
    h = world["recruiter"]
    create(client, h, title="초안")
    make_published(client, h, title="게시")
    mine = client.get("/api/jobs/mine", headers=h).json()
    # fixture jobs (2 drafts) + these two
    assert {j["status"] for j in mine} == {"draft", "published"} and len(mine) == 4
    assert all(j["company_id"] == world["acme"].id for j in mine)
    assert client.get("/api/jobs/mine", headers=world["seeker"]).status_code == 403
