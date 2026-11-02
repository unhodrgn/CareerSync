---
name: CareerSync
description: 기업 맞춤형 AI 채용 매칭 플랫폼 (criteria-based hiring and job matching). Quiet slate on white with one confident blue.
colors:
  signal-blue: "#315cf4"
  signal-blue-deep: "#2049d6"
  blue-wash: "#eaf0ff"
  blue-haze: "#edf2ff"
  blue-mist: "#f0f4ff"
  blue-line: "#b7c9ff"
  focus-blue: "#80a1ff"
  ink: "#202530"
  slate: "#34425c"
  slate-label: "#526079"
  muted: "#7c889c"
  faint: "#8c96a9"
  night-slate: "#26303f"
  line: "#e6eaf1"
  line-field: "#e2e8f2"
  line-soft: "#edf0f5"
  canvas: "#ffffff"
  cool-paper: "#f5f7fc"
  field-wash: "#f8faff"
  error-red: "#a83832"
  error-wash: "#fff0ef"
  gap-amber: "#a0651c"
  gap-wash: "#fff6e8"
typography:
  display:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "69px"
    fontWeight: 800
    lineHeight: 1.23
    letterSpacing: "-4px"
  headline:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "35px"
    fontWeight: 700
    letterSpacing: "-1.4px"
  title:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    letterSpacing: "-0.6px"
  card-title:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    letterSpacing: "-0.6px"
  figure:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "45px"
    fontWeight: 700
    letterSpacing: "-2px"
  body:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.9
  control:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  label:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "11px"
    fontWeight: 500
  eyebrow:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "9px"
    fontWeight: 700
    letterSpacing: "1.8px"
  micro:
    fontFamily: "DM Sans, Noto Sans KR, sans-serif"
    fontSize: "9px"
    fontWeight: 400
rounded:
  tag: "4px"
  status: "5px"
  tab: "7px"
  field: "8px"
  button: "9px"
  tile: "12px"
  card: "13px"
  panel: "14px"
  pill: "30px"
  round: "50%"
spacing:
  header-height: "90px"
  page-top: "48px"
  page-x: "5%"
  panel: "29px"
  card: "24px"
  field: "14px"
  sidebar-width: "220px"
components:
  button-primary:
    backgroundColor: "{colors.signal-blue}"
    textColor: "{colors.canvas}"
    typography: "{typography.control}"
    rounded: "{rounded.button}"
    padding: "16px 23px"
  button-primary-hover:
    backgroundColor: "{colors.signal-blue-deep}"
  button-primary-small:
    padding: "13px 19px"
  button-secondary:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.signal-blue}"
    rounded: "{rounded.button}"
  button-secondary-hover:
    backgroundColor: "#dfe8ff"
  text-field:
    backgroundColor: "{colors.field-wash}"
    textColor: "{colors.slate}"
    rounded: "{rounded.field}"
    padding: "{spacing.field}"
  job-card:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.card}"
    padding: "{spacing.card}"
  panel:
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  tag:
    backgroundColor: "#f3f5f8"
    textColor: "#6b768a"
    typography: "{typography.micro}"
    rounded: "{rounded.tag}"
    padding: "6px 9px"
  status-chip:
    backgroundColor: "{colors.blue-haze}"
    textColor: "#6480bc"
    typography: "{typography.micro}"
    rounded: "{rounded.status}"
    padding: "7px 9px"
  gap-chip:
    backgroundColor: "{colors.gap-wash}"
    textColor: "{colors.gap-amber}"
  pill:
    backgroundColor: "{colors.canvas}"
    textColor: "#596579"
    rounded: "{rounded.pill}"
    padding: "9px 13px"
  category-tab:
    backgroundColor: "{colors.canvas}"
    textColor: "#6d7686"
    rounded: "{rounded.tab}"
    padding: "10px 17px"
  category-tab-selected:
    backgroundColor: "{colors.night-slate}"
    textColor: "{colors.canvas}"
  sidebar-item:
    textColor: "#7f8ba1"
    rounded: "{rounded.field}"
    padding: "13px"
  sidebar-item-selected:
    backgroundColor: "{colors.blue-wash}"
    textColor: "{colors.signal-blue}"
  match-score:
    backgroundColor: "{colors.blue-mist}"
    textColor: "{colors.signal-blue}"
    typography: "{typography.figure}"
    rounded: "{rounded.tile}"
    padding: "20px"
  toast:
    backgroundColor: "#243046"
    textColor: "{colors.canvas}"
    rounded: "{rounded.tile}"
    padding: "17px 23px"
  request-error:
    backgroundColor: "{colors.error-wash}"
    textColor: "{colors.error-red}"
---

# Design System: CareerSync

Source of truth for the frontend's look: `frontend/src/index.css` (base, fonts, focus ring), `frontend/src/App.css` (layout and components), `frontend/src/motion.css` (motion) and the pages in `frontend/src/pages/`. The CSS has no custom properties; every value is a literal, and the tokens above name the values the code actually repeats.

## Overview

**Creative North Star: "The Calm Ledger"**

CareerSync reads like a well-kept ledger: white pages, slate ink, thin cool borders, and one confident blue that marks every place where something can be done or something was found. Hiring data is serious and personal, so the surface stays calm and orderly; the energy comes from a single accent and from small, precise motion, not from color or decoration.

Density is moderate to compact. Content sits in white panels and cards with generous inner padding (24–29px) on a white or cool-paper ground; text is small and tightly tracked, headings are heavy with negative letter-spacing, and secondary copy steps down through a family of blue-tinted grays rather than through weight. The landing adds the only expressive layer: a dotted cool-paper hero with floating artwork that tilts toward the pointer, a pause control, and staggered entrances. App pages drop the decoration and keep the ledger: sidebar, page title, panels, rows.

**Key Characteristics:**
- One accent hue, Signal Blue, used for actions, selection, scores and links; everything else is slate and cool gray.
- Blue-tinted neutrals throughout: grays lean toward the accent, never warm or pure.
- Flat at rest; soft blue-tinted shadows and a small lift appear on hover.
- Heavy, tightly tracked headings over small, airy body text.
- Motion on one curve, `cubic-bezier(.2,.7,.2,1)`, always switched off for reduced motion.

## Colors

A cool, nearly monochrome palette: slate ink and blue-gray neutrals around a single saturated blue, with red and amber reserved for errors and CV gaps.

### Primary
- **Signal Blue** (`signal-blue`): the one accent. Primary buttons, active nav, the brand mark, eyebrows, links on hover, stat numbers, the match score figure and progress fill, selected sidebar items, saved bookmarks. Roughly 40 uses in `App.css`; nothing else competes with it.
- **Deep Signal Blue** (`signal-blue-deep`): primary button hover only.

### Secondary
- **Blue Wash** (`blue-wash`): secondary buttons and the selected sidebar item background.
- **Blue Haze** (`blue-haze`): status chip background and the loading sweep.
- **Blue Mist** (`blue-mist`): the match score panel and selected candidate rows.
- **Blue Line** (`blue-line`): hover border on job cards, empty-state glyph, quote rules.
- **Focus Blue** (`focus-blue`): the 3px focus ring on every interactive element.

### Error
- **Error Red** (`error-red`) on **Error Wash** (`error-wash`): request errors, criterion problems, weight-total warnings, destructive text links and tag-remove hover.

### Tertiary
- **Gap Amber** (`gap-amber`) on **Gap Wash** (`gap-wash`): skills and certificates the job names that the CV lacks (gap tags). Amber means "missing from the CV", never "failed".

### Neutral
- **Ink** (`ink`): base text color set on `:root`.
- **Slate** (`slate`): input text and strong secondary text.
- **Slate Label** (`slate-label`): form labels and avatar initials.
- **Muted** (`muted`) and **Faint** (`faint`): body copy in panels, meta lines, empty states, captions. Many near-duplicates exist (`#737d90`, `#8792a5`, `#8794aa`, `#9199a7`, …); new work should use these two.
- **Night Slate** (`night-slate`): the selected category tab. The toast uses the close variant `#243046`.
- **Line** (`line`), **Field Line** (`line-field`), **Soft Line** (`line-soft`): panel and sidebar borders, input borders, card dividers and the footer rule.
- **Canvas** (`canvas`), **Cool Paper** (`cool-paper`), **Field Wash** (`field-wash`): page and card white, the hero ground, input and upload-zone fill.

Company logo tiles (`.company-logo` with `.orange`, `.yellow`, …) carry their own pastel ground and strong foreground. They are content identifiers, not part of the UI palette.

### Named Rules
**The One Voice Rule.** Signal Blue is the only accent. If something needs emphasis and it is not an action, a selection, a score or a link, use weight or Ink, not a new hue.

**The Cool Neutral Rule.** Every gray is blue-tinted. No pure black text, no warm grays.

**The Amber Means Missing Rule.** Amber marks a gap between the job and the CV; red marks an error or a blocked action. Neither is used for decoration.

## Typography

**Display Font:** DM Sans (with Noto Sans KR, sans-serif)
**Body Font:** DM Sans (with Noto Sans KR, sans-serif)

**Character:** A geometric Latin face paired with a neutral Hangul face; Korean text, which is most of the UI, renders in Noto Sans KR. Both load from Google Fonts in `index.css` (DM Sans 400–700, Noto Sans KR 400–900).

Because DM Sans is loaded only up to 700 and `font-synthesis: none` is set, weights 800 and 900 render Latin glyphs at 700 and Hangul glyphs at the full weight.

### Hierarchy
- **Display** (`display`): the landing hero headline only. Steps down to 59px at ≤1250px and 49px at ≤950px.
- **Headline** (`headline`): the page title on app pages (`.page-title h1`), line-height 1.8 for its lead paragraph. Auth intro headings run larger (43px, -2px).
- **Title** (`title`): panel headings (`.panel h2`). Panel `h1` is 32px / -1px; panel `h3` is 14px.
- **Card title** (`card-title`): job titles on job cards.
- **Figure** (`figure`): the match score number. Stat tiles use 29px / -1px.
- **Body** (`body`): panel paragraphs and page leads in Muted. The hero lead is 14px, line-height 1.9.
- **Control** (`control`): buttons (13px on regular buttons, 12px on small), form labels, inputs, nav items (13px).
- **Label** (`label`): text links, category tabs, AI notices, meta in rows.
- **Eyebrow** (`eyebrow`): small Signal Blue labels above headings; 8px inside the sidebar.
- **Micro** (`micro`): tags, status chips, job meta, card footers, hints.

### Named Rules
**The Tight Heading Rule.** Headings are heavy and negatively tracked (from -0.6px on titles to -4px on display); body copy is never tracked tighter than -0.3px.

**Audit flag: small text.** The incumbent scale leans very small: about 20 rules at 9px, 9 at 8px and 2 at 7px, plus 10px and 11px as the most common sizes. This is recorded as-is, not endorsed. A later `audit` / `typeset` pass decides whether to set a floor; until then, new screens should not go below the sizes the matching existing component uses.

## Layout

- **Header:** 90px tall, max width 1440px, horizontal padding 6%, logo left, nav center, actions right.
- **Landing:** sections max 1280px; the hero is a two-column grid (1.12fr / 1fr) with copy left and artwork right, on Cool Paper with a 22px dot grid that fades in from the left.
- **App pages:** a 220px white sidebar with a right border, then page content max 1280px with padding `48px 5% 70px`. A page opens with a page title block (32px bottom margin), then panels and grids.
- **Grids:** stat tiles in four equal columns (15px gap); job cards in a card grid; auth is two equal columns (70px gap, max 1000px).
- **Rhythm:** spacing values are literal and close together (20–30px between blocks, 24px card padding, 29px panel padding, 12–24px within cards). There is no spacing scale in the code.
- **Breakpoints:** 1500px (wider), 1250px, 950px (sidebar narrows to 165–185px, hero scales down), 700px (nav hidden, hero stacks, stats in two columns). PRODUCT.md targets desktop; the narrower rules exist in the code and are documented here, not extended.

## Elevation & Depth

Hybrid: surfaces are flat at rest, separated by 1px cool borders on white. Shadows are soft, wide and tinted with the accent's navy, and most of them appear only as a response to hover. The landing's floating cards are the one place shadows sit at rest.

### Shadow Vocabulary
- **Button glow** (`box-shadow: 0 4px 9px #315cf413`): primary buttons at rest; secondary buttons drop it.
- **Card lift** (`box-shadow: 0 12px 30px #2a3f6e0c`): job card hover, with `translateY(-5px)` and a Blue Line border.
- **Search float** (`box-shadow: 0 7px 24px #25376208`): the search box.
- **Floating card** (`box-shadow: 0 12px 32px #3349800c` / `0 9px 30px #263e8110`): hero match and score cards.
- **Toast** (`box-shadow: 0 8px 30px #182a4930`): the toast, the strongest shadow in the system.

### Named Rules
**The Lift-On-Intent Rule.** In the app, shadows answer the pointer. A card or button lifts (−2px for buttons, −5px for job cards) and gains its shadow on hover; at rest it is flat with a border.

## Shapes

Gently rounded, never sharp and never pill-shaped except for pills and avatars. Radius grows with the size of the surface: tags 4px, status chips 5px, category tabs 7px, inputs and sidebar items 8px, buttons 9px, logo tiles and the match score 12px, job cards 13px, panels 14px, pills 30px, avatars and the score ring round. Borders are 1px in cool line colors; the upload zone uses a 1.5px dashed Blue Line border.

## Components

### Buttons
Confident and compact: solid blue, slightly rounded, with the label and an arrow glyph spaced apart.
- **Shape:** gently rounded (9px).
- **Primary (`.btn`):** Signal Blue fill, white 13px / 600 text, padding 16px 23px, 20px gap to a trailing icon, the button glow.
- **Hover / Focus:** Deep Signal Blue, lifts 2px, the trailing icon slides 4px right; press scales to .98. Focus shows the 3px Focus Blue outline offset 4px.
- **Small (`.btn.small`):** 13px 19px, 12px text; used in the header.
- **Secondary (`.secondary`):** Blue Wash fill, Signal Blue text, no shadow; hover `#dfe8ff`.
- **Text link (`.text-link`):** 11px / 500 Muted text with a trailing arrow; hover turns Signal Blue. `.danger` turns Error Red.
- **Disabled:** opacity .55, default cursor.

### Chips
- **Tags:** pale gray (`#f3f5f8`) with gray text, 9px, 4px radius; skill and keyword lists on cards.
- **Status chip (`.status`):** Blue Haze with muted blue text, 9px, 5px radius; application status and the match band.
- **Gap chip (`.gap-tags`):** Gap Wash with Gap Amber text.
- **Pill (`.pill`):** white, 1px border, 30px radius, 10px / 500; small announcements on the landing.
- **Category tabs:** white with a 1px border, 7px radius; the selected tab inverts to Night Slate with white text.

### Cards / Containers
- **Job card:** white, 1px `#e4e8f0` border, 13px radius, 24px padding. Top row: a 45px logo tile and the bookmark button; then company name, card title with an ↗ glyph, meta line, tags, and a footer row above a Soft Line divider. Hover: card lift; the logo tile tilts −6° and scales 1.06.
- **Panel:** white, 1px Line border, 14px radius, 29px padding; the default container on app pages.
- **Stat tile:** a panel with an 11px label, a 29px Signal Blue number and a 9px caption.
- **Empty state:** centered, 60px vertical padding, a 70px Blue Line glyph over 14px Muted text.

### Inputs / Fields
- **Style:** Field Wash fill, 1px Field Line border, 8px radius, 14px padding, 12px Slate text, placeholder `#a3adc0`. Labels stack above (12px / 600 Slate Label, 10px gap).
- **Focus:** the global 3px Focus Blue outline, offset 4px.
- **Search box:** a white bar with 12px radius, 1px border and the search float shadow; the input inside is borderless, and selects sit behind a left divider.
- **Upload zone:** Field Wash, 1.5px dashed Blue Line border, 12px radius, min height 270px, Signal Blue content.
- **Error:** the request-error block (Error Wash, Error Red).

### Navigation
- **Header nav:** 13px / 600 text buttons, 30px apart; hover and active turn Signal Blue. A "NEW" mark is an 8px / 800 Signal Blue superscript. The brand is a ✳ glyph in Signal Blue, "CareerSync" at 25px / 800 / -1.1px and a blue period. Signed-in users get a 33px round avatar with their initial on `#e8edff`.
- **Sidebar:** 220px, white, right border; an eyebrow, then 12px Muted items with icons, 8px radius; the selected item is Blue Wash with Signal Blue text at 600. A tip card in `#f5f7fe` sits lower down.
- **Footer:** a Soft Line rule above a single row, max 1200px.

### Match Score (signature)
The seeker's match result. A Blue Mist tile (12px radius, 20px padding) stacking: a small label, the score in the figure style with a smaller 점 (points) unit, the band as a status chip, the disclaimer line and the AI notice (9px). Product rule: the score never appears without its band, disclaimer and notice. A 5px progress bar (`#dae4ff` track, Signal Blue fill, 9px radius) grows from the left on entry.

### Toast
Fixed at bottom center, `#243046` with white 12px text, 12px radius, the toast shadow; enters with a 12px rise.

### Hero Artwork (landing)
Floating match and score cards rotated a few degrees, a 3D core shape and orbit rings with Signal Blue dots, on a soft radial glow. The scene tilts toward the pointer (perspective 950px) and can be paused with the motion toggle. Only on the landing.

### Motion
- **Curve:** `cubic-bezier(.2,.7,.2,1)` for entrances and transforms; plain `ease` for fades and small state changes; buttons and cards transition background, transform and shadow in 200ms.
- **Entrances:** hero copy staggers in (700ms, 17px rise, 70–90ms steps); pages fade up 9px in 360ms; sections reveal on scroll (650ms, 22px), and stay visible if JavaScript never marks them.
- **Feedback:** bookmark pop (350ms), loading sweep on request status, progress fill (900ms).
- **Reduced motion:** all animation and transitions are removed, reveals show immediately, the 3D tilt and the motion toggle are disabled.

## Do's and Don'ts

### Do:
- **Do** use Signal Blue for every primary action, selection, score and link, and nothing else.
- **Do** build app pages from the existing shell: sidebar, page title block, white panels with a 1px Line border and 14px radius.
- **Do** keep surfaces flat at rest and lift them on hover (button −2px with Deep Signal Blue; card −5px with the card-lift shadow and Blue Line border).
- **Do** use Gap Amber chips for what the CV lacks and Error Red only for errors and blocked actions.
- **Do** keep the 3px Focus Blue outline on every interactive element.
- **Do** put new motion on `cubic-bezier(.2,.7,.2,1)` inside `prefers-reduced-motion: no-preference`, with a static fallback.
- **Do** show the match score only in the Match Score component, with its band, disclaimer and AI notice.

### Don't:
- **Don't** introduce a second accent hue; company logo tiles are the only other color, and only as content.
- **Don't** use pure black text, pure gray or warm neutrals.
- **Don't** add heavy or dark shadows at rest; the toast is the only strong shadow.
- **Don't** put a thick colored stripe on one side of a card or block. The 3px left rule on review quotes (`App.css:38`) is flagged for review, not a pattern to copy.
- **Don't** add new near-duplicate grays; use Muted and Faint.
- **Don't** use the hero artwork, dot grid or floating cards on app pages.
