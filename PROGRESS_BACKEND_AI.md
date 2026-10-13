# Tiến độ Backend + AI — CareerSync

> Code: `main` @ `56371c6` + migration `0008` (`evaluations.queued_at`, `attempts`).
> `pytest` (qua `.venv`): **171 passed** trong ~5 s, không cần DB/mạng/key.
> Chỗ code và doc lệch nhau: §7.
> Ký hiệu: ✅ xong · 🟡 làm dở / có một phần · ❌ chưa có · **chưa chắc** = không kiểm chứng được bằng code.

---

## 0. Tóm tắt nhanh

- **Luồng lõi “công ty tự định nghĩa tiêu chí → chấm ứng viên → xếp hạng”: ✅ chạy thật end-to-end** (CV PDF → che PII → cấu trúc hoá → seeker xác nhận → apply → chấm điểm nền → rank theo Fit + bằng chứng → recruiter đổi trạng thái).
- **Nửa “gợi ý”**: ✅ API preferences + Pref (D15), ✅ gợi ý job `GET /api/recommendations/jobs` (D16). Chưa có code: gợi ý ứng viên (talent), offer.
- **Thiếu hẳn**: roadmap kỹ năng, câu hỏi phỏng vấn, AI tự kiểm tra CV, AI viết JD (chỉ có phân tích JD có sẵn), filter nhanh ứng viên, CRUD project công ty.
- **Switch rule/LLM**: ✅ cờ `AI_MODE` (`rules` mặc định / `llm`), key không tự bật LLM, không đọc `ANTHROPIC_API_KEY` (D12).
- **Public (D4)**: ✅ `GET /api/jobs` và `GET /api/jobs/{id}` không cần login. Còn `/criteria` cho guest (Q19) và frontend cho guest (#26).
- **Queue/retry (issue 2, 25)**: ✅ `claim()` (UPDATE có điều kiện) + fencing theo `queued_at`; retry 409 khi đang chạy.
- **Bảo mật/quyền riêng tư**: không thấy lộ điểm từng tiêu chí hay trọng số cho seeker; không lộ danh tính ứng viên chưa accept (vì tính năng talent chưa tồn tại). Rủi ro chính: JWT secret mặc định hardcode, không có rate limit cho endpoint gọi LLM.

---

## 1. Cấu trúc repo

| Phần | Stack | Vị trí |
|---|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, PyJWT (HS256), Argon2id | `backend/app/` |
| AI | Anthropic SDK (`anthropic` 1.11.0 trong `.venv`), sentence-transformers `intfloat/multilingual-e5-base` (fallback `hashing-ngram-v1`), PyMuPDF, regex | `ai/` |
| Dữ liệu tĩnh | `data/blocklist.yaml` (12 rule pháp lý), `data/skills.yaml` (từ điển skill/chứng chỉ) | `data/` |
| DB | PostgreSQL 16; migrations `0001`→`0008` | `backend/migrations/` |
| Frontend | React 19 + Vite + TS | `frontend/` |
| Infra | Docker Compose: `db`, `init` (migrate + seed), `backend`, `frontend` | `docker-compose.yml`, `scripts/` |

**Phân lớp backend**: `api/v1/*` (route + phân quyền qua `CurrentUser`/`CompanyUser` ở `core/deps.py`) → `services/*_service.py` (logic + DB) → `models/` (ORM). Service gọi AI qua `services/ai_runtime.py` (`skills()`, `embedder()`, `llm()`), test thay bằng `FakeLLM`/`HashingEmbedder`.

**Phân lớp AI** (`ai/`):
- `llm/client.py` — cổng duy nhất tới Claude (`get_llm_client()` trả `None` nếu không có key).
- `parsing/` — `pdf.py` (PDF→text), `pii.py` (che PII), `sections.py` (tách section/chunk), `extract.py` (`structure_cv`, `analyze_jd`, rule fallback), `profile.py` (schema `cv_profile.v1`).
- `scoring/` — `scorers.py` (1 scorer / category), `retrieval.py` (RAG đơn giản), `fit.py` (`score_candidate`, `aggregate_fit`, `rank`, `summary_comment`).
- `guardrails/` — blocklist tiêu chí, kiểm tra quote bằng chứng.
- `embedding/` — model embedding, từ điển skill.
- `bias/audit.py`, `cache/store.py` — stub 1 dòng `TODO`.
- `prompts/v1/` — `cv_structure.md`, `jd_analyze.md`, `rubric_score.md`.

**Entrypoint**: `backend/app/main.py` (`app = FastAPI(...)`, mount 7 router, handler `AppError`, `/health`).

**Cách chạy**
```bash
pytest                                        # từ root (dùng .venv: .venv/Scripts/python -m pytest)
cd backend && alembic upgrade head            # migrate
python scripts/seed.py                        # dữ liệu demo (hr@nextcode.test / seeker@demo.test, pw demo1234)
cd backend && uvicorn app.main:app --reload   # API :8000, Swagger /docs
docker compose up                             # db + migrate/seed + backend + frontend
```

---

## 2. Danh sách API endpoint

Mọi endpoint dưới đây đã implement. Endpoint thêm sau bảng này: `GET/PUT /api/preferences/me`, `GET /api/recommendations/jobs`.

“Auth”: — = không cần token · Login = mọi user · Company = `CompanyUser` (403 nếu không phải company) · Seeker = kiểm tra role trong service (403 `SEEKER_ONLY`).

| # | Method | Path | Auth | Làm gì | File |
|---|---|---|---|---|---|
| 1 | POST | `/api/auth/register` | — | Đăng ký seeker/company (bắt buộc 2 consent; company tạo luôn `companies`) | `api/v1/auth.py:13`, `auth_service.py:14` |
| 2 | POST | `/api/auth/login` | — | Trả Bearer token | `auth.py:18` |
| 3 | GET | `/api/users/me` | Login | User hiện tại | `users.py:10` |
| 4 | GET | `/api/companies/me` | Company | Hồ sơ công ty mình | `companies.py:12` |
| 5 | PUT | `/api/companies/me` | Company | Sửa tên, giới thiệu, 인재상 | `companies.py:17` |
| 6 | GET | `/api/companies/{company_id}` | Login | Hồ sơ công ty công khai | `companies.py:28` |
| 7 | POST | `/api/jobs` | Company | Tạo job nháp | `jobs.py:64` |
| 8 | GET | `/api/jobs` | Ai cũng gọi được (token tuỳ chọn) | Job published, chưa hết hạn; `q`, `limit`, `offset` | `jobs.py:69` |
| 9 | GET | `/api/jobs/mine` | Company | Job của công ty, mọi trạng thái | `jobs.py:82` |
| 10 | GET | `/api/jobs/{job_id}` | Ai cũng gọi được (token tuỳ chọn) | Chi tiết job (guest: published chưa hết hạn; owner thấy cả draft/closed) | `jobs.py:87` |
| 11 | PATCH | `/api/jobs/{job_id}` | Company | Sửa (sau publish chỉ deadline/location/salary_note) | `jobs.py:92` |
| 12 | DELETE | `/api/jobs/{job_id}` | Company | Xoá job nháp | `jobs.py:98` |
| 13 | POST | `/api/jobs/{job_id}/publish` | Company | Publish (cần JD + bộ tiêu chí hợp lệ + qua guardrail) | `jobs.py:104` |
| 14 | POST | `/api/jobs/{job_id}/close` | Company | Đóng job | `jobs.py:110` |
| 15 | POST | `/api/jobs/{job_id}/analyze` | Company | AI phân tích JD → gợi ý tiêu chí (không lưu) | `jobs.py:116` |
| 16 | GET | `/api/jobs/{job_id}/criteria` | Login | Company: full (có weight); seeker: tên + category + importance | `criteria.py:40` |
| 17 | PUT | `/api/jobs/{job_id}/criteria` | Company | Thay cả bộ tiêu chí (guardrail + log) | `criteria.py:58` |
| 18 | POST | `/api/jobs/{job_id}/criteria/copy-from/{source_job_id}` | Company | Copy tiêu chí sang job nháp | `criteria.py:68` |
| 19 | POST | `/api/criteria/check` | Company | Check guardrail realtime (không lưu) | `criteria.py:79` |
| 20 | POST | `/api/cv` | Seeker | Upload PDF → che PII → cấu trúc hoá (LLM/rule) | `cv.py:15`, `cv_service.py:158` |
| 21 | GET | `/api/cv/me` | Seeker | Version mới nhất của CV mới nhất | `cv.py:23` |
| 22 | GET | `/api/cv/{profile_id}` | Seeker (của mình) | Đọc 1 version | `cv.py:28` |
| 23 | PUT | `/api/cv/{profile_id}` | Seeker (của mình) | Lưu chỉnh sửa thành version mới; `confirm` | `cv.py:33` |
| 24 | POST | `/api/jobs/{job_id}/applications` | Seeker | Apply bằng CV đã confirm; chấm điểm chạy nền | `applications.py:23`, `application_service.py:55` |
| 25 | GET | `/api/applications/mine` | Login (company nhận `[]`) | Đơn của mình + trạng thái + trạng thái đánh giá | `applications.py:36` |
| 26 | GET | `/api/jobs/{job_id}/applications` | Company | Ứng viên xếp theo Fit | `applications.py:41`, `application_service.py:98` |
| 27 | GET | `/api/applications/{id}/evaluation` | Company | Điểm, lý do, bằng chứng từng tiêu chí + tóm tắt mạnh/yếu | `applications.py:50`, `application_service.py:147` |
| 28 | POST | `/api/applications/{id}/evaluation/retry` | Company | Chạy lại đánh giá `failed` hoặc `pending` quá 10 phút; 409 khi đang chạy | `applications.py:59`, `application_service.py:204` |
| 29 | PUT | `/api/applications/{id}/status` | Company | Recruiter đổi trạng thái đơn | `applications.py:70` |
| 30 | GET | `/health` | — | Health check | `main.py:24` |

Endpoint `[Planned]`, **chưa tồn tại**: `GET /api/jobs/{job_id}/talent`, `/api/talent-offers*`, `/api/companies/me/projects` (doc §4.2).

---

## 3. Đối chiếu feature / yêu cầu

### 3.1 Yêu cầu cốt lõi

| Yêu cầu | Trạng thái | Căn cứ |
|---|---|---|
| Công ty tự định nghĩa tiêu chí, lưu DB | ✅ | `job_criteria` (`models/criteria.py`); `criteria_service.replace_set` (`criteria_service.py:121`); 1–10 mục, tên unique, tổng weight = 100 (`:60-78`); guardrail pháp lý + log (`:81-103`); khoá sau publish, chỉ đổi weight (`:106-115`) |
| Dùng tiêu chí đó để **xếp hạng ứng viên** | ✅ | `evaluation_service.evaluate` (`evaluation_service.py:36`) → `score_candidate` (`ai/scoring/fit.py:22`); rank ở `application_service.ranked` (`application_service.py:98-144`); Fit tính lúc đọc từ weight hiện tại (`evaluation_service.py:93-99`) |
| Dùng **cùng model** để gợi ý job cho seeker | ❌ | Không có code. Evaluation đã được key theo job × CV version để tái dùng (`models/application.py:58`), `load_for_scoring` ghi là “read path for scoring and recommendation” (`criteria_service.py:208`) — mới là chuẩn bị |
| Pref, tính Pref trước | 🟡 | Hàm `ai/scoring/pref.py` `pref_score` + API `GET/PUT /api/preferences/me` (D15). Thứ tự “Pref trước” thuộc API gợi ý job (#7), chưa có |
| Final = 0.5·Fit + 0.5·Pref | ✅ | `recommendation_service.recommend`; hằng `RECO_*` trong `core/config.py` |
| Fit ≥ 40 **và** Pref ≥ 40 mới gợi ý | ✅ | Pref lọc trước, Fit sau (D2) |
| Seeker chỉ thấy match band, không thấy điểm từng tiêu chí | 🟡 | Phần “không thấy điểm”: ✅ — không endpoint nào trả score cho seeker (`ApplicationOut` chỉ có `evaluation_status`, `schemas/application.py:12-19`; seeker xem criteria không có weight, `criteria.py:48-55`). Phần “match band”: ✅ backend (매우 적합/적합/참고, D16); frontend vẫn hiện % giả `demoMatch` |
| Talent recommendation chỉ cho seeker opt-in | ❌ | Chỉ có cột `profile_public` (`models/matching.py:25`), không API |
| Công ty thấy profile ẩn danh tới khi seeker accept offer | ❌ | Chỉ có bảng `talent_offers` (`models/matching.py:101`), không API |
| `GET /api/jobs`, `GET /api/jobs/{id}` xem được khi chưa login | ✅ | Cả hai dùng `CurrentUser` (`jobs.py:72`, `jobs.py:88`) → 401 khi không có token. `get_visible_job` cũng cần `user` (`job_service.py:55`) |
| Dev dùng rule-based, LLM chỉ cho quality test/demo, có switch | ✅ | `AI_MODE` trong `ai/llm/client.py` (D12); `llm` thiếu key hoặc giá trị sai → dừng lúc khởi động (`main.py` lifespan). Model mặc định `claude-sonnet-5-5` ✅ |

### 3.2 Feature seeker

| Feature | Trạng thái | Căn cứ / ghi chú |
|---|---|---|
| Upload CV / profile | ✅ | `POST /api/cv` → `cv_service.upload` (`cv_service.py:158-187`): PDF ≤5 MB/≤5 trang, che PII, cấu trúc hoá, lưu quan hệ; sửa = version mới (`:217-236`), `confirm` |
| AI self-check profile (feedback điểm mạnh/cần cải thiện) | ❌ | Chỉ có cấu trúc hoá + `summary` 2 câu trung lập (chỉ ở mode LLM; mode rule `summary=""`, `extract.py:210`). Không có endpoint feedback. Doc Q8 ghi “AI CV feedback” chưa quyết |
| Xem job | 🟡 | Có list/detail (`jobs.py:69`, `:87`) nhưng bắt login (xem 3.1) |
| Xem match band (D1) | 🟡 | Có trong `GET /api/recommendations/jobs`; frontend chưa dùng |
| Apply | ✅ | `application_service.apply` (`application_service.py:55-77`): check seeker, job published + chưa hết hạn, consent AI, CV confirm, chưa apply |
| Theo dõi trạng thái | ✅ | `GET /api/applications/mine` (`applications.py:36`) trả `status` + `evaluation_status` |
| Skill roadmap cho phần thiếu | ❌ | Không có backend; trang `seeker/Prep` là “준비 중” |
| Câu hỏi phỏng vấn theo JD | ❌ | Không có. (`summary_comment` cho recruiter chỉ nói “면접 등에서 확인이 필요”, `ai/scoring/fit.py:78`) |

### 3.3 Feature employer

| Feature | Trạng thái | Căn cứ / ghi chú |
|---|---|---|
| Đăng ký business | 🟡 | `register` role `company` + `company_name` (`schemas/auth.py:44`, `auth_service.py:20-23`). Chưa có 사업자등록번호 và validate định dạng (D6, Q6) |
| Hồ sơ công ty (giới thiệu, 인재상) | ✅ | `companies.py:17-25`; 인재상 được đưa vào chấm tiêu chí `other` (`scorers.py:197-201`) |
| Đăng job | ✅ | draft → published → closed (`job_service.py`) |
| AI hỗ trợ viết JD | 🟡 | Chỉ có `POST /jobs/{id}/analyze`: đọc JD **đã viết** → gợi ý tiêu chí + weight (`extract.py:290-304`). Không sinh/viết lại JD. Tiêu chí gợi ý chưa qua guardrail (issue 7). Frontend chưa gọi |
| Nhận đơn | ✅ | `GET /api/jobs/{id}/applications` |
| Set tiêu chí riêng | ✅ | `PUT /api/jobs/{id}/criteria` + check realtime + copy |
| Dashboard ứng viên đã rank + điểm mạnh/yếu | ✅ | Rank theo Fit ↓, số tiêu chí ≥75 ↓, apply sớm (`fit.py:64-66`); chi tiết từng tiêu chí với lý do + bằng chứng + `summary` mạnh/yếu (`application_service.py:147-192`, `fit.py:69-81`); có `AI_NOTICE` |
| Filter nhanh | ❌ | `ranked()` không nhận tham số filter (status, Fit tối thiểu, trạng thái đánh giá…) (`applications.py:46`); frontend `Applicants.tsx` cũng không có filter |
| Project đang chạy của công ty | ❌ | Chỉ có bảng `company_projects`, `company_project_techs` (`models/matching.py:124-154`); không API; cách dùng trong scoring chưa quyết (Q3) |
| Đổi trạng thái đơn | ✅ | `set_status` (`application_service.py:195`); AI không bao giờ gọi (đúng quy tắc 5) |
| Gợi ý ứng viên (talent) + offer | ❌ | Xem 3.1 |

---

## 4. Phần AI

### 4.1 Có gì / thiếu gì

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| Fit scoring (theo tiêu chí công ty) | ✅ | 6 category, rule cho `skill`/`experience`/`certificate`/`education`; `project`/`other` = LLM rubric (0/25/50/75/100) với quote được verify + retry 1 lần → fallback retrieval (`scorers.py:204-229`) |
| Công thức Fit | ✅ đúng spec | `Σ(weight·score)/Σweight`, làm tròn 1 chữ số; tiêu chí thiếu điểm = 0 (`fit.py:48-53`). Weight là weight hiệu dụng (bỏ tiêu chí bị blocklist mới chặn, scale lại về 100) (`criteria_service.py:208-243`) |
| Pref | ✅ | `ai/scoring/pref.py` (D15); chưa endpoint nào dùng |
| Final + ngưỡng 40 | ✅ | `recommendation_service` |
| Match band (매우 적합 ≥80 / 적합 60–79 / 참고 40–59) | ✅ | `recommendation_service.match_level` (D16) |
| Roadmap kỹ năng | ❌ | |
| Câu hỏi phỏng vấn | ❌ | |
| CV structuring | ✅ | LLM (`cv_structure.md`) hoặc rule; skill chuẩn hoá theo từ điển; số tháng kinh nghiệm tính bằng code (`extract.py:58-79`) |
| Phân tích JD → gợi ý tiêu chí | ✅ | LLM hoặc rule; weight scale lại = 100 (`extract.py:279-287`) |
| Che PII trước LLM | ✅ | email, URL, 주민번호, SĐT, ngày sinh, địa chỉ, `display_name` (`pii.py`). Có test `test_no_personal_data_reaches_the_llm` (`backend/tests/test_applications_api.py:201`) |
| Guardrail tiêu chí (luật 채용절차법) | ✅ | 12 rule, log khi chặn; kiểm lại lúc load để chấm |
| Verify quote của LLM | ✅ | `guardrails/evidence.py` (fuzzy ≥ 0.9) |
| Switch rule-based / LLM | 🟡 | Xem 4.3 |
| Cache LLM, bias audit, log token | ❌ | Stub / chưa có (issues 9, 10) |

### 4.2 Logic có đúng spec không

- **Fit** — đúng như doc §6: weighted mean 0–100; weight đổi thì rank lại không cần gọi AI (có test `test_weight_change_reranks_without_rescoring`).
- **Dùng chung tiêu chí cho cả rank và gợi ý** — mới đúng ở mức thiết kế (evaluation key theo job × CV version, `load_for_scoring` là đường đọc duy nhất). Phần gợi ý chưa có nên chưa kiểm chứng được.
- **Thứ tự “tính Pref trước”** — chưa có code. Khi làm cần theo đúng doc §6.1: lọc ứng viên → Pref, bỏ < 40 → lấy evaluation `done`, xếp hàng phần thiếu (có giới hạn) → Fit, bỏ < 40 → Final → sort.
- **Vấn đề logic chấm điểm hiện có** (ảnh hưởng chất lượng demo):
  1. ✅ Đã sửa (`required_years`: không đọc năm như “2020년”, tháng quy ra năm, 신입 = 0; `min_experience_years` NULL = 신입, D14). Trước đây: `experience`: regex `(\d{1,2})\s*(?:년|years?)` lấy số đầu tiên trong tên/mô tả tiêu chí → “2020년 이후 경력” thành **yêu cầu 20 năm** (đã chạy thử) (`scorers.py:117-122`).
  2. `experience`: cộng **mọi** kinh nghiệm, không xét liên quan tới vị trí (tiêu chí “관련 직무 경력” vẫn đếm cả việc không liên quan) (`scorers.py:124-125`).
  3. ✅ Đã sửa (chỉ so với ngành tiêu chí nêu; tiêu chí education bắt buộc nêu ngành, tiêu chí cũ không nêu ngành → 50, D13). Trước đây: `education`: nếu mô tả tiêu chí không nêu ngành (từ kết thúc bằng 공학/학과/전공), dùng danh sách ngành **hardcode cho IT** (`_RELATED_MAJOR`, `scorers.py:37`) → job không phải IT vẫn cho ngành CNTT 100 điểm.
  4. ✅ Đã sửa (#15: chấm theo luật chỉ đọc `masked_text`). Trước đây: `skill`: danh sách skill do seeker tự sửa (`have = set(candidate.profile.skills)`, `scorers.py:84`) và `source` do seeker sửa được dùng làm bằng chứng cho `experience`/chứng chỉ chung/“uses” (issue 3) → seeker có thể tự nâng điểm. Chấp nhận được cho luồng apply (recruiter xem bằng chứng), **phải sửa trước talent**.
  5. Retrieval embed lại toàn bộ chunk CV cho mỗi tiêu chí (issue 8); `_most_similar` embed lại toàn bộ skill cho mỗi skill thiếu (`scorers.py:107-112`). Chậm với e5 trên CPU, không sai.
- **Quy tắc AI trong `CLAUDE.md`** (kiểm bằng grep): `ai/` không import `app.*` ✅; `anthropic` chỉ import trong `ai/llm/client.py:35` ✅; status đơn chỉ đổi bởi `set_status` ✅; `api/v1/jobs.py:7` và `api/v1/cv.py:6` import thẳng từ `ai.*` (không qua service/`ai_runtime`) — doc đã ghi nhận, không phạm quy tắc 2/8 nhưng lệch phân lớp.

### 4.3 Switch rule-based / LLM

- Hiện tại: `get_llm_client()` chỉ trả client khi `AI_MODE=llm` và có `LLM_API_KEY`; `rules` (mặc định) → `None` kể cả khi có key; `llm` thiếu key hoặc giá trị sai → `LLMConfigError`, backend không khởi động (`ai/llm/client.py`, `main.py`). Mọi caller có fallback rule: `structure_cv` (`extract.py:226-236`), `analyze_jd` (`:290-304`), `score_one` (`scorers.py:249-260`). Test luôn chạy không key (`conftest.py:113-117`). Compose truyền `AI_MODE` (mặc định `rules`), `LLM_API_KEY` (mặc định rỗng) và mặc định embedder hashing (`docker-compose.yml:14-16`).
- Thiếu so với yêu cầu “dev dùng rule, LLM chỉ cho quality test + demo”:
  - Không bật/tắt theo từng tính năng (CV / JD / chấm điểm) — **chưa chắc** có cần không.
  - Không log token/chi phí (issue 10), không cache (issue 9) → khó làm quality test có kiểm soát chi phí.
- Tham số SDK `messages.parse(output_format=..., output_config={"effort": ...})` khớp chữ ký của `anthropic` 1.11.0 trong `.venv`. **Chưa chắc** hành vi thật với `claude-sonnet-5-5` + `effort=low` vì chưa có lần gọi thật nào. `TypeError`/lỗi khác ngoài `APIStatusError`/`APIConnectionError`/`ValueError` sẽ **không** được đổi thành `LLMError` (`client.py:52-57`) → upload CV trả 500 thay vì fallback rule.

---

## 5. Bug, hardcode, validation, test, bảo mật

### 5.1 Bug

| Mức | Bug | Vị trí | Hậu quả |
|---|---|---|---|
| Vừa | `ensure()` không bắt `IntegrityError` | `evaluation_service.py:24-33` | 2 request đồng thời cho cùng job × CV → 1 cái 500 (issue 25). Tương tự apply đồng thời → 500 do `uq_applications_job_seeker` |
| Vừa | Regex năm kinh nghiệm đọc năm lịch thành số năm | `scorers.py:117-122` | Điểm `experience` sai (xem 4.2) |
| Vừa | Scoring nằm trong `BackgroundTasks` cùng process | `applications.py:18-20` | Restart server → evaluation kẹt `pending` tới khi bấm 다시 분석 (issue 6) |
| Thấp | Tên công ty toàn khoảng trắng qua validation rồi thành rỗng | `companies.py:20`, `schemas/company.py:14` | Issue 13 |
| Thấp | Seeker sửa một version của CV **cũ** → version mới nằm ở document cũ, không thành “mới nhất” | `cv_service.py:190-201`, `:217-236` | Seeker tưởng đã confirm nhưng apply vẫn báo `CV_NOT_CONFIRMED` (liên quan issue 15) |
| Thấp | `evaluation.error` trả nguyên `"{type}: {e}"` cho recruiter | `evaluation_service.py:76` | Có thể lộ chi tiết nội bộ (lỗi DB…) ra UI |
| Thấp | `llm_model` được ghi là model kể cả khi mọi tiêu chí rơi về retrieval/rule | `evaluation_service.py:68` | Metadata hơi sai; `method` từng tiêu chí vẫn đúng |

### 5.2 Hardcode

- `JWT_SECRET_KEY` mặc định `"dev-only-secret-change-me-in-production-please"` khi thiếu biến (`core/config.py:30`); compose mặc định `local-demo-secret-change-before-sharing` (`docker-compose.yml:13`). Biến rỗng → login 500 (issue 4).
- DB mặc định `postgres/postgres` (`core/config.py:20-21`).
- Tham số chấm điểm: `SKILL_LISTED=70`, `SKILL_USE_BONUS=10`, ngưỡng similarity 0.85/0.80, `_LANGUAGE_CERTS`, `EDUCATION_NEUTRAL_SCORE=50`, `_STEM_MAJOR` (`scorers.py:28-38`); `_RETRIEVAL_STEPS` (`scorers.py:233`); `STRONG_SCORE=75`, ngưỡng “yếu” `< 40` (`fit.py:19`, `:73`); `max_workers=4` (`fit.py:42`).
- Giới hạn PDF 5 MB / 5 trang / 40 ký tự mỗi trang (`parsing/pdf.py:4-7`).
- `PROMPT_VERSION = "v1"` (`extract.py:27`).
- Các hằng `RECO_*`, `EVALUATION_STALE_MINUTES`… trong doc §9 **chưa có** trong `config.py`.

### 5.3 Thiếu validation

- `CompanyUpdate.name` không chặn chuỗi toàn khoảng trắng (issue 13).
- `GET /api/jobs?q=` không escape `%`/`_` trong `ilike` (`job_service.py:143`) — không phải SQL injection, chỉ wildcard ngoài ý muốn.
- Tiêu chí do `/analyze` gợi ý không qua guardrail (issue 7).
- Không có giới hạn kích thước body ở tầng server: `file.read(MAX_BYTES + 1)` chỉ cắt sau khi multipart đã được parse (`cv.py:17`) — **chưa chắc** mức ảnh hưởng, phụ thuộc cấu hình Starlette/proxy.
- Không validate `limit` gợi ý / daily cap (vì chưa có).

### 5.4 Thiếu test

Có 171 test (gồm test tham số hoá guardrail). Chưa có test cho:
- `AnthropicClient` ánh xạ lỗi SDK → `LLMError` (có thể mock SDK, không gọi thật).
- FK trên SQLite (`PRAGMA foreign_keys` tắt, issue 5); model ↔ migration drift (test dùng `create_all`, issue 18).
- Toàn bộ phần gợi ý / talent (chưa có code).

### 5.5 Bảo mật / quyền riêng tư

| Kiểm tra | Kết quả |
|---|---|
| Lộ điểm từng tiêu chí hoặc weight cho seeker | **Không thấy**. Seeker chỉ nhận `evaluation_status` (`schemas/application.py:12-19`); `/evaluation` và `/applications` của job là `CompanyUser`; criteria cho seeker không có weight (`criteria.py:48-55`). Importance (높음/보통/낮음) suy từ weight là lộ thô có chủ đích |
| Lộ danh tính ứng viên chưa accept | **Không áp dụng** — talent/offer chưa có. Danh sách ứng viên trả `name` + `email` (`application_service.py:118-119`) nhưng chỉ cho người **đã apply** vào job của chính công ty (đúng doc). Khi làm talent phải theo doc §6.1 (ẩn `reason`/`evidence`, kiểm `profile_public` mỗi lần đọc) |
| Công ty xem đơn của công ty khác | Không — `get_owned` trả 404 (`application_service.py:87-95`) |
| PII tới LLM | Đã che theo regex + `display_name`; tên viết khác (vd. tên tiếng Anh) trong CV **không** bị che — **chưa chắc** mức rủi ro |
| JWT secret mặc định | Rủi ro nếu demo public mà quên đặt biến → ai biết repo đều ký được token |
| Rate limit | Không có cho `POST /api/cv`, `/analyze`, apply, retry → có thể đốt credit LLM (issue 22) |
| Token ở `localStorage` | Phía frontend (issue 12) |

---

## 6. Việc backend + AI còn phải làm (ưu tiên cho demo trước)

Ước lượng: **Nhỏ** ≈ ≤ ½ ngày · **Vừa** ≈ 1–2 ngày · **Lớn** ≈ ≥ 3 ngày. “Cần xác nhận” = nằm trong danh sách “Never, even if asked casually” của `CLAUDE.md` hoặc là quyết định chưa chốt.

### P0 — cần cho demo

| # | Việc | Cỡ | Phụ thuộc |
|---|---|---|---|
| 0 | Commit `0008` + thay đổi `models/application.py` (đang chưa commit trên `main`) | — | Long commit |
| 1 | ~~Cờ `AI_MODE` + bỏ đọc `ANTHROPIC_API_KEY` (issue 1)~~ ✅ xong (D12). Còn: bắt mọi lỗi SDK thành `LLMError` | Nhỏ | — |
| 2 | ~~Sửa upload CV chặn event loop~~ ✅ xong (`upload_cv` là `def`; test `test_cv_upload_concurrency.py`) | Nhỏ | — |
| 3 | ~~Luật queue/retry (issue 2, 25, doc §6.1)~~ ✅ xong (`claim()`, fencing, `ensure()` savepoint, apply trùng → 409; test `test_evaluation_queue.py`) | Vừa | — |
| 4 | ~~Public `GET /api/jobs`, `GET /api/jobs/{id}`~~ ✅ xong (`OptionalUser`, test `test_jobs_public.py`). Còn: `GET /api/jobs/{id}/criteria` cho guest | Nhỏ | Q19 |
| 5 | ~~Thêm `AI_NOTICE` vào `CvOut`, `JdAnalysisOut` (issue 28)~~ ✅ xong. Còn: frontend hiển thị `notice` | Nhỏ | — |
| 6 | ~~API preferences `GET/PUT /api/preferences/me`~~ ✅ xong (D15; test `test_preferences_api.py`, `test_pref.py`). Còn: frontend form | Vừa | Q10 khi làm offer |
| 7 | ~~Gợi ý job `GET /api/recommendations/jobs`~~ ✅ xong (D16; test `test_recommendations_api.py`). Còn: frontend thay `demoMatch` bằng band | Lớn | — |

### P1 — feature trong spec nhưng chưa có (cần chốt phạm vi, doc Q8)

#### P1-A — Talent recommendation + offer

Thứ tự: #15 → #18 (D18). #16 (worker) để sau demo; #17 (giới hạn chi phí) làm cùng #18 bằng cách đếm dư, không migration.

| # | Việc | Cỡ | Phụ thuộc |
|---|---|---|---|
| 15 | ~~Issue 3: bằng chứng `experience`/chứng chỉ/“uses” lấy từ `masked_text`, không từ `source` seeker sửa được~~ ✅ xong (test `test_scoring.py`, `test_cv_edits_scoring.py`; kèm sửa che ngày sinh nuốt dòng mới trong `pii.py`) | Vừa | — |
| 18 | Talent recommendation + offer (ẩn danh, `profile_public` kiểm mỗi lần đọc, liên hệ chỉ sau `accepted`, chặn offer `pending` trùng) — ✅ danh sách `GET /api/jobs/{id}/talent` (D19) + offer `/api/talent-offers*` + migration 0009 (D20); test `test_talent_api.py`, `test_offer_api.py`. Còn: frontend trang 인재 추천 và hộp offer của seeker | Lớn | — |

#### P1-B — Roadmap kỹ năng + câu hỏi phỏng vấn

| # | Việc | Cỡ | Phụ thuộc |
|---|---|---|---|
| 9 | ~~Câu hỏi phỏng vấn theo JD~~ ✅ xong: `POST /api/jobs/{id}/interview-questions` (D21), chung cache và giới hạn với roadmap; test `test_interview.py`, `test_career_api.py`. Còn: frontend trang 취업 준비 | Vừa | — |
| 10 | ~~Skill roadmap cho gap~~ ✅ xong: `POST /api/jobs/{id}/roadmap`, gap theo phương án C (D21), cache `career_contents` (migration 0010), `data/learning_resources.yaml`; test `test_roadmap.py`, `test_career_api.py`. Còn: frontend trang 취업 준비 | Vừa | — |

#### P1-C — Lặt vặt: AI tự kiểm tra CV, AI hỗ trợ viết JD, filter nhanh ứng viên, CRUD project công ty

| # | Việc | Cỡ | Phụ thuộc |
|---|---|---|---|
| 8 | Filter nhanh ứng viên: query param `status`, `min_fit`, `evaluation_status` trên `GET /api/jobs/{id}/applications` | Nhỏ | Frontend: UI filter |
| 11 | AI self-check CV (điểm mạnh / cần bổ sung), có fallback rule, quote phải verify (quy tắc 4) | Vừa | Q8; frontend |
| 12 | AI hỗ trợ **viết** JD (sinh nháp từ tiêu đề/từ khoá) + chạy guardrail cho tiêu chí gợi ý (issue 7) | Vừa (guardrail riêng: Nhỏ) | Frontend chưa gọi `/analyze` |
| 13 | CRUD project công ty `/api/companies/me/projects` | Nhỏ–Vừa | Q3 quyết cách dùng trong scoring (CRUD làm được trước). Frontend |
| 14 | ~~Regex năm, `education` không hardcode ngành IT~~ ✅ xong. Còn: `experience` xét liên quan (Vừa) | Vừa | Làm thay đổi điểm của evaluation mới; không đổi công thức Fit |

### P2 — sau demo / đang bị chặn

| # | Việc | Cỡ | Phụ thuộc |
|---|---|---|---|
| 16 | Issue 6: queue bền (worker riêng hoặc DB-polling) thay `BackgroundTasks` | Lớn | Thêm container worker (có thể Redis) vào Compose; có thể cần cột/bảng mới (migration) |
| 17 | ~~Issue 26: giới hạn chi phí cho talent~~ ✅ xong cùng #18: 10/lần, 30/công ty/ngày chỉ khi `llm`, đếm dư, không migration (D19) | Vừa | — |
| 19 | Rate limit cho endpoint gọi LLM (issue 22) | Vừa | Có thể làm ở tầng proxy |
| 20 | JWT: fail-fast khi `JWT_SECRET_KEY` rỗng/mặc định ngoài môi trường dev (issue 4) | Nhỏ | **Cần xác nhận** (auth/security); sửa cả compose |
| 21 | Nợ test: `PRAGMA foreign_keys` cho SQLite (issue 5, Nhỏ), test drift migration (issue 18, Vừa), test ánh xạ lỗi `AnthropicClient` (Nhỏ) | Nhỏ–Vừa | Sửa `conftest.py` ở root |
| 22 | Hiệu năng/chi phí: cache embedding chunk (issue 8), cache LLM theo hash (issue 9), log token (issue 10) | Vừa | — |
| 23 | Xoá CV / tài khoản (issue 11) | Vừa | Q5; FK `RESTRICT` (cần migration) |
| 24 | Bias audit (`ai/bias/audit.py`) | Vừa | Không chặn demo |
| 25 | Issue 4: `JWT_SECRET_KEY` rỗng phải được coi như thiếu biến (dùng dev default, như README mô tả); hiện rỗng → login 500 | Nhỏ | `core/config.py`; liên quan #20 |
| 26 | Frontend cho guest: vào danh sách và chi tiết job không cần login (`App.tsx` đang bắt login mọi trang); ẩn nút apply/khối tiêu chí khi chưa login | Nhỏ | Backend D4 xong; khối tiêu chí theo Q19; chạy `npm run build` |
| 27 | Frontend gợi ý + consent: trang 추천 dùng `GET /api/recommendations/jobs` (band, `pending_count`, bỏ `demoMatch`); câu đồng ý AI ở 회원가입 nêu “지원 평가 및 맞춤 추천” | Nhỏ–Vừa | D16; chạy `npm run build` |
| 28 | ~~Luồng đồng ý lại + rút lại đồng ý AI; upload CV kiểm tra consent~~ ✅ xong (D17; test `test_consent_api.py`). Còn: màn hình đồng ý lại ở frontend (đọc `consent_required`), nằm trong #27 | Nhỏ | — |
| 29 | Frontend 이력서: nhắc seeker rằng sửa CV (kỹ năng, ngày, ngành…) **không đổi điểm** — điểm theo file PDF gốc; muốn đổi thì upload lại PDF đã sửa | Nhỏ | #15 xong; chạy `npm run build` |
| 30 | Issue 29 (sau demo): `career_service` giữ khoá `users` trong lúc gọi LLM (~60 s) → giữ chỗ lượt trong transaction ngắn, nhả khoá rồi mới gọi LLM | Nhỏ–Vừa | Có thể cần cột trạng thái hoặc dòng tạm trong `career_contents` (migration) |
| 31 | Issue 30: bổ sung pattern dạng câu hỏi vào `data/blocklist.yaml` (vd. “결혼하셨나요”, “자녀 계획”) — ảnh hưởng cả guardrail tiêu chí | Nhỏ | Cần xác nhận pháp lý (Q14 trong DECISIONS) |

---

## 7. Ghi chú: chỗ chưa chắc, mâu thuẫn, code lệch doc

- **Hành vi thật của Claude API** (effort `low`, structured output với `claude-sonnet-5-5`): **chưa chắc**, chưa có lần gọi thật. Nên chạy một lần quality test có kiểm soát (synthetic CV) trước demo.
- **Model e5 trên máy demo**: lần chấm đầu sẽ tải ~1 GB nếu `EMBEDDING_MODEL` không phải `hashing-ngram-v1`; compose mặc định hashing. **Chưa chắc** demo dùng cái nào.
