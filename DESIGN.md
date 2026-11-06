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
  job-card-title: { fontSize: "20px", fontWeight: 700, letterSpacing: "-0.02em" }
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
| Job card title | 20 / 700 | Job card titles |
| Card title | 18 / 700 | Offer titles, job rows in lists |
| Heading | 18 / 700 | Panel titles, aside titles, section heads, record-row titles |

Prose paragraphs (`<p>` on app pages) use `text-wrap: pretty`, so a wrapped line never leaves one word alone on the last line; controls, chips, labels, table cells and inputs are never paragraphs and keep their own wrapping.

Heading levels follow the page, never the look: one h1 per page (a tab page's is for assistive tech only), its sections h2, their parts h3. On job detail the JD's own section heads (주요 업무, 자격 요건 …) and 기업 소개 are h2 at 18/700, 인재상 and 진행 중인 프로젝트 h3 at 14/700; on 내 이력서 the CV's sections (기술, 경력 …) are h2 beside 이력서 점검, whose 강점 / 보완할 점 are h3.

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
  - Pages without a tab of their own belong to a group: 공고 상세, 기업 정보 and (seekers) 취업 준비 to 채용. 기업 정보's back link goes to the page that opened it when that page said so in the link (기업 프로필 → "← 기업 프로필"; only targets the page knows, never a path from the state), otherwise to 공고 목록.
- **Header** (72 px, not sticky): section name (24/700), a chevron, then the group's pages as segmented pill tabs (38 px, 15/700; current tab ink with white text; counts as ink pills, inverted on the current tab). Single-page groups show the name only. On the right, the name (14/700) over the email or company name (12.5 muted) and a 34 px initial avatar on accent-soft.
- **Content panel:** gray, 24 px radius, 24 px from the right and bottom edges, at least the viewport height minus the header. Pages inside use the whole panel width with 20 px padding, the same on every page; only long text (JD, messages) keeps a reading measure.
- **No repeated page title:** the header already names the group and the current tab, so a tab page's H1 stays for assistive tech only (`PageHead tabTitle`) and the page starts with its content; a description line stays only where it says something the user needs. Pages whose subject is their title (job detail, a company job, 취업 준비, a company profile, 새 공고) keep a visible H1. Tab labels and titles use the same words (공고 목록, 내 이력서, 희망 조건 …).
- **Consent-withdrawn banner:** a mint-wash strip with an accent-soft border above the panel.
- **Skip link** (본문으로 건너뛰기, signed-in and guest shells): the first Tab stop, off screen until focused, then an ink pill with white 14/700 text and the focus ring at the top left, over the rail. It moves focus to `<main id="main-content">` itself (no `#hash`, which the router would treat as a navigation) and leaves the scroll position alone. `<main>` takes focus without a ring: it is a region, not a control.
- **Focus after navigation** (`components/layout/useRouteFocus`, in both shells and `PublicLayout`): when the pathname changes — not on the first load, not for a query-string change such as a search or a filter — focus moves to the new page's H1 (the visually hidden one on tab pages), so screen readers read the page name and the next Tab starts in the page. While the page is loading (a `Loading` skeleton, `data-loading`) or has no H1, focus goes to `<main>` and moves on to the H1 when it appears, unless the user has moved focus; it stops following on the next key or pointer press, or after 10 s. The ring shows only when the navigation came from the keyboard (`:focus-visible`); scrolling is left alone. A title change is never announced and never moves focus.
- **Document titles** (`routes/title.ts`): "{page} – CareerSync" from each route's i18n key (`handle.title` in `routes/router.tsx`); pages with a subject put it first once it is loaded — "{job} – 공고 상세 / 취업 준비 / 공고 수정 / 인재 추천", "{company} – 기업 정보", "{applicant} – 지원자 상세" for the open applicant on 지원자 순위 — and show the static title until then. The landing keeps "CareerSync".

**Guest shell:** a 64 px white header (logo, wordmark 20/700, 회원가입 quiet link, 로그인 ink pill) over the same panel.

**Auth pages** (`AuthFrame`): a sticky 64 px white header; below it a `5fr / 7fr` split with 16 px between — the dark gradient field (24 px radius, 40 px padding, 30/700 two-line title, numbered point chips for 회원가입 and the consent page; 로그인 serves both roles, so its field is the role-neutral hub instead — two translucent rows, 구직자 with a mint dot and 기업 with a white dot, and a note under them — content centred vertically) and the gray panel with the form card at the top centre. The field is sticky at the full viewport height under the header, so it keeps its rounded corners while a long form (회원가입) scrolls beside it.

**Detail layouts:** content plus a 360 px sticky aside (job detail), a 380 px sticky applicant detail (지원자 순위, see Applicant detail), a 320 px sticky preview (공고 편집).

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
White, 1 px line-strong border, 12 px radius, 40 px (auth 44 px); hover border muted; focus border focus-green plus the mint halo; invalid border danger-line with a danger-soft halo. On the auth pages the border belongs to the wrapper, and the input inside follows its inner radius, so no fill can cover the rounded border. Browser autofill keeps the white field and ink text (an inset white shadow over the browser's blue), so a password field with its eye button still reads as one field. Selects carry an ink chevron. The job search field is a pill with a leading icon. Textareas that hold a CV description (edit mode) grow with their text (`field-sizing: content`, 76–480 px), so nothing is cut off; elsewhere textareas keep their rows and resize by hand.
- **Field errors** (공고 편집 fields): the label alone names the control (`aria-labelledby`); the error, or else the hint, describes it (`aria-describedby`), and a field with an error is `aria-invalid`, so the error is read with the field without being repeated in its name.
- **Read-only** (`readonly` inputs and textareas, disabled selects: a published or closed job's locked fields, the CV's company name taken from the PDF): sunken fill, line border, ink-2 text and a muted padlock (the icon set's lock, 15 px) where a select's chevron sits (top right in a textarea); no hover, no caret, no date picker, spinner or resize, and no placeholder (an empty locked field shows nothing rather than an instruction it cannot follow). Still focusable: keyboard focus shows the outline, never the editing halo. Fields that can still change stay white, so on a published job 마감일, 근무지, 급여 안내 and the weights stand out.
- **Checkboxes and radios** (`styles/app.css`, every app page): 20 px, 6 px radius (radios round), line-strong border; checked = mint fill with an ink tick or dot; keyboard focus = focus border plus the halo. The 회원가입 role cards use the same mint radio mark.
- **Switch:** focus-green when on. A switch saves on its own and shows what is stored, never a pending value. The 인재 추천 opt-in (희망 조건) asks first when it is turned on: an inline confirm under the switch carries the 기업에게 보이는 것 / 보이지 않는 것 lists, with 공개하기 (secondary) and 취소; turning it off saves at once. Its own status line says 공개로 바꿨습니다 / 공개를 껐습니다. While its save runs it stays focusable (`aria-disabled`) and ignores presses. The preference lists keep their own 희망 조건 저장, and each save sends the other part as stored, so neither changes the other.

### Chips, tags, counts
- **Chips** (preferences, skills, techs): chip gray, 10 px radius, 15/500, round remove button.
- **Preference facts** (추천 공고, between the lead and the result): the label 희망 조건 (14/700 ink-2), then each preference as plain text — 14/500 ink with its 16 px muted line icon (location pin, clock for employment type, target for a role keyword), no fill and no height, 18 px apart like the job card's facts row — so they read as what the list was matched against, not as filter buttons. At most six before a white "+N" tool chip that shows the rest, then a white pencil tool chip that opens 희망 조건 (both 32 px, the only controls in the row); the job count sits on the right. They explain the list and never filter it (Pref is computed on the server, D15). With no preferences the row says so and what that does to the score ("정하지 않아 근무지·고용 형태·직무로 거르지 않고, 희망 조건 점수를 100으로 계산해 적합도에 반영했습니다. 희망 조건을 정하면 적합도가 낮아질 수 있습니다", D46) and the pencil tool chip reads 희망 조건 정하기. A failed preferences request leaves the row out.
- **Tags:** chip gray, 8 px radius, 12/500; tone tags on accent-soft with accent-text.
- **Status:** an 8 px dot before the label, which is always shown, so the dot never carries the meaning alone; the same tags on 지원 현황 and 지원자 순위. Solid means in progress or decided, hollow (a 1.5 px ring) means not started or paused: 검토 전 hollow in the disabled-text gray (`#8b9099`, so the ring stays visible); 서류 검토 and 면접 예정 solid ring mint; 보류 hollow muted; 합격 solid accent-text; 불합격 solid muted. Offers: pending ring mint, accepted accent-text, the rest line-strong. Jobs: published mint, draft line-strong.
- **Counts:** ink pills next to titles and on tabs.
- **Band pill** (where a band shows alone): 매우 적합 ink with a mint dot, 적합 accent-soft, 참고 outlined.

### Job card (`components/seeker/JobCard`)
추천 공고 only (공고 목록 uses Job rows). The reference's feed card, compact. White, 20 px radius; the whole card is the title link and its only link to the job (D45: no 상세 보기 link, no second tab stop for the same page, no mint button on the card); the focus ring goes round the card and hover lifts it to the pop shadow. Left: the 48 px job icon tile (see Job icon), the 20/700 title and the company in muted; one row of facts with line icons (location, employment type, experience, deadline); then, under a hairline, the match reasons with the card's own actions at the end of the same line (준비하기 as a small secondary pill, raised above the card link; its accessible name is "{job title} 준비하기" so the links in a list are told apart, the visible label staying 준비하기). Right, only with a valid match score: a 168 px column on the same white behind a hairline that stops 16 px short of the card's edges, with the match summary centred in it. Cards stack 10 px apart and stagger in. On 추천 공고 the criteria count and the experience come from one shared `GET /api/jobs` request matched by job id (the recommendation response has neither); a job it does not return only loses those two facts.
- **Match summary** (lists): the match score on white — 34/500 ink with a half-size "점" (87점; in a job row 20/700 with a 12 px 점 and the pill beside it) — and the band pill under it. Never "%": the score is not a probability (D47). Screen readers hear 적합도 87점; the visible number is hidden from them. No ring and no dark panel. Below 40, or with an unknown band, the number stands alone.
- **Match reasons** (추천 공고 cards): what the score is made of, as one line with no boxes or fills — 평가 기준 N개 (12/700 muted; "평가 기준" when the count is not known; the same term as on job rows and job detail), then each category the job's criteria use with its score (the plain mean the API sends, no weights): a 13/500 ink-2 label, a 40 × 4 px meter in ring mint on the line track, the number 13/700; then, past a 1 px line-strong divider, 희망 조건 with its meter and number — or, per D46, a muted chip-gray pill **미설정** when the preferences API confirms none is set, **확인 불가** when that request failed, and a meter-shaped skeleton while it loads (never a bare 100). Missing parts are left out. Never per-criterion scores, weights, reasons or evidence (D42).

### Job rows (`components/seeker/JobRow`)
공고 목록 is for browsing many jobs, so it is a record list, not cards: one white list, rows split by hairlines, 16 px vertical padding (about 76 px a row). Left: the 40 px job icon tile, the 18/700 title on one line (ellipsis) and the meta line (the company in ink, then location · employment type · experience). Right, in fixed columns so they line up from row to row: for a seeker the match summary (row size) where an evaluation already exists (D43, empty elsewhere; the column appears only when some listed job has a score), 평가 기준 N개 (13 muted), the deadline (D-n bold, 상시 채용 muted) and the row chevron. The title link is stretched over the row and is its only tab stop; the focus ring goes round the row. Guests and companies see no score column. What a score is made of stays on 추천 공고 and job detail. Above the rows, under the score note, a seeker whose preferences API confirms none is set gets the same 미설정 note as job detail, once for the list (the preference score was counted as 100 and went into 적합도; setting preferences can lower it; 희망 조건 정하기 link); the preferences are asked for once, the first time scores show, and loading or a failed request shows no note.

### Match panel and score rings (`components/seeker/Match`)
What seekers see of a match ([docs/DECISIONS.md](docs/DECISIONS.md) D42, D43). On lists the score is the light match summary (see Job card and Job rows); the dark panel, the rings and the breakdown are for job detail.
- **Match panel** (job detail): the dark gradient, 20 px radius, centred with tight spacing: a 92 px ring (84 px compact) with the match score inside (30/500 plus a half-size "점", D47; read as 적합도 87점), the band under it (16/700). Below 40 the number stands alone, without a band.
- **Breakdown ("적합도 구성", job detail):** a blue AI spark and title, then two columns of 44 px rows, each a light ring with its label beside it — one per criterion category the job uses (plain mean, no weights), then 희망 조건 (the preference score). The 희망 조건 ring follows D46 like the card strip: the 미설정 / 확인 불가 pill in its place, at least a ring wide and centred in it, a 44 px skeleton circle while the preferences load; job detail asks for them only when it shows a score. With 미설정, a note under the rows (12.5 ink-2, 72ch) says the preference score was counted as 100 and went into 적합도, and that setting preferences can lower it, followed by an underlined accent-text 희망 조건 정하기 link.
- **Score guide ("점수 보는 법", `ScoreGuide`):** under the score note wherever scores are listed or shown (추천 공고, 공고 목록 with scores, the job detail 적합도 box), a native disclosure, closed by default: a 12.5/700 accent-text underlined toggle with a 14 px chevron that turns when open, then a short list (13, ink-2, 72ch): what 적합도 is, the band thresholds (매우 적합 80~100 · 적합 60~79 · 참고 40~59, below 40 the number alone; read from one frontend constant kept equal to the backend config by a test, D16), category scores as the plain unweighted mean and why they do not add up to the match score, the preference score (the D15 fields; none set counts as 100 and shows 미설정), and what stays private (weights, per-criterion evidence). It explains how scores work in general, never one particular number.
- **No score on job detail:** the reason when the page knows it — AI consent withdrawn, no CV, an unconfirmed newest CV (with a 내 이력서로 가기 link kept on one line; for the first two the apply panel below already offers the fix as its main button), applied (no score, D43) — otherwise "not analyzed yet", or, when the CV could not be read, what a score needs (a confirmed CV, AI consent, a finished analysis).
- **Missing data:** every score display checks what the API sent. A missing or invalid match score hides the panel or the summary (a card falls back to the plain card, a row leaves its score cell empty); missing categories, preference score or criterion scores hide only those rings; an unknown band hides the band. Nothing about a score can break the page.
- **Per-criterion rings:** 44 px rings at the end of each criterion row on job detail.
- **Ring:** the arc is the score out of 100 in ring mint on a line-gray track (14% white on the dark panel), round caps, starting at 12 o'clock. The number is visible text; the SVG is hidden from assistive tech. Only the large ring shows a unit, its half-size "점" (D47); the 44 px rings show the number alone (a half-size "%" there would be 6 px) and keep the "%" for screen readers.
- **Next to every score:** the AI notice and the note "점수는 합격 가능성을 뜻하지 않습니다. 기업이 정한 가중치는 공개되지 않습니다.", with the score guide under it. Above a list (추천 공고, 공고 목록) both read as one caption — the AI pill, then the notice and the note at 12.5 ink-2, wrapping naturally when narrow; in the job detail 적합도 box they stay two lines.
- Companies keep exact Fit numbers (one decimal) and indicator squares; rings are a seeker-side display. Squares (10 px, 3 px radius): 75 and over filled accent-text, 25–74 accent-soft with an accent-text edge, under 25 empty with a disabled-text gray edge (`#8b9099`) — never amber, which stays for a missing skill or certificate (the 취업 준비 gap rows).

### Job icon (`components/common/jobIcon.ts`, `JobIconTile`)
An illustrative icon for the job's type where the reference shows company logos — on job cards (48 px), next to the job detail title (60 px) and at the start of job rows in lists — 지원 현황 and 공고 관리 (40 px; a closed job's tile turns sunken gray with a muted icon). It is not a company logo. Every group uses the same tile: a rounded square on accent-wash with the line icon in accent-text, so cards stay uniform. Jobs have no category field yet, so the title decides (the helper takes a category first once one exists). Groups are checked in this order and the first match wins; Korean keywords match anywhere, Latin ones only as whole words ("ai" does not match "maintain", "pm" not "npm").

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
- **Panel (`ui.panel`):** white card, 20 px padding, no border. Inside, sections split by hairlines — never a box inside a box. A panel head whose content has not appeared yet (이력서 점검 before it runs) drops its hairline (`ui.panelHeadAlone`, opt-in).
- **Record list:** one white card, rows split by hairlines; whole-row links with secondary actions raised above.
- **Read-only list rows:** 42 px, hairline between rows.
- **Tables** (지원자 순위): inside a panel; header 12/700 muted, every header cell on the bottom line; rows split by hairlines; hover sunken; the selected row on accent-wash with a 3 px mint left edge; rank 1 on a mint tile.
  - **Columns** (fixed layout): rank 40 px, the applicant takes what is left and never less than 168 px, Fit 72 px; the criteria share the rest in equal columns of 40–96 px, so the table never grows past its panel or under the detail panel, with up to 10 criteria at 1280 px.
  - **Criterion headers:** a name never breaks inside a word (`word-break: keep-all`); the full name is the cell's title and its accessible label (with the weight), however it is cut on screen. Columns of 80 px or more show the name on up to two lines with the weight (regular) under it. Narrower columns turn the names 45° on one line (up to 128 px, then an ellipsis), running down into their column from the upper left — over the empty space above 지원자 and Fit, never past the last column — in a 136 px header with the weights level underneath; neighbours sit at least 28 px apart across the slant, so they never touch.
  - **Rows:** 12 px vertical padding; status and experience side by side when the applicant column has room, on two lines when not, never cut short (about 68 px and 86 px rows).
  - One row is always selected: rank 1, or the first visible row when filtered (focus does not move on load). On a focused row ↑/↓ move the selection and focus to the next row up or down and Enter or Space opens the detail (focus to its heading); a click selects without moving focus. Moving only changes the selection, never the ranking or its order. The table keeps native semantics (no grid role): a focused row is read by its name, which Chromium does not build from a table row's cells, so each row is named "{rank}위 {name}" and the selected one "선택됨, {rank}위 {name}"; `aria-selected` (grids only) is not used, and `data-selected` draws the selection.
- **Applicant detail** (지원자 순위): one white card in three parts. A strip at the top with the place in the visible list ("2 / 5", 13/500 muted) and quiet 32 px ↑/↓ buttons for the previous and next applicant (disabled at the ends; after a press focus stays on the button, or on the heading at an end, and the new name is announced). Then the body: the person (name, email cut with an ellipsis, whole in its title) and Fit ("기준 n개 중 m개 충족" on one line), the applied date and experience at full width under them, then 기준별 평가 with the evidence. Then the status in a footer under a hairline: 지원 상태 with the current status tag, and two labelled rows of 32 px options — 진행 (검토 전 · 서류 검토 · 면접 예정) and 결정 (보류 · 합격 · 불합격); the current one is ink. 합격 and 불합격 ask first in an inline confirm in the footer ("불합격으로 바꿀까요?", what the seeker will see, a secondary 불합격으로 바꾸기 and 취소; Esc or 취소 returns focus to the option); every other status applies at once. After any change a neutral line (ink-2, no check) says ‘불합격’ 상태로 바꿨습니다 with a quiet underlined 되돌리기 that sets the previous status in one click, without a second confirm. Undo lasts until the next change or another applicant opens; nothing reverts on a timer, because only a recruiter's click changes a status (AI rule 5). Esc elsewhere in the detail returns focus to the selected row.
  - **Scrolling:** the page is the only scroll container — the card keeps its natural height, with no overflow of its own. It is CSS sticky at the top while it fits the window; a taller card moves its sticky top with the scroll (one update per frame, only while it is taller than the window), down until its bottom is in view and up until its top is, so all the evidence is read with the page scroll and the card never leaves the window. The top strip sticks to the top of the window (white, a hairline under it) and, once the heading has scrolled away, adds the applicant's name (13/700); the status footer sticks to the bottom of the window (white, hairline, a soft upward shadow `0 -8px 24px rgb(16 24 40 / .06)`) while the card runs past it. Choosing another applicant starts the card at its top; at the very end of a long table the card cannot rise above the table's bottom, and the strip's name keeps it identified.

### Tabs inside pages
The header's segmented pills at 40 px: current tab ink with white text, hover chip gray.

### States
- **Loading:** chip-gray skeleton bars with a shimmer, inside the card they replace.
- **Empty / blocked:** centred in a card — a 56 px accent-wash icon circle (inbox for empty, info for a missing precondition), an 18/700 title, a muted body and at most one action (blocked: the primary button that resolves it).
- **Failed request:** the same with a danger-soft circle and alert icon, the message in ink-2, and 다시 시도 as a small secondary button.
- **Not found:** the gray ground with one centred card and 홈으로 가기.
- **Render error** (`RouteError`, the routes' `errorElement`): the failed state with "화면을 표시하지 못했습니다", 다시 시도 (reload) and 홈으로 가기 — inside the content panel when a page fails (rail and header stay), on the gray ground when the shell or an auth page fails. The landing route has none.
- **Inline confirms** replace their trigger inside the card, set off by a hairline, and take focus.
- **Job editor confirms** (공고 편집, the sticky action bar): 마감하기 and 삭제 confirm on one line in the pill bar. 게시하기 and saving changed weights need more lines, so the bar turns into a 16 px-radius card (20 × 16 px padding) holding a 16/700 title, body text at 14 ink-2 (72ch), and 취소 (quiet) then the action (primary) on the right; it takes focus, and Esc or 취소 closes it and returns focus to the button that opened it. **게시하기** first runs the save's own checks (title, criteria rows), then asks: what publishing does; a two-column list of what locks (공고 제목 · 고용 형태 · 최소 경력 · 공고 내용 · 평가 기준 추가·삭제와 기준 이름·분류·설명) and what stays editable (근무지 · 마감일 · 급여 안내 · 기준별 가중치), using the form's own labels and matching backend `EDITABLE_AFTER_PUBLISH` and the criteria lock; that it cannot be undone (no unpublish, no delete, only 마감, and a closed job is never published again); and, with unsaved changes, that they are saved with it. **Changed weights** on a published job (compared by criterion id, so order never counts): Fit is computed from the stored criterion scores and the current weights when it is read, so saving re-ranks analyzed applicants at once and changes seekers' match scores while the criterion scores stay. While a weight differs from its saved value, a notice with an accent-text alert icon sits under the criteria lead (in a status region, so it is announced), and 저장 asks 바꾼 가중치를 저장할까요? with 변경 저장; cancelling keeps the edited weights. The editor reads the job's applicant list once: with n analyzed applicants the text names n; when that request confirms none there is no notice and no confirm; while it loads or after it fails the text is a condition ("분석이 끝난 지원자가 있다면…") and the confirm still applies — a failure is never read as zero. Weights set back to their saved values remove both. **After 게시하기:** on success the button is gone, so focus moves to the success message in the bar (`tabIndex=-1`, no scroll), which is then not a live region, so it is read once, by focus; the next Tab reaches 지원자 순위로. Every other notice in the bar stays a status region. On failure focus never drops to the page: it stays where the error handling put it (the empty 공고 내용), else goes to the first field marked invalid, else to 게시하기, back and enabled, with the error in its alert. The new-job flow (publish after the first save, on the job's own page) ends the same way.
- **Drop area** (내 이력서, no CV yet): the dashed upload card also takes a dropped PDF, with "또는 PDF 파일을 여기로 끌어다 놓으세요" under the button. While a file is over it the border turns solid focus-green on accent-wash and the title reads 놓으면 바로 올립니다. One PDF uploads through the same path as the picker; a non-PDF shows the PDF error and more than one file "PDF 파일 하나만 놓아 주세요". Elsewhere on the page a dropped file is ignored instead of opening in the browser; with a CV on the page nothing takes a drop, and replacing it stays the 새 PDF 올리기 button.

### Notices
- **AI notice** (AI rule 6): the blue "AI" pill with the spark, the server's notice at 12.5 ink-2, the method in muted on the right. Inside an AI box the pill is left out (the box label marks it). Never hidden, one per AI result.
- **Other notices:** a caption with an accent-text info icon.
- **Guest banner** (공고 목록): the match gradient with the mint 가입 action.

### AI markers (`components/common/Ai.tsx`)
Blue shows where AI is used — for users and for transparency about AI use (docs/DECISIONS.md Q29). An AI feature is one whose response carries `AI_NOTICE` (CLAUDE.md AI rule 6), in LLM or rules mode. Nothing else gets a marker, and blue is never decoration.

- **Colours:** `--ds-ai` `#2563eb` (the AI pill fill, white text 5.2:1; the working spark), `--ds-ai-text` `#1d4ed8` (AI text, 6.7:1 on white, 6.1:1 on ai-soft), `--ds-ai-soft` `#eef4ff` and `--ds-ai-line` `#c7d7fe` (AI box). The gradient token starts at the logo's own blue `#3b82f6`; that blue is never used for text (3.7:1).
- **The marker is one "AI" pill** (`AiMark`): white "AI" on AI blue, 18 px tall, 11/700, pill radius (15 px / 9.5 px for the small size next to Fit and in the working state). It is its own element placed directly before the feature's name — never written into the text — so labels stay translatable and screen readers read "AI 추천 공고". It looks the same on white and on a black selected tab. Labels that name AI themselves use the same pill with their wording: "AI 분석", "AI 생성". Strings shown beside a pill do not repeat "AI" (초안 쓰기, 공고 초안, 분석 중).
- **Rail:** labels stay as they are (never "AI 채용"). A group that contains at least one AI feature — on a tab or inside a page — gets a small "AI" badge on the top-right corner of its icon, ringed in white; screen readers hear it after the label, separated by a comma ("채용, AI 기능이 있는 메뉴"), so the two never read as one phrase. Seekers: 채용 (추천 공고, scores, 취업 준비) and 이력서 (CV analysis, self-check). Companies: 채용 (지원자 순위, 인재 추천, the AI JD draft, criteria suggestions). Groups without any AI feature — seeker 프로필, company 기업 — get nothing. The pending-offer count moves to the icon's top-left so the two never overlap. The rail badge says "this section has AI"; the pills on tabs say exactly which pages.
- **Where the pill appears:** header tabs ([AI] 추천 공고, and [AI] 이력서 as the one-page section name), company job tabs ([AI] 지원자 순위, [AI] 인재 추천), 취업 준비 tabs ([AI] 부족한 기술·로드맵, [AI] 면접 예상 질문, [AI] 이력서 점검), buttons that open AI features ([AI] 초안 쓰기, [AI] 공고 내용에서 기준 추천), the headings of AI sections ([AI] 공고 초안, [AI] 추천 기준, [AI] 적합도 on job detail, [AI] 적합도 구성, [AI] 이력서 점검 on 내 이력서), the Fit column and Fit blocks ([AI] Fit), the AI notice and AI box labels. On job lists (추천 공고, 공고 목록) the AI notice at the top of the list is the one marker for every score in it; cards and rows carry no AI pill.
- **AiBox ("AI 분석" / "AI 생성"):** AI-made content sits in a blue-soft box with a blue border and its pill label; what people typed stays in white cards. AI 분석 (the AI read or scored): the analysed CV (view mode, while the version is the AI's; a version the seeker edited — method 직접 수정 — is their own content and stays a white card), the CV self-check, skill gaps, the match section on job detail, an applicant's per-criterion evaluation, and the label over criterion score rings on job detail (at the end of the 이 공고의 평가 기준 heading row, above the ring column). AI 생성 (the AI wrote): roadmap steps, interview questions, the JD draft, criteria suggestions.
- **AiBusy (AI at work):** the small "AI" pill, then a blue spark that pulses and turns, then the text in AI blue breathing (opacity) — for every AI wait: CV processing, the 추천 공고 and 인재 추천 "분석 중" lines, "분석 중" in the applicant table and detail, a pending match on job detail, and the JD draft, criteria suggestion, self-check, roadmap and interview-question loading. Still under `prefers-reduced-motion`. This is the only place the spark remains.
- **Score rings, meters and the match panel stay mint** (they show the result, and mint keeps the seeker pages from turning blue); on job detail the [AI] 적합도 heading and the [AI] before 적합도 구성 say the score is AI-made, on lists the AI notice above them does.

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
