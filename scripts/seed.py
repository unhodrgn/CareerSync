"""Seed demo data: two companies with recruiters, jobs with criteria, and three seekers.

- seeker@demo.test: no CV and no preferences, for uploading data/demo/demo_cv.pdf live.
- seeker2@demo.test: that CV uploaded and confirmed, preferences Seoul · full_time, in the talent pool.
- seeker3@demo.test: that CV uploaded and confirmed only (no preferences, not in the talent pool): a second account for the live checks of
  the practice interview, which need a confirmed CV and allow 3 sessions per seeker per day.

All seekers are named like the person in the demo CV, so the name is masked before any LLM call.
The seed never calls the LLM: it forces AI_MODE=rules for its own process, so the CV is structured by rules
and no API key is needed, whatever mode the app runs in.

Run after migrations:  cd backend && alembic upgrade head && python ../scripts/seed.py
Safe to run again: accounts that already exist are skipped (seeker2 and seeker3 only get what they are still missing).
All accounts use the password printed below.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

# Before anything asks for the LLM client (it reads AI_MODE on every call); also wins over .env
os.environ["AI_MODE"] = "rules"

from sqlalchemy import func, select  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Company, User  # noqa: E402
from app.schemas.auth import RegisterIn  # noqa: E402
from app.schemas.company import CompanyUpdate  # noqa: E402
from app.schemas.criteria import CriterionIn  # noqa: E402
from app.schemas.job import JobCreate  # noqa: E402
from app.schemas.preference import PreferenceIn  # noqa: E402
from app.services import auth_service, criteria_service, cv_service, job_service, preference_service  # noqa: E402
from make_demo_cv import CV_NAME, CV_PATH  # noqa: E402  (scripts/ is on sys.path when this file runs)

PASSWORD = "demo1234"

COMPANIES = [
    {
        "email": "hr@nextcode.test",
        "display_name": "NextCode HR Team",
        "profile": CompanyUpdate(
            name="NextCode",
            intro="A B2B startup building ERP SaaS for small and mid-sized businesses.",
            talent_profile="Engineers who frame problems independently and grow together through code reviews",
        ),
        "jobs": [
            (
                JobCreate(
                    title="Backend Developer (Java/Spring)",
                    description="Build and operate Spring Boot ERP APIs, optimize PostgreSQL queries, and design batch jobs.",
                    min_experience_years=2,
                    location="Seoul, Gangnam-gu",
                    salary_note="Per company policy",
                ),
                [
                    CriterionIn(name="Java proficiency", category="skill", weight=30, description="Java 17, collections and concurrency fundamentals"),
                    CriterionIn(name="Spring experience", category="skill", weight=25, description="Production experience with Spring Boot and JPA"),
                    CriterionIn(name="Database experience", category="skill", weight=20, description="PostgreSQL query tuning and index design"),
                    CriterionIn(name="Project experience", category="project", weight=15, description="Designing and deploying an API server end to end"),
                    CriterionIn(name="Relevant certification", category="certificate", weight=10, description="OCJP, SQLD, or equivalent"),
                ],
                True,
            ),
            (
                JobCreate(
                    title="Frontend Developer (React)",
                    description="Build ERP admin interfaces using React and TypeScript.",
                    employment_type="contract",
                    location="Seoul, Gangnam-gu",
                ),
                [
                    CriterionIn(name="React experience", category="skill", weight=50),
                    CriterionIn(name="TypeScript", category="skill", weight=30),
                    CriterionIn(name="UI project experience", category="project", weight=20),
                ],
                False,  # left as a draft
            ),
        ],
    },
    {
        "email": "hr@cloudlab.test",
        "display_name": "CloudLab Recruiting",
        "profile": CompanyUpdate(
            name="CloudLab",
            intro="We build data pipelines and AI agent solutions.",
            talent_profile="Data-driven builders who learn new technologies quickly",
        ),
        "jobs": [
            (
                JobCreate(
                    title="Data Engineer",
                    description="Build Airflow and Spark data pipelines and operate workloads on AWS.",
                    min_experience_years=None,
                    location="Seongnam, Pangyo",
                    salary_note="Negotiable",
                ),
                [
                    CriterionIn(name="Python proficiency", category="skill", weight=30),
                    CriterionIn(name="Data pipeline experience", category="experience", weight=30),
                    CriterionIn(name="AWS cloud operations", category="skill", weight=20),
                    CriterionIn(name="Computer Science major", category="education", weight=20),
                ],
                True,
            ),
        ],
    },
]

SEEKER = {"email": "seeker@demo.test", "display_name": CV_NAME}
SEEKER_WITH_CV = {"email": "seeker2@demo.test", "display_name": CV_NAME}
SEEKER_WITH_CV_PREFERENCES = PreferenceIn(locations=["Seoul"], employment_types=["full_time"], profile_public=True)
SEEKER_WITH_CV_ONLY = {"email": "seeker3@demo.test", "display_name": CV_NAME}


def _exists(db, email: str) -> bool:
    return db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None


def _register(db, email: str, display_name: str, role: str, company_name: str | None = None) -> User:
    return auth_service.register(
        db,
        RegisterIn(
            email=email,
            password=PASSWORD,
            role=role,
            display_name=display_name,
            company_name=company_name,
            consent_privacy=True,
            consent_ai=True,
        ),
    )


def _seed_seeker_with_cv(db, spec: dict, preferences: PreferenceIn | None) -> None:
    """A seeker with the demo CV uploaded and confirmed as in the app (a confirm saves a new version), then,
    if given, preferences. Each step runs only if still missing, so a run that stopped halfway is completed
    by the next one."""
    email = spec["email"]
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = _register(db, email, spec["display_name"], "seeker")
        print(f"added {email}")
    else:
        print(f"skip  {email} (exists)")
    try:
        profile = cv_service.latest(db, user)
    except AppError:  # CV_NOT_FOUND
        profile = cv_service.upload(db, user, CV_PATH.name, CV_PATH.read_bytes())
        print(f"cv    {email} · {CV_PATH.name} ({profile.method})")
    if profile.confirmed_at is None:
        profile = cv_service.update(db, user, profile.id, cv_service.to_profile_data(profile), confirm=True)
        print(f"cv    {email} · confirmed as version {profile.version}")
    if preferences is not None and preference_service.get_mine(db, user) is None:
        preference_service.replace_mine(db, user, preferences)
        print(f"pref  {email} · Seoul, full_time, talent pool on")


def main() -> None:
    db = SessionLocal()
    try:
        for spec in COMPANIES:
            if _exists(db, spec["email"]):
                print(f"skip  {spec['email']} (exists)")
                continue
            user = _register(db, spec["email"], spec["display_name"], "company", spec["profile"].name)
            company = db.get(Company, user.company_id)
            company.intro = spec["profile"].intro
            company.talent_profile = spec["profile"].talent_profile
            db.commit()
            for job_in, criteria, publish in spec["jobs"]:
                job = job_service.create(db, user, job_in)
                criteria_service.replace_set(db, job, criteria)
                if publish:
                    job_service.publish(db, job)
                print(f"job   {company.name} · {job.title} ({job.status})")
            print(f"added {spec['email']}")
        if _exists(db, SEEKER["email"]):
            print(f"skip  {SEEKER['email']} (exists)")
        else:
            _register(db, SEEKER["email"], SEEKER["display_name"], "seeker")
            print(f"added {SEEKER['email']}")
        _seed_seeker_with_cv(db, SEEKER_WITH_CV, SEEKER_WITH_CV_PREFERENCES)
        _seed_seeker_with_cv(db, SEEKER_WITH_CV_ONLY, None)
        print(f"\nAll demo accounts use the password: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
