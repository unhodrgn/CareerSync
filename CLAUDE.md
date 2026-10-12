# CLAUDE.md — rules for AI coding assistants (CareerSync)

Long là developer duy nhất. Chỉ làm đúng task Long yêu cầu, trong đúng phạm vi đó. Không tự đề xuất phân công, không nhắc review/phụ thuộc vào người khác. Chưa chắc thì hỏi Long.

Khi thấy mâu thuẫn, ghi vào mục câu hỏi mở của docs/DECISIONS.md thay vì tự đoán.

Quyết định và phạm vi: docs/DECISIONS.md (nguồn chuẩn). Tài liệu kỹ thuật (API, schema, cách chạy): PROJECT_DOCUMENTATION.md.
Đọc phần liên quan trong PROJECT_DOCUMENTATION.md trước khi lập plan. Thứ tự ưu tiên: DECISIONS.md > PROJECT_DOCUMENTATION.md > code. Nếu code lệch doc thì sửa CODE theo doc, giữ nguyên doc. Trước khi sửa phải liệt kê chỗ lệch cho Long; nếu nghi doc sai hoặc lỗi thời thì hỏi Long, không tự sửa doc.

## How to work (every task)

1. **Plan first, then wait.** Before editing any file, reply with: files you will change, the main logic, anything you will not do, and open decisions. Wait for the user's OK. For a one-line fix a short plan is enough, but still wait.
2. **Stay in scope.** Change only what the task asks. No drive-by refactors, renames, formatting passes or new dependencies unless asked.
3. **Find callers first.** Before changing a function, schema or endpoint, search its callers in `backend/`, `ai/` and `frontend/src/api/client.ts`.
4. **No git.** Do not run `git commit`, `push`, `merge`, `rebase`, `checkout`/`switch`, `reset` or `stash`. Read-only git (`status`, `diff`, `log`, `branch`) is fine. The user commits. If the branch looks wrong for the task (e.g. missing migrations), stop and say so.
5. **Test.** Run `pytest` from the repo root after every change; it must pass. For frontend changes also run `npm run build` in `frontend/`. Report results, including anything you could not run.
6. **Keep the docs current.** Quyết định ghi vào `docs/DECISIONS.md`; `PROJECT_DOCUMENTATION.md` chỉ ghi nội dung kỹ thuật. If a task adds or changes a table, endpoint, page, env variable or constant, update the matching section of `PROJECT_DOCUMENTATION.md` in the same change (see its "Keeping this document current"). Do not change the header commit line.
7. **Decisions are not yours.** "Đã chốt" = có trong `docs/DECISIONS.md`. Nhãn **[Recommended]**/`TBD` trong `PROJECT_DOCUMENTATION.md` chỉ là gợi ý. Do not implement anything else as if decided; ask, or implement only what the user explicitly confirms in this task.
8. **Language.** Code, comments, commit messages: English. User-facing text (errors, notices, AI comments): Korean.

## Permissions

- Hỏi Long trước khi sửa `backend/app/models/`, `backend/app/db/`, `backend/migrations/` (schema thay đổi luôn qua migration mới).

**Never, even if asked casually** (stop and confirm explicitly):
- edit an already-applied migration — always add a new one (next number, `down_revision` = current head);
- change auth/security (`core/security.py`, `core/deps.py`), an existing API contract, `cv_profile.v1`, `to_profile_data`, the Fit formula or `criteria_service.load_for_scoring` — these change stored scores or what API clients receive (doc issue 20);
- read, create or commit `.env`, API keys or real CVs (use synthetic data only);
- make real LLM calls in tests or scripts.

## AI rules — and whether the code already guarantees them

"Guaranteed" = the structure of the code enforces it today. "By convention" = nothing stops you; you must keep it.

| # | Rule | Today |
|---|---|---|
| 1 | Every feature works in `AI_MODE=rules` (rules / retrieval fallback). | By convention + tests run in `rules` mode without a key (`FakeLLM`, hashing embedder). Add a rules path for anything new. |
| 2 | The LLM is called only through `ai/llm/client.py` (`get_llm_client()` / `ai_runtime.llm()`). | By convention — `anthropic` is imported only in `client.py` today. Do not import it anywhere else. |
| 3 | The LLM sees only PII-masked text (`cv_documents.masked_text`), never the PDF, `display_name`, email or raw text. | By design in `cv_service.upload` and `evaluation_service.evaluate`; tested by `test_no_personal_data_reaches_the_llm` (`backend/tests/test_applications_api.py`). Keep it. |
| 4 | LLM quotes are verified against the masked CV (`ai/guardrails/evidence.py`); failure → one retry → retrieval. | Guaranteed for `project`/`other` scoring. New LLM features must verify quotes too. |
| 5 | The AI never accepts or rejects anyone; `applications.status` changes only by a recruiter action. | Guaranteed — only `application_service.set_status` writes it. Never let AI code call it. |
| 6 | Responses that carry AI results include `AI_NOTICE`. | By design in today's schemas (applicant, evaluation, `CvOut`, `JdAnalysisOut` have a `notice` field). New AI responses must include it. |
| 7 | Scoring reads criteria only through `criteria_service.load_for_scoring()`. | By convention. |
| 8 | `ai/` never imports `app.*`; services reach AI only through `services/ai_runtime.py`. | By convention — currently true. Keep `ai/` DB-free, pass plain objects (`Candidate`, `Criterion`, `JobContext`). |
| 9 | Weights are never stored in `criterion_scores` and never shown to seekers (seekers see importance / match bands only). | By design; keep it in any new seeker-facing response. |
| 10 | Criteria pass the legal guardrail (`data/blocklist.yaml`) on save. | Guaranteed on save; **not** for JD-suggested criteria (doc issue 7). |
| 11 | Prompts live in `ai/prompts/vN/`; changing a prompt's meaning bumps `PROMPT_VERSION`. Evaluations record model, embedding, prompt and skills versions. | By convention. |
| 12 | Pretrained models only; nothing is trained. | By convention. |
| 13 | Evaluations are obtained through `evaluation_service.ensure()` (get-or-create on job × CV version). | Partly — apply uses it but re-queues non-`done` evaluations (doc issue 25). Follow the rule in doc §6.1 when you touch queuing. |

## Commands

```bash
pytest                                   # from the repo root; no DB, network or key needed
pytest --collect-only -q | tail -1       # count tests
cd backend && alembic upgrade head       # migrations (run alembic from backend/)
cd backend && uvicorn app.main:app --reload   # API on :8000, Swagger at /docs
cd frontend && npm run dev               # UI on :3000 (proxy /api → :8000)
cd frontend && npm run build             # type-check + build
```

## Current focus (update when it changes)

- `evaluations.queued_at` and `evaluations.attempts` exist (migration `0008`), but **no code sets them yet**.
- Next work: the queue/retry rules (doc issues 2, 25 and §6.1), then the preferences API, then job recommendation. Talent recommendation stays off until doc issues 3, 6 and 26 are resolved.
