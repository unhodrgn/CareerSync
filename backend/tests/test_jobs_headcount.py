"""모집 인원 (headcount, D47) on jobs, and the draft → criteria → publish → close flow the company pages use."""
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import JobPosting

from .test_criteria_api import PLAN_EXAMPLE
from .test_jobs_api import NEW_JOB, create, make_published


def test_headcount_is_optional_and_returned_everywhere(client, world):
    h = world["recruiter"]
    job = create(client, h).json()
    assert job["headcount"] == NEW_JOB["headcount"] == 2
    assert client.get(f"/api/jobs/{job['id']}", headers=h).json()["headcount"] == 2
    without = client.post("/api/jobs", json={k: v for k, v in NEW_JOB.items() if k != "headcount"}, headers=h).json()
    assert without["headcount"] is None
    published = make_published(client, h, headcount=5)
    assert client.get(f"/api/jobs/{published['id']}", headers=world["seeker"]).json()["headcount"] == 5
    assert client.get(f"/api/jobs/{published['id']}").json()["headcount"] == 5  # public, like the rest of the posting


@pytest.mark.parametrize("value, status", [(0, 422), (1, 201), (999, 201), (1000, 422), (-1, 422), ("many", 422)])
def test_headcount_range_on_create(client, world, value, status):
    assert create(client, world["recruiter"], headcount=value).status_code == status


def test_headcount_on_draft_update(client, world):
    h = world["recruiter"]
    url = f"/api/jobs/{create(client, h).json()['id']}"
    assert client.patch(url, json={"headcount": 10}, headers=h).json()["headcount"] == 10
    assert client.patch(url, json={"title": "다른 제목"}, headers=h).json()["headcount"] == 10  # left out = unchanged
    assert client.patch(url, json={"headcount": None}, headers=h).json()["headcount"] is None  # null clears it
    for bad in (0, 1000):
        r = client.patch(url, json={"headcount": bad}, headers=h)
        assert r.status_code == 422
    assert client.get(url, headers=h).json()["headcount"] is None


def test_headcount_is_locked_after_publish(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    url = f"/api/jobs/{job['id']}"
    r = client.patch(url, json={"headcount": 9, "location": "판교"}, headers=h)
    assert (r.status_code, r.json()["code"], r.json()["fields"]) == (409, "JOB_FIELD_LOCKED", ["headcount"])
    assert client.get(url, headers=h).json()["headcount"] == 2  # nothing applied
    client.post(f"{url}/close", headers=h)
    assert client.patch(url, json={"headcount": 9}, headers=h).json()["code"] == "JOB_CLOSED"


def test_headcount_check_constraint_in_the_database(db, world):
    db.add(JobPosting(company_id=world["acme"].id, title="x", headcount=1000))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_headcount_is_not_a_scoring_input():
    # Scoring reads the job through JobContext / JobFacts only; neither carries headcount
    from dataclasses import fields

    from ai.scoring.pref import JobFacts
    from ai.scoring.types import JobContext

    assert "headcount" not in {f.name for f in fields(JobFacts)} | {f.name for f in fields(JobContext)}


# ── Gaps in the draft / criteria / publish / close flow ──


def test_publish_reports_what_is_missing_in_order(client, world):
    h = world["recruiter"]
    job = create(client, h, description="", category=None).json()
    url = f"/api/jobs/{job['id']}"
    r = client.post(f"{url}/publish", headers=h)
    assert (r.status_code, r.json()["code"], r.json()["fields"]) == (422, "JOB_INCOMPLETE", ["description"])
    client.patch(url, json={"description": "Java/Spring API 개발"}, headers=h)
    r = client.post(f"{url}/publish", headers=h)
    assert (r.status_code, r.json()["code"], r.json()["fields"]) == (422, "FIELD_REQUIRED", ["category"])
    client.patch(url, json={"category": "dev"}, headers=h)
    r = client.post(f"{url}/publish", headers=h)
    assert (r.status_code, r.json()["code"], r.json()["count"]) == (422, "CRITERIA_COUNT_INVALID", 0)
    client.put(f"{url}/criteria", json={"items": PLAN_EXAMPLE}, headers=h)
    assert client.post(f"{url}/publish", headers=h).json()["status"] == "published"


def test_a_draft_whose_deadline_passed_cannot_be_published(client, world, db):
    h = world["recruiter"]
    job = create(client, h, deadline=(date.today() + timedelta(days=1)).isoformat()).json()
    client.put(f"/api/jobs/{job['id']}/criteria", json={"items": PLAN_EXAMPLE}, headers=h)
    db.get(JobPosting, job["id"]).deadline = date.today() - timedelta(days=1)
    db.commit()
    r = client.post(f"/api/jobs/{job['id']}/publish", headers=h)
    assert (r.status_code, r.json()["code"]) == (422, "DEADLINE_IN_PAST")


def test_close_only_published_and_delete_only_drafts(client, world):
    h = world["recruiter"]
    draft = create(client, h).json()
    r = client.post(f"/api/jobs/{draft['id']}/close", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "JOB_NOT_PUBLISHED")
    published = make_published(client, h)
    client.post(f"/api/jobs/{published['id']}/close", headers=h)
    r = client.delete(f"/api/jobs/{published['id']}", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "JOB_NOT_DRAFT")


def test_closed_job_leaves_public_listings_but_stays_in_mine(client, world):
    h = world["recruiter"]
    job = make_published(client, h, title="곧 닫는 공고")
    assert job["id"] in [j["id"] for j in client.get("/api/jobs").json()["items"]]
    client.post(f"/api/jobs/{job['id']}/close", headers=h)
    assert job["id"] not in [j["id"] for j in client.get("/api/jobs", headers=world["seeker"]).json()["items"]]
    assert client.get(f"/api/jobs/{job['id']}/criteria", headers=world["seeker"]).status_code == 404
    mine = {j["id"]: j for j in client.get("/api/jobs/mine", headers=h).json()}
    assert mine[job["id"]]["status"] == "closed"


def test_weights_stay_with_the_owner(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    url = f"/api/jobs/{job['id']}/criteria"
    assert all("weight" in c for c in client.get(url, headers=h).json()["items"])
    for headers in (world["seeker"], world["rival"], None):
        r = client.get(url, headers=headers)
        if headers is world["rival"]:
            assert r.status_code == 404  # another company's job is not readable through the owner view
            continue
        assert r.status_code == 200 and not any("weight" in c for c in r.json()["items"])
