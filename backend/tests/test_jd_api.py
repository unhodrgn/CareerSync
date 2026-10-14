"""AI JD drafts (`POST /api/jobs/{id}/jd-draft`) and criteria suggestions without blocked items (issue 7); D24."""
import pytest

from ai.tests.helpers import FakeLLM
from app.core.config import settings
from app.models import JobPosting
from app.services import ai_runtime, jd_service
from tests.test_jobs_api import make_published

LLM_DRAFT = {
    "intro": "Acme 결제팀에서 함께할 백엔드 개발자를 찾습니다.",
    "responsibilities": ["결제 API 설계 및 개발", "Kafka 기반 이벤트 처리"],
    "requirements": ["Java/Spring 실무 경력 3년 이상", "30세 이하 지원 가능"],
    "preferred": ["MSA 전환 경험", "연봉 협의 가능"],
}


@pytest.fixture(autouse=True)
def _fresh_counts():
    jd_service.reset_counts()
    yield
    jd_service.reset_counts()


@pytest.fixture
def llm_mode(monkeypatch):
    llm = FakeLLM(*[LLM_DRAFT] * 10)
    monkeypatch.setattr(ai_runtime, "mode", lambda: "llm")
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    return llm


def _draft(client, world, job=None, headers=None, **body):
    job_id = job if job is not None else world["job"].id
    return client.post(f"/api/jobs/{job_id}/jd-draft", json=body, headers=headers or world["recruiter"])


def _project(client, headers, name="결제 시스템 MSA 전환", techs=("Kafka", "Java")):
    r = client.post("/api/companies/me/projects", json={"name": name, "techs": list(techs)}, headers=headers)
    return r.json()["id"]


def test_rules_draft_is_not_saved(client, world, db):
    before = world["job"].description
    r = _draft(client, world, keywords=["java", "Spring"], notes="결제팀 백엔드")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert set(body) == {"job_id", "description", "sections", "dropped", "method", "limited", "notice"}
    assert body["method"] == "rules" and body["limited"] is False and "참고용" in body["notice"]
    assert "Java 실무 또는 프로젝트 경험" in body["sections"]["requirements"]
    assert body["sections"]["requirements"][0] == "신입 지원 가능"  # min_experience_years NULL
    assert "자격 요건" in body["description"] and body["dropped"] == []
    db.expire_all()
    assert db.get(JobPosting, world["job"].id).description == before


def test_projects_are_context(client, world):
    pid = _project(client, world["recruiter"])
    body = _draft(client, world, project_ids=[pid]).json()
    assert any("결제 시스템 MSA 전환" in r for r in body["sections"]["responsibilities"])
    other = _project(client, world["rival"], name="경쟁사 프로젝트")
    for ids in ([other], [pid, other], [9999]):
        r = _draft(client, world, project_ids=ids)
        assert r.status_code == 404 and r.json()["code"] == "PROJECT_NOT_FOUND", ids


def test_only_own_draft_jobs(client, world):
    published = make_published(client, world["recruiter"])["id"]
    r = _draft(client, world, job=published)
    assert r.status_code == 409 and r.json()["code"] == "JOB_NOT_DRAFT"
    assert _draft(client, world, job=world["rival_job"].id).status_code == 404
    assert _draft(client, world, job=9999).status_code == 404
    assert _draft(client, world, headers=world["seeker"]).status_code == 403


@pytest.mark.parametrize(
    "body", [{"keywords": ["k"] * 11}, {"keywords": [" "]}, {"keywords": ["가" * 51]}, {"notes": "가" * 1001}]
)
def test_validation(client, world, body):
    assert _draft(client, world, **body).status_code == 422


def test_llm_draft_drops_blocked_and_pay_sentences(client, world, llm_mode):
    pid = _project(client, world["recruiter"])
    body = _draft(client, world, keywords=["Java"], project_ids=[pid]).json()
    assert body["method"] == "llm:fake-llm" and body["limited"] is False
    assert body["sections"]["requirements"] == ["Java/Spring 실무 경력 3년 이상"]
    assert body["sections"]["preferred"] == ["MSA 전환 경험"]
    dropped = {d["text"] for d in body["dropped"]}
    assert dropped == {"30세 이하 지원 가능", "연봉 협의 가능"}
    assert "30세" not in body["description"] and "연봉" not in body["description"]
    _, user = llm_mode.calls[0]
    assert "결제 시스템 MSA 전환" in user and "Acme" in user


def test_daily_llm_limit_returns_the_template(client, world, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "JD_DAILY_LLM_DRAFTS", 2)
    methods = [(_draft(client, world).json()) for _ in range(3)]
    assert [m["method"] for m in methods] == ["llm:fake-llm", "llm:fake-llm", "rules"]
    assert [m["limited"] for m in methods] == [False, False, True]
    assert len(llm_mode.calls) == 2
    # Another company has its own count
    rival = _draft(client, world, job=world["rival_job"].id, headers=world["rival"]).json()
    assert rival["method"] == "llm:fake-llm" and rival["limited"] is False


def test_failed_llm_call_uses_a_slot(client, world, monkeypatch):
    llm = FakeLLM()  # no response queued: LLMError
    monkeypatch.setattr(ai_runtime, "mode", lambda: "llm")
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    monkeypatch.setattr(settings, "JD_DAILY_LLM_DRAFTS", 1)
    first, second = _draft(client, world).json(), _draft(client, world).json()
    assert first["method"] == "rules" and first["limited"] is False
    assert second["method"] == "rules" and second["limited"] is True
    assert len(llm.calls) == 1


def test_rules_mode_is_not_limited(client, world, monkeypatch):
    monkeypatch.setattr(settings, "JD_DAILY_LLM_DRAFTS", 0)
    assert all(_draft(client, world).json()["limited"] is False for _ in range(3))


# ── Issue 7: /analyze leaves out suggestions that saving would reject ──


def test_analyze_drops_blocked_suggestions(client, world, monkeypatch):
    llm = FakeLLM(
        {
            "profile": {"required_skills": ["Java"], "preferred_skills": [], "min_years": 3},
            "criteria": [
                {"name": "Java 활용 능력", "description": "Java 실무 경험", "category": "skill", "weight": 40},
                {"name": "남성 지원자", "description": "", "category": "other", "weight": 20},
                {"name": "관련 전공", "description": "", "category": "education", "weight": 20},
                {"name": "프로젝트 경험", "description": "API 설계 경험", "category": "project", "weight": 20},
            ],
        }
    )
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    r = client.post(f"/api/jobs/{world['job'].id}/analyze", headers=world["recruiter"])
    assert r.status_code == 200, r.json()
    body = r.json()
    kept = body["analysis"]["criteria"]
    assert [c["name"] for c in kept] == ["Java 활용 능력", "프로젝트 경험"]
    assert sum(c["weight"] for c in kept) == 100 and kept[0]["weight"] == 67
    assert {(b["name"], b["code"]) for b in body["blocked"]} == {
        ("남성 지원자", "CRITERIA_BLOCKED"),
        ("관련 전공", "CRITERIA_MAJOR_REQUIRED"),
    }
    # The kept suggestions can be saved as they are
    items = [{k: c[k] for k in ("name", "description", "category", "weight")} for c in kept]
    assert client.put(f"/api/jobs/{world['job'].id}/criteria", json={"items": items}, headers=world["recruiter"]).status_code == 200


def test_analyze_without_blocked_suggestions_is_unchanged(client, world):
    body = client.post(f"/api/jobs/{world['job'].id}/analyze", headers=world["recruiter"]).json()
    assert body["method"] == "rules" and body["blocked"] == []
    assert sum(c["weight"] for c in body["analysis"]["criteria"]) == 100


def test_analyze_logs_nothing(client, world, db, monkeypatch):
    from app.models import CriteriaGuardrailLog

    llm = FakeLLM({"profile": {}, "criteria": [{"name": "30세 이하", "category": "other", "weight": 100}]})
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    body = client.post(f"/api/jobs/{world['job'].id}/analyze", headers=world["recruiter"]).json()
    assert body["analysis"]["criteria"] == [] and body["blocked"][0]["code"] == "CRITERIA_BLOCKED"
    assert db.query(CriteriaGuardrailLog).count() == 0


def test_parallel_slots_respect_the_limit(monkeypatch):
    import threading

    monkeypatch.setattr(settings, "JD_DAILY_LLM_DRAFTS", 5)
    barrier, results, lock = threading.Barrier(20), [], threading.Lock()

    def run():
        barrier.wait()
        ok = jd_service.take_llm_slot(1)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=run) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert results.count(True) == 5 and len(results) == 20
