# How CareerSync works

One set of company-defined criteria powers two things: scoring the people who apply to a job, and recommending that job to people who have not applied. This page explains the flows, the architecture and how scores are made. The exact API, schema and constants are in [PROJECT_DOCUMENTATION.md](../../PROJECT_DOCUMENTATION.md); decisions are in [docs/DECISIONS.md](../DECISIONS.md).

> AI never accepts or rejects a candidate; application status changes only by recruiter action.

## User flows

### Flow A: Job seeker

```
Register → Upload CV → AI analysis → Edit & confirm → Set preferences → Recommended jobs (match band)
        → Prepare for a job (skill gaps, interview questions) → Apply → Track status in 지원 현황 (My applications)
        → (opted in) Answer anonymous offers from companies in 받은 제안 (Received offers)
```

### Flow B: Company

```
Register → Company profile + running projects → Create job → (optional) AI drafts the JD and suggests criteria
        → Set criteria + weights (blocked if discriminatory) → Publish
        → Applicants ranked by Fit → Per-criterion score + evidence → Recruiter updates status
        → 인재 추천 (talent recommendation): anonymous seekers ranked by Fit → Send offer → Contact after acceptance
```

## Architecture

```
Browser ──► Vite dev server :3000 ──(/api proxy)──► FastAPI :8000 ──► PostgreSQL :5433 (Docker)
                                                        │
                                                        └──► ai/ (parsing, scoring, guardrails) ──► LLM API (optional)
```

The backend calls the AI code only through `backend/app/services/ai_runtime.py`, and `ai/` never touches the database. The LLM is called only when `AI_MODE=llm`; every feature also works in the default `AI_MODE=rules`. Ports: 5433 is the manual setup's database; Docker Compose uses its own database on 5434 ([Run with Docker](../how-to/run-with-docker.md)).

## How scoring works

| Step | Approach |
| --- | --- |
| CV / JD structuring | LLM with JSON output when `AI_MODE=llm`, rule-based otherwise (default `AI_MODE=rules`); skill names are normalized with `data/skills.yaml` and experience months are always computed in code. Prompts are versioned in `ai/prompts/v1/` |
| Skill, experience, education, certificate criteria | Rule-based scoring on the masked CV text, in both modes. Skills are matched with a dictionary and declared groups of related skills (`data/skills.yaml`, D27), without embeddings; a skill the dictionary does not know is looked up by the keywords of its name (D28) |
| Project / other (judgment) criteria | `AI_MODE=llm`: LLM with a rubric (0/25/50/75/100) and evidence quoted from the CV; the quotes are verified against the CV, with one retry, then retrieval. `AI_MODE=rules` (D28): a `project` criterion is scored from the entries of the CV's 프로젝트 (projects) section (any entry 25, one entry naming a skill or keyword of the criterion or job 50, two or more 75, no 프로젝트 section 0); an `other` criterion by keyword/embedding retrieval, with a neutral 50 when retrieval finds nothing (only `other` gets it) |
| Retrieval (embeddings) | `intfloat/multilingual-e5-base` (fallback `hashing-ngram-v1`, D26) is used only to find the CV passages relevant to a criterion: for project/other criteria, for skills the dictionary does not know, and for the CV excerpts of interview questions. It never scores a skill on its own |
| Fit score | Weighted average of the stored per-criterion scores, recomputed from the current weights |

Pretrained models only; nothing is trained from scratch. The LLM is always called through `LLMClient` (`ai/llm/client.py`), so the model can be swapped without touching callers. What the LLM sees, and what is masked first, is in [Privacy and legal](privacy-and-legal.md).

## Scoring rules

| Rule | Value |
| --- | --- |
| Criteria per job | At most 10, integer weights summing to 100 |
| Fit score | Weighted average of the per-criterion scores (0–100): Σ(weight × score) / Σ weight |
| Weight edits after publish | Allowed, re-ranked instantly without re-calling AI |
| Seeker visibility of weights | Criterion name + category + importance (핵심 ≥ 25, 중요 ≥ 10, else 일반), no raw numbers; guests see names only. D30 defines the three labels and D35 the guest view; the thresholds are `IMPORTANCE_HIGH` and `IMPORTANCE_MID` in `backend/app/core/config.py` |
| Final score (job recommendation) | `0.5 × Fit + 0.5 × Pref`, recommend only when Fit ≥ 40 and Pref ≥ 40 |

The importance labels 핵심 / 중요 / 일반 mean core / important / general. Coefficients live in `backend/app/core/config.py`. Seekers never see a score: job recommendation shows only a match band (D16), and a seeker's own application shows its status, not its evaluation.
