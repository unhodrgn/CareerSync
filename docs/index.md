# Documentation map

Every CareerSync document, sorted by what it is for. The types follow [Diataxis](https://diataxis.fr/): **how-to** guides solve a task, **explanation** says why things work the way they do, **reference** states facts to look up. All docs are in English; Korean product terms keep their Korean name with an English gloss (D40, glossary in [PROJECT_DOCUMENTATION.md §12](../PROJECT_DOCUMENTATION.md#12-glossary)).

## Start here

| Document | Type | Purpose |
| --- | --- | --- |
| [README](../README.md) | Overview | What CareerSync is, Quick Start, status, known limitations |

## How-to guides

| Document | Type | Purpose |
| --- | --- | --- |
| [Run with Docker Compose](how-to/run-with-docker.md) | How-to | Start the full demo (database, backend, frontend) with one command |
| [Run locally](how-to/run-locally.md) | How-to | Manual setup: PostgreSQL in Docker, backend and frontend on your machine, `.env`, demo accounts, tests |
| [Troubleshooting](how-to/troubleshooting.md) | How-to | Fixes for common setup and runtime errors |

There are no tutorials yet; a guided first-demo walkthrough is planned.

## Explanation

| Document | Type | Purpose |
| --- | --- | --- |
| [How CareerSync works](explanation/how-it-works.md) | Explanation | User flows, architecture, how scoring works and the scoring rules |
| [Privacy and legal](explanation/privacy-and-legal.md) | Explanation | What the LLM sees (masking), consent, the discriminatory-criteria guardrail, the laws |

## Reference

| Document | Type | Purpose |
| --- | --- | --- |
| [DECISIONS.md](DECISIONS.md) | Reference | Decisions, demo scope and open questions. The source of truth: on any conflict it wins |
| [PROJECT_DOCUMENTATION.md](../PROJECT_DOCUMENTATION.md) | Reference | Technical reference: database, API (§4.1), frontend, AI, files (§8), configuration (§9), known issues (§11), glossary (§12) |
| Swagger at http://localhost:8000/docs | Reference | Request and response schemas as implemented (while the backend runs) |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Reference | How to run the tests and doc guards, the doc rules, commit style |
| [CLAUDE.md](../CLAUDE.md) | Reference | Rules for AI coding assistants working on this repository |
| [DESIGN.md](../DESIGN.md) | Reference | Design system of the frontend |
| [PRODUCT.md](../PRODUCT.md) | Reference | Product context for design work (not a source of decisions) |

## Source material and history

| Folder | Purpose |
| --- | --- |
| [reference/](reference/) | Source PDFs kept as they were delivered: the project proposal (과제계획서), the design document (설계서) and the market research report (시장조사 보고서). They are inputs, not maintained docs; where they differ from DECISIONS.md, DECISIONS.md wins |
| [archive/](archive/) | Historical snapshots, kept for the record and no longer updated (D37) |
