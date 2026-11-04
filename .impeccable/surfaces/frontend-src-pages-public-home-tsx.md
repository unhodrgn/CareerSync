---
version: 1
slug: "frontend-src-pages-public-home-tsx"
primary_target: "frontend/src/pages/public/Home.tsx"
related_targets: []
---

# Landing (`/`)

Mode: Persuade. Target: `frontend/src/pages/public/Home.tsx` (+ `Home.module.css`, `styles/tokens.css`, `components/common/icons.tsx`, `i18n/ko.ts` landing.* keys).

## Brief (confirmed by Long 2026-10-16; replaces the first landing brief)

- Reference: `EN V3 · Dual-Trail Outcome Flow (Off-White & Deep Rich Panels).html` (repo root). In Long's words: "Rebuild the landing to match that file", "superseding the PNG and the current build where they differ". Code-led; the rendered reference is the critique reference.
- Visitor: guest (capstone demo audience, first-time seeker or recruiter). Success = picks a side.
- Actions: 구직자로 시작하기 → `/register?role=seeker`, 로그인 없이 둘러보기 → `/jobs`, 기업으로 시작하기 → `/register?role=company`, 로그인 → `/login`. A click on a panel's open area also signs up for that side (the section's onClick ignores links, buttons and the example cards; no nested links).
- Content: static, synthetic, labeled 예시; seed job 클라우드랩 · 데이터 엔지니어 and its 4 real criteria. No stats, logos, testimonials.
- Seeker card: the 4 criteria names aligned 1:1 with the spine, neutral "구간 반영" badge, criterion 3 (AWS) as the amber dashed "이력서에 없음" gap row (D21), the JD-only gap (Airflow) in the footer, band 매우 적합; no checkmarks, no numbers (D1). Long will judge in the preview whether neutral rows read as "met"; fallback is the earlier gap list.
- Spine: category tags 기술/경력/기술/학력 instead of High/Core/Gap (Q2 undecided).
- Employer card: ranked applicants with synthetic names, "기준 4개 중 N개 충족", 4 indicator squares, one strength line (quoted CV evidence) and one weakness line each; not anonymous.
- Trust note: talent recommendation is anonymous until the seeker accepts an offer; AI analysis needs consent; recruiters decide.
- Approved deviations from the HTML: Pretendard and icons.tsx (no SF/Inter, tabler or Tailwind); Korean headline line-height 1.2; muted gray #6E6E73; no select-none; footer legal items as plain text; headlines ≤ 8 syllables per line; leads capped at 19.5em so line breaks never move; strength/weakness as one nowrap line each; hint/note alphas 0.62; text arrows drawn as icons; trust bar and footer full width (the HTML caps them at 1440px).
- Accepted exceptions (Long, 2026-10-16): the 01/02 numerals, the 공유 기준 pill, the "패널을 클릭해 가입" hints; the audience labels (● 구직자 / ● 기업) and the small heads above the cards and criteria list carried over from the earlier accepted label exception.
- Interactions: panel hover or `:focus-visible` inside a panel → that side 1.12fr, spine 324px, other side 0.88fr and dimmed (opacity .72, saturate .75, brightness .94), the active side's input chip lights; 400ms `cubic-bezier(0.2, 0, 0, 1)` after an 80ms delay, immediate collapse; under reduced motion no expansion (dimming still applies). Criterion: hover/focus previews, click pins, click again or Escape unpins; the lit criterion lights the seeker row, spine row, employer tag and both applicants' squares, the rest dim to .38.
- Layout: desktop only, 1280–1600px. Every column stacks fixed zones 256 / 68 / (20 + 360) so rows align at every width and state; no text may change its line breaks between states.

## Direction contract

THESIS: One criteria set is the page's spine; both outcomes hang off it at the same row heights. Refuses the split hero with a headline over a row of feature cards.

OWN-WORLD: Three vertical fields: deep navy #102C54 (seekers), off-white #F5F5F7 spine with a 2px axis, deep green #0D4A3E (employers). White 18px-radius cards with a soft 30px shadow on the dark fields, a near-black hub where both input chips meet, 2px wire stubs with 8px end dots, amber only for a skill missing from the CV. Pretendard 600 headlines at 40px, faint 116px numerals.

STORY: A visitor sees that the company's criteria give seekers a band and the skills their CV lacks and give employers a ranked applicant list with evidence, that recruiters decide, and starts on their side.

FIRST VIEWPORT: Header (logo, tagline, 로그인). Navy panel left (1fr), spine 324px center, green panel right (1fr), full height: each side has its role row, two-line headline, two-line lead, CTA, an input chip feeding the hub, and its 360px outcome card; the spine holds the identity card, the hub level with both chips, and the 4 criterion rows wired to both cards at the same heights. Trust note and footer close the page.

FORM: Pinned HTML reference (user-confirmed binding reference), dual-trail outcome flow with fixed zones; signature interactions: panel expansion with dimming, and the criterion trail lighting the same criterion across seeker card, spine, employer tags and applicant squares. seed: none (direction pinned by the user; no roll was run)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
