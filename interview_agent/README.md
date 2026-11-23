# Interview Agent (M5)

The realtime interviewer of the seeker practice interview (`docs/DECISIONS.md` D51–D58, D80, D81). It is a separate runtime with its own
virtual environment (D56). It runs the engine of `ai/interview/` in-process and reaches the backend only through the internal agent API. It never
touches the database and never imports the backend. Stages S0 to S5 exist: the agent core, a text driver, the consent-withdrawal rule, the
audio-only LiveKit voice worker with a developer test page, and the Compose `agent` service. The voice worker ran once live (22/11/2026: C1, C3
and C4 passed; the numbers are in `PROJECT_PROGRESS.md` §5.9); the other checks under "Live run" are still to do. The Compose image has not
been built or run yet.

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
- **Consent withdrawal** (D81, Q39). The backend ends the seeker's active sessions when the AI consent is withdrawn, so the next post is refused
  and the runner stops. In `AI_MODE=llm` the runner also reads the context right before every model call (one attempt, no retry): an ended session
  stops it; an active session whose seeker has no current consent gets an aborted end and a stop; an unreadable context means no model call for that
  turn. A call already running may finish, but its answer is refused when posted and nothing of it is stored.
- **The model** (D52, D80 (5), D83). Groq `openai/gpt-oss-120b`, through the LiveKit Groq plugin, only in `AI_MODE=llm`. A turn goes only through
  `prepare_turn` → `ai.interview.boundary.ask` → `parse_turn`. `turn_model.py` sends exactly `ModelInput.system` and `ModelInput.user`. The per-turn
  timeout defaults to 3 s and is never above the session's limit. After a timeout, an error or an invalid answer, the engine's rules decide at once.
- **The voice session has no LLM.** `AgentSession` is built without `llm`: the SDK then still runs the hook that receives the answer and skips the
  reply, so no transcript can reach a model except through `turn_model`. LiveKit's speech services are not LLMs (D80, Q35).
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

PowerShell, from the repository root. Python 3.12. The versions are pinned (D79).

```powershell
py -3.12 -m venv interview_agent\.venv
interview_agent\.venv\Scripts\python.exe -m pip install -r interview_agent\requirements-dev.txt
interview_agent\.venv\Scripts\python.exe -m interview_agent.voice download-files   # local models (Silero, the v1-mini fallback), before the first live run
```

`requirements.txt` holds the direct pins. `requirements.lock.txt` holds the full resolved set (`pip install -r interview_agent\requirements.lock.txt`
reinstalls it exactly). `livekit-agents` stays at 1.8.12 (D79).

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

## Run it with Docker Compose

`docker compose --profile voice up --build -d` starts the agent next to the backend (service `agent`, built from `interview_agent/Dockerfile`; a
plain `docker compose up` leaves it out and needs no LiveKit key). The step-by-step walk-through, with the test page, is in
[`docs/how-to/run-locally.md`](../docs/how-to/run-locally.md#voice-interview-with-docker-compose). What matters here:

- **Variables.** The container reads no `.env`. Compose takes `INTERVIEW_AGENT_SECRET`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
  `GROQ_API_KEY` and `INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS` from the repository `.env` or the shell and hands them to the agent (the backend gets
  the secret and the three `LIVEKIT_*` names), and sets `INTERVIEW_AGENT_BACKEND_URL=http://backend:8000` itself. Every other variable of the
  table above keeps its default under Compose.
- **The agent's mode.** `INTERVIEW_AGENT_AI_MODE` (`rules` or `llm`) is read by Compose only: the container's `AI_MODE` is that value when it is
  set, otherwise the backend's `AI_MODE`. So the agent can run `llm` (Groq) while the backend runs `rules` and needs no Anthropic key. Shell
  variables win over `.env`; the backend and the agent can only differ when the shell or `.env` says so.
- **Change only the agent.** Set the variable, then `docker compose --profile voice up -d --no-deps agent`. `--no-deps` leaves the backend alone
  even when your shell differs from the one you started in.
- **Models.** `python -m livekit.agents download-files` runs at build time and a second command loads Silero VAD and the local turn-detector
  fallback, so a missing model file fails the build. In livekit-agents 1.8.12 nothing is downloaded (Silero ships in its wheel, `v1-mini` in
  `livekit-local-inference`); the check is what the build gives you. The speech models run in LiveKit Inference, not in the image.
- **Health.** The worker's own endpoint (port 8081 in the container) is the image's healthcheck: `healthy` means registered with LiveKit.
  An agent that keeps restarting has a missing or short variable; `docker compose --profile voice logs agent` names it (never its value).
- **Reports.** Timing reports are written in the container (`/app/interview_agent/.runs`) and are lost with it. Copy them out before you
  recreate or remove the container: `docker compose --profile voice cp agent:/app/interview_agent/.runs/. interview_agent/.runs/`. The same
  numbers are logged as `session summary: {...}`.
- **Clock.** LiveKit rejects tokens when the clock is off by more than about a minute (`401`):
  [troubleshooting](../docs/how-to/troubleshooting.md#livekit-answers-401-in-the-voice-interview-although-the-keys-are-right).
- **The lock.** The image installs `requirements.lock.txt`, which was resolved on Windows. pip still resolves, so Linux-only packages are added,
  and `pip check` fails the build on a conflict; every pin has a Linux x86_64 wheel on PyPI (checked 23/11/2026), but a first build is the real
  test; the first Linux build succeeded on 23/11/2026. **Follow-up, still open (redone together with the later Dockerfile switch; the lock file made from the first build was removed):** freeze the set the image really has, so later builds are reproducible:

  ```powershell
  docker compose --profile voice run --rm -T --no-deps agent python -m pip freeze | Set-Content -Encoding utf8 interview_agent\requirements.linux.lock.txt
  ```

  Then install that file in the Dockerfile with `--no-deps` instead of the Windows lock, and keep `pip check`. The Windows lock stays the lock of
  the local virtual environment.

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

**Plan the sessions** (3 per account per day): the checks that are still open fit into four sessions on the Compose stack, set out step by step
under the table ("The remaining checks in four sessions"). The first session of 22/11/2026 (manual run, `seeker2@demo.test`) passed C1, C3 and C4.

**Status** (the results and their numbers are recorded in `PROJECT_PROGRESS.md` §5.9, "S4 live run" and "Live run on the Compose stack"): session 3
on 22/11/2026 (seeker2) passed C1, C3 and C4; C7 was not confirmed in it. Session 6 on 23/11/2026 (Compose, seeker3) ran C2 (a variant result), C5,
C6a and C7; the other checks have not run.

| # | Check | Do | Expect | Record | Status |
|---|---|---|---|---|---|
| C1 | Dispatch into a new room | Page: log in, tick the consent, job id, **면접 시작**. Allow the microphone | Within 20 s the page says the interviewer joined; the worker logs the session line; the greeting ("저는 CareerSync의 AI 면접관입니다 …") and then the first question are spoken | The page's "joined the room -> the interviewer (agent) joined" and "-> first interviewer audio track" seconds; the report's `opening.say_to_first_audio_s` | Passed (session 3) |
| C2 | Dispatch when the room already exists | LiveKit applies a token's room settings only when it creates the room. Session B. (1) Stop the worker (Ctrl+C). (2) Page, tab 1: start, so a room exists with no agent; wait for the 20 s error. (3) Start the worker again. (4) Tab 2: fill **기존 세션 번호** with that session's id and start: the room exists. (5) Close both tabs, wait 40 s (the empty room expires after 30 s), join that session again from the page | (3) the dispatch made when the room was created is still pending, so the agent joins that room when the worker registers (session 6: after 57.6 s); (4) a second join into the existing room makes no new dispatch of its own (LiveKit's documentation; not observed yet), so an agent seen then is the pending one from (2); (5) a new room is created and the agent arrives, if the session is still `created` (5 minutes from creation) | Whether an agent joined after (3), in (4) and in (5), and after how many seconds. If (5) fails, say so: the remedy (an explicit dispatch call from the backend) is not built | Variant result (session 6): steps (4) and (5) not done as written; with the worker stopped at the join, the agent joined the same existing room 57.6 s later, from the pending dispatch |
| C3 | Korean turn detection | Session A, answer each question in Korean. (a) One clause, silence ~1 s, then the rest, e.g. "멱등성은 같은 요청을 여러 번 보내도 결과가 같게 만드는 성질입니다 … (1 s) … 예를 들어 결제 요청에 멱등성 키를 붙였습니다." (b) Silence ~2.5 s inside an answer. (c) Silence ~3.5 s or more: the turn is expected to end. (d) Stop mid-thought ("그래서 멱등성은 …") and stay silent. Say nothing while the interviewer speaks | (a) and (b): one answer line on the page, no reply in between; (c) the turn ends; (d) it ends between about 3 and 6 s after your last word | Per turn, from the report: `endpointing_s`; `turn_detector.model_at_end` (must be `turn-detector-v1`) and `fell_back` (must be false); the number of answers the page shows split into two lines, and for which case | Passed (session 3) |
| C4 | End-to-end latency | Session A: answer each question normally in 15 to 40 s, stay silent when done, all five questions | The interviewer speaks after your last word | The report's `turns[].gap_s` (last word to first sound, the headline), and its parts `stt_final_after_stop_s` (the final transcript against the stop; negative is normal), `endpointing_s`, `processing_s` (Groq + engine + two posts), `tts_start_s`; `gap_s` min, median, max. Not judged here: no target is decided (the PoC estimated about 4.4 s at 3.0 s endpointing, without Groq) | Passed (session 3) |
| C5 | Groq timeout falls back to the rules | Session C: restart the worker with `$env:INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS = "0.2"`. Answer two questions. (Optionally first, with a wrong `GROQ_API_KEY`, to see `error:*`) | The interviewer still answers every time; the worker logs `turn analysis: timeout`; no error on the page | `llm_calls[].outcome` and `seconds` (`timeout` at ~0.2 s), `processing_s` of those turns. Then, with the 3 s default in session A: the share of `ok` against `timeout`, `error:*` and `rejected:*`, and the longest `seconds` | Passed (session 6: 3 of 3 `timeout` at 0.20 s) |
| C6a | The seeker's End stops the voice | Session C: while the interviewer is speaking, press **종료** | Speech stops; the page shows `aborted (seeker_ended)`; the worker exits the room | Seconds from the click to silence (up to about 5 s) | Passed functionally (session 6); seconds to silence not measured |
| C6b | Deleting a live session stops the voice | Session D: while the interviewer is speaking, `DELETE /api/interview-sessions/{id}` in Swagger (`/docs`, Authorize with the seeker's token) | The agent stops within about 5 s and the room is deleted | Seconds to silence; the worker's log line `runner stopped: gone` | Pending |
| C6c | Closing the tab ends it | Session E: close the browser tab mid-answer | The session reads `aborted` with `candidate_left`; no closing line | The end reason in the page of a new tab or `GET /api/interview-sessions`; seconds until it appears | Pending |
| C6d | Consent withdrawal stops it | Session F: `DELETE /api/users/me/consent/ai` in Swagger mid-interview; afterwards consent again (`POST /api/users/me/consent`) | The agent stops within about 5 s with no further model call; the session reads `aborted` (`consent_withdrawn`) | Seconds to silence; the worker log; no Groq call after the withdrawal | Pending |
| C7 | Masking in the live path | Session A: "제 이름은 홍길동이고 전화번호는 공일공 일이삼사 오육칠팔입니다 …" | The page's stored transcript shows `[이름]` and a phone placeholder, not the words | The page's line; confirm that the worker log holds no part of what you said | Done (session 6): own name, phone and email masked; a third-party name was misrecognized and not masked (recognizer limit, no change) |
| C8 | A second session after the first | Start a session right after one ended | It works, in a new room | Whether the first attempt after an ended session connected | Pending |

### The remaining checks in four sessions (Compose)

Open: C6b to C6d and C8 (session 6, the first session of this plan, ran C2 as a variant, C5, C6a and C7). The four ways a session can be stopped (C6a to C6d) each end one
session, so **four sessions** is the minimum; C2, C5, C7 and C8 ride along. Accounts: `seeker3@demo.test` for sessions 1 to 3 (its 3 sessions of
the day), then `seeker@demo.test`; every demo password is `demo1234`. Use only the synthetic sentences below. The quota is counted per
database, and the Compose database (host port 5434) is separate from a manual one (5433).

**Before session 1** (once). Window 1 is the Compose window: keep it open all day, because its variables decide what Compose passes on.

```powershell
# Window 1, repo root
$env:AI_MODE = "rules"                  # the backend: no Anthropic key needed
$env:INTERVIEW_AGENT_AI_MODE = "llm"    # the agent: Groq per turn (GROQ_API_KEY in .env)
docker compose --profile voice up --build -d
docker compose --profile voice ps -a                       # the agent reads "healthy" about a minute after it started
docker compose --profile voice logs agent                  # contains "registered worker"
docker compose --profile voice exec agent date -u          # compare with the next line: within a few seconds, or LiveKit answers 401
(Get-Date).ToUniversalTime()

# Window 2, repo root: the test page (standard library only), open http://127.0.0.1:8788/ in Chrome
python -m interview_agent.devclient.serve

# Window 3: helpers for the API calls of C6b to C6d
$base = "http://127.0.0.1:8000"
function Get-SeekerHeaders($email) {
    $body = @{ email = $email; password = "demo1234" } | ConvertTo-Json
    $login = Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -ContentType "application/json" -Body $body
    @{ Authorization = "Bearer $($login.access_token)" }
}
function Show-Sessions { (Invoke-RestMethod "$base/api/interview-sessions" -Headers $h).items | Select-Object id, status, end_reason, created_at }
```

On the page: log in, tick the consent, job id `1`, press **면접 시작** (Start interview), allow the microphone. **기존 세션 번호** (existing session
number) stays empty for a new session; **종료** (End) ends it. The status line shows `세션 N: …` (the session number N). A new session needs a
reloaded page (F5) and a new login. The join window of a created session is 5 minutes.

After every session, before you recreate the agent container, copy the timing reports out and collect the log lines (the commands are the same
each time; use the session's `--since`):

```powershell
docker compose --profile voice cp agent:/app/interview_agent/.runs/. interview_agent/.runs/
docker compose --profile voice logs --no-color --since 20m agent | Select-String "voice session|turn analysis|runner stopped|session summary|WARNING|ERROR|Traceback"
```

**Session 1: `seeker3@demo.test`, C2, C7, C5, C6a.** The agent runs `llm` with a 0.2 s model timeout from step 3.

1. Window 1: `docker compose --profile voice stop agent`. There is no worker now.
2. Page, tab 1: log in as seeker3, tick the consent, **면접 시작**. Note N. Leave tab 1 open: it keeps the room alive. The 5 minutes start now.
   Wait for the page's 20-second message (no interviewer arrived) before step 3.
3. Window 1: `$env:INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS = "0.2"`, then `docker compose --profile voice up -d --no-deps agent`. Wait until `ps` says healthy.
4. Tab 2 (a new tab on the same page address): log in, tick the consent, type N into **기존 세션 번호**, **면접 시작**. The room exists, so this join makes
   no new dispatch (LiveKit's documentation); an interviewer that joins now is the one still pending from step 2, delivered when the worker registered
   in step 3 (session 6: 57.6 s after tab 1 joined). **Record: did an interviewer join (yes or no), and when.** (C2 (3), (4))
5. Close tab 1 and tab 2. Wait 40 s: an empty room expires after 30 s. (C2 (5))
6. Tab 3: log in, tick the consent, type N, **면접 시작**. **Record the seconds** to "the interviewer joined" and to the first audio (the page's
   measurements). A 409 `INTERVIEW_NOT_JOINABLE` means the 5 minutes passed: record that, and do not repeat it with a new session. (C2 (5))
7. Answer the first question with this, in Korean, then stay silent (C7): "제 이름은 홍길동이고 전화번호는 공일공 일이삼사 오육칠팔입니다. 이메일은
   hong 골뱅이 example 점 com 입니다. 같이 일한 한도윤 님과 주문 API를 개발하면서 멱등성 키를 적용했습니다." When the interviewer has answered, the
   page's transcript line must read like "제 이름은 [이름]이고 전화번호는 [전화번호]입니다. 이메일은 [이메일] 입니다. …" with none of 홍길동, 한도윤 or the
   digits. The recognizer may write the number in digits: it is masked either way. **Record the line exactly as the page shows it.**
8. Answer the next two questions in full sentences, 15 to 30 s each (a very short answer is decided by the rules alone and asks no model). The
   interviewer must answer every time and the page shows no error. (C5)
9. While the interviewer is speaking its next line, press **종료**. **Record the seconds from the click to silence.** The page reads `aborted (seeker_ended)`. (C6a)

Send back: N; yes or no (step 4); the seconds (step 6); the transcript line (step 7); the seconds (step 9); the log lines of the command above
(`turn analysis: timeout in 0.2x s` for each answer that asked the model: a very short answer asks none and writes no such line; and `runner stopped: <reason>`); the report file `interview_agent/.runs/session-N-*.json`.

**Session 2: `seeker3@demo.test`, C8, C6b.** Do not restart anything between session 1 and 2 (C8 is about the same worker taking the next room).

1. Window 3: `$h = Get-SeekerHeaders "seeker3@demo.test"`. Reload the page, log in, tick the consent, **면접 시작** with **기존 세션 번호** empty, within a minute
   of the end of session 1. **Record whether the interviewer joined on this first attempt, and the seconds.** (C8) The session count is now 2 of 3.
2. Window 3: `$id = (Invoke-RestMethod "$base/api/interview-sessions" -Headers $h).active.id`
3. Answer the first question. When the interviewer starts speaking its next line, run
   `Invoke-RestMethod -Method Delete -Uri "$base/api/interview-sessions/$id" -Headers $h` and start counting. **Record the seconds to silence.** (C6b)
   The page shows an error about a session that is not found and stops.

Send back: yes or no and the seconds (step 1); the seconds (step 3); the log lines, which must hold `runner stopped: gone`; the report file.

**Session 3: `seeker3@demo.test`, C6c, and a voice interview through Compose in `rules` mode.**

1. Copy the reports and the logs of session 2 first (the commands above). Then Window 1:
   `$env:INTERVIEW_AGENT_AI_MODE = "rules"; Remove-Item Env:INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS; docker compose --profile voice up -d --no-deps agent`.
   Wait until healthy. A session's log line must now say `ai_mode=rules`.
2. Reload the page, log in as seeker3, tick the consent, **면접 시작** (the third session). Window 3:
   `$id = (Invoke-RestMethod "$base/api/interview-sessions" -Headers $h).active.id` (a 401 means the token of `$h` expired after 2 hours: run
   `Get-SeekerHeaders` again). Answer the first two questions normally: the interviewer must answer from the engine's rules, with no model call
   (`turn analysis` does not appear in the log).
3. While you are speaking a third answer, close the browser tab. (C6c) In Window 3, repeat `Show-Sessions` every few seconds. **Record the seconds until
   the session reads `aborted` with `candidate_left`**, and check that no interviewer line follows your last answer:
   `(Invoke-RestMethod "$base/api/interview-sessions/$id" -Headers $h).turns | Select-Object role, seq`.

Send back: the seconds, the end reason, the last turns' roles, the log lines, the report file. That the interview worked in `rules` mode is also the
"done" condition of stage S5.

**Session 4: `seeker@demo.test`, C6d.** The account has no CV: this part costs no interview session.

1. Browser, http://localhost:3000 (the Compose frontend): log in as `seeker@demo.test`, open 내 이력서 (My CV), upload `data/demo/demo_cv.pdf`, confirm it.
2. Copy the reports and the logs of session 3. Then Window 1: `$env:INTERVIEW_AGENT_AI_MODE = "llm"; docker compose --profile voice up -d --no-deps agent`
   (the timeout variable was removed in session 3, so the default of 3 s applies). Wait until healthy. Window 3: `$h = Get-SeekerHeaders "seeker@demo.test"`.
3. Test page: reload, log in as `seeker@demo.test`, tick the consent, **면접 시작**. Answer the first question normally (its model call should be `ok`).
4. When the interviewer starts speaking its next line, withdraw the AI consent and start counting, then stay silent:
   `Invoke-RestMethod -Method Delete -Uri "$base/api/users/me/consent/ai" -Headers $h` (C6d). **Record the seconds to silence.** The page must read
   `aborted (consent_withdrawn)`, and no model call may follow the withdrawal.
5. Give the consent back, so the account works again:
   `$me = Invoke-RestMethod -Uri "$base/api/users/me" -Headers $h`, then
   `Invoke-RestMethod -Method Post -Uri "$base/api/users/me/consent" -Headers $h -ContentType "application/json" -Body (@{ version = $me.current_consent_version; consent_privacy = $true; consent_ai = $true } | ConvertTo-Json)`.

Send back: the seconds; the page's last status line; the log lines (`runner stopped: consent_withdrawn`; no `turn analysis` line may come after the
withdrawal, so their number cannot exceed the answers you gave before it); the report file.

If something fails: write down what the page and the log said and stop; do not retry with a new session, each one is counted. If the first
build or the health check fails, send the output of `docker compose --profile voice logs agent` and `docker compose --profile voice build agent`.

If an agent does not join within 20 s: the worker is not running or is registered under another name (`INTERVIEW_AGENT_NAME`), the LiveKit project
differs between the backend's token and the worker, or the room already existed and its creation-time dispatch is spent (a join into an existing room makes no new dispatch; C2). A worker that was not running when the room was created still gets that room's pending dispatch once it registers (session 6: 57.6 s later), so start the worker and wait before joining again. If a join answers 503: a `LIVEKIT_*` or the agent secret is
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

The Compose wiring (the `voice` profile, the backend URL, the shared secret, the agent's mode variable, the two Dockerfiles, `.dockerignore`) is checked
statically by `backend/tests/docs/test_compose_agent.py`; it cannot build an image. The runner and the controller are also tested against the real
application in `backend/tests/test_interview_agent_runner.py` and
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
| `Dockerfile` | The Compose image: the pinned lock, `pip check`, the local-model check at build time, the worker as the command, its health endpoint as the healthcheck |
| `tests/` | Offline tests (agent environment) |
