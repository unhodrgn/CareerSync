"""End-to-end smoke test against a running app (Docker Compose by default), as an outside client.

Flow: login seeker → upload a sample CV PDF → confirm it → PUT preferences → poll
GET /api/recommendations/jobs until results appear → apply to the first recommended job →
login as that job's recruiter → list its applicants.

Uses the demo accounts from scripts/seed.py. It only calls the HTTP API: no app imports, no
.env, no database access. Run it with the app in AI_MODE=rules (the Compose default) so no LLM
is called.

    python scripts/smoke_test.py                    # http://localhost:8000
    python scripts/smoke_test.py --base-url http://localhost:8000 --timeout 30
    python scripts/smoke_test.py --fresh-seeker     # new seeker each run (re-runnable)

Each run uploads a new CV version. With the demo seeker, jobs it already applied to are no longer
recommended, so after applying to every demo job use --fresh-seeker.
"""
import argparse
import sys
import time
from datetime import datetime

import httpx
import pymupdf

PASSWORD = "demo1234"  # scripts/seed.py
DEMO_SEEKER = "seeker@demo.test"
RECRUITERS = {"넥스트코드": "hr@nextcode.test", "클라우드랩": "hr@cloudlab.test"}  # company name → recruiter

SAMPLE_CV = """홍길동
연락처: 010-1234-5678 / smoke@example.com

경력
넥스트소프트 백엔드 개발자 2021.03 ~ 현재
- Java, Spring Boot, JPA로 주문 API 개발 및 운영
- PostgreSQL 쿼리 튜닝과 인덱스 설계로 응답 시간 40% 단축

프로젝트
데이터 파이프라인 구축 2023.01 ~ 2023.12
- Python, Airflow로 일일 배치 파이프라인 구축, AWS EC2·S3 운영

기술
Java, Spring, JPA, PostgreSQL, Python, AWS, Docker

학력
한국대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02

자격증
정보처리기사 2020.11
"""
PREFERENCES = {"locations": ["서울", "판교"], "employment_types": ["full_time"], "job_keywords": [], "profile_public": False}


class StepFailed(Exception):
    pass


def ok(step: str, detail: str) -> None:
    print(f"✅ {step} — {detail}")


def fail(step: str, detail: str) -> None:
    print(f"❌ {step} — {detail}")
    raise StepFailed(step)


def call(client: httpx.Client, step: str, method: str, path: str, *, token: str | None = None, expect=(200,), **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = client.request(method, path, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        fail(step, f"không kết nối được {client.base_url}{path}: {e}")
    if r.status_code not in expect:
        try:
            body = r.json()
            message = f"{body.get('code', '')} {body.get('message') or body.get('detail') or body}".strip()
        except ValueError:
            message = r.text[:300]
        fail(step, f"HTTP {r.status_code}: {message}")
    return r.json() if r.content else None


def login(client: httpx.Client, step: str, email: str) -> str:
    return call(client, step, "POST", "/api/auth/login", json={"email": email, "password": PASSWORD})["access_token"]


def sample_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), SAMPLE_CV, fontname="korea", fontsize=10)
    return doc.tobytes()


def run(base_url: str, timeout: float, fresh_seeker: bool) -> None:
    with httpx.Client(base_url=base_url, timeout=60) as client:
        call(client, "Health", "GET", "/health")
        ok("Health", base_url)

        # 1. Seeker login
        email = DEMO_SEEKER
        if fresh_seeker:
            email = f"smoke-{datetime.now():%Y%m%d%H%M%S}@demo.test"
            body = {"email": email, "password": PASSWORD, "role": "seeker", "display_name": "스모크 테스트",
                    "consent_privacy": True, "consent_ai": True}
            call(client, "Đăng ký seeker mới", "POST", "/api/auth/register", json=body, expect=(201,))
        seeker = login(client, "Login seeker", email)
        me = call(client, "Login seeker", "GET", "/api/users/me", token=seeker)
        ok("Login seeker", f"{me['email']} (role {me['role']}, consent {me['consent_version']})")

        # 2. Upload CV
        files = {"file": ("smoke_cv.pdf", sample_pdf(), "application/pdf")}
        cv = call(client, "Upload CV", "POST", "/api/cv", token=seeker, files=files, expect=(201,))
        ok(
            "Upload CV",
            f"profile #{cv['id']} v{cv['version']}, method {cv['method']}, {len(cv['profile']['skills'])} kỹ năng, "
            f"kinh nghiệm {cv['total_experience_months']} tháng, che PII: {', '.join(cv['masked_kinds']) or '-'}",
        )

        # 3. Confirm CV
        if cv["confirmed"]:
            ok("Xác nhận CV", "đã xác nhận sẵn")
        else:
            body = {"profile": cv["profile"], "confirm": True}
            cv = call(client, "Xác nhận CV", "PUT", f"/api/cv/{cv['id']}", token=seeker, json=body)
            ok("Xác nhận CV", f"profile #{cv['id']} v{cv['version']}, confirmed={cv['confirmed']}")

        # 4. Preferences
        prefs = call(client, "PUT preferences", "PUT", "/api/preferences/me", token=seeker, json=PREFERENCES)
        ok("PUT preferences", f"địa điểm {prefs['locations']}, loại hình {prefs['employment_types']}")

        # 5. Recommendations, polled until scoring in the background has finished
        step = "Gợi ý job"
        deadline = time.monotonic() + timeout
        polls = 0
        while True:
            polls += 1
            reco = call(client, step, "GET", "/api/recommendations/jobs", token=seeker)
            if reco["items"] and reco["pending_count"] == 0:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(2)
        items = reco["items"]
        if not items:
            hint = " (seeker đã apply hết job demo? thử --fresh-seeker)" if not fresh_seeker else ""
            fail(step, f"không có job nào sau {polls} lần gọi, pending_count={reco['pending_count']}{hint}")
        listed = ", ".join(f"{i['title']} · {i['company_name']} ({i['match_level']})" for i in items)
        ok(step, f"gợi ý {len(items)} job: {listed}; pending {reco['pending_count']} (sau {polls} lần gọi)")

        # 6. Apply
        job = items[0]
        application = call(client, "Apply", "POST", f"/api/jobs/{job['job_id']}/applications", token=seeker, expect=(201,))
        ok("Apply", f"{job['title']} → đơn #{application['id']}, đánh giá: {application['evaluation_status']}")

        # 7. Recruiter of that job
        recruiter_email = RECRUITERS.get(job["company_name"])
        if recruiter_email is None:
            fail("Login recruiter", f"không biết recruiter của công ty {job['company_name']} (không phải dữ liệu seed)")
        recruiter = login(client, "Login recruiter", recruiter_email)
        ok("Login recruiter", f"{recruiter_email} ({job['company_name']})")

        # 8. Applicants, polled until this application is scored
        step = "Danh sách ứng viên"
        deadline = time.monotonic() + timeout
        while True:
            ranked = call(client, step, "GET", f"/api/jobs/{job['job_id']}/applications", token=recruiter)
            mine = next((r for r in ranked["items"] if r["application_id"] == application["id"]), None)
            if mine is None:
                fail(step, f"không thấy đơn #{application['id']} trong danh sách")
            if mine["evaluation_status"] != "pending" or time.monotonic() >= deadline:
                break
            time.sleep(2)
        rows = ", ".join(
            f"#{r['rank'] or '-'} {r['name']} (Fit {r['fit'] if r['fit'] is not None else '-'}, {r['evaluation_status']}, {r['status']})"
            for r in ranked["items"]
        )
        if mine["evaluation_status"] != "done":
            fail(step, f"đơn #{application['id']} chưa chấm xong: {mine['evaluation_status']}")
        ok(step, f"{len(ranked['items'])} ứng viên: {rows}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # ✅ and Korean on a Windows console
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=30, help="seconds to wait for background scoring")
    parser.add_argument("--fresh-seeker", action="store_true", help="register a new seeker instead of the demo one")
    args = parser.parse_args()
    try:
        run(args.base_url.rstrip("/"), args.timeout, args.fresh_seeker)
    except StepFailed:
        return 1
    print("Xong: toàn bộ luồng chạy thành công.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
