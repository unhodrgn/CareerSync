from sqlalchemy import select

from app.models import CriteriaGuardrailLog
from app.services.criteria_service import load_for_scoring

PLAN_EXAMPLE = [
    {"name": "Java 활용 능력", "category": "skill", "weight": 30, "description": "Java 17, 동시성"},
    {"name": "Spring 경험", "category": "skill", "weight": 25},
    {"name": "DB 경험", "category": "skill", "weight": 20},
    {"name": "프로젝트 경험", "category": "project", "weight": 15},
    {"name": "관련 자격증", "category": "certificate", "weight": 10},
]


def put(client, job_id, items, headers):
    return client.put(f"/api/jobs/{job_id}/criteria", json={"items": items}, headers=headers)


def publish(client, job_id, headers):
    return client.post(f"/api/jobs/{job_id}/publish", headers=headers)


def test_save_and_read_plan_example(client, world):
    r = put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"])
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["total_weight"] == 100
    assert [i["name"] for i in body["items"]] == [i["name"] for i in PLAN_EXAMPLE]
    assert [i["importance"] for i in body["items"]] == ["높음", "높음", "보통", "보통", "보통"]
    assert client.get(f"/api/jobs/{world['job'].id}/criteria", headers=world["recruiter"]).json() == body


def test_weight_sum_must_be_100(client, world):
    items = [{**PLAN_EXAMPLE[0], "weight": 50}, {**PLAN_EXAMPLE[1], "weight": 40}]
    r = put(client, world["job"].id, items, world["recruiter"])
    assert r.status_code == 422
    assert r.json()["code"] == "WEIGHT_SUM_INVALID" and r.json()["total"] == 90


def test_duplicate_names_case_insensitive(client, world):
    items = [{**PLAN_EXAMPLE[0], "weight": 50}, {**PLAN_EXAMPLE[0], "name": " java 활용 능력 ", "weight": 50}]
    r = put(client, world["job"].id, items, world["recruiter"])
    assert r.status_code == 422 and r.json()["code"] == "CRITERIA_DUPLICATE_NAME"


def test_item_count_limits(client, world):
    assert put(client, world["job"].id, [], world["recruiter"]).json()["code"] == "CRITERIA_COUNT_INVALID"
    items = [{"name": f"항목 {i}", "category": "other", "weight": 9} for i in range(11)]
    assert put(client, world["job"].id, items, world["recruiter"]).json()["code"] == "CRITERIA_COUNT_INVALID"


def test_weight_range_validated_by_schema(client, world):
    items = [{**PLAN_EXAMPLE[0], "weight": 0}]
    assert put(client, world["job"].id, items, world["recruiter"]).status_code == 422


def test_blocked_criterion_rejects_whole_set_and_logs(client, world, db):
    items = PLAN_EXAMPLE[:4] + [{"name": "키 175cm 이상", "category": "other", "weight": 10}]
    r = put(client, world["job"].id, items, world["recruiter"])
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "CRITERIA_BLOCKED"
    assert body["items"][0]["index"] == 4
    assert body["items"][0]["rule_id"] == "physical.height"
    assert body["items"][0]["law_ref"] == "채용절차법 제4조의3 제1호"
    assert client.get(f"/api/jobs/{world['job'].id}/criteria", headers=world["recruiter"]).json()["items"] == []
    logs = db.scalars(select(CriteriaGuardrailLog)).all()
    assert [(log.rule_id, log.input_name) for log in logs] == [("physical.height", "키 175cm 이상")]


def test_blocked_text_in_description(client, world):
    items = [{"name": "기본 소양", "category": "other", "weight": 100, "description": "미혼자 우대"}]
    r = put(client, world["job"].id, items, world["recruiter"])
    assert r.json()["items"][0]["field"] == "description"


def test_live_check(client, world):
    r = client.post("/api/criteria/check", json={"name": "남성 우대"}, headers=world["recruiter"])
    assert r.status_code == 200
    assert r.json()["allowed"] is False and r.json()["hits"][0]["rule_id"] == "gender"
    r = client.post("/api/criteria/check", json={"name": "장애 대응 경험"}, headers=world["recruiter"])
    assert r.json()["allowed"] is True
    assert client.post("/api/criteria/check", json={"name": "x"}, headers=world["seeker"]).status_code == 403


def test_publish_requires_valid_set(client, world):
    r = publish(client, world["job"].id, world["recruiter"])
    assert r.status_code == 422 and r.json()["code"] == "CRITERIA_COUNT_INVALID"
    put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"])
    assert publish(client, world["job"].id, world["recruiter"]).json()["status"] == "published"
    assert publish(client, world["job"].id, world["recruiter"]).status_code == 409


def test_after_publish_only_weights_change(client, world):
    saved = put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"]).json()["items"]
    publish(client, world["job"].id, world["recruiter"])
    ids = [c["id"] for c in saved]

    reweighted = [
        {k: c[k] for k in ("id", "name", "description", "category")} | {"weight": w}
        for c, w in zip(reversed(saved), [40, 15, 15, 15, 15], strict=True)
    ]
    r = put(client, world["job"].id, reweighted, world["recruiter"])
    assert r.status_code == 200, r.json()
    assert [c["id"] for c in r.json()["items"]] == list(reversed(ids))  # same ids, new order
    assert r.json()["items"][0]["weight"] == 40

    added = reweighted[:4] + [{"name": "새 항목", "category": "other", "weight": 15}]
    assert put(client, world["job"].id, added, world["recruiter"]).status_code == 409
    removed = [{**reweighted[0], "weight": 55}] + reweighted[1:4]
    assert put(client, world["job"].id, removed, world["recruiter"]).json()["code"] == "CRITERIA_LOCKED"
    renamed = [{**reweighted[0], "name": "이름 변경"}] + reweighted[1:]
    assert put(client, world["job"].id, renamed, world["recruiter"]).status_code == 409


def test_draft_can_be_rebuilt(client, world):
    put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"])
    items = [{"name": "Python", "category": "skill", "weight": 60}, {"name": "java 활용 능력", "category": "skill", "weight": 40}]
    r = put(client, world["job"].id, items, world["recruiter"])
    assert r.status_code == 200
    assert [c["name"] for c in r.json()["items"]] == ["Python", "java 활용 능력"]


def test_seeker_sees_importance_not_weights(client, world):
    put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"])
    url = f"/api/jobs/{world['job'].id}/criteria"
    assert client.get(url, headers=world["seeker"]).status_code == 404  # draft is not visible
    publish(client, world["job"].id, world["recruiter"])
    body = client.get(url, headers=world["seeker"]).json()
    assert body["items"][0] == {"name": "Java 활용 능력", "category": "skill", "importance": "높음"}
    assert all("weight" not in i and "description" not in i for i in body["items"])
    assert put(client, world["job"].id, PLAN_EXAMPLE, world["seeker"]).status_code == 403


def test_other_company_gets_404(client, world):
    job_id = world["job"].id
    put(client, job_id, PLAN_EXAMPLE, world["recruiter"])
    assert client.get(f"/api/jobs/{job_id}/criteria", headers=world["rival"]).status_code == 404
    assert put(client, job_id, PLAN_EXAMPLE, world["rival"]).status_code == 404
    assert publish(client, job_id, world["rival"]).status_code == 404
    copy = f"/api/jobs/{world['rival_job'].id}/criteria/copy-from/{job_id}"
    assert client.post(copy, headers=world["rival"]).status_code == 404


def test_requires_auth(client, world):
    assert client.get(f"/api/jobs/{world['job'].id}/criteria").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get(f"/api/jobs/{world['job'].id}/criteria", headers=bad).status_code == 401


def test_copy_from_another_job(client, world):
    put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"])
    r = client.post(f"/api/jobs/{world['job2'].id}/criteria/copy-from/{world['job'].id}", headers=world["recruiter"])
    assert r.status_code == 200
    assert [c["name"] for c in r.json()["items"]] == [c["name"] for c in PLAN_EXAMPLE]
    publish(client, world["job2"].id, world["recruiter"])
    r = client.post(f"/api/jobs/{world['job2'].id}/criteria/copy-from/{world['job'].id}", headers=world["recruiter"])
    assert r.status_code == 409


def test_load_for_scoring_excludes_newly_blocked(client, world, db, monkeypatch):
    put(client, world["job"].id, PLAN_EXAMPLE, world["recruiter"])
    result = load_for_scoring(db, world["job"].id)
    assert [c.weight for c in result.items] == [30, 25, 20, 15, 10]
    assert sum(c.effective_weight for c in result.items) == 100

    # Simulate a blocklist update that now blocks "관련 자격증"
    from ai.guardrails.blocklist import parse_blocklist
    from app.services import criteria_service

    newer = parse_blocklist(
        {"version": "test.2", "rules": [{"id": "t", "category": "t", "law_ref": "t", "reason": "t", "patterns": ["자격증"]}]}
    )
    monkeypatch.setattr(criteria_service, "blocklist", lambda: newer)
    result = load_for_scoring(db, world["job"].id)
    assert [c.name for c in result.excluded] == ["관련 자격증"]
    assert round(sum(c.effective_weight for c in result.items), 6) == 100
    assert round(result.items[0].effective_weight, 4) == round(30 * 100 / 90, 4)
