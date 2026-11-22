# Interview Agent (M5)

The realtime interviewer of the seeker practice interview (`docs/DECISIONS.md` D51–D58, D79, D80). It is a separate runtime with its own
virtual environment (D56). It runs the engine of `ai/interview/` in-process and reaches the backend only through the internal agent API. It never
touches the database and never imports the backend. Stages S0 to S4 exist: the agent core, a text driver, the consent-withdrawal rule, and the
audio-only LiveKit voice worker with a developer test page. **The voice worker has not been run against a LiveKit project yet**: everything
below under "Live run" is still to do, and no latency figure exists.

## What it does, and the rules it keeps

- **The engine decides** every question, follow-up, nudge, skip and ending. The runner (`runner.py`) carries: it reads the session's
  context, runs the engine over the plan the backend stored, posts every line and answer, and hands back the lines to speak. The controller
  (`controller.py`) holds the conversation rules around it; `voice.py` connects both to a LiveKit room.
- **Store, then speak.** A line is posted before it is spoken (or printed). If a post is refused, nothing more is said.
- **One end event per interview.** The runner sends `ended` with the closing line when the plan is done or time is up. It sends `aborted`
  without a closing line when the candidate leaves or after an agent error.
- **Stop.**
  - on a 404 (the session was deleted or expired, or this is not its room);
  - on `INTERVIEW_ALREADY_ENDED` or `INTERVIEW_NOT_ACTIVE` (the seeker ended it, or its time is over);
  - when the status check says the session is over (about every 5 s in the voice worker), or ended because the seeker withdrew the AI consent
    (`consent_withdrawn`).

  After a stop, nothing more is posted and the speech is interrupted by force (a plain interrupt would let an uninterruptible line play on).
- **Consent withdrawal** (D80, Q39). The backend ends the seeker's active sessions when the AI consent is withdrawn, so the next post is refused
  and the runner stops. In `AI_MODE=llm` the runner also reads the context right before every model call (one attempt, no retry): an ended session
  stops it; an active session whose seeker has no current consent gets an aborted end and a stop; an unreadable context means no model call for that
  turn. A call already running may finish, but its answer is refused when posted and nothing of it is stored.
- **The model** (D52, D79 (5), D82). Groq `openai/gpt-oss-120b`, through the LiveKit Groq plugin, only in `AI_MODE=llm`. A turn goes only through
  `prepare_turn` → `ai.interview.boundary.ask` → `parse_turn`. `turn_model.py` sends exactly `ModelInput.system` and `ModelInput.user`. The per-turn
  timeout defaults to 3 s and is never above the session's limit. After a timeout, an error or an invalid answer, the engine's rules decide at once.
- **The voice session has no LLM.** `AgentSession` is built without `llm`: the SDK then still runs the hook that receives the answer and skips the
  reply, so no transcript can reach a model except through `turn_model`. LiveKit's speech services are not LLMs (D79, Q35).
- **Personal data.** Every transcript, interim and final, is masked in the speech-recognition node before anything else sees it, and again in the hook
  and by the engine, with the seeker's display name from the context (held in memory only). Logs carry codes and timings, never a text, a name, the
  secret or a key. `session.start(record=False)`: nothing is uploaded to LiveKit Cloud. Only the microphone is subscribed.
- **Not interruptible.** The interviewer's lines are spoken with `allow_interruptions=False`; an answer spoken over the interviewer is not heard
  (the SDK does not deliver a turn that ends during uninterruptible speech, and the controller drops one that arrives while it is busy).

### The speech providers the agent actually uses

Read from the installed packages (livekit-agents 1.8.12, `interview_agent/.venv`), not from the plan. There is no Deepgram or Cartesia plugin
installed: everything goes through LiveKit Inference, whose gateway routes by the model id.

| Part | Model id (default) | Where it runs | Korean |
|---|---|---|---|
| Speech recognition | `deepgram/nova-3` (`inference.STT`, `provider == "livekit"`) | LiveKit Inference gateway | `ko` and `ko-KR` listed in LiveKit's model table |
| Speech synthesis | `cartesia/sonic-3` (`inference.TTS`, `provider == "livekit"`) with the voice `INTERVIEW_AGENT_TTS_VOICE` | LiveKit Inference gateway | `ko` listed; the default voice is a sample voice with no Korean claim: listen and change it |
| Turn detection | `turn-detector-v1` (`inference.TurnDetector(version="v1", local_fallback=True)`) | LiveKit Inference gateway; falls back to the local `v1-mini` | Korean is supported by the detector (PoC README) |
| Voice activity | Silero VAD (`livekit-plugins-silero`) | local, in the worker | language independent |
| Per-turn analysis | `openai/gpt-oss-120b` (`livekit-plugins-groq`) | Groq, `AI_MODE=llm` only | Groq cites Korean support; unmeasured |
| Session LLM | none (`session.llm is None`, a test checks it) | | |

The names Deepgram and Cartesia come from the model ids. Whether LiveKit forwards the audio to those companies or runs the models itself is for
LiveKit's Inference data-processing terms to say (Q35); the consent drafts carry a 【확인 필요】 for it.

## Setup (once)

PowerShell, from the repository root. Python 3.12. The versions are pinned (D78).

```powershell
py -3.12 -m venv interview_agent\.venv
interview_agent\.venv\Scripts\python.exe -m pip install -r interview_agent\requirements-dev.txt
interview_agent\.venv\Scripts\python.exe -m interview_agent.voice download-files   # local models (Silero, the v1-mini fallback), before the first live run
```

`requirements.txt` holds the direct pins. `requirements.lock.txt` holds the full resolved set (`pip install -r interview_agent\requirements.lock.txt`
reinstalls it exactly). `livekit-agents` stays at 1.8.12 (D78).

## Environment variables

The **backend** reads the repository-root `.env` (or the shell). The **agent** reads only its own process environment, never a `.env` file: set them
in the terminal that starts it.

| Name | Backend | Agent | Value |
|---|---|---|---|
| `INTERVIEW_AGENT_SECRET` | required | required | The same random string in both, at least 32 characters. Fail closed: unset or shorter refuses every internal call and the join route |
| `LIVEKIT_URL` | required | required | `wss://<your-project>.livekit.cloud` (LiveKit Cloud: Settings, Project) |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | required | required | An API key of the same project (Settings, API keys). The backend signs the join token with it; the agent registers with it and LiveKit Inference checks it |
| `INTERVIEW_AGENT_BACKEND_URL` | | `http://127.0.0.1:8000` | The backend (default `http://localhost:8000`) |
| `AI_MODE` | `rules` is enough | `llm` | Agent `llm`: Groq per turn. Backend `rules`: template questions and rules feedback, so the live run needs no Anthropic key |
| `GROQ_API_KEY` | | required with `AI_MODE=llm` | A Groq key (console.groq.com/keys) |
| `INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS` | | `3` | Per-turn model timeout, above 0 and at most 30 |
| `INTERVIEW_AGENT_LLM_MODEL` | | `openai/gpt-oss-120b` | A Claude model name is refused |
| `INTERVIEW_AGENT_REASONING_EFFORT` | | `low` for gpt-oss | `low`, `medium` or `high` |
| `INTERVIEW_AGENT_NAME` | `careersync-interviewer` | `careersync-interviewer` | Leave both unset; a test checks that the defaults agree |
| `INTERVIEW_AGENT_STT_MODEL`, `INTERVIEW_AGENT_TTS_MODEL` | | `deepgram/nova-3`, `cartesia/sonic-3` | Change the model without code |
| `INTERVIEW_AGENT_TTS_VOICE` | | a Cartesia sample voice | The voice id |
| `INTERVIEW_AGENT_ENDPOINT_MIN_SECONDS`, `..._MAX_SECONDS` | | `3.0`, `6.0` | End-of-turn waits (the PoC's values) |
| `INTERVIEW_AGENT_STATUS_POLL_SECONDS` | | `5` | How often the worker asks the backend whether the session is still active |
| `INTERVIEW_AGENT_CONSOLE_SESSION_ID` | | | `console` mode only |
| `INTERVIEW_AGENT_DATA_DIR` | | the repository's `data/` | The two blocklists |
| `INTERVIEW_DEMO_PASSWORD` | | | `text_cli --job-id` only: the synthetic seeker's password (otherwise it is asked) |

Never put a key in a file you commit. The agent prints the names of missing variables and never a value.

## Run it

Four terminals, from the repository root. The accounts are the documented synthetic ones (`docs/how-to/run-locally.md`): `seeker2@demo.test` has a
confirmed CV (password `demo1234`). **Sessions are limited to 3 per seeker per KST day and a reservation is never refunded**, so plan the checks.

```powershell
# Terminal 1: the backend (the database of .env; migrate and seed once)
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
.\.venv\Scripts\python.exe scripts\seed.py
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload        # http://localhost:8000, Swagger at /docs

# Terminal 2: the voice worker
$env:INTERVIEW_AGENT_SECRET = "<the value in .env>"
$env:INTERVIEW_AGENT_BACKEND_URL = "http://127.0.0.1:8000"
$env:LIVEKIT_URL = "wss://<project>.livekit.cloud"; $env:LIVEKIT_API_KEY = "<key>"; $env:LIVEKIT_API_SECRET = "<secret>"
$env:AI_MODE = "llm"; $env:GROQ_API_KEY = "<groq key>"
interview_agent\.venv\Scripts\python.exe -m interview_agent.voice start

# Terminal 3: the developer test page (a browser page; it forwards /api/ to the backend and never /api/internal/)
interview_agent\.venv\Scripts\python.exe -m interview_agent.devclient.serve      # http://127.0.0.1:8788/  (Chrome)
```

The worker log must show, for each session, `voice session <id>: stt=deepgram/nova-3 tts=cartesia/sonic-3 detector=turn-detector-v1 endpointing
min=3.0s max=6.0s ai_mode=llm`. If it says `turn-detector-v1-mini`, the session is not running the cloud detector.

**Console mode** (no browser, no LiveKit room: your microphone and speakers; speech services still go through LiveKit Inference): create a session
that nobody has joined, then run the worker in `console` within the join time (5 minutes):

```powershell
interview_agent\.venv\Scripts\python.exe -m interview_agent.text_cli --job-id 1 --email seeker2@demo.test --consent --create-only
$env:INTERVIEW_AGENT_CONSOLE_SESSION_ID = "<the id it printed>"
interview_agent\.venv\Scripts\python.exe -m interview_agent.voice console
```

The job id is one of `GET /api/jobs` (the seeded backend job of 넥스트코드 is normally 1). **Text driver** (no LiveKit, no keys, rules mode):
`python -m interview_agent.text_cli --job-id 1 --email seeker2@demo.test --consent` (see its docstring).

## Live run: the checklist

Use synthetic answers only. The run sends your voice to LiveKit and its speech providers, and masked text to Groq (Q35 is open). Each session also
writes `interview_agent/.runs/session-<id>-<UTC>.json` (git-ignored; numbers and codes only) and logs the same figures as `session summary: {...}`.
Do not run the worker with `--log-level debug`: the SDK then prints transcript lines.

**Plan the sessions** (3 per account per day): session A (seeker2): C1, C3, C4, C7. Session B (seeker2): C2. Session C (seeker2): C5 and C6a.
A second day, or `seeker@demo.test` after uploading and confirming `data/demo/demo_cv.pdf`: sessions D, E, F for C6b, C6c, C6d.

| # | Check | Do | Expect | Record |
|---|---|---|---|---|
| C1 | Dispatch into a new room | Page: log in, tick the consent, job id, **면접 시작**. Allow the microphone | Within 20 s the page says the interviewer joined; the worker logs the session line; the greeting ("저는 CareerSync의 AI 면접관입니다 …") and then the first question are spoken | The page's "joined the room -> the interviewer (agent) joined" and "-> first interviewer audio track" seconds; the report's `opening.say_to_first_audio_s` |
| C2 | Dispatch when the room already exists | LiveKit applies a token's room settings only when it creates the room. Session B. (1) Stop the worker (Ctrl+C). (2) Page, tab 1: start, so a room exists with no agent; wait for the 20 s error. (3) Start the worker again. (4) Tab 2: fill **기존 세션 번호** with that session's id and start: the room exists. (5) Close both tabs, wait 40 s (the empty room expires after 30 s), join that session again from the page | (4) per LiveKit's documentation no agent arrives; (5) a new room is created and the agent arrives, if the session is still `created` (5 minutes from creation) | Whether an agent joined in (4) and in (5), and after how many seconds. If (5) fails, or (4) surprisingly succeeds, say so: the remedy (an explicit dispatch call from the backend) is not built |
| C3 | Korean turn detection | Session A, answer each question in Korean. (a) One clause, silence ~1 s, then the rest, e.g. "멱등성은 같은 요청을 여러 번 보내도 결과가 같게 만드는 성질입니다 … (1 s) … 예를 들어 결제 요청에 멱등성 키를 붙였습니다." (b) Silence ~2.5 s inside an answer. (c) Silence ~3.5 s or more: the turn is expected to end. (d) Stop mid-thought ("그래서 멱등성은 …") and stay silent. Say nothing while the interviewer speaks | (a) and (b): one answer line on the page, no reply in between; (c) the turn ends; (d) it ends between about 3 and 6 s after your last word | Per turn, from the report: `endpointing_s`; `turn_detector.model_at_end` (must be `turn-detector-v1`) and `fell_back` (must be false); the number of answers the page shows split into two lines, and for which case |
| C4 | End-to-end latency | Session A: answer each question normally in 15 to 40 s, stay silent when done, all five questions | The interviewer speaks after your last word | The report's `turns[].gap_s` (last word to first sound, the headline), and its parts `stt_delay_s`, `endpointing_s`, `processing_s` (Groq + engine + two posts), `tts_start_s`; `gap_s` min, median, max. Not judged here: no target is decided (the PoC estimated about 4.4 s at 3.0 s endpointing, without Groq) |
| C5 | Groq timeout falls back to the rules | Session C: restart the worker with `$env:INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS = "0.2"`. Answer two questions. (Optionally first, with a wrong `GROQ_API_KEY`, to see `error:*`) | The interviewer still answers every time; the worker logs `turn analysis: timeout`; no error on the page | `llm_calls[].outcome` and `seconds` (`timeout` at ~0.2 s), `processing_s` of those turns. Then, with the 3 s default in session A: the share of `ok` against `timeout`, `error:*` and `rejected:*`, and the longest `seconds` |
| C6a | The seeker's End stops the voice | Session C: while the interviewer is speaking, press **종료** | Speech stops; the page shows `aborted (seeker_ended)`; the worker exits the room | Seconds from the click to silence (up to about 5 s) |
| C6b | Deleting a live session stops the voice | Session D: while the interviewer is speaking, `DELETE /api/interview-sessions/{id}` in Swagger (`/docs`, Authorize with the seeker's token) | The agent stops within about 5 s and the room is deleted | Seconds to silence; the worker's log line `runner stopped: gone` |
| C6c | Closing the tab ends it | Session E: close the browser tab mid-answer | The session reads `aborted` with `candidate_left`; no closing line | The end reason in the page of a new tab or `GET /api/interview-sessions`; seconds until it appears |
| C6d | Consent withdrawal stops it | Session F: `DELETE /api/users/me/consent/ai` in Swagger mid-interview; afterwards consent again (`POST /api/users/me/consent`) | The agent stops within about 5 s with no further model call; the session reads `aborted` (`consent_withdrawn`) | Seconds to silence; the worker log; no Groq call after the withdrawal |
| C7 | Masking in the live path | Session A: "제 이름은 홍길동이고 전화번호는 공일공 일이삼사 오육칠팔입니다 …" | The page's stored transcript shows `[이름]` and a phone placeholder, not the words | The page's line; confirm that the worker log holds no part of what you said |
| C8 | A second session after the first | Start a session right after one ended | It works, in a new room | Whether the first attempt after an ended session connected |

If an agent does not join within 20 s: the worker is not running or is registered under another name (`INTERVIEW_AGENT_NAME`), the LiveKit project
differs between the backend's token and the worker, or the room already existed (C2). If a join answers 503: a `LIVEKIT_*` or the agent secret is
missing in the backend's environment. If it answers 409 `AI_CONSENT_REQUIRED`: the seeker has withdrawn the consent. The quota is
`INTERVIEW_DAILY_SESSIONS` = 3 per KST day (code constant, not an environment variable).

## Text driver (developer tool)

The backend must run with the same `INTERVIEW_AGENT_SECRET`. Use synthetic accounts only.

```powershell
$env:INTERVIEW_AGENT_SECRET = "<the backend's value>"
interview_agent\.venv\Scripts\python.exe -m interview_agent.text_cli --job-id 3 --email seeker2@demo.test --consent
# or, for a session created through the seeker API:
interview_agent\.venv\Scripts\python.exe -m interview_agent.text_cli --session-id 12
```

Type an answer and press Enter. `/silence 25` stays silent for 25 seconds; `/quit` (or end of input) leaves. The driver checks the session
before every answer. The last line lists the outcome of each model call and its time.

## Tests

```powershell
interview_agent\.venv\Scripts\python.exe -m pytest interview_agent/tests -q   # the agent's own tests, offline
python scripts/run_all_tests.py -q                                              # the backend suite and this one
```

The runner and the controller are also tested against the real application in `backend/tests/test_interview_agent_runner.py` and
`backend/tests/test_interview_voice.py` (the backend suite). No test makes a model, Groq, LiveKit or network call. What no test covers is the
live checklist above: dispatch into a real room, the real recognizer and synthesizer, the turn detector on real Korean speech, and the latency.

## Files

| File | Purpose |
|---|---|
| `runner.py` | The interview loop over the engine; store then speak; stop rules; the per-turn model call |
| `controller.py` | The conversation rules around the runner (opening, one answer at a time, silence, status poll, ending), independent of LiveKit |
| `voice.py` | The LiveKit worker: the session without an LLM, the masking STT node, the hook, the room options, dispatch by name, shutdown |
| `timing.py` | The numbers-only timing report of a voice session |
| `backend_client.py` | The internal API for one session: secret and room headers, retries with the same payload, answers sorted into what to do |
| `turn_model.py` | The Groq client with the `LLMClient` shape that `ask` uses; the one module that talks to a model |
| `rooms.py` | The room name of a session, `HMAC-SHA256(secret, session id)`, and the dispatch metadata (the backend computes the same room) |
| `config.py` | Settings from the environment |
| `text_cli.py` | The text driver |
| `devclient/` | The developer test page and its server (localhost only; forwards `/api/`, never `/api/internal/`) |
| `tests/` | Offline tests (agent environment) |
