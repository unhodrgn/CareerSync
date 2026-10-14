"""Company running projects: CRUD, public display, limits (docs/DECISIONS.md D23)."""
import os
import threading

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.models import CompanyProject, CompanyProjectTech, User
from app.schemas.company import CompanyProjectIn
from app.services import company_project_service

URL = "/api/companies/me/projects"
BODY = {"name": "결제 시스템 MSA 전환", "description": "모놀리식 결제 서버를 서비스 단위로 분리", "techs": ["java", "Spring Boot", "Kafka"]}


def _create(client, h, **override):
    return client.post(URL, json={**BODY, **override}, headers=h)


def test_crud(client, world):
    h = world["recruiter"]
    r = _create(client, h)
    assert r.status_code == 201, r.json()
    created = r.json()
    assert set(created) == {"id", "name", "description", "techs", "created_at", "updated_at"}
    assert created["name"] == BODY["name"] and created["description"] == BODY["description"]
    assert "Java" in created["techs"] and "Kafka" in created["techs"]  # normalized with the skills dictionary
    second = _create(client, h, name="사내 데이터 플랫폼", techs=[]).json()
    assert [p["id"] for p in client.get(URL, headers=h).json()] == [created["id"], second["id"]]

    pid = created["id"]
    r = client.put(f"{URL}/{pid}", json={"name": "  결제   v2 ", "description": "", "techs": ["Kafka", "Go"]}, headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "결제 v2" and r.json()["description"] == "" and r.json()["techs"] == ["Kafka", "Go"]

    assert client.delete(f"{URL}/{pid}", headers=h).status_code == 204
    assert [p["id"] for p in client.get(URL, headers=h).json()] == [second["id"]]
    assert client.delete(f"{URL}/{pid}", headers=h).status_code == 404


def test_replacing_techs_with_the_same_names_works(client, world, db):
    h = world["recruiter"]
    pid = _create(client, h, techs=["Java", "Kafka"]).json()["id"]
    r = client.put(f"{URL}/{pid}", json={**BODY, "techs": ["Kafka", "Java"]}, headers=h)
    assert r.status_code == 200 and r.json()["techs"] == ["Kafka", "Java"]
    assert len(db.scalars(select(CompanyProjectTech)).all()) == 2


def test_duplicate_techs_are_merged_ignoring_case(client, world):
    r = _create(client, world["recruiter"], techs=["Kafka", "kafka", " KAFKA ", "Redis"])
    assert r.json()["techs"] == ["Kafka", "Redis"]


def test_only_the_owner_company(client, world):
    pid = _create(client, world["recruiter"]).json()["id"]
    for method in ("put", "delete"):
        kwargs = {"json": BODY} if method == "put" else {}
        r = getattr(client, method)(f"{URL}/{pid}", headers=world["rival"], **kwargs)
        assert r.status_code == 404 and r.json()["code"] == "PROJECT_NOT_FOUND"
    assert client.get(URL, headers=world["rival"]).json() == []
    assert client.get(URL, headers=world["seeker"]).status_code == 403
    assert _create(client, world["seeker"]).status_code == 403
    assert client.get(URL).status_code == 401


def test_public_profile_shows_projects(client, world):
    _create(client, world["recruiter"])
    r = client.get(f"/api/companies/{world['acme'].id}", headers=world["seeker"])
    assert r.status_code == 200
    [project] = r.json()["projects"]
    assert project["name"] == BODY["name"] and "Kafka" in project["techs"]
    # The other company's profile does not list them
    other = client.get("/api/companies/me", headers=world["rival"]).json()["id"]
    assert client.get(f"/api/companies/{other}", headers=world["seeker"]).json()["projects"] == []


@pytest.mark.parametrize(
    "override",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "가" * 201},
        {"description": "가" * 2001},
        {"techs": ["x"] * 21},
        {"techs": ["  "]},
        {"techs": ["가" * 101]},
    ],
)
def test_validation(client, world, override):
    assert _create(client, world["recruiter"], **override).status_code == 422


def test_limit_per_company(client, world, monkeypatch):
    monkeypatch.setattr(company_project_service, "MAX_PROJECTS", 2)
    h = world["recruiter"]
    assert _create(client, h).status_code == 201
    assert _create(client, h).status_code == 201
    r = _create(client, h)
    assert r.status_code == 409 and r.json()["code"] == "PROJECT_LIMIT"
    # Another company has its own limit
    assert _create(client, world["rival"]).status_code == 201


on_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)


@on_postgres
def test_pg_parallel_creates_respect_the_limit(db, world, monkeypatch):
    monkeypatch.setattr(company_project_service, "MAX_PROJECTS", 3)
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(6)
    outcomes, lock = [], threading.Lock()

    def run():
        session = sessions()
        try:
            user = session.scalars(select(User).where(User.email == "hr@acme.test")).one()
            barrier.wait()
            company_project_service.create(session, user, CompanyProjectIn(**BODY))
            result = "created"
        except AppError as e:
            result = e.code
        finally:
            session.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=run) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(60)
    assert sorted(outcomes) == ["PROJECT_LIMIT"] * 3 + ["created"] * 3
    assert len(db.scalars(select(CompanyProject)).all()) == 3
