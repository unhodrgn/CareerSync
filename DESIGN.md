---
name: CareerSync
description: 기업 맞춤형 AI 채용 매칭 플랫폼. One company criteria set, read by seekers on the navy side and employers on the green side.
colors:
  ink: "#1d1d1f"
  ink-soft: "#333333"
  ink-muted: "#6e6e73"
  paper: "#ffffff"
  canvas: "#f5f5f7"
  sunken: "#fafafc"
  line: "#e0e0e0"
  line-soft: "#f0f0f0"
  axis: "#d2d2d7"
  hub: "#1d1d1f"
  hub-text: "#cccccc"
  seeker: "#102c54"
  seeker-badge: "#1e467a"
  seeker-accent: "#93c5fd"
  seeker-dot: "#60a5fa"
  seeker-soft: "#e8f0ff"
  seeker-lit: "#eff6ff"
  seeker-lit-line: "#2563eb"
  employer: "#0d4a3e"
  employer-badge: "#146353"
  employer-accent: "#6ee7b7"
  employer-dot: "#34d399"
  employer-soft: "#e4f6ee"
  employer-tag-line: "#b7e4d4"
  gap: "#b45309"
  gap-strong: "#92400e"
  gap-line: "#d97706"
  gap-soft: "#fffbeb"
  gap-badge: "#fef3c7"
  danger: "#b42318"
  danger-soft: "#fef3f2"
  danger-line: "#f04438"
  logo-blue: "#3b82f6"
  logo-green: "#10b981"
typography:
  display:
    fontFamily: "'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', system-ui, sans-serif"
    fontSize: "40px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  field-title:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  form-title:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    letterSpacing: "-0.02em"
  title:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  lead:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.47
    letterSpacing: "-0.015em"
  body:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  input:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
  button:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  label:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  caption:
    fontFamily: "'Pretendard Variable', Pretendard, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  chip: "11px"
  hub: "12px"
  lg: "16px"
  card: "18px"
  pill: "999px"
spacing:
  zone-top: "256px"
  zone-trail: "68px"
  zone-gap: "20px"
  zone-card: "360px"
  spine-width: "324px"
  spine-pad: "16px"
  card-pad: "20px"
  page-gutter: "40px"
  row-gap: "8px"
  row-height: "44px"
  control-height: "44px"
  submit-height: "48px"
  form-card: "480px"
  form-card-pad: "36px 40px 32px"
  auth-field-pad: "56px 48px"
components:
  button-on-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.seeker}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: "12px 20px"
  button-on-field-hover:
    backgroundColor: "{colors.canvas}"
  button-ink:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-ink-hover:
    backgroundColor: "{colors.ink-soft}"
  outcome-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "{spacing.card-pad}"
    height: "{spacing.zone-card}"
  criterion-row:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "{spacing.row-height}"
  criterion-row-lit:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  seeker-row-lit:
    backgroundColor: "{colors.seeker-lit}"
  gap-row:
    backgroundColor: "{colors.gap-soft}"
    textColor: "{colors.gap-strong}"
    rounded: "{rounded.md}"
    height: "{spacing.row-height}"
  input-chip:
    backgroundColor: "rgb(255 255 255 / 0.08)"
    textColor: "{colors.paper}"
    rounded: "{rounded.chip}"
    padding: "8px 14px"
  band-pill:
    backgroundColor: "{colors.seeker}"
    textColor: "{colors.paper}"
    rounded: "{rounded.pill}"
    padding: "6px 14px"
  employer-tag:
    backgroundColor: "{colors.employer-soft}"
    textColor: "{colors.employer}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
  employer-tag-lit:
    backgroundColor: "{colors.employer}"
    textColor: "{colors.paper}"
  hub:
    backgroundColor: "{colors.hub}"
    textColor: "{colors.paper}"
    rounded: "{rounded.hub}"
    padding: "0 14px"
    height: "{spacing.zone-trail}"
  text-field:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.ink}"
    typography: "{typography.input}"
    rounded: "{rounded.md}"
    padding: "0 14px"
    height: "{spacing.control-height}"
  text-field-focus:
    backgroundColor: "{colors.paper}"
  text-field-invalid:
    backgroundColor: "{colors.paper}"
  field-error:
    textColor: "{colors.danger}"
    typography: "{typography.caption}"
  button-submit:
    backgroundColor: "{colors.seeker}"
    textColor: "{colors.paper}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    height: "{spacing.submit-height}"
  button-submit-employer:
    backgroundColor: "{colors.employer}"
  button-submit-hub:
    backgroundColor: "{colors.hub}"
  form-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "{spacing.form-card-pad}"
    width: "{spacing.form-card}"
  role-card:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chip}"
    padding: "12px 14px 12px 38px"
  role-card-seeker-checked:
    backgroundColor: "{colors.seeker-lit}"
    textColor: "{colors.seeker}"
  role-card-employer-checked:
    backgroundColor: "{colors.employer-soft}"
    textColor: "{colors.employer}"
  consent-group:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chip}"
  consent-body:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  draft-badge:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.pill}"
    padding: "1px 7px"
  form-alert-error:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  form-alert-notice:
    backgroundColor: "{colors.sunken}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  point-chip:
    backgroundColor: "rgb(255 255 255 / 0.08)"
    textColor: "{colors.paper}"
    rounded: "{rounded.chip}"
    padding: "14px 16px"
---

# Design System: CareerSync

## Overview

Binding visual reference: `EN V3 · Dual-Trail Outcome Flow (Off-White & Deep Rich Panels).html` (repo root), confirmed by Long 2026-10-16; it supersedes the earlier PNG and the first landing build.

**Creative North Star: "One Spine, Two Fields"**

CareerSync is drawn as three vertical fields: a deep navy field for job seekers, a deep green field for employers, and an off-white spine between them that carries the company's criteria on a 2px axis. Both outcomes hang off the spine at the same row heights, so the eye can follow one criterion straight across from a seeker's card, through the spine, to an employer's applicant list. The system's job is to make the product's mechanism (one criteria set read in two directions) visible as geometry.

The mood is calm, dense and exact, closer to an instrument panel than a marketing page. White cards sit on the dark fields with one soft shadow; on the light spine the same cards are flat, with only a 1px line around them. Pretendard does all the type work at two weights, regular (400) and semibold (600). Color is functional: navy marks seekers, green marks employers, and amber appears only when a skill is missing from a CV. The interactions keep that same geometry. Hovering a field widens it and dims the other, and a criterion lights its own row on every column at once.

The system is desktop-only and Korean-first. Body text breaks at word boundaries (`word-break: keep-all`), and every block is sized so its line breaks never change between states. The landing page and the auth pages (login, register, consent) exist in this system so far. The auth pages keep the world at a smaller scale: one audience field on the left and a white form card on the canvas on the right. App navigation is described under Navigation and the shared app-page patterns under App pages; tables have no established pattern yet.

**Key Characteristics:**
- Three aligned columns (`1fr / 324px / 1fr`) with fixed vertical zones 256 / 68 / (20 + 360).
- The audience's color sets each field: navy for seekers, green for employers. Amber is used only for absence.
- White 18px-radius cards; one ambient shadow, used only on the dark fields.
- Pretendard at 400 and 600 only; 40px headlines with tight negative tracking.
- Thin linework: 1px lines, 2px axis and wires, 8px end dots.
- Motion is state feedback: 400ms field expansion, 220ms criterion trail, .95 press.
- Forms take their accent from the page's `--tone` (navy, green or Hub Ink); errors are red, never amber.

## Colors

The palette is two saturated, dark audience fields on a cool off-white ground, plus a narrow amber reserved for absence.

### Primary
- **Deep Seeker Navy** (seeker): the seeker field background, the band pill, seeker wires and seeker-side emphasis text. Seeker Badge Navy (seeker-badge) fills icon tiles on the field. Sky Accent (seeker-accent) is for labels and links on navy, Signal Blue (seeker-dot) for dots, ticks and feed lines, Pale Seeker Wash (seeker-soft) for neutral seeker badges and text selection. Seeker Lit Wash and Lit Blue Line (seeker-lit, seeker-lit-line) mark the lit seeker row.

### Secondary
- **Deep Employer Green** (employer): the employer field background, applicant rank tile, indicator squares, employer wires and tags when lit. Employer Badge Green (employer-badge) fills icon tiles on the field. Mint Accent (employer-accent) is for labels on green, Signal Mint (employer-dot) for dots and ticks, Pale Employer Wash (employer-soft) with Mint Tag Line (employer-tag-line) for employer tags and the count/met badges.

### Tertiary
- **Missing-Skill Amber** (gap): the alert icon and badge text on a gap row. Burnt Amber (gap-strong) is the gap row's name text, Amber Line (gap-line) its dashed border, seeker wire and missing-square ring. Amber Wash (gap-soft) and Amber Badge (gap-badge) are the gap row and missing-square fills.

### Error
- **Form Error Red** (danger): field error text and icons, the form error alert's text. Error Line (danger-line) is the border of an invalid field, an invalid consent group and the error alert; Error Wash (danger-soft) is the error alert fill and the focus halo of an invalid field. Used only in forms.

### Neutral
- **Ink** (ink): primary text, the 로그인 button, the trust icon disc, and a lit criterion row. Hub Ink (hub) is the same near-black and fills the hub where both input trails meet, with Hub Caption Gray (hub-text) for its caption. Hub Ink is also the tone of pages that serve both sides (login, consent): their field, submit button and focus ring.
- **Soft Ink** (ink-soft): secondary strong text, card notes, tag labels, ink button hover.
- **Muted Gray** (ink-muted): meta lines, captions, footer. Chosen over the reference's #7A7A7A so 12–13px text passes 4.5:1.
- **Paper** (paper): card surfaces, text on dark fields, the on-field CTA.
- **Canvas** (canvas): page ground, header, spine, footer, CTA hover.
- **Sunken** (sunken): row fills inside cards.
- **Line / Soft Line** (line, line-soft): 1px card and row borders / internal dividers and neutral tags.
- **Axis Gray** (axis): the spine's 2px axis and the neutral row marks.

### Named Rules
**The Two Fields Rule.** Navy always means seekers and green always means employers, on fields, dots, wires, badges and focus rings. Never swap them and never use either as a neutral accent.

**The Amber Is Absence Rule.** Amber marks one thing only: a skill the CV lacks. It is not a warning, error or highlight color.

**The Bands Not Numbers Rule.** Seeker-facing surfaces never show numeric scores or "met" verdicts; seeker rows stay neutral and only the band pill and the amber gap carry meaning. Employer surfaces may show criteria met (기준 4개 중 N개 충족) and indicator squares.

**The Red Is For Errors Rule.** Form Error Red and its line and wash mark one thing only: input that cannot be submitted, or a request that failed. Never use amber for an error, and never use red for a missing skill.

**The Tone Rule.** A page sets `--tone` (with `--tone-soft`, `--tone-accent`, `--tone-dot`, `--tone-badge`) once, from its audience: seeker navy, employer green, or Hub Ink for a page that serves both sides. AuthFrame sets it per audience; the form controls read it for the focus border and halo, the caret, checkboxes, the 필수 tag, the submit fill and links. Controls never name navy or green themselves.

**The Logo Colors Stay In The Logo Rule.** Logo Blue and Logo Green (logo-blue, logo-green) appear only in the LogoMark: two 14px squares overlapping with `mix-blend-mode: screen` on an 8px-radius Ink tile. They are not UI colors.

## Typography

**Display Font:** Pretendard Variable (self-hosted woff2, OFL, weight range 45–920), falling back to Pretendard, -apple-system, Apple SD Gothic Neo, Malgun Gothic, system-ui
**Body Font:** the same family

**Character:** one neutral Korean-first grotesque at two weights, so emphasis comes from size, weight and tracking rather than a second typeface.

### Hierarchy
- **Display** (600, 40px, 1.2, -0.025em): field headlines, two lines set with `pre-line`, max 490px, at most 8 syllables per line.
- **Field Title** (600, 34px, 1.25, -0.025em): the two-line title on the auth field, set with `pre-line`.
- **Form Title** (600, 24px, -0.02em): the heading inside a form card, followed by a 14px/1.6 Muted Gray lead.
- **Title** (600, 18px, 1.3, -0.02em): card titles and the spine identity title. The wordmark uses 19px/600.
- **Lead** (400, 17px, 1.47, -0.015em): the sentence under a headline, capped at 19.5em so it breaks the same way at every field width; 80% white on fields.
- **Body** (400, 16px, 1.5): page default.
- **Input** (400, 15px): text typed into a field.
- **Button** (600, 15px): primary actions, the form submit and text links on fields.
- **Label** (600, 13px, -0.01em): role labels, input titles, criterion rows (13–14.5px across rows and list titles).
- **Caption** (400, 12px): meta, notes, hints, footers. Field errors use 12.5px/1.4. Small tags and badges use 11–12.5px at 600.

### Named Rules
**The Two Weights Rule.** Only 400 and 600. Hierarchy comes from size and tracking; never add a bold or light step.

**The Still Text Rule.** No text may change its line breaks between interaction states: cap measures (19.5em leads) and set one-line notes to nowrap with an ellipsis.

## Layout

The page is a header (64px, 40px gutters, bottom line), a full-height split stage, a trust bar and a footer (16px × 40px padding, both full width). The split is a three-column grid `minmax(0,1fr) 324px minmax(0,1fr)`. Every column stacks the same fixed zones: top 256px (role row, headline, lead, actions), trail 68px with 20px above and below (input chip, feed line, hub), and a 20px head plus a 360px card. Because the zones are fixed, rows align across the columns at every width and in every state. Fields pad 40px vertically, 48px on the outer edge and 32px toward the spine; the spine pads 16px and cards pad 20px. Inside cards the rows are 44px tall with an 8px gap.

The auth pages use the same header (64px, 40px gutters), then a two-column split `minmax(0,5fr) minmax(0,7fr)`: the audience field on the left (56px × 48px padding, content sticky at 56px, max 440px) and the canvas on the right (56px top, 48px sides, 64px bottom), with a 480px form card at the top centre. Inside the card the form stacks with an 18px gap; within a field, label, control, error and hint sit 6px apart.

Desktop web only: body `min-width: 1280px`, verified from 1280 to 1600px, with no breakpoints.

### Named Rules
**The Shared Rows Rule.** Anything that must be compared across columns sits in the same fixed zone at the same height. Wires are sized to span exactly card padding + spine padding + 1px border.

## Elevation & Depth

Depth is mostly tonal: dark fields, a light spine, white cards. There is a single ambient shadow, and it is used only where a white card sits on a dark field. On the canvas, cards are flat and outlined with a 1px line. Rings drawn with `box-shadow` (a paper gap, then a colored ring) mark state, not elevation.

### Shadow Vocabulary
- **Card on field** (`box-shadow: 3px 5px 30px 0 rgb(0 0 0 / 0.22)`): outcome cards on the navy and green fields only.
- **Pinned ring** (`0 0 0 2px #fff, 0 0 0 4px` ink): a pinned criterion row.
- **Lit square ring** (`0 0 0 2px #fff, 0 0 0 3.5px` employer or gap-line): the lit criterion's applicant square.
- **Gap glow** (`0 0 0 3px rgb(217 119 6 / 0.2)`): a lit gap row.
- **Focus halo** (`0 0 0 3px` tone-soft, or Error Wash when invalid): a focused text field.
- **Chosen role ring** (`inset 0 0 0 1px` role color): the checked role card, doubling its 1px border.

### Named Rules
**The One Shadow Rule.** One soft shadow, only for white on dark. Surfaces on the canvas stay flat and use a line. This includes the form card.

## Shapes

Corners scale with the size of the element: 4px for tiny tags, 6px for employer tags, 8px for buttons, rows and icon tiles, 11px for input chips and applicant rows, 12px for the hub, 16px for the spine identity card, 18px for outcome cards, and full pills for the band, count badges and the example tag. Dots are 8px circles (6px for neutral row marks), and indicator squares are 10px with a 2px radius. Lines are 1px everywhere except the axis, wires, ticks and feed lines, which are 2px. A dashed border is used only on the gap row. Forms follow the same scale: 8px for text fields, the submit button, alerts and consent texts; 11px for role cards, the consent group and the auth field's point chips; 18px for the form card; pills for the 초안 badge and the consent version. Role cards carry a 14px radio ring, and checkboxes are 18px native boxes tinted with the tone.

## Components

### Buttons
Solid, compact and quiet, with press feedback only.
- **Shape:** 8px radius.
- **On-field primary:** Paper fill, text in the field's own color, 15px/600, 12px × 20px, trailing arrow icon; hover goes to Canvas.
- **Ink:** Ink fill, Paper text, 14px/600, 8px × 16px (the header 로그인); hover goes to Soft Ink.
- **Text link on field:** 15px, accent color, underlined at a 4px offset; hover goes to Paper.
- **Submit:** full card width, 48px tall, tone fill, Paper text at 15px/600; hover brightens it (`brightness(1.12)`), press scales to .98, and while busy it is disabled with a 16px spinning ring before the busy label.
- **Header link:** the auth header's page link (로그인, 회원가입, 다른 계정으로 로그인) is the Ink button.
- **Quiet in-field buttons:** the password reveal (40 × 36px, 18px eye icon) and the consent disclosure (12.5px, chevron that turns 180°) are Muted Gray with no fill; hover goes to Ink text on Soft Line.
- **Press:** `scale(.95)` over 150ms with the system ease.
- **Focus:** 2px outline at a 3px offset, in Paper inside fields, in the audience color inside cards, and Seeker Navy elsewhere.

### Chips
- **Input chip:** 11px radius, white 8% fill, 20% white border, 32px icon tile in the badge color. When its field is active it lights to 14% fill and an accent border (220ms).
- **Band pill:** Seeker Navy, Paper text, Signal Blue dot, pill shape, 6px × 14px.
- **Point chip:** on the auth field, 11px radius, white 8% fill, 20% white border, 14px × 16px, 15px text at 88% white, led by a 24px number tile in the tone's badge color and accent. Hub pages use the same chip at 6% fill and 16% border, led by a seeker or employer dot.
- **Badges and tags:** pill or 4px radius at 11–12px/600. Neutral ones use Soft Line with Soft Ink text, seeker ones Pale Seeker Wash with Navy text, employer ones Pale Employer Wash with Green text.

### Cards / Containers
- **Corner Style:** 18px (outcome cards and rubric), 16px (identity card).
- **Background:** Paper.
- **Shadow Strategy:** the field shadow on dark fields only (see Elevation).
- **Border:** a 1px line, with 1px soft-line dividers under the head and above the foot.
- **Internal Padding:** 20px. Fixed height 360px, with head, rows and foot spread by `space-between`.
- **Form card:** 480px wide, Paper, 1px line, 18px radius, 36px × 40px × 32px padding, on the canvas. A switch line (13.5px Muted Gray, centred, with a tone link) closes it above a soft-line divider.

### Inputs / Fields
Quiet at rest, tone-colored when in use, red only when wrong.
- **Style:** 13px/600 Ink label above a 44px control on the Sunken fill, 1px line, 8px radius; 15px input text with 14px side padding. Hover darkens the border to Axis Gray.
- **Focus:** the border turns to the tone, the fill to Paper, and a 3px tone-soft halo appears (160ms, system ease). The caret takes the tone.
- **Error:** the border turns to Error Line and the fill to Paper (Error Wash halo when focused); below it a 12.5px Form Error Red line led by a 14px alert icon, linked by `aria-describedby`. A link inside an error (e.g. to login) inherits the red at 600.
- **Hint:** 12px Muted Gray, after the error.
- **Password:** the same field with a reveal toggle inside the control (`aria-pressed`, eye / eye-off).
- **Form alert:** a whole-form message, 8px radius, 12px × 14px, 13.5px/1.5 with a 16px leading icon. Error: Error Wash, Error Line border, Form Error Red text (`role=alert`). Notice: Sunken fill, 1px line, Soft Ink text, info icon (`role=status`).

### Role Switch
Two radio cards side by side (10px gap), each in its own audience color: the seeker card in navy, the employer card in green, whatever the page's tone is. At rest Sunken with a 1px line and an empty Axis ring; checked, the card takes its role wash (Seeker Lit Wash or Pale Employer Wash), a 2px role-colored edge, a filled radio dot and a role-colored 15px/600 name over a 12.5px Muted Gray description. Keyboard focus draws a 2px outline in the role color. Changes run 200ms.

### Consent Group
A Paper fieldset with a 1px line and 11px radius. 모두 동의 (600) sits on top above a soft-line divider; the required items follow, each with a 필수 tag (12px/600, tone) and a quiet 내용 보기 disclosure. The disclosure opens the text inline, indented under its checkbox, on a Sunken 8px panel led by a 초안 pill badge and note while the wording is a draft; the text is 13px/1.65 Soft Ink with `pre-line`. When a required item is missing, the group border turns to Error Line and the error line sits inside the group. A consent version, where shown, is a tabular-numeral pill on the canvas.

### Navigation
The landing header (logo, tagline, ink button) is the base. The auth pages reuse it with the Ink button as the link to the other auth page.

**App top bar.** Signed-in pages use the same 64px header on the canvas (40px gutters, sticky, 1px bottom line); the shell sets `--tone` once from the role (navy for seekers, green for companies).
- **Left:** LogoMark and wordmark (to the role's home), then the role's pages as text links: seekers 추천 공고 · 공고 목록 · 내 이력서 · 지원 현황 · 받은 제안; companies 공고 관리 · 보낸 제안 · 기업 프로필. At most five; settings-like pages do not go in the bar.
- **Links:** 14px/600 Muted Gray, hover Ink; the current page takes the tone with a 2px tone underline on the header line. A count (pending offers) is a small tone pill after the label, read out as text.
- **Right: the account menu.** The user's display name as a quiet trigger (28px tone-soft initial tile, 13.5px/600 Soft Ink name, chevron), Line Soft fill on hover and while open, the name in the tone while one of its pages is open. It opens a 240px Paper panel below, flat with a 1px line and 12px radius (it sits on the canvas: no shadow): who is signed in (name, email; a company account also shows its company), then the settings-like pages (seekers: 희망 조건, 내 정보) and 로그아웃 as 36px rows. It is a disclosure, not an ARIA menu: Tab walks its rows, Escape or a click outside closes it and returns focus, tabbing out closes it.
- **No role label** (● 구직자 계정) and no ink button in the signed-in bar: the darkest element on a page is the page's own primary action.
- **Guests** keep the landing header: tagline, 회원가입 as a quiet link, 로그인 as the Ink button.
- **Under the bar,** a page-wide line on Paper carries a state that changes what the user can do everywhere (AI consent withdrawn, with 다시 동의하기).

### Criterion Trail (signature)
One criterion lights the same item across all three columns. The seeker row goes to Seeker Lit Wash with a Lit Blue Line border (gap rows keep amber and gain the gap glow), the spine row turns Ink with Paper text, the employer tag fills green and lifts 1px, and each applicant's square gets a ring. Everything else in the trail dims to .38 opacity. Hover or focus previews, a click pins (`aria-pressed`, pinned ring), and a second click or Escape unpins. Transitions run 220ms on the system ease. Each spine row has 2px wires to both cards that end in 8px dots: navy on the left, green on the right, amber on the left for a gap.

### Field Expansion (signature)
Hovering a field, or `:focus-visible` inside it, widens it to 1.12fr while the spine stays at 324px and the other field drops to .88fr. The other field also dims (opacity .72, saturate .75, brightness .94) and the active field's input chip lights. The expansion runs 400ms on `cubic-bezier(0.2, 0, 0, 1)` after an 80ms delay, and collapses immediately. The pointer wins over focus left in the other field. Under `prefers-reduced-motion` there is no expansion, but the dimming still applies.

### Auth Frame (signature)
The landing's fields reduced to one: the audience field fills the left 5fr of the page in the tone's color, with a two-line 34px Field Title and three numbered point chips naming what that side gets; the form card sits on the canvas in the right 7fr. Register follows the role switch, so choosing 기업 recolors the field from navy to green over 400ms on the system ease (instant under reduced motion). Login and consent serve both sides, so they use Hub Ink with a seeker-dot row, an employer-dot row and a 13px note at 62% white. Inside the field, focus outlines are Paper.

### App pages (shared patterns)
- **One H1 per page.** The title, with a count next to it when the page lists things. Panels below never repeat it. When the page's subject is its own title (a job), the page head is only the back link.
- **One filled button per page:** the page's primary action. Everything else is secondary, quiet or a text link.
- **No box inside a box.** Inside a panel, sections are split by 1px Line Soft rules or columns, never by nested panels or tiles.
- **Lists of records** (recommended jobs, past offers, criteria, interview questions) are one bordered Paper list with rows split by Line Soft.
  - Rows that open something are whole-row links, with a secondary link raised above the row's hit area.
  - Read-only rows have no box and no dot.
- **AI notice** (AI rule 6). A caption line right by the AI result: Ink "AI" badge (11px/600), the server's notice text at 12.5px Soft Ink, and the method in Muted Gray on the right. No box. Never collapsed or hidden, one per AI result.
- **Other notices** (status, guidance) are a caption with an info icon in the tone, so they never read as the AI notice.
- **Inline confirms** replace their trigger inside the panel or card, set off by a Line Soft rule.
  - Focus moves into the confirm when it opens.
  - It returns to the trigger on 취소. After the action it goes to the result.
- **Long edit forms** keep their save and cancel in a bottom bar that stays in view: Paper, 1px line, 12px radius, flat on the canvas.

### Motion (app pages)
Motion explains state and continuity; it never decorates or makes anyone wait.
- **Material.** Transform and opacity only, on the system ease (`--ease-out`), with no bounce or overshoot.
- **Timing.** Feedback 150ms, routine state 160–260ms, entrances under 400ms including any stagger. Exits and collapses are immediate.
- **Never in the way.** Fill mode is `backwards`, so nothing stays transformed after it arrives, and no animation adds layout shift. Content is never held back beyond a capped stagger of at most 100ms.
- **The focal moment** is the band reveal on 추천 공고. Each band pill settles in (scale .9 → 1, 260ms), then its jobs rise 6px after it. Groups start 40ms apart, and the page has fully arrived within 380ms.
- **Continuity:**
  - A new route's page rises 8px and fades in (260ms, once per path; tab and query changes do not replay it).
  - Tab panels fade in (200ms).
  - The account menu and the withdrawn-consent banner drop 4px into place (160–220ms).
  - Consent texts and answer tips open the same way.
  - A result that arrives after an action (이력서 점검) rises in.
- **Lists that appear as lists** (jobs, criteria, gaps, roadmap steps, questions, past offers, applications) stagger their rows 25ms apart, capped at the fifth row (100ms).
- **Feedback:**
  - Buttons press to .95.
  - Row links press to .995.
  - The nav and tab indicators grow in under the current item (scaleX .4 → 1 with a fade, 220ms).
  - Notices, errors, done lines and failed-request panels fade in (180ms). Inline confirms rise in (200ms).
- **Loading skeletons** carry a shimmer, a light band moved with transform, only while something loads.
- **Reduced motion:** under `prefers-reduced-motion: reduce`, every animation and transition inside the app shell is off. States still change; they just change at once.

### Icons
Line icons drawn in-house on a 24px grid with a 1.75 stroke and round caps and joins, using currentColor, rendered at 15–20px. Arrows are icons, not text glyphs.

## Do's and Don'ts

### Do:
- **Do** route every UI string through `t()` (Korean source `ko.ts`) and keep `word-break: keep-all` for body text.
- **Do** use navy for anything seeker-facing and green for anything employer-facing, including focus rings inside their cards.
- **Do** keep comparable content in fixed zones of the same height so rows align across columns (256 / 68 / 20 + 360, 44px rows).
- **Do** keep 12–13px secondary text at Muted Gray (#6E6E73) or darker on light ground, and at no less than 62% white on dark fields.
- **Do** use the system ease `cubic-bezier(0.2, 0, 0, 1)` for every state transition, and keep expansion off under reduced motion.
- **Do** set `--tone` once per page from its audience (Hub Ink when it serves both sides) and let form controls read it.
- **Do** show field errors under the field in Form Error Red with the alert icon, and whole-form failures (401, network, 5xx) as a form alert.

### Don't:
- **Don't** show numeric scores, weights or "met" verdicts on seeker-facing surfaces; use the band and the amber gap.
- **Don't** use amber for anything except a skill missing from the CV.
- **Don't** use red outside forms, or for anything but an error.
- **Don't** hard-code navy or green inside a form control; take the color from `--tone` (the role switch is the one control that shows both audiences).
- **Don't** put a shadow on a card that sits on the canvas; use the 1px line.
- **Don't** add a third type weight or a second typeface.
- **Don't** let a hover, focus or pin state change any text's line breaks.
- **Don't** repeat the landing's ghost 01/02 numerals, the 공유 기준 pill, the "패널을 클릭해 가입" hints, the ● audience labels or the small heads above cards on other screens. They are landing-only exceptions, not patterns.
- **Don't** use the logo blue or green outside the LogoMark.
