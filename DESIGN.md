---
name: CareerSync
description: 기업 맞춤형 AI 채용 매칭 플랫폼. App pages follow the "job example" reference — white icon rail, segmented header tabs, gray content panel with white cards, one mint accent, dark gradient match panel. The landing page keeps its own legacy system.
scope:
  app: every page except the landing (`/`) — signed-in shell, guest job pages, login, register, consent, not found
  landing: "`/` only — legacy Dual-Trail system, documented at the end of this file"
colors:
  bg: "#ffffff"
  panel: "#f4f5f7"
  surface: "#ffffff"
  sunken: "#f7f8fa"
  chip: "#eceef1"
  chip-hover: "#e2e5e9"
  tag: "#eef3f1"
  ink: "#111111"
  ink-2: "#3a3a3c"
  muted: "#646b78"
  line: "#ececee"
  line-strong: "#dcdfe3"
  accent: "#00eb9c"
  accent-hover: "#00d48c"
  on-accent: "#0b0b0b"
  accent-soft: "#b2fae2"
  accent-wash: "#eef8f3"
  ring: "#2dd4a7"
  accent-text: "#067a55"
  focus: "#0b8f6c"
  halo: "0 0 0 4px rgb(0 235 156 / 0.3)"
  disabled: "#e7e9ec"
  on-disabled: "#8b9099"
  ai: "#2563eb"
  ai-text: "#1d4ed8"
  ai-soft: "#eef4ff"
  ai-line: "#c7d7fe"
  ai-on-dark: "#bfdbfe"
  ai-gradient: "linear-gradient(135deg, #3b82f6, #2563eb)"
  match-from: "#07120f"
  match-to: "#0f5e4a"
  on-match: "#ffffff"
  on-match-muted: "rgb(255 255 255 / 0.78)"
  danger: "#b42318"
  danger-soft: "#fef3f2"
  danger-line: "#f04438"
  gap: "#b45309"
  gap-strong: "#92400e"
  gap-line: "#d97706"
  gap-soft: "#fffbeb"
  gap-badge: "#fef3c7"
typography:
  family: "'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', system-ui, sans-serif"
  weights: [400, 500, 700]
  section: { fontSize: "24px", fontWeight: 700, letterSpacing: "-0.03em" }
  job-title: { fontSize: "26px", fontWeight: 700, letterSpacing: "-0.03em" }
  title: { fontSize: "22px", fontWeight: 700, letterSpacing: "-0.03em" }
  card-title: { fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em" }
  heading: { fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em" }
  body: { fontSize: "15px", fontWeight: 400, lineHeight: 1.5 }
  meta: { fontSize: "14px", fontWeight: 400 }
  caption: { fontSize: "13px", fontWeight: 400 }
  tiny: { fontSize: "12px", fontWeight: 500 }
  match-number: { fontSize: "34px", fontWeight: 500, letterSpacing: "-0.03em" }
rounded:
  sm: "8px"
  chip: "10px"
  md: "12px"
  card: "16px"
  surface: "20px"
  match: "20px"
  panel: "24px"
  pill: "999px"
shadow:
  card: "0 1px 2px rgb(16 24 40 / 0.04)"
  pop: "0 8px 24px rgb(16 24 40 / 0.08)"
spacing: [4, 8, 12, 14, 16, 20, 24, 32]
layout:
  min-width: "1280px"
  rail-width: "88px"
  header-height: "72px"
  page-padding: "24px"
  aside: "360px"
---

# Design System: CareerSync

Tokens live in [`frontend/src/styles/tokens.css`](frontend/src/styles/tokens.css): the `--ds-*` variables are this system; the `--color-*` / `--radius-*` variables above them belong to the landing and must not change value.

## Overview

**Reference:** `job example.jpg` (a job-feed screen), approved by Long on 2026-11-05 for every page except the landing ([docs/DECISIONS.md](docs/DECISIONS.md) Q28). It replaces the 2026-10-16 "Dual-Trail" reference for those pages. Only its design language is used — no product names, logos or sample content from it.

**Character:** light, roomy and calm. A white frame (icon rail and header) holds one large gray panel; on it sit white cards that are almost flat. Black marks what is selected, a single mint green marks the one action that matters and every score ring, and one dark green-black gradient is reserved for the match score. Type is Pretendard at three weights; hierarchy comes from size and weight, not color.

**Key characteristics:**
- One palette for both roles. Seekers and companies share every color; the role shows in the navigation and wording only.
- Desktop web only: `body { min-width: 1280px }`, laid out for 1280 px and wider, no breakpoints.
- Korean-first: body text breaks between words (`word-break: keep-all`), and every UI string goes through `t()` (`frontend/src/i18n/ko.ts`).
- Motion is feedback: page enters, list stagger, press scale; all of it off under `prefers-reduced-motion`.

## Colors

- **Frame (bg, `#ffffff`):** the page behind everything, the rail, the header, the auth page.
- **Content panel (panel, `#f4f5f7`):** the one large rounded area pages draw on. Also the form side of the auth pages and the not-found ground.
- **Surface (`#ffffff`) and sunken (`#f7f8fa`):** cards; fills inside cards (quotes, project tiles).
- **Chips (`#eceef1`, hover `#e2e5e9`):** filter-style chips, neutral tags, quiet-button hover.
- **Ink (`#111111`), ink-2 (`#3a3a3c`), muted (`#646b78`):** titles and selected states; body text; meta, captions and placeholders. Muted passes 4.5:1 on white (5.4:1) and on the panel (4.9:1).
- **Lines (`#ececee`, strong `#dcdfe3`):** dividers inside cards; input and outlined-control borders.
- **Accent (mint `#00eb9c`, measured from the reference's APPLY NOW buttons; hover `#00d48c`):** the primary button fill (always with ink text, never white), the rank-1 tile, the current-group badge, published-status dots. **accent-soft** (`#b2fae2`, the reference's highlighted bubble) is the focus halo and tone chips; **accent-wash** (`#eef8f3`) the current rail item, the company tile on cards, icon circles and the selected applicant row.
- **Ring (`#2dd4a7`):** score-ring arcs and the breakdown spark.
- **Accent text (`#067a55`, 5.3:1 on white):** mint-family text and links on white, importance 핵심, done lines.
- **Focus (`#0b8f6c`) and halo (`0 0 0 4px` mint at 30%):** focus outlines and focused input borders; the halo surrounds a focused input, checkbox or radio. Outlines appear only for keyboard focus (`:focus-visible`), never after a click.
- **Disabled (`#e7e9ec`, text `#8b9099`):** every disabled button, the auth submit while busy and disabled checkboxes — a gray fill, never a faded copy of the enabled colour.
- **Match gradient (`#07120f` → `#0f5e4a`):** the match panel, and the same gradient on the guest banner, the CV rule card and the auth field. White text; secondary text at 78% white.

### Named rules
**The One Mint Rule.** Mint fills one primary action per view, plus score rings. It is never a background for text-heavy areas and never carries white text.

**The Black Is Selected Rule.** Selected tabs, pressed filter toggles, chosen status options and chosen role cards are ink with white text (or an ink edge). Hover is a chip-gray fill.

**The Amber Is Absence Rule** (kept). Amber (gap tokens) marks one thing only: a skill or certificate the CV lacks.

**The Red Is For Errors Rule** (kept). Danger red marks input that cannot be submitted or a request that failed; on failed-request states the red sits on the icon, the text stays ink-2.

**The Blue Is AI Rule.** The AI blue (`--ds-ai*`) marks one thing only: something an AI feature made or is making (see AI markers). It is never decoration, never a link or action colour, never a status. Mint stays the brand and action colour.

**The Logo Colors Stay In The Logo Rule** (kept). `LogoMark`'s blue and green appear only inside the mark.

## Typography

Pretendard Variable (self-hosted woff2), weights **400 / 500 / 700**.

| Role | Size / weight | Used for |
|---|---|---|
| Section | 24 / 700, -0.03em | The group name in the shell header ("채용") |
| Job title | 26 / 700 | The H1 on job detail |
| Page title | 22 / 700 | Every other visible page H1 (company job header 24) |
| Card title | 18 / 700 | Job card titles, offer titles |
| Heading | 18 / 700 | Panel titles, aside titles, section heads, record-row titles |
| Body | 15 / 400 (JD text 16, line-height 1.75) | Default text, inputs, buttons |
| Meta | 14 / 400 | Meta lines, list rows, small buttons |
| Caption | 13 / 400 | Captions, hints, footnotes |
| Tiny | 12 / 500–700 | Tags, rail labels, counts, importance |
| Match number | 34 / 500 in a 104 px ring | The match score |

## Layout

**Signed-in shell** (`components/layout/AppShell`):
- **Rail** (88 px, white, sticky, full height): the `LogoMark` (36 px) level with the header, then one item per group, 4 px apart — 22 px icon over a 12/700 label, 10 / 8 px padding, 16 px radius, current group on accent-wash with an accent-text icon — and 로그아웃 at the bottom in the same form. A pending-offer count is a mint badge on the 채용 icon.
  - Seekers: 채용 (추천 공고 · 공고 목록 · 지원 현황 · 받은 제안) · 이력서 (내 이력서) · 프로필 (희망 조건 · 내 정보).
  - Companies: 채용 (공고 관리 · 보낸 제안) · 기업 (기업 프로필).
  - Pages without a tab of their own belong to a group: 공고 상세, 기업 정보 and (seekers) 취업 준비 to 채용.
- **Header** (72 px, not sticky): section name (24/700), a chevron, then the group's pages as segmented pill tabs (38 px, 15/700; current tab ink with white text; counts as ink pills, inverted on the current tab). Single-page groups show the name only. On the right, the name (14/700) over the email or company name (12.5 muted) and a 34 px initial avatar on accent-soft.
- **Content panel:** gray, 24 px radius, 24 px from the right and bottom edges, at least the viewport height minus the header. Pages inside use the whole panel width with 20 px padding, the same on every page; only long text (JD, messages) keeps a reading measure.
- **No repeated page title:** the header already names the group and the current tab, so a tab page's H1 stays for assistive tech only (`PageHead tabTitle`) and the page starts with its content; a description line stays only where it says something the user needs. Pages whose subject is their title (job detail, a company job, 취업 준비, a company profile, 새 공고) keep a visible H1. Tab labels and titles use the same words (공고 목록, 내 이력서, 희망 조건 …).
- **Consent-withdrawn banner:** a mint-wash strip with an accent-soft border above the panel.

**Guest shell:** a 64 px white header (logo, wordmark 20/700, 회원가입 quiet link, 로그인 ink pill) over the same panel.

**Auth pages** (`AuthFrame`): a sticky 64 px white header; below it a `5fr / 7fr` split with 16 px between — the dark gradient field (24 px radius, 40 px padding, 30/700 two-line title, numbered point chips, content centred vertically) and the gray panel with the form card at the top centre. The field is sticky at the full viewport height under the header, so it keeps its rounded corners while a long form (회원가입) scrolls beside it.

**Detail layouts:** content plus a 360 px sticky aside (job detail), a 380 px sticky applicant detail (지원자 순위), a 320 px sticky preview (공고 편집).

## Elevation

Cards are nearly flat: `0 1px 2px rgb(16 24 40 / .04)` and no border. Things that float — job cards on hover, sticky save and action bars, the pending line — use `0 8px 24px rgb(16 24 40 / .08)`. Rings drawn with `box-shadow` mark state (focus halo, selected applicant edge), not elevation.

## Shapes

8 px small tags · 10 px chips · 12 px inputs, list tiles, status options · 12 px job icon tiles (16 px on job detail) · 16 px rail items, project tiles · 20 px cards, panels and the match panel · 24 px the content panel and auth field · pills for every button, tab, toggle, count, band and the search field. Score rings are full circles; icon circles 56 px.

## Components

### Buttons (`ui.btn`)
Pills, 40 px (small 32), 15/700 (small 14/700), press `scale(.95)`.
- **Primary:** mint fill, ink text; hover mint-hover. One per view.
- **Secondary:** white with a 1.5 px ink border (the reference's outlined "Connect" style); hover sunken.
- **Quiet:** no fill, ink text; hover chip gray.
- **Link (`linkTone`):** accent-text, underlined.
- **Auth submit:** full width, 52 px, mint, ink text; while busy, the disabled gray with a spinner.
- **Disabled (all variants):** the disabled gray fill with muted text.

### Inputs
White, 1 px line-strong border, 12 px radius, 40 px (auth 44 px); hover border muted; focus border focus-green plus the mint halo; invalid border danger-line with a danger-soft halo. On the auth pages the border belongs to the wrapper, and the input inside follows its inner radius, so no fill can cover the rounded border. Browser autofill keeps the white field and ink text (an inset white shadow over the browser's blue), so a password field with its eye button still reads as one field. Selects carry an ink chevron. The job search field is a pill with a leading icon.
- **Checkboxes and radios** (`styles/app.css`, every app page): 20 px, 6 px radius (radios round), line-strong border; checked = mint fill with an ink tick or dot; keyboard focus = focus border plus the halo. The 회원가입 role cards use the same mint radio mark.
- **Switch:** focus-green when on.

### Chips, tags, counts
- **Chips** (preferences, skills, techs): chip gray, 10 px radius, 15/500, round remove button.
- **Tags:** chip gray, 8 px radius, 12/500; tone tags on accent-soft with accent-text.
- **Status:** an 8 px dot before the label — submitted/reviewing/pending in ring mint, accepted/interview/passed in accent-text, published in mint, draft in line-strong.
- **Counts:** ink pills next to titles and on tabs.
- **Band pill** (where a band shows alone): 매우 적합 ink with a mint dot, 적합 accent-soft, 참고 outlined.

### Job card (`components/seeker/JobCard`)
The reference's feed card, compact. White, 20 px radius; the whole card is the title link (focus ring on the card, hover lifts to the pop shadow). Left: the 48 px job icon tile (see Job icon), the 20/700 title and the company in muted; one row of facts with line icons (location, employment type, experience, deadline); the score breakdown when scored; a footer with the criteria count, the card's own actions (추천 공고: 준비하기 as a small secondary pill) and the mint 상세 보기 pill. The pill is a picture of the card link (no second tab stop). Right, only with a valid match score: the 184 px match panel, as tall as the card. Cards stack 12 px apart and stagger in.

### Match panel and score rings (`components/seeker/Match`)
What seekers see of a match ([docs/DECISIONS.md](docs/DECISIONS.md) D42, D43):
- **Match panel:** the dark gradient, 20 px radius, centred with tight spacing: the blue AI chip "AI 적합도" (light blue on 16% blue, see AI markers), a 92 px ring (84 px compact) with the match score inside (30/500 plus a half-size "%"), the band under it (16/700). Below 40 the number stands alone, without a band.
- **Breakdown ("적합도 구성"):** a blue AI spark and title, then a row of 44 px light rings — one per criterion category the job uses (plain mean, no weights), then 희망 조건 (the preference score) — each with its label beside it.
- **Missing data:** every score display checks what the API sent. A missing or invalid match score hides the panel (the card falls back to the plain card); missing categories, preference score or criterion scores hide only those rings; an unknown band hides the band. Nothing about a score can break the page.
- **Per-criterion rings:** 44 px rings at the end of each criterion row on job detail.
- **Ring:** the arc is the score out of 100 in ring mint on a line-gray track (14% white on the dark panel), round caps, starting at 12 o'clock. The number is visible text; the SVG is hidden from assistive tech.
- **Next to every score:** the AI notice and the note "점수는 합격 가능성을 뜻하지 않습니다. 기업이 정한 가중치는 공개되지 않습니다."
- Companies keep exact Fit numbers (one decimal) and indicator squares; rings are a seeker-side display.

### Job icon (`components/common/jobIcon.ts`, `JobIconTile`)
An illustrative icon for the job's type where the reference shows company logos — on job cards (48 px) and next to the job detail title (60 px). It is not a company logo. Every group uses the same tile: a rounded square on accent-wash with the line icon in accent-text, so cards stay uniform. Jobs have no category field yet, so the title decides (the helper takes a category first once one exists). Groups are checked in this order and the first match wins; Korean keywords match anywhere, Latin ones only as whole words ("ai" does not match "maintain", "pm" not "npm").

| Group | Icon | Title keywords |
|---|---|---|
| Security | shield | 보안, 정보보호, 시큐리티, security |
| AI / ML | chip | 인공지능, 머신러닝, 딥러닝, AI, ML, LLM, MLOps |
| Data | chart | 데이터, 분석, data, analyst, analytics, BI |
| Infra / DevOps / Cloud | cloud | 인프라, 데브옵스, 클라우드, 쿠버네티스, infra, devops, cloud, SRE, kubernetes |
| Mobile | phone | 모바일, 안드로이드, 앱 개발, mobile, iOS, android, flutter, react native |
| QA | check circle | 테스트, 품질, QA, test, SDET |
| Frontend | monitor with code | 프론트엔드, 프런트엔드, 퍼블리셔, frontend, front-end, react, vue |
| Backend | stacked servers | 백엔드, 서버, backend, server, java, spring, node, django, api |
| Design | palette | 디자이너, 디자인, design, UX, UI |
| PM / Planning | clipboard | 기획, 프로덕트 매니저, 사업, PM, PO, product manager |
| Anything else | briefcase | — |

### Candidate avatar (`components/company/CandidateAvatar`)
Where the reference shows profile photos, company pages show an abstract avatar: a circle (40 px; 48 px in the applicant detail) with one of six compositions of geometric shapes (circles, a quarter circle and turned square, a diagonal band, a tile grid, rings, a half disc and triangle) in token colours only (accent, ring, accent-text, match gradient, accent-soft, accent-wash, chip). No faces, figures or anything that suggests gender, age or ethnicity. It is deterministic from a non-identifying seed — the talent `anonymous_id` on 인재 추천 and 보낸 제안, `"A-" + application_id` on 지원자 순위 and the applicant detail — and never from a name, email or other personal data. Decorative (`aria-hidden`): the ID or name beside it is the text.
- **The two seeds are kept apart on purpose:** matching avatars would let a company link an anonymous talent profile to a named applicant and break the anonymization, so the same person may look different in the two places.

### Cards and lists
- **Panel (`ui.panel`):** white card, 20 px padding, no border. Inside, sections split by hairlines — never a box inside a box.
- **Record list:** one white card, rows split by hairlines; whole-row links with secondary actions raised above.
- **Read-only list rows:** 42 px, hairline between rows.
- **Tables** (지원자 순위): inside a panel; header 12/700 muted; rows split by hairlines; hover sunken; the selected row on accent-wash with a 3 px mint left edge; rank 1 on a mint tile.

### Tabs inside pages
The header's segmented pills at 40 px: current tab ink with white text, hover chip gray.

### States
- **Loading:** chip-gray skeleton bars with a shimmer, inside the card they replace.
- **Empty / blocked:** centred in a card — a 56 px accent-wash icon circle (inbox for empty, info for a missing precondition), an 18/700 title, a muted body and at most one action (blocked: the primary button that resolves it).
- **Failed request:** the same with a danger-soft circle and alert icon, the message in ink-2, and 다시 시도 as a small secondary button.
- **Not found:** the gray ground with one centred card and 홈으로 가기.
- **Render error** (`RouteError`, the routes' `errorElement`): the failed state with "화면을 표시하지 못했습니다", 다시 시도 (reload) and 홈으로 가기 — inside the content panel when a page fails (rail and header stay), on the gray ground when the shell or an auth page fails. The landing route has none.
- **Inline confirms** replace their trigger inside the card, set off by a hairline, and take focus.

### Notices
- **AI notice** (AI rule 6): the blue "AI" pill with the spark, the server's notice at 12.5 ink-2, the method in muted on the right. Inside an AI box the pill is left out (the box label marks it). Never hidden, one per AI result.
- **Other notices:** a caption with an accent-text info icon.
- **Guest banner** (공고 목록): the match gradient with the mint 가입 action.

### AI markers (`components/common/Ai.tsx`)
Blue shows where AI is used — for users and for transparency about AI use (docs/DECISIONS.md Q29). An AI feature is one whose response carries `AI_NOTICE` (CLAUDE.md AI rule 6), in LLM or rules mode. Nothing else gets a marker, and blue is never decoration.

- **Colours:** `--ds-ai` `#2563eb` (the AI pill fill, white text 5.2:1; the working spark), `--ds-ai-text` `#1d4ed8` (AI text, 6.7:1 on white, 6.1:1 on ai-soft), `--ds-ai-soft` `#eef4ff` and `--ds-ai-line` `#c7d7fe` (AI box). The gradient token starts at the logo's own blue `#3b82f6`; that blue is never used for text (3.7:1).
- **The marker is one "AI" pill** (`AiMark`): white "AI" on AI blue, 18 px tall, 11/700, pill radius (15 px / 9.5 px for the small size next to Fit and in the working state). It is its own element placed directly before the feature's name — never written into the text — so labels stay translatable and screen readers read "AI 추천 공고". It looks the same on white, on a black selected tab and on the dark match panel. Labels that name AI themselves use the same pill with their wording: "AI 분석", "AI 생성", "AI 적합도". Strings shown beside a pill do not repeat "AI" (초안 쓰기, 공고 초안, 분석 중).
- **Rail:** labels stay as they are (never "AI 채용"). A group that contains at least one AI feature — on a tab or inside a page — gets a small "AI" badge on the top-right corner of its icon, ringed in white; screen readers hear "AI 기능이 있는 메뉴". Seekers: 채용 (추천 공고, scores, 취업 준비) and 이력서 (CV analysis, self-check). Companies: 채용 (지원자 순위, 인재 추천, the AI JD draft, criteria suggestions). Groups without any AI feature — seeker 프로필, company 기업 — get nothing. The pending-offer count moves to the icon's top-left so the two never overlap. The rail badge says "this section has AI"; the pills on tabs say exactly which pages.
- **Where the pill appears:** header tabs ([AI] 추천 공고, and [AI] 이력서 as the one-page section name), company job tabs ([AI] 지원자 순위, [AI] 인재 추천), 취업 준비 tabs ([AI] 부족한 기술·로드맵, [AI] 면접 예상 질문, [AI] 이력서 점검), buttons that open AI features ([AI] 초안 쓰기, [AI] 공고 내용에서 기준 추천), the headings of AI sections ([AI] 공고 초안, [AI] 추천 기준, [AI] 적합도 on job detail, [AI] 적합도 구성), the Fit column and Fit blocks ([AI] Fit), the AI notice, AI box labels and the match panel chip.
- **AiBox ("AI 분석" / "AI 생성"):** AI-made content sits in a blue-soft box with a blue border and its pill label; what people typed stays in white cards. AI 분석 (the AI read or scored): the analysed CV (view mode, while the version is the AI's; a version the seeker edited — method 직접 수정 — is their own content and stays a white card), the CV self-check, skill gaps, the match section on job detail, an applicant's per-criterion evaluation, and the label over criterion score rings on job detail. AI 생성 (the AI wrote): roadmap steps, interview questions, the JD draft, criteria suggestions.
- **AiBusy (AI at work):** the small "AI" pill, then a blue spark that pulses and turns, then the text in AI blue breathing (opacity) — for every AI wait: CV processing, the 추천 공고 and 인재 추천 "분석 중" lines, "분석 중" in the applicant table and detail, a pending match on job detail, and the JD draft, criteria suggestion, self-check, roadmap and interview-question loading. Still under `prefers-reduced-motion`. This is the only place the spark remains.
- **Score rings and the match panel stay mint** (they show the result, and mint keeps the seeker pages from turning blue); the panel's "AI 적합도" pill and the [AI] before 적합도 구성 say the score is AI-made.

### Icons
In-house line icons on a 24 px grid, 1.75 stroke, round caps and joins, `currentColor`, rendered at 15–24 px (`components/common/icons.tsx`).

## Motion

Transform, opacity and colour only, on `cubic-bezier(0.2, 0, 0, 1)`; feedback 150 ms, state 160–260 ms, entrances under 400 ms; fill mode `backwards`. A new route's page rises 8 px (260 ms, once per path). Lists stagger 25 ms per item, capped at 100 ms. Tabs and the rail's current fill fade (200–220 ms). Buttons press to .95, cards and rows to .995. Skeletons shimmer only while loading. Under `prefers-reduced-motion: reduce` every animation and transition in the shell is off.

## Do's and Don'ts

**Do**
- Read colors, radii and spacing from the `--ds-*` tokens.
- Keep one mint primary action per view, with ink text.
- Show seekers scores only as decided in D42/D43 — match panel, breakdown and per-criterion rings — always with the AI notice and the score note.
- Keep secondary text at muted or darker; on the dark gradient at 66% white or more.

**Don't**
- Don't change a `--color-*` or `--radius-*` token, `global.css` or `pages/public/Home*`: the landing depends on them.
- Don't bring back per-role colors (navy / green) on app pages.
- Don't show weights, a criterion's reason or evidence, or any score for a job the seeker applied to.
- Don't use amber for anything but a missing skill, or red for anything but an error.
- Don't add a fourth font weight or a second typeface.

## Landing page (legacy system)

The landing (`/`, `pages/public/Home.tsx` + `Home.module.css`) is outside this redesign and unchanged. It keeps the "Dual-Trail Outcome Flow" system confirmed on 2026-10-16:

- **Tokens:** the `--color-*`, `--radius-*` and `--shadow-card` variables in `tokens.css` and the body defaults in `global.css` (canvas `#f5f5f7` ground, Pretendard, `min-width: 1280px`). Their values are frozen.
- **Concept "One Spine, Two Fields":** a deep navy seeker field (`#102c54`), an off-white spine carrying the company's criteria on a 2 px axis, and a deep green employer field (`#0d4a3e`), in a `1fr / 324px / 1fr` grid with fixed zones 256 / 68 / (20 + 360) so rows align across columns.
- **Rules that hold there:** navy means seekers and green means employers; amber only for a missing skill; Pretendard at 400 and 600 only; one shadow, only for white cards on the dark fields; the seeker card shows the band pill, score-worded labels (점수 반영, D42) and gaps, but no score figure.
- **Signatures:** field expansion on hover (1.12fr / .88fr, 400 ms) and the criterion trail that lights one criterion across all three columns (220 ms).

Changing the landing is a separate decision; until then, treat this section as a description, not a pattern for new screens.
