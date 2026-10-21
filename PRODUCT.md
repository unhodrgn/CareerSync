# Product

<!-- impeccable:product-schema 1 -->

Product context for design work. Decisions and scope: `docs/DECISIONS.md` (wins on any conflict). Technical reference: `PROJECT_DOCUMENTATION.md`. This file does not decide features; it records who the product serves and what design work must not break.

## Platform

web

## Users

Two co-equal audiences; neither side's needs automatically win. The shared-criteria mechanism that connects them is the product.

- **Job seekers** (`seeker`, Korean-speaking): upload a text PDF CV, check and confirm what the AI extracted, set preferences, browse jobs (also without logging in), get recommended jobs with a match band, apply and track status, prepare for a specific job (skill gaps / roadmap, interview practice questions, CV self-check), and answer anonymous offers from companies.
- **Recruiters** (`company`, one account = one company): keep a company profile and running projects, write job postings (with AI drafting and criteria suggestions), define their own evaluation criteria and weights, review applicants ranked by Fit with per-criterion evidence, change application status, browse anonymous opt-in talent and send offers.

Near-term audience: this is a Soongsil University RISE capstone prototype, demoed locally via Docker Compose.

## Product Purpose

Each company defines evaluation criteria and weights per job. The same criteria (1) score applicants and (2) recommend the company's jobs to seekers who have not applied. Both sides get an explainable result: recruiters see scores with evidence quoted from the CV; seekers see a match band and what is missing from their CV.

Success: a recruiter trusts and acts on the ranking because every score points to CV evidence; a seeker understands what a company values and how well they fit before applying.

## Positioning

One set of company-defined criteria works in both directions on a single platform: it ranks applicants and guides seekers. Scores are explainable and evidence-backed (quotes are checked against the PII-masked CV), and **AI never accepts or rejects anyone**: application status changes only by recruiter action.

## Operating Context

- Seeker flow: register (privacy + AI consent) → upload CV PDF → AI structures it → edit and confirm (each save is a new version) → browse / recommended jobs → apply → track status; prep tools per job; offers inbox.
- Company flow: register → company profile → create job (draft) → optional AI JD draft and criteria suggestions → save criteria (legal guardrail) → publish → ranked applicants with evidence → status changes; talent list and sent offers.
- AI runs in `rules` mode by default; LLM mode is an explicit flag. Every feature must work and look complete in `rules` mode.
- Demo runs locally (`docker compose up`); no deployed environment.

## Capabilities and Constraints

Binding product rules that every screen must respect (see `docs/DECISIONS.md` for the full text):

- **Seekers see bands, never numbers** (D1, D16): no Fit %, Final, per-criterion score or weight. Recommendation bands: 매우 적합 / 적합 / 참고. Job-prep gaps are skills/certificates the job names that the CV text lacks, computed by code, not from company scores (D21).
- **AI never decides** (CLAUDE.md AI rule 5): status changes only from a recruiter click. UI copy must not imply the AI accepted or rejected anyone.
- **AI results carry a notice** (AI rule 6): responses with AI output include `notice` (`AI_NOTICE`); the UI shows it.
- **Talent is anonymous until offer acceptance** (D3, D19, D20): companies see `anonymous_id` and verified facts only; acceptance reveals only `display_name` + email. Applicants (who applied) are not anonymous to the company.
- **Consent gates AI use** (D16, D17): AI consent, re-consent for a newer `CONSENT_VERSION`, and withdrawal each change what a seeker can do; screens must handle the 409 consent states.
- Talent recommendation (anonymous list + offers) is in the demo (D29).
- Criteria pass a legal guardrail on save (discriminatory criteria blocked with the law cited).
- Frontend stack (existing): React 19, TypeScript, Vite, React Router 7. Korean UI, `lang="ko"`. All UI strings go through `t()` from `src/i18n` (source locale `ko.ts`); no new dependencies without approval.
- Devices: **desktop web only** for now. No mobile or tablet layouts; do not spend effort on responsive breakpoints.
- Decided since the first design pass (`docs/DECISIONS.md`): signed-in seekers see each criterion with an importance label 핵심 / 중요 / 일반, never a number or weight (D30), and guests see criterion names only (D35); the band appears only on recommended jobs, not on job detail or applied jobs (D31); no 사업자등록번호 field (D32); no job search filters, saved jobs or company dashboard metrics (D33); CV/account deletion is deferred to a later phase (D34).
- Undecided (do not design as if decided): the rest of Q11 (seeker profile fields 경력 수준 / 보유 기술 스택, a 기업 탐색 page).

## Brand Commitments

- Name: **CareerSync**. Tagline in docs: 기업 맞춤형 AI 채용 매칭 플랫폼 (criteria-based hiring and job matching). Logo mark: drawn in `frontend/src/components/common/icons.tsx` (`LogoMark`); no separate asset file.
- Voice: user-facing text is Korean; claims stay factual (what the AI checked, what evidence exists), never promises of hiring outcomes.
- **Binding visual reference:** "EN V3 · Dual-Trail Outcome Flow (Off-White & Deep Rich Panels)" is the landing reference, confirmed by Long 2026-10-16 (the HTML file is no longer in the repo; `DESIGN.md` and the shipped landing carry its decisions); it supersedes the earlier PNG of the same name and the first landing build. Its visuals bind later design work; its sample content does not override product rules. How the build resolved its content conflicts:
  - Seeker card: the 4 criteria names with a neutral "구간 반영" badge, the AWS row as the amber "이력서에 없음" gap (D21), the JD-only gap in the footer; no "Matched" rows, no numbers (D1, D16, D21).
  - Spine: neutral category tags instead of the High / Core / Gap badges (importance levels are Q2, undecided).
  - Employer card: named applicants (not anonymous); anonymity is stated only for talent recommendation, in the trust note.
  - Copy is Korean through `t()`; the example uses the seed job 클라우드랩 · 데이터 엔지니어, labeled 예시.

## Evidence on Hand

- Market research: `docs/reference/CareerSync 시장조사 보고서.pdf` (README cites companies struggling most with finding candidates, 44.5%, and reviewing applications, 41.0%).
- Plans: `docs/reference/CareerSync_과제계획서.pdf`, `docs/reference/CareerSync_설계서.pdf` (design document; not a source of decisions, D11).
- Demo data: `scripts/seed.py` (synthetic). Real CVs must never be used.
- None exist, and must not be invented: testimonials, customer logos, usage numbers, accuracy benchmarks, pricing, partner companies.

## Product Principles

1. **One criteria set, two directions.** Every surface should make visible that the company's own criteria drive both applicant ranking and seeker guidance.
2. **Evidence before verdict.** Show what the AI found in the CV (quotes, verified facts) alongside any score; a number without evidence is incomplete.
3. **Humans decide.** The AI scores and explains; recruiters decide; seekers control their data, consent and visibility.
4. **Each side sees only what it is entitled to.** Seekers get bands and gaps, not company weights; companies get anonymous talent until a seeker accepts.
5. **Rules mode is the real product.** Design for deterministic rule-based output first; LLM mode adds richer text, not new screens.
