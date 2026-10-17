from datetime import date, timedelta

from sqlalchemy import select

from app.models import CriteriaGuardrailLog, JobPosting
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
    assert [i["importance"] for i in body["items"]] == ["핵심", "핵심", "중요", "중요", "중요"]
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
    assert body["items"][0] == {"name": "Java 활용 능력", "category": "skill", "importance": "핵심"}
    assert all("weight" not in i and "description" not in i for i in body["items"])
    assert put(client, world["job"].id, PLAN_EXAMPLE, world["seeker"]).status_code == 403


# Weights 50 / 20 / 20 / 5 / 5 give every importance level (D30)
LABEL_SET = [
    {"name": "Java 활용 능력", "category": "skill", "weight": 50},
    {"name": "Spring 경험", "category": "skill", "weight": 20},
    {"name": "프로젝트 경험", "category": "project", "weight": 20},
    {"name": "관련 자격증", "category": "certificate", "weight": 5},
    {"name": "AWS 경험", "category": "skill", "weight": 5},
]


def published_with_labels(client, world):
    assert put(client, world["job"].id, LABEL_SET, world["recruiter"]).status_code == 200
    assert publish(client, world["job"].id, world["recruiter"]).status_code == 200
    return f"/api/jobs/{world['job'].id}/criteria"


def numbers_and_keys(value, path=""):
    """Every (path, key) and every number below `value`, except the top-level job_id."""
    keys, numbers = set(), []
    if isinstance(value, dict):
        for k, v in value.items():
            keys.add(k)
            if not (path == "" and k == "job_id"):
                sub_keys, sub_numbers = numbers_and_keys(v, f"{path}.{k}")
                keys |= sub_keys
                numbers += sub_numbers
    elif isinstance(value, list):
        for v in value:
            sub_keys, sub_numbers = numbers_and_keys(v, path + "[]")
            keys |= sub_keys
            numbers += sub_numbers
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        numbers.append((path, value))
    return keys, numbers


def test_guest_gets_names_only(client, world):
    url = published_with_labels(client, world)
    r = client.get(url)
    assert r.status_code == 200
    assert r.json() == {"job_id": world["job"].id, "items": [{"name": c["name"]} for c in LABEL_SET]}


def test_guest_cannot_read_draft_closed_or_expired_jobs(client, db, world):
    draft_url = f"/api/jobs/{world['job2'].id}/criteria"
    assert put(client, world["job2"].id, LABEL_SET, world["recruiter"]).status_code == 200
    assert client.get(draft_url).status_code == 404

    url = published_with_labels(client, world)
    db.get(JobPosting, world["job"].id).deadline = date.today() - timedelta(days=1)
    db.commit()
    assert client.get(url).status_code == 404  # expired: hidden from guests like GET /api/jobs/{id}
    assert client.get(url, headers=world["seeker"]).status_code == 200  # signed-in seekers still see it

    assert client.post(f"/api/jobs/{world['job'].id}/close", headers=world["recruiter"]).status_code == 200
    assert client.get(url).status_code == 404
    assert client.get(url, headers=world["seeker"]).status_code == 404


def test_seeker_gets_labels_without_numbers(client, world):
    url = published_with_labels(client, world)
    body = client.get(url, headers=world["seeker"]).json()
    assert body["items"] == [
        {"name": "Java 활용 능력", "category": "skill", "importance": "핵심"},
        {"name": "Spring 경험", "category": "skill", "importance": "중요"},
        {"name": "프로젝트 경험", "category": "project", "importance": "중요"},
        {"name": "관련 자격증", "category": "certificate", "importance": "일반"},
        {"name": "AWS 경험", "category": "skill", "importance": "일반"},
    ]


def test_no_weight_in_seeker_or_guest_response(client, world):
    url = published_with_labels(client, world)
    for headers in (None, world["seeker"]):
        keys, numbers = numbers_and_keys(client.get(url, headers=headers).json())
        assert not keys & {"weight", "total_weight", "position", "id", "description", "blocklist_version"}
        assert numbers == []


def test_owner_view_keeps_its_fields(client, world):
    url = published_with_labels(client, world)
    body = client.get(url, headers=world["recruiter"]).json()
    assert set(body) == {"job_id", "items", "total_weight", "blocklist_version"}
    assert body["total_weight"] == 100
    assert [set(i) for i in body["items"]] == [
        {"id", "name", "description", "category", "weight", "position", "importance"}
    ] * len(LABEL_SET)
    assert [(i["weight"], i["importance"]) for i in body["items"]] == [
        (50, "핵심"), (20, "중요"), (20, "중요"), (5, "일반"), (5, "일반")
    ]


def test_other_company_gets_404(client, world):
    job_id = world["job"].id
    put(client, job_id, PLAN_EXAMPLE, world["recruiter"])
    assert client.get(f"/api/jobs/{job_id}/criteria", headers=world["rival"]).status_code == 404
    assert put(client, job_id, PLAN_EXAMPLE, world["rival"]).status_code == 404
    assert publish(client, job_id, world["rival"]).status_code == 404
    copy = f"/api/jobs/{world['rival_job'].id}/criteria/copy-from/{job_id}"
    assert client.post(copy, headers=world["rival"]).status_code == 404


def test_requires_auth(client, world):
    url = f"/api/jobs/{world['job'].id}/criteria"
    # Reading is open to guests (D35), but only for jobs they can see; this one is a draft
    assert client.get(url).status_code == 404
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get(url, headers=bad).status_code == 401
    assert client.put(url, json={"items": PLAN_EXAMPLE}).status_code == 401
    assert client.post("/api/criteria/check", json={"name": "Java"}).status_code == 401


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


# ── education criteria must name a major (or 이공계/STEM) ──

NO_MAJOR = {"name": "관련 전공", "category": "education", "weight": 10}


def _with(education: dict) -> list[dict]:
    return [*PLAN_EXAMPLE[:4], education]


def test_education_without_major_is_rejected(client, world):
    r = put(client, world["job"].id, _with(NO_MAJOR), world["recruiter"])
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "CRITERIA_MAJOR_REQUIRED" and "전공" in body["message"]
    assert body["items"] == [{"index": 4, "name": "관련 전공"}]


def test_education_with_major_or_stem_is_saved(client, world):
    for education in (
        {"name": "컴퓨터공학 관련 전공", "category": "education", "weight": 10},
        {"name": "전공", "description": "경영학과 또는 유관 전공", "category": "education", "weight": 10},
        {"name": "이공계 전공", "category": "education", "weight": 10},
    ):
        r = put(client, world["job"].id, _with(education), world["recruiter"])
        assert r.status_code == 200, (education, r.json())


def test_old_education_criterion_blocks_publish_and_copy(client, world, db):
    job = world["job"]
    put(client, job.id, PLAN_EXAMPLE, world["recruiter"])
    # As if saved before the rule: written straight to the DB
    job.criteria[-1].name, job.criteria[-1].category = "관련 전공", "education"
    db.commit()
    r = publish(client, job.id, world["recruiter"])
    assert (r.status_code, r.json()["code"]) == (422, "CRITERIA_MAJOR_REQUIRED")
    r = client.post(f"/api/jobs/{world['job2'].id}/criteria/copy-from/{job.id}", headers=world["recruiter"])
    assert (r.status_code, r.json()["code"]) == (422, "CRITERIA_MAJOR_REQUIRED")


def test_published_job_with_old_education_criterion_can_change_weights(client, world, db):
    job = world["job"]
    put(client, job.id, _with({"name": "컴퓨터공학 전공", "category": "education", "weight": 10}), world["recruiter"])
    assert publish(client, job.id, world["recruiter"]).status_code == 200
    job.criteria[-1].name = "관련 전공"  # as if saved before the rule
    db.commit()
    items = client.get(f"/api/jobs/{job.id}/criteria", headers=world["recruiter"]).json()["items"]
    reweighted = [{**i, "weight": w} for i, w in zip(items, [25, 25, 20, 20, 10], strict=True)]
    r = put(client, job.id, reweighted, world["recruiter"])
    assert r.status_code == 200, r.json()
