# Interview Agent (M5)

The realtime interviewer of the seeker practice interview (`docs/DECISIONS.md` D51–D58, D79). It is a separate runtime with its own
virtual environment (D56). It runs the engine of `ai/interview/` in-process and reaches the backend only through the internal agent API.
It never touches the database and never imports the backend. Stages S0 to S2 exist: the agent core and a text driver for developers. The
LiveKit voice worker (S4) does not exist yet.

## What it does, and the rules it keeps

- **The engine decides** every question, follow-up, nudge, skip and ending. The runner (`runner.py`) carries: it reads the session's
  context, runs the engine over the plan the backend stored, posts every line and answer, and hands back the lines to speak.
- **Store, then speak.** A line is posted before it is spoken (or printed). If a post is refused, nothing more is said.
- **One end event per interview.** The runner sends `ended` with the closing line when the plan is done or time is up. It sends `aborted`
  without a closing line when the candidate leaves or after an agent error.
- **Stop:**
  - on a 404 (the session was deleted or expired, or this is not its room);
  - on `INTERVIEW_ALREADY_ENDED` or `INTERVIEW_NOT_ACTIVE` (the seeker ended it, or its time is over);
  - when the status check (`check()`) says the session is over.

  After a stop, nothing more is posted.
- **The model** (D52, D79 (5)). Groq `openai/gpt-oss-120b`, through the LiveKit Groq plugin, only in `AI_MODE=llm`. A turn goes only
  through `prepare_turn` → `ai.interview.boundary.ask` → `parse_turn`. `turn_model.py` sends exactly `ModelInput.system` and
  `ModelInput.user`. The per-turn timeout defaults to 3 s and is never above the session's limit. After a timeout, an error or an invalid
  answer, the engine's rules decide at once (D54).
- **Personal data.** The engine masks every answer, including the seeker's display name from the context, before anything is posted or
  sent to a model. The name is held in memory only. Logs carry codes and timings, never a text, the secret or a key.

## Setup (once)

PowerShell, from the repository root. Python 3.12. The versions are pinned (D78).

```powershell
py -3.12 -m venv interview_agent\.venv
interview_agent\.venv\Scripts\python.exe -m pip install -r interview_agent\requirements-dev.txt
```

`requirements.txt` holds the direct pins. `requirements.lock.txt` holds the full resolved set (`pip install -r
interview_agent\requirements.lock.txt` reinstalls it exactly). `livekit-agents` stays at 1.8.12 (D78).

## Settings (environment variables only; no `.env` file is read)

| Name | Default | Meaning |
|---|---|---|
| `INTERVIEW_AGENT_SECRET` | none (required) | The backend's `INTERVIEW_AGENT_SECRET`, at least 32 characters |
| `INTERVIEW_AGENT_BACKEND_URL` | `http://localhost:8000` | The backend |
| `AI_MODE` | `rules` | `llm` uses Groq per turn |
| `GROQ_API_KEY` | none | Required with `AI_MODE=llm` |
| `INTERVIEW_AGENT_LLM_MODEL` | `openai/gpt-oss-120b` | A Claude model name is refused |
| `INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS` | `3` | Per-turn model timeout (D79) |
| `INTERVIEW_AGENT_REASONING_EFFORT` | `low` for `openai/gpt-oss-*` | Sent to Groq |
| `INTERVIEW_AGENT_DATA_DIR` | the repository's `data/` | Where the two blocklists are read |
| `INTERVIEW_DEMO_PASSWORD` | none | `text_cli --job-id` only: the synthetic seeker's password (otherwise it is asked) |

## Text driver (developer tool)

The backend must run with the same `INTERVIEW_AGENT_SECRET`. Use synthetic accounts only.

```powershell
$env:INTERVIEW_AGENT_SECRET = "<the backend's value>"
interview_agent\.venv\Scripts\python.exe -m interview_agent.text_cli --job-id 3 --email seeker2@demo.test --consent
# or, for a session created through the seeker API:
interview_agent\.venv\Scripts\python.exe -m interview_agent.text_cli --session-id 12
```

Type an answer and press Enter. `/silence 25` stays silent for 25 seconds; `/quit` (or end of input) leaves. The driver checks the session
before every answer. The last line lists the outcome of each model call and its time. Afterwards, the seeker API shows the session and its
masked transcript, and `POST /api/interview-sessions/{id}/feedback` gives the report.

## Tests

```powershell
interview_agent\.venv\Scripts\python.exe -m pytest interview_agent/tests -q   # the agent's own tests, offline
python scripts/run_all_tests.py -q                                              # the backend suite and this one
```

The runner's tests against the real application are in `backend/tests/test_interview_agent_runner.py` (the backend suite). They need
neither LiveKit nor a key. No test makes a model, Groq or LiveKit call.

## Files

| File | Purpose |
|---|---|
| `runner.py` | The interview loop over the engine; store, then speak; stop rules; the per-turn model call |
| `backend_client.py` | The internal API for one session: secret and room headers, retries with the same payload, answers sorted into what to do |
| `turn_model.py` | The Groq client with the `LLMClient` shape that `ask` uses; the one module that talks to a model |
| `rooms.py` | The room name of a session, `HMAC-SHA256(secret, session id)` (the backend computes the same) |
| `config.py` | Settings from the environment |
| `text_cli.py` | The text driver |
| `tests/` | Offline tests (agent environment) |
