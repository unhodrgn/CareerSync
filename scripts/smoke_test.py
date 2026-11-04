"""End-to-end smoke test of every backend feature against a running app, as an outside client.

Run it with the app in AI_MODE=rules (the Compose default): every AI step checks `method == "rules"`, so a
backend in llm mode makes those steps fail instead of silently paying for calls. It only calls the HTTP API:
no app imports, no .env, no database access.

Each run registers a new company and a new seeker (random tag in the e-mails), so it can run any number of
times on the same database. Flow:

  Guest    job list and detail without a token
  Company  register → project CRUD → public profile → draft job A → AI JD draft (with project) → save it →
           /analyze → PUT criteria → publish A; draft job B with the same JD → copy criteria → publish B
  Seeker   register → /users/me consent → upload CV → CV review → confirm → preferences (public) →
           recommendations (polled) → roadmap and interview questions for A → apply to A
  Company  applicants of A (polled until scored) with quick filters → evaluation → status change →
           talent list of B (polled; the seeker applied to A, and talent excludes applicants of that job) →
           offer with a message
  Seeker   sees the offer → accepts;  Company sees the contact
  Errors   bad token → 401, no token → 401, seeker on company APIs → 403, company on seeker APIs → 403,
           guest on a draft job → 404

    python scripts/smoke_test.py                       # http://localhost:8000
    python scripts/smoke_test.py --base-url http://localhost:8000 --timeout 30

Every step prints one ✅/❌ line (⏭️ when an earlier step it needs failed); the last line counts them.
Exit code 0 only when every step passed.
"""
import argparse
import secrets
import sys
import time
from collections.abc import Callable
from datetime import date, timedelta

import httpx
import pymupdf

PASSWORD = "smoke1234"
SEEKER_NAME = "홍길동"
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
JOB = {
    "title": "백엔드 개발자",
    "employment_type": "full_time",
    "min_experience_years": 2,
    "location": "서울 강남구",
    "salary_note": "회사 내규에 따름",
}


class StepFailed(Exception):
    pass


def sample_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), SAMPLE_CV, fontname="korea", fontsize=10)
    return doc.tobytes()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise StepFailed(message)


class Smoke:
    def __init__(self, client: httpx.Client, timeout: float):
        self.client = client
        self.timeout = timeout
        self.ctx: dict = {}
        self.passed = self.failed = self.skipped = 0

    # ── HTTP ──

    def call(self, method: str, path: str, *, token: str | None = None, expect=(200,), **kwargs):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = self.client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as e:
            raise StepFailed(f"không kết nối được {self.client.base_url}{path}: {e}") from e
        if r.status_code not in expect:
            raise StepFailed(f"{method} {path} → HTTP {r.status_code} (mong đợi {'/'.join(map(str, expect))}): {r.text[:500]}")
        return r.json() if r.content else None

    def error(self, method: str, path: str, status: int, *, token: str | None = None, code: str | None = None, **kwargs) -> str:
        body = self.call(method, path, token=token, expect=(status,), **kwargs)
        if code is not None:
            check(body.get("code") == code, f"mã lỗi {body.get('code')!r}, mong đợi {code!r}: {body}")
        return f"HTTP {status}" + (f" {body.get('code')}" if body and body.get("code") else "")

    def poll(self, fetch: Callable[[], object], done: Callable[[object], bool]) -> tuple[object, int]:
        deadline, polls = time.monotonic() + self.timeout, 0
        while True:
            polls += 1
            result = fetch()
            if done(result) or time.monotonic() >= deadline:
                return result, polls
            time.sleep(2)

    # ── Steps ──

    def step(self, name: str, fn: Callable[[], str], needs: tuple[str, ...] = ()) -> None:
        missing = [k for k in needs if k not in self.ctx]
        if missing:
            self.skipped += 1
            print(f"⏭️  {name} — bỏ qua (bước trước không tạo được: {', '.join(missing)})")
            return
        try:
            detail = fn()
        except StepFailed as e:
            self.failed += 1
            print(f"❌ {name} — {e}")
            return
        except (KeyError, TypeError, IndexError, ValueError) as e:
            self.failed += 1
            print(f"❌ {name} — response không đúng dạng mong đợi: {type(e).__name__}: {e}")
            return
        self.passed += 1
        print(f"✅ {name} — {detail}")

    def register(self, key: str, role: str, email: str, **extra) -> str:
        body = {"email": email, "password": PASSWORD, "role": role, "consent_privacy": True, "consent_ai": True, **extra}
        self.call("POST", "/api/auth/register", json=body, expect=(201,))
        token = self.call("POST", "/api/auth/login", json={"email": email, "password": PASSWORD})["access_token"]
        self.ctx[key] = token
        return email


def run(s: Smoke) -> None:
    tag = secrets.token_hex(3)
    c = s.ctx
    c["tag"] = tag
    deadline = (date.today() + timedelta(days=30)).isoformat()

    s.step("Health", lambda: s.call("GET", "/health") and str(s.client.base_url))

    # ── Guest ──
    def guest_jobs():
        page = s.call("GET", "/api/jobs", params={"limit": 50})
        check(page["items"], "không có job public nào (DB chưa seed?)")
        c["public_job"] = page["items"][0]["id"]
        return f"{len(page['items'])} job (total {page.get('total', '?')}), ví dụ: {page['items'][0]['title']}"

    def guest_detail():
        job = s.call("GET", f"/api/jobs/{c['public_job']}")
        return f"#{job['id']} {job['title']} · {job['company_name']} ({job['status']})"

    s.step("Khách: GET /api/jobs (không token)", guest_jobs)
    s.step("Khách: chi tiết job (không token)", guest_detail, needs=("public_job",))

    # ── Company: account, projects, jobs ──
    company_email = f"smoke-hr-{tag}@demo.test"

    def company_register():
        s.register("company", "company", company_email, display_name="스모크 인사팀", company_name=f"스모크테크 {tag}")
        me = s.call("GET", "/api/companies/me", token=c["company"])
        c["company_id"] = me["id"]
        s.call("PUT", "/api/companies/me", token=c["company"], json={
            "name": me["name"], "intro": "B2B 결제 SaaS를 만드는 팀입니다.", "talent_profile": "주도적으로 문제를 정의하는 사람"})
        return f"{company_email}, công ty #{me['id']} {me['name']}"

    def project_crud():
        t = c["company"]
        p = s.call("POST", "/api/companies/me/projects", token=t, expect=(201,),
                   json={"name": "결제 시스템 MSA 전환", "description": "모놀리식 결제 서버 분리", "techs": ["java", "Spring Boot", "Kafka"]})
        p = s.call("PUT", f"/api/companies/me/projects/{p['id']}", token=t,
                   json={"name": "결제 시스템 MSA 전환", "description": "모놀리식 결제 서버를 서비스 단위로 분리", "techs": ["Java", "Kafka", "Redis"]})
        extra = s.call("POST", "/api/companies/me/projects", token=t, expect=(201,), json={"name": "임시 프로젝트", "techs": []})
        s.call("DELETE", f"/api/companies/me/projects/{extra['id']}", token=t, expect=(204,))
        listed = s.call("GET", "/api/companies/me/projects", token=t)
        check([x["id"] for x in listed] == [p["id"]], f"danh sách project sau khi xoá: {[x['id'] for x in listed]}")
        c["project_id"] = p["id"]
        return f"tạo/sửa/xoá xong; còn project #{p['id']} techs={p['techs']}"

    def draft_job_a():
        job = s.call("POST", "/api/jobs", token=c["company"], expect=(201,), json={**JOB, "deadline": deadline})
        check(job["status"] == "draft", f"status {job['status']}")
        c["job_a"] = job["id"]
        return f"job A #{job['id']} draft"

    def jd_draft():
        body = {"keywords": ["Java", "Spring", "PostgreSQL"], "notes": "결제팀 백엔드", "project_ids": [c["project_id"]]}
        d = s.call("POST", f"/api/jobs/{c['job_a']}/jd-draft", token=c["company"], json=body)
        check(d["method"] == "rules", f"method {d['method']} (backend không ở AI_MODE=rules?)")
        check("결제 시스템 MSA 전환" in d["description"], "JD nháp không dùng project đã chọn")
        check(d["sections"]["requirements"], "không có 자격 요건")
        s.call("PATCH", f"/api/jobs/{c['job_a']}", token=c["company"], json={"description": d["description"]})
        c["jd"] = d["description"]
        return (f"{len(d['description'])} ký tự, {len(d['sections']['responsibilities'])} 업무 / "
                f"{len(d['sections']['requirements'])} 요건 / {len(d['sections']['preferred'])} 우대, dropped {len(d['dropped'])}; đã lưu vào job A")

    def analyze():
        a = s.call("POST", f"/api/jobs/{c['job_a']}/analyze", token=c["company"])
        check(a["method"] == "rules", f"method {a['method']}")
        items = a["analysis"]["criteria"]
        check(items and sum(i["weight"] for i in items) == 100, f"gợi ý tiêu chí không hợp lệ: {items}")
        c["criteria"] = [{k: i[k] for k in ("name", "description", "category", "weight")} for i in items]
        return f"{len(items)} tiêu chí gợi ý ({', '.join(i['name'] for i in items)}), blocked {len(a['blocked'])}"

    def put_criteria():
        r = s.call("PUT", f"/api/jobs/{c['job_a']}/criteria", token=c["company"], json={"items": c["criteria"]})
        return f"lưu {len(r['items'])} tiêu chí cho job A"

    def publish_a():
        job = s.call("POST", f"/api/jobs/{c['job_a']}/publish", token=c["company"])
        check(job["status"] == "published", f"status {job['status']}")
        c["job_a_published"] = True
        return f"job A #{job['id']} published"

    def job_b():
        t = c["company"]
        job = s.call("POST", "/api/jobs", token=t, expect=(201,),
                     json={**JOB, "title": "백엔드 개발자 (플랫폼팀)", "description": c["jd"], "deadline": deadline})
        s.call("POST", f"/api/jobs/{job['id']}/criteria/copy-from/{c['job_a']}", token=t)
        job = s.call("POST", f"/api/jobs/{job['id']}/publish", token=t)
        check(job["status"] == "published", f"status {job['status']}")
        c["job_b"] = job["id"]
        return f"job B #{job['id']} (copy tiêu chí từ A) published"

    s.step("Công ty: đăng ký + sửa hồ sơ", company_register)
    s.step("Công ty: CRUD project", project_crud, needs=("company",))
    s.step("Công ty: tạo job A (draft)", draft_job_a, needs=("company",))
    s.step("Công ty: AI viết nháp JD (project_ids)", jd_draft, needs=("job_a", "project_id"))
    s.step("Công ty: /analyze gợi ý tiêu chí", analyze, needs=("jd",))
    s.step("Công ty: PUT criteria", put_criteria, needs=("criteria",))
    s.step("Công ty: publish job A", publish_a, needs=("criteria",))
    s.step("Công ty: job B + copy tiêu chí + publish", job_b, needs=("job_a_published",))

    # ── Seeker ──
    seeker_email = f"smoke-seeker-{tag}@demo.test"

    def seeker_register():
        s.register("seeker", "seeker", seeker_email, display_name=SEEKER_NAME)
        me = s.call("GET", "/api/users/me", token=c["seeker"])
        check(me["consent_required"] is False, f"consent_required={me['consent_required']} ngay sau khi đăng ký")
        check(me["consent_version"] == me["current_consent_version"], f"consent {me['consent_version']} ≠ {me['current_consent_version']}")
        return f"{seeker_email}, consent {me['consent_version']}, consent_required=False"

    def public_company():
        p = s.call("GET", f"/api/companies/{c['company_id']}", token=c["seeker"])
        check([x["name"] for x in p["projects"]] == ["결제 시스템 MSA 전환"], f"projects: {p['projects']}")
        return f"{p['name']}: {len(p['projects'])} project ({p['projects'][0]['techs']})"

    def upload():
        cv = s.call("POST", "/api/cv", token=c["seeker"], expect=(201,), files={"file": ("smoke_cv.pdf", sample_pdf(), "application/pdf")})
        check(cv["method"] == "rules", f"method {cv['method']}")
        check({"email", "phone", "name"} <= set(cv["masked_kinds"]), f"PII che chưa đủ: {cv['masked_kinds']}")
        c["cv"] = cv
        return (f"profile #{cv['id']} v{cv['version']}, {len(cv['profile']['skills'])} kỹ năng, "
                f"{cv['total_experience_months']} tháng, che PII: {', '.join(cv['masked_kinds'])}")

    def review():
        r = s.call("POST", f"/api/cv/{c['cv']['id']}/review", token=c["seeker"])
        check(r["method"] == "rules", f"method {r['method']}")
        check(r["strengths"], "không có điểm mạnh")
        flagged = sum(i["affects_scoring"] for i in r["improvements"])
        return (f"bản chưa xác nhận: {len(r['strengths'])} điểm mạnh ({', '.join(i['title'] for i in r['strengths'])}), "
                f"{len(r['improvements'])} cần bổ sung ({flagged} ảnh hưởng điểm)")

    def confirm():
        cv = s.call("PUT", f"/api/cv/{c['cv']['id']}", token=c["seeker"], json={"profile": c["cv"]["profile"], "confirm": True})
        check(cv["confirmed"], "chưa confirmed")
        c["cv_confirmed"] = cv
        return f"profile #{cv['id']} v{cv['version']} confirmed"

    def preferences():
        body = {"locations": ["서울"], "employment_types": ["full_time"], "job_keywords": ["백엔드", f"smoke{tag}"], "profile_public": True}
        p = s.call("PUT", "/api/preferences/me", token=c["seeker"], json=body)
        check(p["profile_public"] is True, "profile_public chưa bật")
        return f"địa điểm {p['locations']}, loại hình {p['employment_types']}, từ khoá {p['job_keywords']}, public=True"

    def recommendations():
        reco, polls = s.poll(lambda: s.call("GET", "/api/recommendations/jobs", token=c["seeker"]), lambda r: bool(r["items"]))
        check(reco["items"], f"không có job nào sau {polls} lần gọi (~{s.timeout:.0f}s), pending_count={reco['pending_count']}")
        check(all(set(i) >= {"match_level"} and "fit" not in i for i in reco["items"]), "response lộ Fit hoặc thiếu match_level")
        listed = ", ".join(f"{i['title']} · {i['company_name']} ({i['match_level']})" for i in reco["items"][:5])
        return f"{len(reco['items'])} job sau {polls} lần gọi, pending {reco['pending_count']}: {listed}"

    def roadmap():
        r = s.call("POST", f"/api/jobs/{c['job_a']}/roadmap", token=c["seeker"])
        check(r["method"] == "rules", f"method {r['method']}")
        gaps = ", ".join(g["name"] for g in r["gaps"]) or "-"
        return f"gaps: {gaps}; {len(r['steps'])} bước" + (f"; {r['message']}" if r.get("message") else "")

    def interview():
        r = s.call("POST", f"/api/jobs/{c['job_a']}/interview-questions", token=c["seeker"])
        check(r["method"] == "rules", f"method {r['method']}")
        check(3 <= len(r["questions"]) <= 10, f"{len(r['questions'])} câu hỏi")
        return f"{len(r['questions'])} câu, ví dụ: {r['questions'][0]['question']}"

    def apply():
        a = s.call("POST", f"/api/jobs/{c['job_a']}/applications", token=c["seeker"], expect=(201,))
        c["application"] = a["id"]
        return f"đơn #{a['id']} vào job A, đánh giá: {a['evaluation_status']}"

    s.step("Seeker: đăng ký + /users/me consent", seeker_register)
    s.step("Seeker: hồ sơ công ty công khai có project", public_company, needs=("seeker", "project_id"))
    s.step("Seeker: upload CV", upload, needs=("seeker",))
    s.step("Seeker: AI tự kiểm tra CV", review, needs=("cv",))
    s.step("Seeker: xác nhận CV", confirm, needs=("cv",))
    s.step("Seeker: PUT preferences (public)", preferences, needs=("seeker",))
    s.step("Seeker: gợi ý job (polling)", recommendations, needs=("cv_confirmed",))
    s.step("Seeker: roadmap job A", roadmap, needs=("cv_confirmed", "job_a_published"))
    s.step("Seeker: câu hỏi phỏng vấn job A", interview, needs=("cv_confirmed", "job_a_published"))
    s.step("Seeker: apply job A", apply, needs=("cv_confirmed", "job_a_published"))

    # ── Company: applicants, talent, offer ──
    def applicants():
        url = f"/api/jobs/{c['job_a']}/applications"
        ranked, polls = s.poll(
            lambda: s.call("GET", url, token=c["company"]),
            lambda r: any(i["application_id"] == c["application"] and i["evaluation_status"] != "pending" for i in r["items"]),
        )
        mine = next((i for i in ranked["items"] if i["application_id"] == c["application"]), None)
        check(mine is not None, "không thấy đơn trong danh sách")
        check(mine["evaluation_status"] == "done", f"đánh giá {mine['evaluation_status']} sau {polls} lần gọi")
        check(mine["name"] == SEEKER_NAME and mine["email"] == seeker_email, "tên/email ứng viên sai")
        c["fit"] = mine["fit"]
        return f"total {ranked['total_count']}, đơn #{mine['application_id']} rank {mine['rank']}, Fit {mine['fit']} (sau {polls} lần gọi)"

    def filters():
        url, t, app = f"/api/jobs/{c['job_a']}/applications", c["company"], c["application"]

        def ids(params):
            r = s.call("GET", url, token=t, params=params)
            check(r["total_count"] >= 1, "total_count sai")
            return [i["application_id"] for i in r["items"]]

        check(app in ids({"status": "submitted"}), "status=submitted không có đơn")
        check(app in ids({"evaluation_status": "done", "min_fit": c["fit"]}), "evaluation_status=done&min_fit=Fit không có đơn")
        if c["fit"] < 100:
            check(app not in ids({"min_fit": c["fit"] + 0.1}), "min_fit cao hơn Fit vẫn có đơn")
        check(app not in ids({"evaluation_status": "failed"}), "evaluation_status=failed lại có đơn")
        s.call("PUT", f"/api/applications/{app}/status", token=t, json={"status": "reviewing"})
        check(app in ids([("status", "reviewing"), ("status", "interview")]), "status=reviewing&status=interview không có đơn")
        check(app not in ids({"status": "submitted"}), "đổi sang reviewing mà status=submitted vẫn có đơn")
        s.error("GET", url, 422, token=t, params={"min_fit": 101})
        return "status (1 và 2 giá trị), min_fit, evaluation_status, đổi trạng thái → reviewing, min_fit=101 → 422 đều đúng"

    def evaluation():
        ev = s.call("GET", f"/api/applications/{c['application']}/evaluation", token=c["company"])
        check(ev["status"] == "done" and ev["items"], f"evaluation {ev['status']}")
        scores = ", ".join(f"{i['name']} {i['score']}" for i in ev["items"])
        return f"Fit {ev['fit']}: {scores}"

    def talent():
        url = f"/api/jobs/{c['job_b']}/talent"
        mine = lambda r: next((i for i in r["items"] if f"smoke{tag}" in i["desired"]["job_keywords"]), None)  # noqa: E731
        result, polls = s.poll(lambda: s.call("GET", url, token=c["company"]), lambda r: mine(r) is not None)
        cand = mine(result)
        check(cand is not None, f"không thấy seeker sau {polls} lần gọi, {len(result['items'])} ứng viên, pending {result['pending_count']}")
        check(not ({"name", "email", "display_name"} & set(cand)), "talent lộ danh tính")
        c["anonymous_id"] = cand["anonymous_id"]
        applied_a = s.call("GET", f"/api/jobs/{c['job_a']}/talent", token=c["company"])
        check(mine(applied_a) is None, "seeker đã apply job A mà vẫn có trong talent của job A")
        return (f"{len(result['items'])} ứng viên (sau {polls} lần gọi); seeker = {cand['anonymous_id']}, Fit {cand['fit']}, "
                f"{cand['experience_years']} năm, kỹ năng {cand['skills'][:5]}; không có trong talent job A (đã apply)")

    def offer():
        body = {"job_id": c["job_b"], "anonymous_id": c["anonymous_id"], "message": f"안녕하세요, 플랫폼팀 백엔드 포지션을 제안드립니다. ({tag})"}
        o = s.call("POST", "/api/talent-offers", token=c["company"], json=body, expect=(201,))
        check(o["status"] == "pending" and o["contact"] is None, f"offer {o['status']}, contact {o['contact']}")
        c["offer"] = o["offer_id"]
        return f"offer #{o['offer_id']} pending, chưa lộ liên hệ"

    s.step("Công ty: danh sách ứng viên job A (polling)", applicants, needs=("application",))
    s.step("Công ty: filter ứng viên", filters, needs=("fit",))
    s.step("Công ty: chi tiết đánh giá", evaluation, needs=("fit",))
    s.step("Công ty: talent list job B (polling)", talent, needs=("job_b", "cv_confirmed", "application"))
    s.step("Công ty: gửi offer kèm message", offer, needs=("anonymous_id",))

    # ── Seeker answers, company sees the contact ──
    def seeker_offers():
        offers = s.call("GET", "/api/talent-offers/mine", token=c["seeker"])
        o = next((x for x in offers if x["offer_id"] == c["offer"]), None)
        check(o is not None, "không thấy offer")
        check(o["status"] == "pending" and tag in (o["message"] or ""), f"offer {o['status']}, message {o['message']!r}")
        return f"offer #{o['offer_id']} từ {o['company_name']} cho {o['job']['title']}, hết hạn {o['expires_at'][:10]}"

    def accept():
        o = s.call("POST", f"/api/talent-offers/{c['offer']}/accept", token=c["seeker"])
        check(o["status"] == "accepted", f"status {o['status']}")
        c["accepted"] = True
        return "accepted"

    def contact():
        sent = s.call("GET", "/api/talent-offers/sent", token=c["company"], params={"job_id": c["job_b"]})
        o = next((x for x in sent if x["offer_id"] == c["offer"]), None)
        check(o is not None, "không thấy offer đã gửi")
        check(o["status"] == "accepted" and o["contact"] == {"display_name": SEEKER_NAME, "email": seeker_email}, f"offer {o}")
        return f"contact {o['contact']['display_name']} <{o['contact']['email']}>"

    s.step("Seeker: xem offer", seeker_offers, needs=("offer",))
    s.step("Seeker: accept offer", accept, needs=("offer",))
    s.step("Công ty: thấy liên hệ sau accept", contact, needs=("accepted",))

    # ── Errors ──
    s.step("Lỗi: token sai → 401", lambda: s.error("GET", "/api/users/me", 401, token="not-a-valid-token"))
    s.step("Lỗi: không token vào API công ty → 401", lambda: s.error("GET", "/api/jobs/mine", 401))
    s.step("Lỗi: seeker gọi API công ty → 403", lambda: "; ".join([
        s.error("GET", "/api/jobs/mine", 403, token=c["seeker"]),
        s.error("POST", "/api/companies/me/projects", 403, token=c["seeker"], json={"name": "x"}),
        s.error("GET", f"/api/jobs/{c['job_a']}/applications", 403, token=c["seeker"]),
    ]), needs=("seeker", "job_a"))
    s.step("Lỗi: công ty gọi API seeker → 403", lambda: s.error(
        "GET", "/api/recommendations/jobs", 403, token=c["company"], code="SEEKER_ONLY"), needs=("company",))

    def draft_hidden():
        job = s.call("POST", "/api/jobs", token=c["company"], expect=(201,), json={**JOB, "title": "비공개 초안"})
        return s.error("GET", f"/api/jobs/{job['id']}", 404, code="JOB_NOT_FOUND")

    s.step("Lỗi: khách xem job draft → 404", draft_hidden, needs=("company",))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # ✅ and Korean on a Windows console
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=30, help="seconds to wait for background scoring")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60) as client:
        smoke = Smoke(client, args.timeout)
        run(smoke)
    total = smoke.passed + smoke.failed + smoke.skipped
    print(f"\nTổng: {total} bước — ✅ {smoke.passed} pass, ❌ {smoke.failed} fail, ⏭️ {smoke.skipped} bỏ qua")
    return 0 if smoke.failed == 0 and smoke.skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
