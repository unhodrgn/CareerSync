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

Every endpoint with who may call it and its errors: [`PROJECT_DOCUMENTATION.md` §4.1](PROJECT_DOCUMENTATION.md#41-existing-endpoints-current) (the standard, D11); request/response schemas as implemented: Swagger at http://localhost:8000/docs while the backend runs.

## 📁 Project Structure

The folder tree with what each part does: [`PROJECT_DOCUMENTATION.md` §8](PROJECT_DOCUMENTATION.md#8-files-and-folders).

## 🔄 Core User Flows and Scoring Rules

The seeker and company flows and the scoring rules table: [docs/explanation/how-it-works.md](docs/explanation/how-it-works.md#user-flows).

## 🎯 MVP Scope (plan)

**Assumptions:** IT/Software jobs only · Korean UI · 1 recruiter account = 1 company · text-based PDF CVs (≤ 5 MB, ≤ 5 pages) · synthetic demo data.

**Out of scope:** OCR, HWP/DOCX, scraping job sites, multiple recruiters per company, email notifications, interview scheduling, preference model trained from logs, admin screen, payments, mobile app.

**Targets** (demo scale, ≤ 100 seekers, ≤ 50 jobs): CRUD p95 < 500 ms · CV analysis ≤ 60 s · evaluation after applying ≤ 30 s · every criterion score has evidence · no email or phone, and on a best-effort basis no seeker name or labeled reference name, sent to the LLM.

## 🔒 Legal & Ethics

The laws the product follows, the discriminatory-criteria guardrail, consent and masking: [docs/explanation/privacy-and-legal.md](docs/explanation/privacy-and-legal.md).
