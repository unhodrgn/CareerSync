# 🎯 CareerSync

**Criteria-Based Hiring & Job Matching Platform**

A multi-company recruiting platform where each company's own evaluation criteria are used both to score applicants and to recommend jobs to people who haven't applied yet.

Soongsil University RISE Capstone project. This is a working prototype under active development; the [Status](#-status) section says what runs today and what is still planned.

Decisions and scope: [`docs/DECISIONS.md`](docs/DECISIONS.md) (source of truth). Technical reference: [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md).

[Status](#-status) · [Run with Docker](docs/how-to/run-with-docker.md) · [Run It Locally](docs/how-to/run-locally.md) · [Troubleshooting](docs/how-to/troubleshooting.md) · [How It Works](docs/explanation/how-it-works.md) · [Privacy & Legal](docs/explanation/privacy-and-legal.md) · [API](#-api-overview) · [Project Structure](#-project-structure)

---

## 📌 Overview

CareerSync connects a company's real hiring criteria with a job seeker's skills and preferences, and returns an explainable match result to both sides.

- **Companies** struggle most with finding candidates (44.5%) and reviewing applications (41.0%).
- **Job seekers** don't know what a company actually values, or how well their CV fits before applying.

The core idea: **one set of company-defined criteria powers two things**: scoring submitted applicants and recommending jobs to non-applicants, on a single shared platform.

> AI never accepts or rejects a candidate; application status changes only by recruiter action.

## 🚦 Status

| Feature | Status | What exists today |
| --- | --- | --- |
| 🔐 Authentication | ✅ Done | Register as seeker or company with privacy and AI consent, JWT login (2 h access token, Argon2id passwords), re-consent screen, seeker can withdraw AI consent |
| 🏢 Company profile | ✅ Done | Name, intro, 인재상 (talent profile), running projects (shown on the public company page and usable as context for AI JD drafts) |
| 📝 Job postings | ✅ Done | Draft → published → closed; after publish only deadline, location and salary note can change. AI drafts a JD for a draft job and suggests a criteria draft from the JD |
| ⚖️ Criteria & weights | ✅ Done | Per-job criteria (max 10, integer weights summing to 100), live guardrail that blocks discriminatory criteria with the law that forbids them |
| 📄 CV analysis | ✅ Done | Upload a text PDF (≤ 5 pages, ≤ 5 MB), PII is masked, skills/education/experience/projects/certificates are extracted, the seeker edits and confirms (each save is a new version); AI self-check of the CV (strengths, improvements) |
| 📊 Applicant evaluation | ✅ Done | Apply → background scoring → recruiter sees applicants ranked by Fit with per-criterion score, evidence and comment, with quick filters. Weight edits re-rank without new AI calls |
| 🧑‍💼 Recruiter workflow | ✅ Done | Status changes (검토 전, 서류 검토, 면접 예정, 보류, 합격, 불합격) only happen when the recruiter clicks |
| 🎯 Job recommendation | ✅ Done | 추천 공고: jobs matching the seeker's preferences and the job's criteria, shown with a match band (매우 적합 / 적합 / 참고), no scores |
| 🧭 Job preparation | ✅ Done | 취업 준비 for a job: skills the job asks for that the CV lacks with a learning plan, and interview practice questions |
| 🔎 Talent recommendation (인재 추천) | ✅ Done | Companies see anonymous opted-in seekers per published job and send offers; contact details only after the seeker accepts |
| 🐳 `docker compose up` | ✅ Done | Starts DB, migrations + demo seed, backend and frontend. See [Compose guide](docs/how-to/run-with-docker.md) |

## 🧠 How Scoring Works

Rule-based scoring of each company-defined criterion on the masked CV text, an optional LLM rubric for judgment criteria, and a Fit score that is the weighted average of the criterion scores. The flows, the scoring table, the scoring rules and the architecture: [docs/explanation/how-it-works.md](docs/explanation/how-it-works.md). What is masked before the LLM, consent and the legal guardrail: [docs/explanation/privacy-and-legal.md](docs/explanation/privacy-and-legal.md).

## 🧰 Tech Stack

| Layer | Technologies |
| --- | --- |
| Frontend | React 19 · TypeScript · Vite · React Router (Korean UI, desktop-first) |
| Backend | Python 3.11+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 |
| AI | Anthropic API behind `LLMClient` (optional) · sentence-transformers (multilingual-e5-base) · PyMuPDF |
| Database | PostgreSQL 16 (tests use in-memory SQLite) |
| Auth | JWT (PyJWT) · Argon2id |
| Infrastructure | Docker (for PostgreSQL) · Git / GitHub |

The architecture diagram is in [How it works](docs/explanation/how-it-works.md#architecture).

## 🐳 Run with Docker Compose

With Docker Desktop running, create `.env` from `.env.example` if needed, then run `docker compose up --build -d`. The demo embedding `intfloat/multilingual-e5-base` is the default and downloads about 1 GB on the first run (kept in the `model-cache` volume); set `EMBEDDING_MODEL=hashing-ngram-v1` only for a quick try. Open http://localhost:3000. See [the full guide](docs/how-to/run-with-docker.md) for ports, logs, stopping the app and which `.env` variables Compose passes on. This uses a separate database from the manual setup below. Demo accounts (password `demo1234`): `hr@nextcode.test`, `hr@cloudlab.test`, `seeker@demo.test`, `seeker2@demo.test`.

## ⚙️ Run It Locally

Manual setup (PostgreSQL in Docker, the backend and frontend on your machine), the `.env` variables, the demo accounts, tests and a command reference: [docs/how-to/run-locally.md](docs/how-to/run-locally.md). If something fails, see [docs/how-to/troubleshooting.md](docs/how-to/troubleshooting.md).

## 🔌 API Overview

Base URL `http://localhost:8000`. Request/response schemas as currently implemented are at **http://localhost:8000/docs**; the API in `PROJECT_DOCUMENTATION.md` §4 is the standard. All endpoints except register, login, `/health`, `GET /api/jobs`, `GET /api/jobs/{job_id}` and `GET /api/jobs/{job_id}/criteria` need `Authorization: Bearer <token>`.

### Auth & users

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/register` | Register as seeker or company (consents required) |
| POST | `/api/auth/login` | Log in, returns a bearer token |
| GET | `/api/users/me` | Current user (`consent_required` → show the consent screen) |
| POST | `/api/users/me/consent` | Consent again to the current consent text |
| DELETE | `/api/users/me/consent/ai` | Seeker withdraws AI-analysis consent |

### Companies

| Method | Endpoint | Description |
| --- | --- | --- |
| GET / PUT | `/api/companies/me` | Own company profile |
| GET | `/api/companies/{company_id}` | Public company profile with its running projects |
| GET / POST | `/api/companies/me/projects` | Company: list / add running projects |
| PUT / DELETE | `/api/companies/me/projects/{project_id}` | Company: replace / delete a running project |

### Jobs

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/jobs` | Create a draft job |
| GET | `/api/jobs` | Published jobs, newest first |
| GET | `/api/jobs/mine` | Own company's jobs in every status |
| GET / PATCH / DELETE | `/api/jobs/{job_id}` | Detail, edit (limited after publish), delete a draft |
| POST | `/api/jobs/{job_id}/publish` | Publish (needs a JD and a valid criteria set) |
| POST | `/api/jobs/{job_id}/close` | Close (final) |
| POST | `/api/jobs/{job_id}/analyze` | AI reads the JD and suggests criteria (not saved; blocked suggestions left out) |
| POST | `/api/jobs/{job_id}/jd-draft` | AI drafts a JD for a draft job (not saved) |

### Criteria

| Method | Endpoint | Description |
| --- | --- | --- |
| GET / PUT | `/api/jobs/{job_id}/criteria` | Read or replace the criteria set |
| POST | `/api/jobs/{job_id}/criteria/copy-from/{source_job_id}` | Copy criteria from another own job (API only; the UI does not offer it) |
| POST | `/api/criteria/check` | Guardrail check for one criterion (used live in the editor) |

### CV

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/cv` | Upload a PDF and analyze it |
| GET | `/api/cv/me` | Latest version of the seeker's CV |
| GET / PUT | `/api/cv/{profile_id}` | Read a version, or save edits as a new version (`confirm=true` to make it usable) |
| POST | `/api/cv/{profile_id}/review` | Seeker: AI self-check of a CV version (strengths, improvements) |

### Applications & evaluation

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/jobs/{job_id}/applications` | Apply with the confirmed CV; scoring starts in the background |
| GET | `/api/applications/mine` | Seeker's own applications |
| GET | `/api/jobs/{job_id}/applications` | Applicants ranked by Fit (recruiter only); filters `status`, `min_fit`, `evaluation_status` |
| GET | `/api/applications/{application_id}/evaluation` | Per-criterion score, evidence, comment |
| POST | `/api/applications/{application_id}/evaluation/retry` | Retry a failed evaluation |
| PUT | `/api/applications/{application_id}/status` | Recruiter changes the status |
| GET / PUT | `/api/preferences/me` | Seeker's job preferences and talent-pool opt-in |
| GET | `/api/recommendations/jobs` | Recommended jobs with a match band (매우 적합 / 적합 / 참고) |
| GET | `/api/jobs/{job_id}/talent` | Company: anonymous opted-in seekers for a job, ranked by Fit |
| POST | `/api/talent-offers` | Company sends an offer to an anonymous seeker |
| GET | `/api/talent-offers/sent` | Company's sent offers (contact only after accepted) |
| POST | `/api/talent-offers/{offer_id}/cancel` | Company cancels a pending offer |
| GET | `/api/talent-offers/mine` | Seeker's received offers |
| POST | `/api/talent-offers/{offer_id}/accept` · `/reject` | Seeker answers an offer |
| POST | `/api/jobs/{job_id}/roadmap` | Seeker: skills the job asks for that the CV lacks, with a learning plan |
| POST | `/api/jobs/{job_id}/interview-questions` | Seeker: interview practice questions for a job |

## 📁 Project Structure

```
CareerSync/
├── .env.example                 # Copy to .env (repo root)
├── conftest.py                  # Test-wide settings: no network, no .env, hashing embedder
├── pyproject.toml               # pytest config (run pytest from the repo root)
├── docker-compose.yml           # DB, init, backend and frontend
├── docs/
│   ├── DECISIONS.md             # Decisions and scope (source of truth)
│   ├── how-to/                  # run-with-docker.md, run-locally.md, troubleshooting.md
│   ├── explanation/             # how-it-works.md, privacy-and-legal.md
│   ├── archive/                 # PROGRESS_BACKEND_AI.md: old progress snapshot (2026-10-08..14), not maintained
│   └── reference/               # Project proposal, design document and market research (PDF)
├── backend/
│   ├── alembic.ini              # Run alembic from backend/
│   ├── migrations/versions/     # 0001 … 0011
│   ├── requirements.txt         # Backend + AI + test dependencies
│   ├── app/
│   │   ├── main.py              # FastAPI app (run uvicorn from backend/)
│   │   ├── core/                # Settings (.env loading), JWT, dependencies, errors
│   │   ├── api/v1/              # auth, users, companies, jobs, criteria, cv, applications, preferences, recommendations, talent, career
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic; calls ai/ through ai_runtime
│   │   └── db/                  # Engine and session
│   └── tests/                   # API tests (SQLite in memory)
├── ai/
│   ├── llm/client.py            # LLMClient (Anthropic); None unless AI_MODE=llm
│   ├── prompts/v1/              # cv_structure, jd_analyze, jd_draft, rubric_score, roadmap, interview_questions, cv_review
│   ├── jd/                      # JD drafts for companies
│   ├── parsing/                 # PDF → text, PII masking, CV/JD structuring
│   ├── embedding/               # e5 / hashing embedders, skill dictionary
│   ├── scoring/                 # Per-criterion scorers, Fit and Pref (shared by evaluation and recommendations)
│   ├── guardrails/              # Criteria blocklist, evidence check
│   ├── career/                  # Skill gaps, roadmap, interview questions, CV self-check
│   └── tests/
├── data/
│   ├── demo/demo_cv.pdf         # Synthetic demo CV (built by scripts/make_demo_cv.py)
│   ├── blocklist.yaml           # Disallowed criteria with their legal basis
│   ├── interview_blocklist.yaml # Disallowed interview question topics
│   ├── learning_resources.yaml  # Verified learning resources for the roadmap
│   └── skills.yaml              # Skill dictionary, aliases and related-skill groups
├── scripts/
│   ├── seed.py                  # Demo companies, jobs, criteria and accounts (one seeker with the demo CV)
│   ├── make_demo_cv.py          # Builds data/demo/demo_cv.pdf and checks it reads back
│   ├── docker_init.py           # Compose init: migrations + seed
│   └── smoke_test.py            # End-to-end check of a running app over HTTP
└── frontend/                    # React + TypeScript + Vite
    ├── vite.config.ts           # Port 3000, /api proxy to :8000
    └── src/
        ├── api/                 # Fetch client and error texts
        ├── auth/                # Login state and role guard
        ├── components/          # Layouts and shared UI (common, seeker, company)
        ├── i18n/                # UI text (ko)
        ├── pages/               # public/*, seeker/*, company/*
        ├── routes/              # Router and paths
        ├── styles/              # Design tokens and global CSS
        └── types/               # API types
```

## 🔄 Core User Flows and Scoring Rules

The seeker and company flows and the scoring rules table: [docs/explanation/how-it-works.md](docs/explanation/how-it-works.md#user-flows).

## 🎯 MVP Scope (plan)

**Assumptions:** IT/Software jobs only · Korean UI · 1 recruiter account = 1 company · text-based PDF CVs (≤ 5 MB, ≤ 5 pages) · synthetic demo data.

**Out of scope:** OCR, HWP/DOCX, scraping job sites, multiple recruiters per company, email notifications, interview scheduling, preference model trained from logs, admin screen, payments, mobile app.

**Targets** (demo scale, ≤ 100 seekers, ≤ 50 jobs): CRUD p95 < 500 ms · CV analysis ≤ 60 s · evaluation after applying ≤ 30 s · every criterion score has evidence · no email or phone, and on a best-effort basis no seeker name or labeled reference name, sent to the LLM.

## 🔒 Legal & Ethics

The laws the product follows, the discriminatory-criteria guardrail, consent and masking: [docs/explanation/privacy-and-legal.md](docs/explanation/privacy-and-legal.md).
