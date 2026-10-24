# CLAUDE.md — rules for AI coding assistants (CareerSync)

Long is the only developer. Do exactly the task Long asks for, within exactly that scope. Do not propose a division of work on your own, and do not mention reviews by or dependencies on other people. If unsure, ask Long.

When you find a contradiction, record it in the open questions section of docs/DECISIONS.md instead of guessing.

Decisions and scope: docs/DECISIONS.md (source of truth). Technical documentation (API, schema, how to run): PROJECT_DOCUMENTATION.md.
Read the relevant part of PROJECT_DOCUMENTATION.md before making a plan. Priority order: DECISIONS.md > PROJECT_DOCUMENTATION.md > code. If the code differs from the doc, fix the CODE to match the doc and leave the doc unchanged. Before fixing, list the differences for Long; if you suspect the doc is wrong or outdated, ask Long and do not fix the doc yourself.

## How to work (every task)

1. **Plan first, then wait.** Before editing any file, reply with: files you will change, the main logic, anything you will not do, and open decisions. Wait for the user's OK. For a one-line fix a short plan is enough, but still wait.
2. **Stay in scope.** Change only what the task asks. No drive-by refactors, renames, formatting passes or new dependencies unless asked.
3. **Find callers first.** Before changing a function, schema or endpoint, search its callers in `backend/`, `ai/` and `frontend/src/api/client.ts`.
4. **No git.** Do not run `git commit`, `push`, `merge`, `rebase`, `checkout`/`switch`, `reset` or `stash`. Read-only git (`status`, `diff`, `log`, `branch`) is fine. The user commits. If the branch looks wrong for the task (e.g. missing migrations), stop and say so.
5. **Test.** Run `pytest` from the repo root after every change; it must pass. For frontend changes also run `npm run build` in `frontend/`. Report results, including anything you could not run.
6. **Keep the docs current.** Decisions go into `docs/DECISIONS.md`; `PROJECT_DOCUMENTATION.md` records only technical content. If a task adds or changes a table, endpoint, page, env variable or constant, update the matching section of `PROJECT_DOCUMENTATION.md` in the same change (see its "Keeping this document current"). Do not change the header commit line.
7. **Decisions are not yours.** "Decided" = present in `docs/DECISIONS.md`. The **[Recommended]**/`TBD` labels in `PROJECT_DOCUMENTATION.md` are only suggestions. Do not implement anything else as if decided; ask, or implement only what the user explicitly confirms in this task.
8. **Language.** Code, comments, commit messages: English. User-facing text (errors, notices, AI comments): Korean. Markdown docs: English; Korean product/UI terms and law names stay Korean with an English gloss at first use (D40; terms in `PROJECT_DOCUMENTATION.md` §12).

## Permissions

- Ask Long before changing `backend/app/models/`, `backend/app/db/`, `backend/migrations/` (schema changes always go through a new migration).

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
| 6 | Responses that carry AI results include `AI_NOTICE`. | By design in today's schemas (applicant, evaluation, `CvOut`, `JdAnalysisOut`, recommendation, talent and career responses have a `notice` field). New AI responses must include it. |
| 7 | Scoring reads criteria only through `criteria_service.load_for_scoring()`. | By convention. |
| 8 | `ai/` never imports `app.*`; services reach AI only through `services/ai_runtime.py`. | By convention — currently true. Keep `ai/` DB-free, pass plain objects (`Candidate`, `Criterion`, `JobContext`). |
| 9 | Weights are never stored in `criterion_scores` and never shown to seekers (seekers see importance / match bands only). | By design; keep it in any new seeker-facing response. |
| 10 | Criteria pass the legal guardrail (`data/blocklist.yaml`) on save. | Guaranteed on save; **not** for JD-suggested criteria (doc issue 7). |
| 11 | Prompts live in `ai/prompts/vN/`; changing a prompt's meaning bumps `PROMPT_VERSION`. Evaluations record model, embedding, prompt and skills versions. | By convention. |
| 12 | Pretrained models only; nothing is trained. | By convention. |
| 13 | Evaluations are obtained through `evaluation_service.ensure()` (get-or-create on job × CV version). | By convention — apply and retry use `ensure()` then `evaluation_service.claim()`, which queues only new, `failed` or stale `pending` evaluations; runs write results only with their `queued_at` token. New queue paths must do the same. |
| 14 | Rule scorers give points only for what is in the masked CV text; the seeker-edited profile only says what to look for. Numbers shown to companies (experience) use the same check. | By design in `ai/scoring/scorers.py` (`verified_experience`, `line_in_text`); tested in `ai/tests/test_scoring.py`. Keep it for new rule scorers. |

## Commands

```bash
pytest                                   # from the repo root; no DB, network or key needed
pytest --collect-only -q | tail -1       # count tests
pytest backend/tests/docs -q             # doc-drift guards only (links, IDs, API, env, constants, numbers, tree, language)
cd backend && alembic upgrade head       # migrations (run alembic from backend/)
cd backend && uvicorn app.main:app --reload   # API on :8000, Swagger at /docs
cd frontend && npm run dev               # UI on :3000 (proxy /api → :8000)
cd frontend && npm run build             # type-check + build
```

## Current focus (update when it changes)

- Queue/retry rules are in place (`evaluation_service.claim()`, fencing on `queued_at`).
- Preferences API and job recommendation are in place (`recommendation_service`, D15, D16). Re-consent and AI-consent withdrawal are in place (D17). The frontend (redesign, PR #10) is wired to the real API for every seeker and company page, including recommendation, preferences, the consent screen, talent and offers (PROJECT_DOCUMENTATION.md §5). Talent list `GET /api/jobs/{job_id}/talent` and offers `/api/talent-offers*` are in place (D18–D20, migration `0009`). Skill roadmap and interview questions (`POST /api/jobs/{job_id}/roadmap`, `/interview-questions`) are in place (D21, migration `0010`). Applicant quick filters and company projects CRUD are in place (D22, D23). AI JD drafts `POST /api/jobs/{job_id}/jd-draft` and the `/analyze` guardrail (issue 7) are in place (D24). CV self-check `POST /api/cv/{profile_id}/review` is in place (D25, migration `0011`). Demo embedding is e5, tests use hashing (D26); related skills come from `related` groups in `data/skills.yaml`, not embeddings (D27); rules-mode project scoring, neutral 50 only for vague `other` criteria, unlisted skills looked up by name (D28).
