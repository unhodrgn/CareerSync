"""API test fixtures. Uses SQLite in memory by default; set TEST_DATABASE_URL to run against PostgreSQL."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Company, JobPosting, User


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL", "sqlite://")
    kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool} if url.startswith("sqlite") else {}
    engine = create_engine(url, **kwargs)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


PASSWORD = "secret123"
_PASSWORD_HASH = hash_password(PASSWORD)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def world(db):
    """Two companies with one recruiter each, a seeker, and draft jobs."""
    acme, other = Company(name="Acme"), Company(name="Other")
    db.add_all([acme, other])
    db.flush()
    recruiter = User(email="hr@acme.test", password_hash=_PASSWORD_HASH, role="company", company_id=acme.id)
    rival = User(email="hr@other.test", password_hash=_PASSWORD_HASH, role="company", company_id=other.id)
    seeker = User(email="me@seeker.test", password_hash=_PASSWORD_HASH, role="seeker")
    jd = "Java/Spring 백엔드 API 개발"
    job = JobPosting(company_id=acme.id, title="Backend Engineer", description=jd)
    job2 = JobPosting(company_id=acme.id, title="Platform Engineer", description=jd)
    rival_job = JobPosting(company_id=other.id, title="Rival job", description=jd)
    db.add_all([recruiter, rival, seeker, job, job2, rival_job])
    db.commit()
    return {
        "job": job,
        "job2": job2,
        "rival_job": rival_job,
        "acme": acme,
        "recruiter": auth(recruiter),
        "rival": auth(rival),
        "seeker": auth(seeker),
    }
