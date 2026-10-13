"""Issue 3: what a seeker edits in the structured CV never raises their score or what the company sees."""
from datetime import date

from ai.parsing.extract import verified_experience
from app.models import CvProfile, Evaluation

from .test_applications_api import job, seeker, upload  # noqa: F401  (job is a fixture)


def _apply_with(client, db, job_id, email, edit=None):
    h = seeker(db, email, "김지원")
    cv = upload(client, h).json()
    profile = edit(cv["profile"]) if edit else cv["profile"]
    confirmed = client.put(f"/api/cv/{cv['id']}", json={"profile": profile, "confirm": True}, headers=h)
    assert confirmed.status_code == 200
    app_id = client.post(f"/api/jobs/{job_id}/applications", headers=h).json()["id"]
    return confirmed.json(), app_id


def _stretch_dates(profile):
    for e in profile["experiences"]:
        e["start"] = "2005-01"
    profile["skills"] = [*profile["skills"], "Rust"]
    return profile


def test_edited_dates_change_neither_the_score_nor_the_months_the_company_sees(client, db, world, job):
    plain_cv, plain_app = _apply_with(client, db, job, "plain@seeker.test")
    edited_cv, edited_app = _apply_with(client, db, job, "edited@seeker.test", _stretch_dates)

    # The seeker's own view follows their edits
    assert edited_cv["total_experience_months"] > plain_cv["total_experience_months"]

    # The company's view and the scores follow the uploaded CV text
    rows = {r["application_id"]: r for r in client.get(f"/api/jobs/{job}/applications", headers=world["recruiter"]).json()["items"]}
    assert rows[edited_app]["experience_months"] == rows[plain_app]["experience_months"]
    row = db.get(CvProfile, edited_cv["id"])
    expected, _ = verified_experience(row.document.masked_text, [], date.today().strftime("%Y-%m"))
    assert rows[edited_app]["experience_months"] == expected < edited_cv["total_experience_months"]
    assert rows[edited_app]["fit"] == rows[plain_app]["fit"]
    scores = {ev.cv_profile_id: sorted((s.job_criteria_id, s.score) for s in ev.scores) for ev in db.query(Evaluation)}
    assert scores[edited_cv["id"]] == scores[plain_cv["id"]]
