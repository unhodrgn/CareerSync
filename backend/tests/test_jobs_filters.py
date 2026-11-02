"""Job category, public filters, wider search and computed tags (docs/DECISIONS.md D45)."""
from app.core.config import settings

from .test_criteria_api import PLAN_EXAMPLE
from .test_jobs_api import create, make_published


def ids(page: dict) -> list[int]:
    return [j["id"] for j in page["items"]]


def test_category_is_stored_and_returned_everywhere(client, world):
    h = world["recruiter"]
    job = create(client, h, category="data_ai").json()
    assert job["category"] == "data_ai"
    assert client.get(f"/api/jobs/{job['id']}", headers=h).json()["category"] == "data_ai"
    assert [j["category"] for j in client.get("/api/jobs/mine", headers=h).json() if j["id"] == job["id"]] == ["data_ai"]
    assert create(client, h, category="sales").status_code == 422


def test_publishing_requires_a_category(client, world):
    h = world["recruiter"]
    job = create(client, h, category=None).json()
    assert job["category"] is None
    client.put(f"/api/jobs/{job['id']}/criteria", json={"items": PLAN_EXAMPLE}, headers=h)
    r = client.post(f"/api/jobs/{job['id']}/publish", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "FIELD_REQUIRED" and r.json()["fields"] == ["category"]
    assert client.patch(f"/api/jobs/{job['id']}", json={"category": "dev"}, headers=h).json()["category"] == "dev"
    assert client.post(f"/api/jobs/{job['id']}/publish", headers=h).status_code == 200


def test_category_is_locked_after_publish(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    r = client.patch(f"/api/jobs/{job['id']}", json={"category": "design"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "JOB_FIELD_LOCKED" and r.json()["fields"] == ["category"]


def test_filter_by_category(client, world):
    h = world["recruiter"]
    dev = make_published(client, h)
    design = make_published(client, h, title="프로덕트 디자이너", category="design")
    assert ids(client.get("/api/jobs?category=design").json()) == [design["id"]]
    assert dev["id"] in ids(client.get("/api/jobs?category=dev").json())
    assert client.get("/api/jobs?category=marketing").json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    assert client.get("/api/jobs?category=sales").status_code == 422


def test_filter_by_region_matches_short_and_full_province_names(client, world):
    h = world["recruiter"]
    seoul = make_published(client, h, location="서울 강남구")
    gyeonggi = make_published(client, h, location="경기도 성남시")
    chungbuk = make_published(client, h, location="충청북도 청주시")
    assert ids(client.get("/api/jobs?region=서울").json()) == [seoul["id"]]
    assert ids(client.get("/api/jobs?region=경기").json()) == [gyeonggi["id"]]
    assert ids(client.get("/api/jobs?region=충북").json()) == [chungbuk["id"]]
    assert ids(client.get("/api/jobs?region=서울&category=dev").json()) == [seoul["id"]]
    r = client.get("/api/jobs?region=Seoul")
    assert r.status_code == 422 and r.json()["code"] == "REGION_INVALID" and r.json()["regions"][:2] == ["서울", "경기"]
    assert list(settings.JOB_REGIONS)[:2] == ["서울", "경기"]


def test_search_matches_title_company_name_and_tags(client, world):
    h = world["recruiter"]
    java = make_published(client, h)  # NEW_JOB: Java/Spring JD, PLAN_EXAMPLE criteria
    react = create(client, h, title="프론트엔드 개발자", description="React와 TypeScript로 화면을 만듭니다.").json()
    client.put(f"/api/jobs/{react['id']}/criteria", json={"items": [{"name": "React 경험", "category": "skill", "weight": 100}]}, headers=h)
    assert client.post(f"/api/jobs/{react['id']}/publish", headers=h).status_code == 200
    assert ids(client.get("/api/jobs", params={"q": "프론트"}).json()) == [react["id"]]  # title
    assert set(ids(client.get("/api/jobs", params={"q": "acme"}).json())) == {java["id"], react["id"]}  # company
    assert ids(client.get("/api/jobs", params={"q": "리액트"}).json()) == [react["id"]]  # tag by alias
    assert ids(client.get("/api/jobs", params={"q": "spring"}).json()) == [java["id"]]  # tag
    assert client.get("/api/jobs", params={"q": "없는 검색어"}).json()["total"] == 0


def test_search_pages_after_filtering(client, world):
    h = world["recruiter"]
    made = [make_published(client, h, title=f"Java 개발자 {i}")["id"] for i in range(3)]
    first = client.get("/api/jobs", params={"q": "java", "limit": 2}).json()
    second = client.get("/api/jobs", params={"q": "java", "limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"] == 3
    assert ids(first) + ids(second) == list(reversed(made))  # newest first, no overlap


def test_tags_come_from_criteria_and_jd_and_are_capped(client, world):
    h = world["recruiter"]
    job = make_published(client, h)
    tags = client.get(f"/api/jobs/{job['id']}").json()["tags"]
    assert tags[:2] == ["Java", "Spring"]  # criteria first
    assert len(tags) <= settings.JOB_TAGS_MAX
    listed = [j for j in client.get("/api/jobs").json()["items"] if j["id"] == job["id"]]
    assert listed[0]["tags"] == tags
