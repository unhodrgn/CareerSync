# 🎯 CareerSync

**Criteria-Based Hiring & Job Matching Platform**

*Company-defined criteria. Explainable fit scores. Two-way recommendations.*

A multi-company recruiting platform where each company's own evaluation criteria are used both to score applicants and to recommend jobs to people who haven't applied yet.

[Features](#-features) · [Tech Stack](#-tech-stack) · [Getting Started](#️-getting-started) · [API Overview](#-api-overview)

---

## 📌 Overview

CareerSync connects a company's real hiring criteria with a job seeker's skills and preferences, and returns an explainable match result to both sides.

- **Companies** struggle most with finding candidates (44.5%) and reviewing applications (41.0%).
- **Job seekers** don't know what a company actually values, or how well their CV fits before applying.

The core idea: **one set of company-defined criteria powers two things** — scoring submitted applicants and recommending jobs to non-applicants — on a single shared platform.

> AI only supports decisions. Recruiters make the final call. The system never auto-accepts or auto-rejects a candidate.

## ✨ Features

| Feature | Description |
| --- | --- |
| 🔐 Authentication | Role-based registration (seeker / company) with consent to data processing, JWT login |
| 📄 CV Analysis | Upload a PDF CV, AI extracts skills, education, experience, projects, certificates; seeker reviews, edits and confirms |
| 🏢 Company Profile | Company info, 인재상 (talent philosophy), and running projects |
| 📝 Job Management | Create/edit jobs, AI parses the JD, publish or close, job detail page |
| ⚖️ Criteria & Weights | Per-job criteria with weights; inappropriate criteria are blocked with a reason |
| 📊 Applicant Evaluation | Applicants ranked by fit score, with per-criterion score, evidence and overall comment |
| 🎯 Job Recommendation | Fit, Preference and Final scores, a recommended job list, and the reason behind each recommendation |
| 🧑‍💼 Recruiter Workflow | Status changes only happen when a recruiter clicks, no auto-reject |
| 🛡️ Safety | PII masking before LLM calls, offline bias checks (Skew@k, counterfactual), "AI is advisory" notice |

## 🧠 AI Pipeline

| Step | Approach |
| --- | --- |
| CV / JD structuring | LLM with JSON output, schema and prompt versioned |
| Criteria scoring | LLM + RAG, each score comes with evidence quoted from the CV |
| Skill matching | Multilingual sentence embeddings (e.g. AWS ≈ Cloud Computing) |
| Two-way recommendation | Company→Seeker fit + Seeker→Company preference, content-based first (cold start) |
| Criteria guardrail | Blocks discriminatory criteria, e.g. "height 175cm+", per 채용절차법 제4조의3 |
| Bias check | Skew@k and re-ranking, counterfactual tests on synthetic labeled data |

Pretrained models only, nothing is trained from scratch.

## 🧰 Tech Stack

| Layer | Technologies |
| --- | --- |
| Frontend | React · TypeScript (API types generated from OpenAPI) |
| Backend | Python · FastAPI · REST API |
| AI | LLM (behind an `LLMClient` layer) · Embedding model · PyTorch · Hugging Face |
| Database | PostgreSQL |
| Authentication | JWT |
| Infrastructure | Docker · Docker Compose · Git / GitHub |

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│                Frontend                 │
│        React · TypeScript · UI          │
│        (Korean UI, desktop-first)       │
└────────────────────┬────────────────────┘
                     │ HTTP / JSON
                     ▼
┌─────────────────────────────────────────┐
│                 Backend                 │
│        Python · FastAPI · REST API      │
│   Auth · Business Logic · AI Services   │
└──────────┬─────────────────┬────────────┘
           │ SQL             │ API / local inference
           ▼                 ▼
┌──────────────────┐ ┌───────────────────────┐
│    PostgreSQL    │ │  LLM · Embedding model │
└──────────────────┘ └───────────────────────┘
```

## 📁 Project Structure

```
careersync/
├── frontend/                      # React + TypeScript
│   ├── src/
│   │   ├── api/                   # Types + client generated from OpenAPI
│   │   ├── pages/
│   │   │   ├── auth/              # Register, login
│   │   │   ├── seeker/            # Profile, CV, recommendations, reasons
│   │   │   └── company/           # Company profile, jobs, criteria, applicants
│   │   ├── components/            # Reusable UI (Table, Form, Stepper, ScoreCard)
│   │   ├── theme/                 # Design tokens
│   │   ├── hooks/
│   │   └── i18n/                  # Korean UI strings
│   ├── public/
│   └── package.json
│
├── backend/                       # FastAPI REST API
│   ├── app/
│   │   ├── main.py                # App entrypoint
│   │   ├── core/                  # Config, security (JWT), dependencies
│   │   ├── api/v1/                # auth, users, cv, companies, jobs,
│   │   │                          # criteria, applications, recommendations
│   │   ├── models/                # SQLAlchemy models
│   │   ├── schemas/               # Pydantic schemas
│   │   ├── services/              # Business logic (calls ai/ via interfaces only)
│   │   └── db/                    # Engine, session, Base
│   ├── migrations/                # Alembic
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── ai/                            # AI layer, imported by the backend
│   ├── llm/client.py              # LLMClient: swap models without touching callers
│   ├── prompts/                   # Versioned prompts (v1/, v2/ ...)
│   ├── schemas/                   # Versioned JSON output schemas
│   ├── parsing/                   # PDF → text, PII masking, CV/JD structuring
│   ├── embedding/                 # Embeddings + skill dictionary
│   ├── scoring/                   # Per-criterion scoring, Fit / Pref / Final
│   ├── guardrails/                # Criteria blocklist, evidence check
│   ├── bias/                      # Skew@k, counterfactual tests (offline)
│   └── cache/                     # Cache keyed by content hash
│
├── data/
│   ├── seed/                      # Synthetic jobs, companies, seekers
│   ├── gold_set/                  # Reference samples for scoring quality tests
│   └── blocklist.yaml             # Disallowed criteria, managed as config
│
├── scripts/                       # Seed DB, run AI spike, run bias audit
├── docs/                          # Blueprint, ERD, API spec, mockups
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

> **Note:** This tree represents the planned organization. Actual file and route names may differ as development progresses.

**Design rules**

- `services/` talks to `ai/` through interfaces only, so the core mechanism (one criteria set used for both applicant scoring and recommendations) lives in a single place: `ai/scoring/`.
- The LLM is always called through `LLMClient`, so models can be swapped after the spike.
- Prompts, JSON schemas and model versions are versioned and stored with every AI result.

## 🔄 Core User Flows

### Flow A — Job Seeker

```
Register → Upload CV → AI Analysis → Edit & Confirm
        → Set Preferences → Get Recommended Jobs
        → View Reasons (matched / missing) → Apply
```

### Flow B — Company

```
Register → Company Profile + Projects → Create Job → AI parses JD
        → Set Criteria + Weights (blocked if inappropriate) → Publish
        → View Applicants ranked by Fit → Per-criterion Score + Reason
        → Recruiter updates status manually
```

## 📏 Scoring Rules

| Rule | Default |
| --- | --- |
| Final score | `0.5 × Fit + 0.5 × Pref` |
| Recommendation threshold | Only when Fit ≥ 40 and Pref ≥ 40 |
| Weight edits after publish | Allowed, recalculated instantly without re-calling AI |
| Add/remove criteria after publish | Locked |
| Seeker visibility of weights | Criterion name + importance level (높음 / 보통 / 낮음), no raw numbers |

All coefficients live in config.

## 🎯 MVP Scope

| Item | Planned |
| --- | --- |
| Must-have features | 28 |
| Screens | 19 |
| Database tables | 22 |
| API endpoints | 48 |

**Assumptions:** IT/Software jobs only · Korean UI · 1 recruiter account = 1 company · text-based PDF CVs (≤ 5 MB, ≤ 5 pages) · synthetic demo data.

**Out of scope:** OCR, HWP/DOCX, scraping job sites, multiple recruiters per company, email notifications, interview scheduling, preference model trained from logs, admin screen, payments, mobile app.

## 🔌 API Overview

Local base URL: `http://localhost:8000`

> The endpoints below describe the planned interface and may change during implementation.

### Authentication & User

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/register` | Register as seeker or company |
| POST | `/api/auth/login` | Log in |
| GET | `/api/users/me` | Get the current user |

### Seeker & CV

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/cv` | Upload a CV and start analysis |
| GET | `/api/cv/:id` | Get the analysis result |
| PUT | `/api/cv/:id` | Edit and confirm the result |
| GET | `/api/recommendations` | Recommended jobs with reasons |

### Company, Jobs & Criteria

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/jobs` | Create a job |
| POST | `/api/jobs/:id/analyze` | AI parses the JD |
| PUT | `/api/jobs/:id/criteria` | Set criteria and weights |
| POST | `/api/jobs/:id/publish` | Publish a job |

### Applications & Evaluation

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/jobs/:id/applications` | Apply to a job |
| GET | `/api/jobs/:id/applications` | Applicants ranked by fit (recruiter only) |
| GET | `/api/applications/:id/evaluation` | Per-criterion score, evidence, comment |
| PUT | `/api/applications/:id/status` | Recruiter changes status |

## ⚡ Non-Functional Targets

Targets are for demo scale (≤ 100 seekers, ≤ 50 jobs) and may be adjusted after the AI spike.

| Area | Target |
| --- | --- |
| CRUD API | p95 < 500 ms |
| CV analysis (≤ 5 pages) | ≤ 60 s with progress bar |
| Evaluation after applying | ≤ 30 s |
| Recommendation list load | ≤ 1 s |
| Consistency | Same input run 3 times differs by ≤ 2 points |
| Explainability | 100% of criterion scores have evidence |
| Security | All endpoints except auth/health/meta need JWT, 0 IDOR |
| Privacy | No name, email or phone sent to the LLM |
| Deployment | `docker compose up` on a fresh machine ≤ 10 min |

## 🔒 Legal & Ethics

- 채용절차법 제4조의3
- 개인정보 보호법 제37조의2
- AI 기본법

The product does not collect sensitive group attributes. Bias is audited offline on synthetic labeled data.

## ⚙️ Getting Started

### Prerequisites

- Git
- Docker and Docker Compose

### 1. Clone the Repository

```bash
git clone https://github.com/<your-org>/careersync.git
cd careersync
```

### 2. Configure Environment Variables

Create `.env` from the example file and fill in your values:

```env
DB_HOST=db
DB_USER=postgres
DB_PASSWORD=your_db_password
DB_NAME=careersync_db
JWT_SECRET_KEY=replace_with_a_secure_random_secret
LLM_API_KEY=your_llm_api_key
```

> 🔒 **Security:** Never commit `.env` files or real credentials. Commit a `.env.example` with placeholders only.

### 3. Run Everything

```bash
docker compose up
```

This starts the frontend, backend, database and seed data.

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## 🧪 Quick Command Reference

| Task | Command |
| --- | --- |
| Start everything | `docker compose up` |
| Rebuild after changes | `docker compose up --build` |
| Stop everything | `docker compose down` |
| Run tests (from repo root) | `pip install -r backend/requirements.txt && pytest` |
| Apply DB migrations | `cd backend && alembic upgrade head` |
| Load demo data (password `demo1234`) | `cd backend && python ../scripts/seed.py` |

## 🗓️ Timeline

| Milestone | Date |
| --- | --- |
| Requirement Freeze | 2026-10-07 |
| Design Freeze | 2026-10-13 |
| Prototype Complete | 2026-10-18 |
| Coding starts | 2026-10-19 |
| Recommendation MVP | 2026-11-29 |
| Final demo | before 2026-12-13 |

## 🛠️ Troubleshooting

### Containers fail to start

### Database connection refused

### LLM call returns an authentication error

### Frontend cannot reach the backend
