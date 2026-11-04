# CareerSync

**Criteria-based hiring and job matching.** Each company's own evaluation criteria score its applicants and recommend its jobs to seekers who have not applied yet.

[![CI](https://github.com/unhodrgn/CareerSync/actions/workflows/ci.yml/badge.svg)](https://github.com/unhodrgn/CareerSync/actions/workflows/ci.yml)

A working prototype for a local demo, built as a Soongsil University Capstone project. [Status](#status) lists what works today and what is partial; [Known limitations](#known-limitations) lists what to keep in mind before showing it to anyone.

<!-- Screenshot: seeker view — 추천 공고 (Recommended jobs) with match bands. Add docs/images/seeker-recommended.png, then replace this comment with the image. -->
<!-- Screenshot: company view — 지원자 순위 (Applicant ranking) with per-criterion scores and evidence. Add docs/images/company-applicants.png. -->
<!-- GIF: 30-second demo — upload a CV, apply, see the ranked applicant. Add docs/images/demo.gif. -->

## 한국어 요약

CareerSync는 기업이 직접 정한 평가 기준 하나로 지원자 평가와 공고 추천을 함께 처리하는 채용 매칭 플랫폼입니다.

- **기업**: 공고마다 평가 기준과 가중치를 정하면, 지원자를 적합도 순으로 보고 기준별 점수와 근거(이력서에서 인용한 문장)를 확인할 수 있습니다. 차별적인 기준은 입력 단계에서 차단됩니다.
- **구직자**: 이력서(PDF)를 올리고 희망 조건을 정하면 추천 공고를 적합도 구간(매우 적합 / 적합 / 참고)과 함께 받고, 취업 준비 화면에서 부족한 역량의 학습 계획과 면접 연습 질문을 볼 수 있습니다. 구직자에게는 점수와 가중치가 공개되지 않습니다.
- **인재 추천**: 인재풀 공개에 동의한 구직자만 익명으로 기업에 보이며, 구직자가 제안을 수락한 뒤에만 연락처가 공개됩니다.
- **AI는 합격·불합격을 결정하지 않습니다.** 지원 상태는 채용 담당자가 직접 변경할 때만 바뀝니다.
- 이메일, 전화번호, 본인 이름(가능한 범위에서) 등 개인정보는 LLM에 보내기 전에 가립니다. 기본 채점은 규칙 기반이며, LLM은 설정으로 켰을 때만 사용합니다.

숭실대학교 캡스톤 프로젝트이며, 로컬에서 실행하는 데모용 프로토타입입니다.

## What it does

One set of company-defined criteria powers two things on one platform: **scoring the applicants** of a job and **recommending that job** to seekers who have not applied.

- **Companies** define criteria and weights per job and see applicants ranked by Fit, with a score, evidence quoted from the CV and a comment for every criterion.
- **Seekers** upload a CV and set preferences, then get recommended jobs with a match band instead of a score, plus help preparing for a job (missing skills, interview questions, a CV self-check).

Why: in a 잡코리아 (JobKorea) survey of 1,286 recruiters (February–March 2026), the most burdensome tasks were finding suitable candidates (44.5%) and reviewing applications (41.0%); seekers, in turn, cannot tell what a company actually values. Source: the market research report and the project proposal in [docs/reference/](docs/reference/).

> The AI never accepts or rejects anyone: an application's status changes only when a recruiter changes it.

## Quick Start

With [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, from the repository root:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
```

Open http://localhost:3000. The first build takes several minutes. The demo embedding model `intfloat/multilingual-e5-base` (about 1 GB) downloads in the background when the backend first starts and is kept in the `model-cache` volume; set `EMBEDDING_MODEL=hashing-ngram-v1` in `.env` only for a quick try. Ports, logs, stopping and which `.env` variables Compose passes on: [Run with Docker Compose](docs/how-to/run-with-docker.md).

Demo accounts (password `demo1234` for all):

| Role | Email | Start with |
| --- | --- | --- |
| Company | `hr@nextcode.test` | One published backend job with criteria and one draft job: edit criteria, try a blocked one, open 지원자 순위 (Applicant ranking) and 인재 추천 (Talent recommendation) |
| Company | `hr@cloudlab.test` | One published data engineer job |
| Seeker | `seeker@demo.test` | No CV yet: upload `data/demo/demo_cv.pdf`, confirm it, set preferences, apply |
| Seeker | `seeker2@demo.test` | Ready-made: demo CV confirmed, preferences set, in the talent pool |

A typical demo:

1. Log in as `seeker@demo.test`, open 내 이력서 (My CV), upload `data/demo/demo_cv.pdf` and confirm the extracted profile.
2. Open 추천 공고 (Recommended jobs). The first visit only starts scoring ("분석 중", analyzing); press 새로고침 (refresh) after a few seconds to see the jobs with their match band. Open the 넥스트코드 backend job and press 지원하기 (Apply).
3. Log in as `hr@nextcode.test`, open the job in 공고 관리 (Job management) and its 지원자 순위 tab: the applicant is ranked by Fit with a score, evidence and comment per criterion.
4. In the job's 공고 수정 (Edit job) tab, move weight from one criterion to another (the total must stay 100) and save: the Fit is recomputed without new AI calls. To see the guardrail, open the draft 프론트엔드 개발자 (React) job instead, add a criterion such as "키 175cm 이상" (height of at least 175 cm) and leave the field: it is blocked with the law that forbids it. A published job's criteria are fixed, so this only works on a draft.
5. Open the backend job's 인재 추천 tab; after 새로고침, `seeker2@demo.test` appears as an anonymous seeker. Send an offer, then log in as that seeker and accept it in 받은 제안 (Received offers).

To run the backend and frontend on your machine instead, see [Run locally](docs/how-to/run-locally.md); if something fails, see [Troubleshooting](docs/how-to/troubleshooting.md).

## Status

**Done** = works end to end in the demo. **Partial** = works, with the gap named in the row.

| Feature | Status | What exists today |
| --- | --- | --- |
| Guest browsing | Done | Published jobs and job detail (criterion names only) without logging in (D4, D35); company pages need a login. |
| Authentication and consent | Partial | Register as seeker or company with privacy and AI consent, JWT login (2 h access token, Argon2id passwords), re-consent screen, seeker can withdraw AI consent. Gap: the consent text is still marked as a draft |
| Company profile | Done | Name, intro, 인재상 (talent profile), running projects (shown on the public company page and usable as context for AI JD drafts) |
| Job postings | Done | Draft → published → closed; after publishing only the deadline, location and salary note can change. AI drafts a JD for a draft job and suggests criteria from the JD |
| Criteria and weights | Done | Per-job criteria (max 10, integer weights summing to 100), live guardrail that blocks discriminatory criteria and names the law that forbids them |
| CV analysis | Done | Upload a text PDF (≤ 5 pages, ≤ 5 MB); PII is masked; skills, education, experience, projects and certificates are extracted; the seeker edits and confirms (each save is a new version); AI self-check of the CV (strengths, improvements) |
| Applicant evaluation | Done | Apply → background scoring → recruiter sees applicants ranked by Fit with per-criterion score, evidence and comment, with quick filters. Weight edits re-rank without new AI calls |
| Recruiter workflow | Done | Status changes (검토 전 submitted, 서류 검토 reviewing, 면접 예정 interview, 보류 on hold, 합격 passed, 불합격 rejected) happen only when the recruiter clicks |
| Preferences and talent-pool opt-in | Done | Seeker sets desired locations, employment types and role keywords (희망 조건, preferences) and can opt in to the talent pool (D15) |
| Job recommendation | Partial | 추천 공고 (Recommended jobs): jobs that match the seeker's preferences and the job's criteria, shown with a match band (매우 적합 / 적합 / 참고: very good / good / reference), no scores. Gap: no prompt yet asking a seeker with empty preferences to fill them in |
| Job preparation | Done | 취업 준비 (Job preparation): skills the job asks for that the CV lacks, with a learning plan, and interview practice questions |
| Talent recommendation | Done | Companies see anonymous opted-in seekers per published job and send offers; contact details only after the seeker accepts |
| `docker compose up` | Done | Starts the database, migrations + demo seed, backend and frontend |

## Known limitations

- **Scoring runs inside the backend process** (`BackgroundTasks`): a restart leaves evaluations `pending` until a recruiter clicks 다시 분석 (Re-analyze) or a recommendation call re-queues them. Counted as mitigated for the demo (D18); a separate worker comes later (issue 6).
- **No rate limit** on the endpoints that can call the LLM (issue 22).
- **Name masking is best effort**: the seeker's own name and its spellings, labeled name lines and the name at the top of the CV are masked; other people's unlabeled names are not (D39, issue 33).
- **Public dev secrets**: the built-in and Compose default secrets are in the repository; change `JWT_SECRET_KEY` and `TALENT_ID_SECRET` before sharing a deployment (issue 34, Q23).
- **Access token in `sessionStorage`**, readable by any script on the page if there is an XSS bug (issue 12).
- **The consent text is a draft** and still says so on the consent screen.
- **Not deployed**: the demo runs locally with Docker Compose only (D7).
- **LLM mode quality is not measured yet**: the AI quality evaluation plan in [PROJECT_DOCUMENTATION.md §6](PROJECT_DOCUMENTATION.md#6-ai--ml) has not been run.

Every known issue with its status: [PROJECT_DOCUMENTATION.md §11](PROJECT_DOCUMENTATION.md#11-known-issues-and-risks).

## How it works

Rule-based scorers grade each company-defined criterion on the PII-masked CV text and quote the line they used as evidence; an optional LLM rubric (`AI_MODE=llm`) handles judgment criteria such as projects, with every quote checked against the CV. Fit is the weighted average of the criterion scores. Job recommendation combines Fit with Pref, how well the job matches the seeker's preferences, and shows seekers only a match band. Details: [How CareerSync works](docs/explanation/how-it-works.md) (flows, architecture, scoring rules) and [Privacy and legal](docs/explanation/privacy-and-legal.md) (masking, consent, the discriminatory-criteria guardrail).

## Tech stack

| Layer | Technologies |
| --- | --- |
| Frontend | React 19 · TypeScript · Vite · React Router (Korean UI, desktop-first) |
| Backend | Python 3.11+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 |
| AI | Anthropic API behind `LLMClient` (optional) · sentence-transformers (multilingual-e5-base) · PyMuPDF |
| Database | PostgreSQL 16 (tests use in-memory SQLite) |
| Auth | JWT (PyJWT) · Argon2id |
| Infrastructure | Docker Compose (full demo: database, backend, frontend) · Docker (PostgreSQL only, for the manual setup) · GitHub Actions (CI) |

## Documentation

Start at the [documentation map](docs/index.md). The main documents:

| Document | What it is for |
| --- | --- |
| [Run with Docker Compose](docs/how-to/run-with-docker.md) | Start the full demo with one command |
| [Run locally](docs/how-to/run-locally.md) | Manual setup, `.env`, demo accounts, tests, command reference |
| [Troubleshooting](docs/how-to/troubleshooting.md) | Fixes for common setup and runtime errors |
| [How CareerSync works](docs/explanation/how-it-works.md) | User flows, architecture, how scoring works |
| [Privacy and legal](docs/explanation/privacy-and-legal.md) | What the LLM sees, consent, the guardrail, the laws |
| [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md) | Technical reference: database, API (§4.1), frontend, AI, configuration, known issues, glossary |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions, scope and open questions (source of truth) |
| [CLAUDE.md](CLAUDE.md) | Rules for AI coding assistants working on this repository |
| [DESIGN.md](DESIGN.md) · [PRODUCT.md](PRODUCT.md) | Design system and product context for the frontend |

API request and response schemas as implemented: Swagger at http://localhost:8000/docs while the backend runs.

## Repository layout

| Folder | Contents |
| --- | --- |
| `backend/` | FastAPI app, models, services, Alembic migrations and API tests (including the doc-drift guards) |
| `ai/` | Parsing, PII masking, embeddings, scoring, guardrails, LLM client and prompts; never imports the backend |
| `frontend/` | React + TypeScript + Vite app (Korean UI) |
| `data/` | Blocklists, skill dictionary, learning resources and the synthetic demo CV |
| `scripts/` | Demo seed, demo CV builder, Compose init and an end-to-end smoke test |
| `docs/` | How-to guides, explanations, decisions, source PDFs and archived snapshots |
| `.github/` | CI workflow |

The full tree, file by file: [PROJECT_DOCUMENTATION.md §8](PROJECT_DOCUMENTATION.md#8-files-and-folders).

## Scope

**Assumptions:** IT/Software jobs only · Korean UI · 1 recruiter account = 1 company · text-based PDF CVs (≤ 5 MB, ≤ 5 pages) · synthetic demo data.

What is required for the demo, what is in product scope and what is out of scope: [docs/DECISIONS.md §1](docs/DECISIONS.md#1-demo-scope). Performance targets for the demo are proposed but not measured yet: [Q27](docs/DECISIONS.md#32-undecided-scope).

## Development

Run `pytest` from the repository root (no database, network or API key needed); it includes the doc-drift guards in `backend/tests/docs/`, which also run in CI. For frontend changes, also run `npm run build` in `frontend/`. Doc rules and commit style: [CONTRIBUTING.md](CONTRIBUTING.md); details: [Run locally §9](docs/how-to/run-locally.md#9-run-the-tests).

## Acknowledgements

Soongsil University Capstone.

License: not chosen yet; all rights reserved until a license is added.
