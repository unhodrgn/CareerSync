# Contributing to CareerSync

## Run the tests

- `pytest` from the repository root: the whole suite, with no database, network or API key needed (in-memory SQLite, hashing embedder, a fake LLM). It must pass before every commit.
- `pytest backend/tests/docs -q`: only the doc-drift guards (links and anchors, D/Q/issue IDs, API and env tables, constants and claims, demo accounts, the folder tree, English-only docs).
- `npm run build` in `frontend/` after a frontend change: type check and build.
- CI (`.github/workflows/ci.yml`) runs `pytest` and the frontend build on every push to `main` and on every pull request.

Setup and the full command list: [Run locally](docs/how-to/run-locally.md).

## Doc rules

- **The doc is the standard (D11).** Priority: `docs/DECISIONS.md` > `PROJECT_DOCUMENTATION.md` > code. If the code differs from the doc, fix the code; if the doc looks wrong or outdated, ask Long instead of editing it.
- **Decisions live only in `docs/DECISIONS.md`.** Add a row with the real decision date; never rewrite or delete an old row, add a new one that says "replaces D#". Open questions go to its §3.
- **Keep the docs current.** A change that adds or changes a table, endpoint, page, env variable, constant or file updates the matching section of `PROJECT_DOCUMENTATION.md` (including the §8 tree) in the same commit.
- **Guards and the allowlist.** A failing doc guard names the doc place and the code place. A known, intended difference goes into `backend/tests/docs/allowlist.yaml` with a reason; an entry that is no longer needed fails, so remove it then.
- **English only (D40).** All Markdown docs are in English. Korean product/UI terms and law names stay Korean, with an English gloss at first use (glossary: `PROJECT_DOCUMENTATION.md` §12). User-facing text in the app is Korean.
- **No hand-typed test counts** in docs: describe what must pass, and count with `pytest --collect-only -q | tail -1`.

## Commits

- Imperative, capitalized English sentence, e.g. "Add talent offer expiry" or "Fix the README demo steps".
- One reviewable change per commit; docs and the guards they need change in the same commit.
- Never commit `.env`, API keys or real CVs; use synthetic data only.

## AI coding assistants

Read [CLAUDE.md](CLAUDE.md) first: how to plan and work, permissions, and the AI rules the code must keep.
