---
version: 1
slug: "frontend-src-pages-public-register-tsx"
primary_target: "frontend/src/pages/public/Register.tsx"
related_targets: ["frontend/src/pages/public/Login.tsx","frontend/src/pages/public/Consent.tsx"]
---

# Login, register, consent (`/login`, `/register`, `/consent`)

Mode: Operate. Targets: `frontend/src/pages/public/Register.tsx`, `Login.tsx`, `Consent.tsx` (+ `Auth.module.css`), `components/common/AuthFrame.tsx`, `components/common/Form.tsx`. Inherits the landing world (DESIGN.md); no new visual world.

## Brief (confirmed by Long 2026-10-16)

- Register: `?role=` preselects 구직자/기업 (default 구직자), the switch rewrites the param in place. Fields from `RegisterIn`: both roles 이름 (`display_name`), 이메일, 비밀번호 (+ client-only 비밀번호 확인); company adds 회사명 (`company_name`). No 사업자등록번호 (Q6). Both consents required for both roles (backend rule).
- Seeker 이름 hint: shown to companies the seeker applies to, and to a company only after accepting its offer (D3/D19/D20) — never "recruiters see it" in general.
- Consent texts are drafts marked 초안, consistent with D16/D17; Long replaces them before the demo.
- After register: automatic login, then the role home (`/seeker`, `/company/jobs`), or `/consent` when the server asks; if that login fails, `/login?registered=1&email=…`.
- Login: presence checks only; 401 `INVALID_CREDENTIALS` is one form-level message (password cleared, focus to it). Success → `/consent` if `consent_required`, else a same-site `?next=`, else the role home.
- Consent: version from `current_consent_version`; 409 `CONSENT_VERSION_OUTDATED` reloads the user and asks again; lead text distinguishes a changed version from a withdrawn AI consent.
- Errors: client checks mirror `RegisterIn`; server 422 mapped to fields (backend Korean text for `value_error`), whole-body issues to a form alert; `EMAIL_TAKEN` under the email with a login link; network and 5xx as form alerts.
- Token in sessionStorage (issue 12, Long 2026-10-16); any later 401 clears it and the login page says the session expired.
- Desktop only; Korean via `t()`; no new dependencies.

## Layout

- AuthFrame: the landing header, then a 5fr/7fr split: the audience field on the left (seeker navy / employer green, recoloured by the role switch over 400ms; hub ink for login and consent, which serve both sides) with a two-line title and numbered point chips, the white form card (480px) on the off-white ground on the right.
- Form system: 44px fields on the sunken fill, tone-coloured focus ring, red (`--color-danger*`) for errors with an icon, never amber; role switch as two radio cards in their audience colours; consent group with 모두 동의 and inline disclosures.

## Open

- Final consent wording and retention period (draft says 확정 예정).
- 사업자등록번호 (Q6).
