# CareerSync — Quyết định và phạm vi (nguồn chuẩn)

> **Nguồn chuẩn duy nhất về tính năng và quyết định.** Mọi lần rà soát đều đối chiếu code với file này.
> Thấy mâu thuẫn hoặc chỗ chưa rõ: ghi vào [§3 Câu hỏi còn mở](#3-câu-hỏi-còn-mở), **không tự đoán**.
> Chỉ ghi vào §2 những gì Long đã chốt.
> Tạo: 2026-10-13.

---

## 1. Phạm vi demo

### 1.1 Bắt buộc có cho demo (đã chốt)

| Hạng mục | Quyết định |
|---|---|
| Xem job khi chưa login | `GET /api/jobs`, `GET /api/jobs/{job_id}` public — D4 |
| Match band cho seeker | Seeker chỉ thấy band (높음/보통/낮음) — D1 |
| Gợi ý job cho seeker | Final = 0.5·Fit + 0.5·Pref, ngưỡng 40/40, tính Pref trước — D2 |
| Chế độ AI | Mặc định rule-based; LLM bật bằng `AI_MODE` — D5, D12 |
| Đăng ký business | Validate định dạng 사업자등록번호 — D6 |
| Project đang chạy của công ty | Trong phạm vi — D8 |
| Cách chạy demo | Local bằng Docker Compose — D7 |

### 1.2 Trong phạm vi sản phẩm, chưa chốt có bắt buộc cho demo hay không

Có trong brief 2026-10-13; chưa chốt bắt buộc cho demo hay làm sau (Q10, Q11).

- Seeker: upload CV / profile, AI tự kiểm tra profile, xem job + match band, apply, theo dõi trạng thái, skill roadmap cho phần thiếu, câu hỏi phỏng vấn theo JD.
- Employer: đăng ký business, đăng job (AI hỗ trợ viết JD), nhận đơn, tự đặt tiêu chí đánh giá, dashboard ứng viên đã xếp hạng + điểm mạnh/yếu, filter nhanh, project đang chạy.
- Talent recommendation (opt-in, ẩn danh): quy tắc đã chốt (D3), phạm vi demo chưa chốt (Q8).

### 1.3 Ngoài phạm vi demo

| Hạng mục | Quyết định |
|---|---|
| Xác minh 사업자등록번호 thật (gọi API 국세청 v.v.) | Không làm trong demo — D6 |
| Deploy lên server/cloud | Không làm trong demo; demo chạy local — D7 |

---

## 2. Quyết định đã chốt

| ID | Ngày | Quyết định | Lý do ngắn |
|---|---|---|---|
| D1 | 2026-10-13 | Seeker chỉ thấy **match band**; **không** thấy Fit %, Final, điểm từng tiêu chí hay weight. | Không lộ cách công ty chấm và trọng số; tránh seeker coi điểm AI là kết quả tuyển dụng |
| D2 | 2026-10-13 | Gợi ý job: **Final = 0.5·Fit + 0.5·Pref**; chỉ gợi ý khi **Fit ≥ 40 và Pref ≥ 40**; **tính Pref trước**, chỉ tính Fit cho job đã qua ngưỡng Pref. | Cân bằng năng lực và mong muốn; tính Pref trước để bớt số evaluation và số lần gọi LLM |
| D3 | 2026-10-13 | Talent recommendation chỉ gồm seeker **opt-in**; công ty chỉ thấy **profile ẩn danh** cho tới khi seeker **chấp nhận offer**. | Quyền riêng tư (개인정보 보호법); seeker kiểm soát việc bị liên hệ |
| D4 | 2026-10-13 | `GET /api/jobs` và `GET /api/jobs/{job_id}` **public**, không cần login. | Khách xem được job trước khi đăng ký; apply, CV và tính năng AI vẫn cần login |
| D5 | 2026-10-13 | Dev dùng **rule-based**. LLM (Claude API, **Sonnet 5.5**) chỉ dùng cho quality test và demo, bật bằng cờ **`AI_MODE`** tường minh; **không** tự bật chỉ vì có API key. | Kiểm soát chi phí, tránh gọi API có phí ngoài ý muốn |
| D6 | 2026-10-13 | Đăng ký business: **chỉ validate định dạng** 사업자등록번호; **không** xác minh thật (ngoài phạm vi demo). | Xác minh thật cần dịch vụ bên ngoài, không cần cho demo |
| D7 | 2026-10-13 | Demo chạy **local bằng Docker Compose**. | Một lệnh chạy được cả hệ thống, không phụ thuộc hạ tầng ngoài |
| D8 | 2026-10-13 | Feature **project đang chạy của công ty**: **trong phạm vi**. | Có trong brief và 과제계획서 |
| D9 | 2026-10-13 | Quyết định và phạm vi: `docs/DECISIONS.md` (nguồn chuẩn). Tài liệu kỹ thuật (API, schema, cách chạy): `PROJECT_DOCUMENTATION.md`. | Mỗi loại thông tin chỉ có một nơi chuẩn, tránh hai tài liệu mâu thuẫn |
| D10 | 2026-10-13 | “Đã chốt” = có trong `docs/DECISIONS.md` (quy tắc 7 `CLAUDE.md`); nhãn `[Recommended]`/`TBD` trong `PROJECT_DOCUMENTATION.md` chỉ là gợi ý. Đầu `PROJECT_DOCUMENTATION.md` trỏ sang file này; nếu mâu thuẫn thì file này đúng. | Một định nghĩa duy nhất cho “đã chốt” |
| D11 | 2026-10-13 | Thứ tự ưu tiên: `docs/DECISIONS.md` > `PROJECT_DOCUMENTATION.md` > code. Code lệch doc thì sửa code, giữ doc; nghi doc sai hoặc lỗi thời thì hỏi Long. `[Planned]` = hướng dự kiến, chưa phải quyết định. Quyết định chỉ ghi ở file này; `PROJECT_DOCUMENTATION.md` chỉ ghi nội dung kỹ thuật. README, 설계서, Swagger và comment trong code không phải nguồn quyết định. | Doc là chuẩn để code bám theo; tránh code hoặc tài liệu phụ tự định nghĩa quyết định |
| D12 | 2026-10-13 | `AI_MODE` nhận `rules` hoặc `llm` (không phân biệt hoa thường; không đặt/rỗng = `rules`). Chỉ `llm` mới gọi LLM; có key mà ở `rules` thì không gọi. Chỉ đọc `LLM_API_KEY`, không đọc `ANTHROPIC_API_KEY`. `AI_MODE=llm` mà thiếu key → backend dừng lúc khởi động, không fallback rule. Giá trị khác → báo lỗi lúc khởi động. Compose mặc định `rules`. | Chi tiết của D5; quality test/demo phải biết chắc đang chạy LLM, gõ sai không được âm thầm đổi mode |
| D13 | 2026-10-13 | Tiêu chí `education` phải nêu ít nhất một ngành (trong tên hoặc mô tả) hoặc 이공계/STEM; không thì lưu (`PUT /criteria`, `copy-from`) và publish bị từ chối với 422 `CRITERIA_MAJOR_REQUIRED`. Job đã publish chỉ đổi weight nên không bị chặn. Tiêu chí education cũ không nêu ngành được chấm **50** (trung tính, như nhau cho mọi ứng viên, reason “전공 미지정”, không cần bằng chứng). Chỉ so với ngành tiêu chí nêu; không có danh sách ngành liên quan cài sẵn. | Không có ngành thì không có căn cứ chấm; retrieval với embedder hashing cho 0 với mọi ứng viên. Điểm trung tính giữ nguyên thứ hạng và không phải đổi Fit hay `load_for_scoring` |
| D14 | 2026-10-13 | Số năm kinh nghiệm yêu cầu: lấy từ tiêu chí (“3년”; “3~5년” → 3; “1년 6개월” → 1.5; “6개월” → 0.5; “신입” → 0; năm như “2020년” không phải thời hạn); tiêu chí không nêu thì lấy `job_postings.min_experience_years`; **NULL = 신입 (0 năm)**, không có mặc định 2 năm. Yêu cầu 0 năm → mọi ứng viên 100 (không cần bằng chứng). | Khớp `PROJECT_DOCUMENTATION.md` §3.2 (“NULL = 신입 가능”); tháng không bị bỏ |
| D15 | 2026-10-13 | **Preferences + Pref.** Ba field: `locations`, `employment_types`, `job_keywords` (không lương/remote). Mỗi field 0 hoặc 100: địa điểm khớp khi bằng nhau hoặc chuỗi này chứa chuỗi kia (“서울” ↔ “서울 강남구”); loại hình khớp khi loại hình của job nằm trong danh sách; từ khoá khớp khi xuất hiện trong tiêu đề hoặc JD — từ khoá chữ Latin khớp theo nguyên từ (“Java” không khớp “JavaScript”). So sánh sau khi bỏ khác biệt hoa thường và khoảng trắng; chưa xử lý từ đồng nghĩa. **Pref = trung bình chỉ trên các field seeker đã điền**; không điền field nào → Pref = 100. Opt-in talent (`profile_public`) nằm trong `PUT /api/preferences/me`. Validate: mỗi danh sách tối đa 10 mục, mỗi mục 2–100 ký tự; mục trùng được gộp. | Sửa `PROJECT_DOCUMENTATION.md` §6.1 (trước đây field trống tính là khớp): như vậy field đã điền mất tác dụng — chỉ điền “서울”, job ở 부산 vẫn ra 66.7 và qua ngưỡng 40 |
| D16 | 2026-10-13 | **Gợi ý job cho seeker** (`GET /api/recommendations/jobs`). Chỉ trả job đã có Fit (evaluation `done`); job đang phân tích chỉ được đếm trong `pending_count`. Band theo Final: **매우 적합** ≥ 80 · **적합** 60–79 · **참고** 40–59. Response không có Fit/Pref/Final/điểm từng tiêu chí/weight, không có `matched`/`gaps` (Q3). Giới hạn: tối đa **10** lần xếp hàng evaluation mỗi lần gọi (luôn áp dụng); **30**/seeker/ngày (KST) **chỉ khi `AI_MODE=llm`**; recommendation tự xếp hàng lại một evaluation tối đa **3** lần. Các lần gọi của cùng seeker chạy lần lượt (`SELECT … FOR UPDATE` trên `users`). Chưa có CV đã xác nhận / chưa đồng ý → 409 `CV_NOT_CONFIRMED` / `AI_CONSENT_REQUIRED`. `CONSENT_VERSION` = `2026-10-13`; gợi ý cần `consent_version ≥ 2026-10-13` (đồng ý bản cũ → 409); apply và upload CV không xét version. | Chi phí ở mode LLM; rules mode không tốn tiền nên không giới hạn theo ngày. Dùng CV cho job seeker chưa apply là mục đích mới nên cần đồng ý lại |
| D17 | 2026-10-13 | **Đồng ý lại và rút lại đồng ý AI.** `POST /api/users/me/consent` (mọi user đã đăng nhập; body gồm `version` phải bằng `CONSENT_VERSION`, cả hai cờ đồng ý = true) ghi lại `consent_privacy_at`, `consent_ai_at`, `consent_version`; không lưu lịch sử (không migration). `DELETE /api/users/me/consent/ai` (chỉ seeker): `consent_ai_at = null`, giữ `consent_version`, tắt `profile_public`. Sau khi rút lại: chặn mọi lần dùng AI mới trên dữ liệu seeker — upload CV, apply, gợi ý (409 `AI_CONSENT_REQUIRED`), công ty bấm 다시 분석 (409 `AI_CONSENT_WITHDRAWN`); evaluation đã xếp hàng trước đó vẫn chạy nốt, không huỷ; CV, evaluation, đơn ứng tuyển giữ nguyên. Upload CV chỉ cần có `consent_ai_at` (không xét version). `/api/users/me` trả thêm `current_consent_version` và `consent_required`. | User đồng ý bản cũ cần cách nhận gợi ý (D16); 개인정보 보호법 cho phép rút lại đồng ý. Không bắt version mới khi upload để không chặn apply của user cũ |
| D18 | 2026-10-13 | **Điều kiện bật talent recommendation.** Làm issue 3 (#15: bằng chứng chấm điểm không lấy từ field seeker sửa được) **trước** talent. Issue 6 (chấm điểm trong tiến trình, restart làm evaluation kẹt `pending`) **coi như đã giảm nhẹ cho demo**: `claim()` xếp hàng lại `pending` quá `EVALUATION_STALE_MINUTES`, và mỗi lần gọi gợi ý/talent làm việc đó; worker riêng (#16) để sau demo. Issue 26 (chi phí) giải quyết trong talent bằng giới hạn 10/lần (luôn) và 30/công ty/ngày (chỉ `AI_MODE=llm`), đếm dư, không migration. | Doc §6.1 cấm bật talent trước khi xử lý issue 3, 6, 26; cơ chế xếp hàng lại đã có làm restart không còn để evaluation kẹt vĩnh viễn |

Quy tắc khi thêm dòng: ghi ngày chốt thật (không phải ngày ghi), lý do ≤ 1 câu. Đổi một quyết định thì thêm dòng mới ghi “thay D#”, không xoá dòng cũ.

---

## 3. Câu hỏi còn mở

Chỉ gồm những gì chưa chốt. Chốt xong thì chuyển thành một dòng ở §2 và xoá khỏi đây.

### 3.1 Lệch giữa 설계서 / `PROJECT_DOCUMENTATION.md` / code và file này

| # | Câu hỏi | Lệch ở đâu |
|---|---|---|
| Q1 | 설계서 ghi seeker xem **“적합도 점수”**, còn Figma và frontend đang hiện **%**. Xác nhận là các chỗ này bị D1 thay thế? | 설계서 기본 §3.1(4) (tr. 12–13: “추천 채용공고 목록과 적합도 정보”, “적합도 점수와 추천 근거”); Figma ghi chú “예시 데이터” (tr. 17); `frontend/src/pages/seeker/Recommended.tsx` + `mock/data.ts` `demoMatch` (%) |
| Q2 | Seeker đang thấy **mức quan trọng** của tiêu chí (높음/보통/낮음), suy từ weight (≥25 / ≥10). Như vậy có tính là “thấy weight” theo D1 không? Giữ hay bỏ? | `criteria_service.importance_level`, `GET /api/jobs/{id}/criteria` (seeker view); `PROJECT_DOCUMENTATION.md` §4.1 coi là được phép |
| Q3 | Kết quả gợi ý có được trả **tên tiêu chí khớp / còn thiếu** (`matched`, `gaps`) cho seeker không? D1 chỉ nói band. | 설계서 상세 §1.3 (tr. 36–37) và `PROJECT_DOCUMENTATION.md` §6.1 có `matched`/`gaps` |
| Q4 | Ngoài danh sách gợi ý, seeker có xem được band **cho một job bất kỳ** (trang chi tiết, “AI 적합도 분석” theo yêu cầu) và cho job **đã apply** không? Nếu có thì sẽ sinh evaluation cho job chưa apply. Có tính vào giới hạn chi phí không? | 설계서 기본 §3.2(4) (tr. 21–23): seeker tự yêu cầu phân tích độ phù hợp cho một job |
| Q6 | 사업자등록번호: lưu ở đâu (cột mới ở `companies`? cần migration), bắt buộc lúc đăng ký company không, có unique không, “định dạng” chỉ là 10 chữ số `XXX-XX-XXXXX` hay kiểm cả checksum, có hiện công khai không? Thêm field bắt buộc sẽ đổi contract `POST /api/auth/register` (frontend `Register`, `scripts/seed.py`). | Không có trong 설계서 (tr. 7–8 chỉ có form seeker), DB, code (`schemas/auth.py` `RegisterIn`) |
| Q7 | Project công ty dùng vào việc gì: chỉ CRUD + hiển thị, làm ngữ cảnh cho gợi ý tiêu chí (`/analyze`), hay đưa vào prompt chấm điểm (làm đổi điểm)? Job ↔ project là 1–1 hay 1–n? Có trang frontend không (hiện chưa có)? | `PROJECT_DOCUMENTATION.md` Q3; 설계서 상세 §3.1 (tr. 44) chỉ có CRUD; 과제계획서 hứa “반영” vào tiêu chí |
| Q8 | Talent recommendation có **bắt buộc cho demo** không? Doc ghi không được bật trước khi sửa xong issue 3, 6, 26. Sau khi seeker accept: công ty chỉ nhận liên hệ (`display_name`, email) hay thấy cả profile không ẩn danh (tên trường, tổ chức, evidence)? Pref dùng thế nào trong talent (“보조 반영”)? | 설계서 기본 §8 (tr. 32), 상세 §1.3 (tr. 37); `PROJECT_DOCUMENTATION.md` §6.1, issue 3/6/23/24/26, Q10 |
| Q9 | Các luật `[Planned]` trong `PROJECT_DOCUMENTATION.md` §6.1, §9 — chuyển vào §2 không? Gồm: luật queue/retry (`ensure()` + `IntegrityError`, chỉ queue khi mới / `failed` / `pending` ≥ 10 phút, fencing theo `queued_at`); giới hạn 10 evaluation mới/lần, 30/seeker/ngày (KST), tối đa 3 lần thử; trả về `done` + `pending_count`; cách khớp Pref (location bằng nhau hoặc chứa nhau, employment type bằng nhau, keyword là substring của title/JD); preference trống = khớp + nhắc nhập; tie-break Final ↓, Fit ↓, `published_at` mới nhất; bump `CONSENT_VERSION` + đồng ý lại; `GET /api/jobs/{id}/criteria` public (seeker view). | `PROJECT_DOCUMENTATION.md` §6.1, §9 |
| Q19 | `GET /api/jobs/{job_id}/criteria` (seeker view: tên + nhóm + mức quan trọng, không weight) có mở cho guest như D4 không? `PROJECT_DOCUMENTATION.md` §4.2 ghi `[Planned]` mở cùng trang chi tiết job; D4 chỉ nêu 2 endpoint. Nếu không mở, trang chi tiết job của guest phải ẩn khối tiêu chí. Liên quan Q2. | D4; `PROJECT_DOCUMENTATION.md` §4.2; `criteria.py` |

### 3.2 Phạm vi chưa chốt

| # | Câu hỏi | Nguồn |
|---|---|---|
| Q10 | Tính năng nào trong brief là **bắt buộc cho demo**: AI tự kiểm tra CV (điểm mạnh / cải thiện), skill roadmap, câu hỏi phỏng vấn theo JD, AI hỗ trợ **viết** JD (hiện chỉ có phân tích JD đã viết), filter nhanh ứng viên? | Brief 2026-10-13. 설계서: có “강점 및 개선 제안” (tr. 11), “부족한 역량 … 개선 방향” (tr. 2); **không** có câu hỏi phỏng vấn, viết JD, filter ứng viên. Code: chưa có cái nào (`PROGRESS_BACKEND_AI.md` §3) |
| Q11 | Các mục có trong 설계서 / Figma nhưng không có trong brief: lưu job (공고 저장); tìm job theo tên công ty / tech stack + filter location / employment type / kinh nghiệm; field “경력 수준”, “보유 기술 스택” trong profile seeker; số liệu dashboard công ty (ứng viên mới, chờ xét, lịch phỏng vấn); trang 기업 탐색. Trong hay ngoài phạm vi? | 설계서 tr. 9, 10, 12, 15, 18; `PROJECT_DOCUMENTATION.md` Q8. Code: chỉ tìm theo title (`job_service.list_public`) |
| Q12 | Demo chạy `AI_MODE` nào (rules hay llm)? Embedding nào: `hashing-ngram-v1` (mặc định Compose) hay `multilingual-e5-base` (~1 GB)? | D5, D7; `docker-compose.yml:16` |
| Q13 | Xoá CV / tài khoản: trong hay ngoài phạm vi demo? | `PROJECT_DOCUMENTATION.md` Q5, issue 11 |
| Q14 | `law_ref` trong blocklist cần xác nhận lại tính pháp lý trước demo: xác nhận dựa trên nguồn nào, và có đưa vào §1.1 thành hạng mục bắt buộc không? | `PROJECT_DOCUMENTATION.md` Q7, issue 21; `data/blocklist.yaml` |

### 3.3 Tài liệu và quy tắc cần đồng bộ

| # | Câu hỏi | Nguồn |
|---|---|---|
| Q16 | Phiên bản 설계서: PDF trong repo ghi **버전 1.0, 2026-10-11**, còn `PROJECT_DOCUMENTATION.md` dẫn **v1.1, 2026-10-12**. File nào là bản hiện hành? | `CareerSync_설계서.pdf` tr. 1; `PROJECT_DOCUMENTATION.md` dòng 7 |
| Q17 | Có cập nhật các tài liệu sau theo file này không, và khi nào: (a) 설계서 (tr. 5, 12–13, 21, 26–27 — key bật LLM, điểm phù hợp cho seeker); (b) `PROJECT_DOCUMENTATION.md` §1 (chưa có 사업자등록번호; project công ty đang là `[DB only]`); (c) `PROGRESS_BACKEND_AI.md` (project công ty xếp P1 và phụ thuộc Q3)? | Các file nêu trên |
