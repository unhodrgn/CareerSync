# How the frontend talks to the backend

The frontend uses the existing backend contract as it is: Bearer JWT, `/api/*` paths, and the backend DTOs. Anything the screens need in another shape is mapped in the frontend. The full list of endpoints is in `PROJECT_DOCUMENTATION.md` §4; the frontend pages and the calls each one makes are in §5.

## Data flow

`User → page → useCareerStore (hooks/) → api (services/apiService.ts) → httpClient → /api → Vite proxy → backend`

Pages never call `fetch` and never write to storage. They read state and call actions from `useCareer()`.

| Path | Responsibility |
| --- | --- |
| `src/App.tsx` | Layout; picks the page from the hash URL (`#jobs`, `#detail/12`, …) |
| `src/hooks/useCareerStore.ts` | All state and actions: session, page guard (`resolvePage`), jobs list and detail |
| `src/services/httpClient.ts` | Base `/api`, `Authorization: Bearer`, JSON or multipart body, `ApiError`, 401 handling |
| `src/services/apiService.ts` | One typed function per backend endpoint (`api.*`) |
| `src/services/errors.ts` | `ApiError` → one Korean sentence |
| `src/services/jobView.ts` | Backend job DTOs → `Job` / `JobDetail` view models (labels, D-day) |
| `src/services/jobForm.ts` | Company job pages: job form ↔ `JobCreate` (the two text areas ↔ one `description`), criteria rows ↔ `CriterionIn` with the server's checks, refused publish and criteria saves → Korean text and where to fix |
| `src/services/matchView.ts` | What the match-score parts show (D42–D44): the disclaimer, the detail-page state, the next step after a refused recommendation |
| `src/services/tokenStorage.ts` | The access token in `sessionStorage` (memory fallback) |
| `src/types/` | Backend DTOs (`auth.ts`, `job.ts`, `criteria.ts`, `common.ts`) and view models (`index.ts`) |

## Running against the backend

The browser always calls `/api` on its own origin. The Vite dev server (port 3000) forwards `/api` to `VITE_API_TARGET`, default `http://127.0.0.1:8000`. Docker Compose sets `http://backend:8000`. The backend has no CORS setup, so do not point the browser at `:8000` directly.

```sh
cd backend && uvicorn app.main:app --reload   # API on :8000
cd frontend && npm run dev                     # UI on :3000
```

To use another backend, copy `.env.example` to `.env.local` and change `VITE_API_TARGET`. `VITE_*` values reach the browser bundle, so never put a secret in one. There is no mock mode.

## Auth and session

- `POST /api/auth/login` returns `access_token`. It is stored in `sessionStorage` (it ends with the tab; XSS exposure is issue 12) and sent as `Authorization: Bearer …`. No cookies are used.
- After login, and on page load when a token is stored, `GET /api/users/me` gives the role (`seeker` / `company`), the display name and the consent state.
- `POST /api/auth/register` needs `display_name`, `company_name` (companies only) and both `consent_privacy` and `consent_ai` set to true. It returns the user without a token, so the store logs in right after.
- A 401 on a call made with a token clears the token. `httpClient` fires `careersync:session-expired`, and the store shows the login page.
- Logout only drops the token. The JWT is stateless and there is no logout endpoint.
- `consent_required` with an older `consent_version` sends the user to the consent page (`POST /api/users/me/consent` with `current_consent_version`, D17). A seeker who withdrew AI consent can choose “나중에 하기” (later).
- The page guard only picks the screen. The backend checks every call (`403 SEEKER_ONLY`, `기업 회원만 …`).

## Errors

The backend answers in three shapes. `httpClient` turns each one into an `ApiError`:

| Body | `code` | Text shown |
| --- | --- | --- |
| `{code, message}` (`AppError`) | the backend code, e.g. `EMAIL_TAKEN` | the UI's own sentence for known codes, otherwise `message` |
| `{detail: "…"}` (FastAPI `HTTPException`, e.g. 401/403) | `HTTP_<status>` | `detail` |
| 422 `{detail: [...]}` (validation) | `VALIDATION` | the first issue, without Pydantic's “Value error, ” prefix |
| no JSON / network failure | `SERVER` / `NETWORK` | a generic sentence |

## Not connected yet

These actions show “이 기능은 아직 서버와 연결되지 않았습니다.” (this feature is not connected to the server yet): candidates. The company dashboard counts need backend work first (`docs/DECISIONS.md` D45), so the company dashboard shows no numbers yet.

## Saved jobs

`GET /api/saved-jobs/mine`, `PUT` and `DELETE /api/jobs/{job_id}/save` (seekers only, D45). The store loads the list once after a seeker signs in. A bookmark click changes the list at once; if the server refuses, only that change is undone and the error is shown. Guests who click go to login, and companies do not see the button. Closed and expired jobs stay in the saved list and show 마감 (closed).

## CV and applying

- `GET /api/cv/me` loads the newest CV version after a seeker signs in and on every visit to the CV page; 404 `CV_NOT_FOUND` means none yet.
- `POST /api/cv` (multipart `file`, text PDF ≤ 5 MB / 5 pages) returns the analysis of the PII-masked text (D39). The page shows the kinds of masked data, never the data, and logs nothing.
- The seeker corrects the result in `CvEditor` and confirms it with `PUT /api/cv/{id}` and `confirm: true`. This saves a new version, the one used to apply. Each item's `source` line is kept unchanged.
- `POST /api/cv/{id}/review` returns `strengths` and `improvements` as `{title, detail, cv_quote, affects_scoring}`. The page shows every `notice` the API returns.
- `POST /api/jobs/{id}/applications` has no body. After it, success or not, the store loads `GET /api/applications/mine` again, so the button shows the real status. The 409s `CV_NOT_CONFIRMED`, `AI_CONSENT_REQUIRED`, `ALREADY_APPLIED` and `JOB_EXPIRED` are explained on the job page, with a link to the CV page or the consent page where that helps.
- Statuses are set by the company; their Korean labels are in `src/data/labels.ts`. Seekers never see a score for an applied job.

## Company jobs

- `GET /api/jobs/mine` fills the company dashboard on every visit and after each change. Status labels: 작성 중 (draft), 게시 중 (published), 기간 만료 (published, deadline passed), 마감 (closed).
- `POST /api/jobs` always creates a draft; the store then opens `#criteria/<id>`. `PATCH /api/jobs/{id}` edits a draft from `#post/<id>`; `DELETE /api/jobs/{id}` deletes a draft (confirm dialog). The form sends every field: empty numbers and dates as `null`, `headcount` 1–999 (D47), and the two text areas as one `description` with the headings `[주요 업무]` and `[자격 요건 및 우대 사항]`. A JD written elsewhere opens whole in the first text area.
- `GET` and `PUT /api/jobs/{id}/criteria` as the owner carry the weights; only company pages request them, and seekers keep getting importance labels only (D30). `POST /api/criteria/check` runs half a second after typing stops. The editor checks count, names, weights and the total before saving; the server's `CRITERIA_BLOCKED` and `CRITERIA_MAJOR_REQUIRED` items and a 422 on `items[i]` are shown on that row.
- `POST /api/jobs/{id}/publish`: `FIELD_REQUIRED` (`category`), `JOB_INCOMPLETE`, `DEADLINE_IN_PAST` link to the job form; `CRITERIA_COUNT_INVALID`, `WEIGHT_SUM_INVALID` and the other criteria codes link to the criteria editor. `POST /api/jobs/{id}/close` asks for confirmation first; a closed job leaves `GET /api/jobs` and recommendations.
- Nothing on these pages says who saved a job (D45).

## Match score

- `GET /api/recommendations/jobs?limit=20` feeds 추천 공고 (recommended jobs) and the count tile on the seeker dashboard; it is loaded on every visit to either page and on 새로고침 (refresh). Each item has `match_score` (an integer 0–100), `match_level`, `strengths` and `gaps` (≤ 3 each). `pending_count` jobs are still being scored. The 409s `CV_NOT_CONFIRMED` and `AI_CONSENT_REQUIRED` show their sentence with a link to the CV page or the consent page (`services/matchView.ts`).
- `GET /api/jobs/{id}/match` is called on the job page for seekers, never for a job they applied to. It only reads and never starts scoring (D44). `done` shows the score; `pending` says scoring is in progress; `none` points to 추천 공고 instead of a number. Guests and companies never call it.
- `components/MatchScore.tsx` always shows the band, “점수는 합격 가능성을 뜻하지 않습니다.” (the score does not mean a chance of being hired) and the response's `notice` beside the score (D42). Fit, Pref, per-criterion scores and weights never reach the frontend.

## Profile

- `PATCH /api/users/me` with only `display_name`; the email is the login and read-only. The store replaces `user` with the response, so the header shows the new name at once.
- A seeker's name is locked once a CV was uploaded (409 `NAME_LOCKED`, D46): the CV was masked with that name (D39). The page disables the field as soon as it knows a CV exists. An upload during which the name changed is refused with 409 `NAME_CHANGED`.
- `GET` and `PUT /api/preferences/me` feed the form through `services/preferenceView.ts`. Job keywords, regions and employment types feed Pref. `experience_level` and `skills` are display only, and the page labels them so. The talent opt-in (`profile_public`) is sent back exactly as stored.

## Job search and filters

`GET /api/jobs?q=&category=&region=` does all filtering on the server (D45). `q` matches the title, the company name or a job tag. `category` is one of `dev`, `data_ai`, `design`, `marketing`, `planning`; the Korean labels are in `src/data/categories.ts`. `region` is a name from `JOB_REGIONS` in the backend config, and the same list is kept in `src/data/categories.ts`. Every job carries `tags`: skills the backend finds in the criteria and the JD. They are for display and search only.

## Tests

```sh
npm run build
node --test tests/services.test.mjs
```

`tests/services.test.mjs` runs the service layer in Node with a fake `fetch`. It covers the `/api` paths, the Bearer header, no cookies, JSON and multipart bodies, the three error shapes and their Korean text, 401 handling, network errors, the job view mapping, the match-score calls and states, and the company job and criteria calls with the form and error mappers. It does not replace browser or end-to-end tests.
