# AI avatar interview: standalone proof of concept (Phase 1)

An experimental **seeker practice interview** with an AI avatar. It extends CareerSync's interview preparation idea
(`docs/DECISIONS.md` D21) but is **not** an employer-facing screening tool and makes **no** scoring, ranking or hiring
decision. It uses **synthetic data only**. Nothing here touches the CareerSync app, database, auth or Docker setup, and no
file in this folder imports `app.*` or `ai.*`.

> **Temporary standalone LLM integration.** This PoC calls **Groq** through **LiveKit's official Groq plugin**
> (`livekit-plugins-groq`) with the key passed explicitly (`api_key=`, from `GROQ_API_KEY`), because a live voice loop needs a
> streaming-capable client and CareerSync's `ai/llm/client.py` (the only LLM gateway of the app, AI rule 2, Anthropic-based)
> is untouched. It is not a decision for the product (D5 still names Claude for CareerSync; see Q34 in `docs/DECISIONS.md`).
> The model is `LLM_MODEL` (default `openai/gpt-oss-120b`); if it fails, the session says so and ends. It never falls back to
> another model. **No Anthropic API is called anywhere in this folder** (a test checks the files and the installed packages).

## What it does

1. The AI greets and discloses that it is an AI avatar (spoken, on the page, and as Anam's watermark).
2. It asks one predefined technical question (REST API idempotency).
3. The candidate answers by voice. Speech is transcribed (Korean), **personal data is masked**, and only masked text goes on.
4. The LLM writes one follow-up question; code screens it (protected topics, verdict words) before it is spoken.
5. The candidate answers again; the LLM writes a short closing reply (screened); the session ends.
6. About three minutes at most (Anam Free plan limit): wrap-up at 140 s, hard stop at 168 s, 30 s silence timeout.

```
Browser (static page)  --mic only-->  LiveKit Cloud  -->  agent.py (LiveKit Agents 1.8.12)
   ^  avatar video+audio  <------------------------------   STT (Inference, Deepgram nova-3, ko)
   |  masked transcript lines (poc.event)                    mask personal data -> conductor.py
   |                                                         Groq LLM (LiveKit Groq plugin) -> screen -> TTS (Inference, Cartesia sonic-3, ko)
token_server.py (127.0.0.1)  mints a mic-only token         Anam avatar (lip-synced audio+video published into the room)
```

## Privacy rules (what is enforced, where)

| Rule | How |
|---|---|
| No audio or video recorded or stored by the PoC | No code writes media. `session.start(record=False)` turns off LiveKit Cloud's audio, transcript, trace and log upload (its default follows a project setting). |
| Camera preview is local only | `app.js` opens the camera with `getUserMedia` for a muted `<video>`; it never publishes a camera track. The token allows only `microphone` (`can_publish_sources`), so LiveKit refuses any other track. |
| Microphone audio only | Only the microphone is published. The agent subscribes to audio only (`AutoSubscribe.AUDIO_ONLY`, no video input). The page lets **only the interviewer agent** subscribe to the microphone (`setTrackSubscriptionPermissions`), not the Anam avatar worker (the Anam plugin gives that participant default, subscribe-capable grants). `?open=1` turns this off for debugging. |
| Masked text only to the LLM | `guards.mask_spoken_pii` runs in the STT node (interim and final transcripts), again in the turn hook, and again in the conductor; the LLM sees a fixed prompt, the predefined question and the masked answers, nothing else. Preemptive replies are off. |
| Candidate audio reaches LiveKit Inference on **two** paths | Masking works on text, not on audio, so the raw voice cannot be masked. It already goes to LiveKit Inference for speech recognition (Deepgram nova-3). Since the turn detector is pinned to `v1` (`TURN_DETECTOR_VERSION`), the same audio is streamed a **second** time to LiveKit Inference for end-of-turn detection (a second connection to the same LiveKit gateway; the PoC itself stores nothing). Besides audio, `v1` also receives the text of the last assistant message in the chat context, and there is none today because the interviewer's lines are spoken with `add_to_chat_ctx=False`. LiveKit lists zero data retention for Inference on every plan (pricing page, read 2026-11-15); that is LiveKit's statement, not something this code can check. If the detector falls back to `v1-mini`, that audio path stays on the machine. See "Turn-taking" below. The page's notice already names LiveKit for speech recognition but does not mention turn detection: update it before anyone other than the developer (or a non-synthetic person) uses the PoC. |
| No raw PII on disk or in logs | Transcript is masked, kept in memory, shown on the page. Logs and the run report hold timings and counts only. (`--log-level debug` is the exception: the SDK then prints transcript lines to the local console. The ones read in the SDK source come after the STT node and are masked, but an SDK error line can carry raw provider data, so keep such a log local and delete it.) |
| AI disclosure | Spoken greeting, page banner, `show_ai_avatar_disclosure=True`. |
| LLM only when explicit | The agent refuses to start unless `AI_MODE=llm` is set (`docs/DECISIONS.md` D5, D12), even with a key. |

Masking is best effort (like `docs/DECISIONS.md` D39): email, phone (digits and spoken digits), URL, resident registration
number, labeled birth date, names the candidate introduces ("제 이름은 …", "my name is …") and names in `POC_MASK_NAMES`.
A name said without any introduction is not found. Lines about age, gender or military service are not masked (same open
question as Q24 in `docs/DECISIONS.md`).

## LLM: Groq, and why `openai/gpt-oss-120b`

Checked on 2026-11-15 against the LiveKit Groq LLM plugin guide, the plugin source at the `livekit-agents@1.8.12` tag and
Groq's public model pages (`livekit-plugins-groq` 1.8.12 is installed through the `livekit-agents[groq]` extra). No Groq API call was made for this.

| | `openai/gpt-oss-120b` (**default**) | `llama-3.3-70b-versatile` (the plugin's own default) |
|---|---|---|
| In the plugin's `LLMModels` list | yes | yes |
| Groq status | Production | Listed as Production on the models page; its model page says "Enterprise" |
| Speed (Groq) | about 500 tokens/s | about 280 tokens/s |
| Max output | 65,536 tokens | 32,768 tokens |
| Price per 1M tokens | $0.15 input / $0.60 output | not listed on the page |
| Korean | Groq cites 81+ languages (MMMLU 81.3%) | not mentioned on Groq's page |
| Reasoning | yes: `reasoning_effort` low / medium / high; the PoC sends `low` | none, so no `reasoning_effort` is sent |

Why gpt-oss-120b: a Korean interview needs Korean quality first, and it is the only candidate with a stated multilingual
claim; it is also faster, cheaper and production-tier. The cost is reasoning latency before the first spoken token, and this is
**not measured yet**: `verify_llm.py` prints `ttft` and `total` for the live check. Not verified in the docs: whether reasoning
tokens count against `max_completion_tokens` (so the budget is 1024, and the prompts keep the reply to one or two sentences),
and where streamed reasoning appears (the plugin keeps only `content`, so reasoning is never spoken; an empty answer is `empty_output`).
To compare another model, set `LLM_MODEL` for one run (no code change, no automatic fallback; see "Run").

## Checked against the official LiveKit docs

Looked up through the LiveKit Docs MCP (`https://docs.livekit.io/mcp/`) and the installed livekit-agents 1.8.12 source (the
source wins where they differ). Page paths are relative to `https://docs.livekit.io`.

| What the PoC does | Documented in |
|---|---|
| `session.start(record=False)` uploads no audio, transcript, trace or log; omitting `record` follows the project setting | `/reference/agents/session-recording-options/` |
| `stt_node` override with `Agent.default.stt_node`; edit `new_message.content`; raise `StopResponse` to skip the reply | `/agents/logic/nodes/`, `/agents/logic/turns/` |
| Preemptive generation is on by default; `turn_handling={"preemptive_generation": {"enabled": False}}` turns it off | `/agents/multimodality/audio/` |
| Avatar: `avatar.start` → `wait_for_join()` → `session.start` with audio output disabled; the worker is kind `agent` with attribute `lk.publish_on_behalf`; it leaves with the job | `/agents/models/avatar/` |
| `ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)`, `participant_attributes_changed`, `participant.attributes` | `/agents/server/job/` |
| `session.shutdown(drain=True)` (non-blocking), `ctx.delete_room()`, shutdown hooks (10 s budget), `delete_room_on_close` | `/agents/server/job/`, `/agents/logic/sessions/` |
| `close_on_disconnect` closes the session only for CLIENT_INITIATED, ROOM_DELETED, USER_REJECTED, so the PoC also ends on any candidate departure | `/agents/logic/sessions/` |
| `session.say(text, allow_interruptions=False, add_to_chat_ctx=False)` and its speech handle | `/agents/multimodality/audio/`, `/agents/logic/nodes/` |
| `server.setup_fnc = prewarm`, `@server.rtc_session(agent_name=...)` | `/agents/server/options/` |
| Token: `canPublishSources` (camera, microphone, screen_share, screen_share_audio), `canUpdateOwnMetadata`, `RoomConfiguration` agent dispatch, short TTL | `/frontends/reference/tokens-grants/`, `/transport/data/state/participant-attributes/` |
| `setTrackSubscriptionPermissions(false, [{participantIdentity, allowAll: true}])` | `/transport/media/publish/` |
| Korean is supported by the default audio turn detector | `/agents/logic/turns/turn-detector/` |
| Metric meanings (`transcription_delay`, `end_of_turn_delay`, `e2e_latency`, `llm_node_ttft`, `tts_node_ttfb`) | `/reference/api/projects/sessions/observability/` |
| Groq as the LLM: `from livekit.plugins import groq`, `groq.LLM(model=...)`, `GROQ_API_KEY`, parameters | `/agents/models/llm/groq/` |

Changes the review led to: `delete_room_on_close=True`, ending on any candidate departure, identifying the avatar worker by
`lk.publish_on_behalf` (the identity stays as a second guard), and a fix so a repeated `abort` cannot overwrite the ended state.

Not verified against docs or a run: the live behaviour of the subscription restriction, the Cartesia Korean voice, and the
Anam Korean lip-sync. The docs now present `lk agent dev|start|console` as the way to run an agent; `python agent.py start`
runs the same worker (checked with the pinned SDK), and the `lk` CLI is not installed here.

## Setup (once)

PowerShell, from the repo root. Uses its own virtualenv; the CareerSync environment is never touched.

```powershell
py -3.12 -m venv interview_poc\.venv
interview_poc\.venv\Scripts\python.exe -m pip install -r interview_poc\requirements-dev.txt
Copy-Item interview_poc\.env.example interview_poc\.env     # then fill in interview_poc\.env (git-ignored)
```

Environment variables (names only; values go in `interview_poc/.env`, never in source code):

| Name | Needed for | Note |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | agent, token server | LiveKit Cloud project |
| `ANAM_API_KEY`, `ANAM_AVATAR_ID` | agent (avatar on) | stock avatar id from the Anam Avatar Gallery |
| `GROQ_API_KEY`, `AI_MODE=llm` | agent, `verify_llm.py` | Groq key from https://console.groq.com/keys. `LLM_API_KEY` is no longer read. |
| `LLM_MODEL` | optional | default `openai/gpt-oss-120b`; a name starting with `claude` is refused (this PoC calls Groq only) |
| `POC_AVATAR` | optional | `on` (default) or `off` (audio only) |
| `POC_TTS_VOICE` | optional | Cartesia voice id; the default is a documented sample voice, not a verified Korean one |
| `POC_LLM_REASONING_EFFORT` | optional | `low`, `medium`, `high`. Unset: `low` for `openai/gpt-oss-*` models, nothing for other models |
| `POC_MASK_NAMES` | optional | comma-separated synthetic names to mask |

Only `interview_poc/.env` is read; the repo-root `.env` is never loaded.

## Run, in the order of the plan

Run from `interview_poc/` with the virtualenv (`$py = ".venv\Scripts\python.exe"`).

```powershell
cd interview_poc
$py = ".venv\Scripts\python.exe"
& $py -m pytest tests -q            # offline tests, no key needed
& $py check_livekit.py              # Task 3: LiveKit URL, key and secret work, a client can join and leave
& $py verify_llm.py                 # Task 5 (LLM): a model-list lookup and two tiny real Groq calls; needs GROQ_API_KEY
```

Compare another Groq model for one run (nothing is changed on disk, nothing falls back automatically):

```powershell
$env:LLM_MODEL = "llama-3.3-70b-versatile"; & $py verify_llm.py; Remove-Item Env:LLM_MODEL
```

Audio-only first (Tasks 4–5: Korean STT, LLM answer, Korean TTS), then with the avatar (Task 6):

```powershell
$env:POC_AVATAR = "off"; & $py agent.py start     # terminal 1 (audio only); waits for a room, Ctrl+C stops it
& $py token_server.py                             # terminal 2 -> http://127.0.0.1:8787/
# later, avatar on (terminal 1):  Remove-Item Env:POC_AVATAR; & $py agent.py start
```

Use `start`: in livekit-agents 1.8.12 `agent.py dev` still works but prints a deprecation notice and has no hot reload (the
recommended replacement, `lk agent dev`, needs the LiveKit CLI, which is not installed here and was not tried).
`& $py agent.py download-files` downloads local models if a first run asks for them. Open `http://127.0.0.1:8787/` in
Chrome, tick the box, press **면접 시작**, allow the microphone and camera.

## Manual checks (these need a browser, a microphone and your keys)

Each session also writes `interview_poc/.runs/session-<time>.json` (timings only) and the page shows its own figures.

| Check | How to judge |
|---|---|
| Local camera preview, mic access | Preview shows you; the status line says the microphone is on. |
| Avatar joins | Video appears within ~35 s, otherwise the page shows an error. |
| Lip synchronization | Rate 1–5 over the greeting and the follow-up: mouth opens with the first syllable (not before or after), closes in pauses, no drift over a long sentence. Note the avatar's Korean mouth shapes separately from timing. |
| Korean STT / TTS | Say the sample answer; the page's transcript matches what you said; the Korean voice sounds natural (change `POC_TTS_VOICE` if not). |
| Relevant follow-up | The follow-up builds on something you actually said. |
| PII masking | Say "제 이름은 김철수이고 번호는 공일공 …": the page shows `[이름]` and `[전화번호]`. |
| Safe ending | The AI ends the session itself; the End button works; closing the tab ends it; a second start works afterwards. |

Figures to report (from the run report and the page): speech recognition latency (`stt_transcription_delay_s`,
`end_of_utterance_delay_s`), LLM latency (`llm_ttft_s`, `llm_total_s`), time to first avatar audio
(`time_to_first_avatar_audio_s`, `say_to_avatar_audio_s`, `user_stopped_to_avatar_audio_s`, and the page's "첫 소리"
and "응답 지연"), total session length (`total_session_seconds`), and the turn detector (`turn_detector.model_at_end`,
`fell_back`, `cloud_predictions`).

## Turn-taking: when the candidate's turn ends

The session uses LiveKit's audio turn detector on top of Silero VAD (unchanged SDK defaults). Settings, in `config.py` and
`build_session` in `agent.py`:

| Setting | Value | Meaning |
|---|---|---|
| `TURN_DETECTOR_VERSION` | `"v1"` | The full model, served by LiveKit Inference. Pinned on purpose: without a version, `agent.py start` silently runs the local `v1-mini` (only `dev` and `console` pick `v1`). Korean is supported. |
| `local_fallback` | `True` (set in `agent.py`) | If Inference fails, times out (about 1 s) or the quota is used up, the SDK moves the session to the local `v1-mini` for the rest of that session. |
| `ENDPOINTING_MIN_DELAY_SECONDS` | `3.0` | Wait after the candidate's last speech when the detector thinks the sentence is complete. |
| `ENDPOINTING_MAX_DELAY_SECONDS` | `6.0` | Wait when the detector thinks the candidate is not done. After this the turn ends whatever the detector says. |

Both delays count from the candidate's last speech, not from the end of Silero's own 0.55 s silence window. History: the SDK
default `min_delay` (0.3 s, `max_delay` 2.5 s) is below 0.55 s, so it never delayed anything and a one-second thinking pause
ended the turn. At 1.5 s / 5.0 s the 2026-11-15 15:24 UTC run still ended both turns after about 1.5 s of silence (read from the
report: `user_stopped_to_avatar_audio_s` 2.83 and 2.86 s minus the LLM and speech start, plus Silero's 0.55 s), so the detector
had rated those pauses complete and the wait ended at `min_delay`. Hence the longer delays and the full `v1` model (LiveKit's
public end-of-turn benchmark, English table: 4.5 % false cutoffs at 600 ms for `v1` against 12.1 % for `v1-mini`; no Korean or
non-native figure was found).

Latency: with 1.5 s a finished answer got its reply about 3.4 s after the candidate's last word (`user_stopped_to_avatar_audio_s`
2.83–2.86 s). With 3.0 s expect about 4.9 s after the last word (`user_stopped_to_avatar_audio_s` about 4.3–4.4 s), and up to
about 7.9 s when the candidate trails off (6 s plus the LLM and speech start). These are estimates until the checklist below
is run. A pause longer than `min_delay` after a complete-sounding clause still ends the turn.

### `v1` sends audio to LiveKit Inference, and uses the monthly allowance

- **Privacy:** see the "two paths" row of the privacy table. The candidate's raw audio is streamed to LiveKit Inference a second
  time for turn detection. A fallback to `v1-mini` keeps that path on the machine.
- **Quota:** this PoC is a self-hosted agent (you run `agent.py start`), so `v1` draws on the project's **development
  allowance of 7,500 predictions per month** (LiveKit "Quotas and limits", read 2026-11-15; the allowance is per project and
  resets on the first of each month). A prediction is requested each time the candidate pauses for 200 ms or longer, and it
  counts even if they resume before the answer returns. Rough use: 20–60 per two-answer interview (an estimate from the SDK
  code and ordinary speech; hesitant speech gives more), so about 125–375 interviews a month. The run report counts the answered
  ones in `turn_detector.cloud_predictions` (a lower bound: a request that times out sends no metric).
- **Past the allowance:** on the Build plan LiveKit Inference rejects the requests and the session falls back to `v1-mini`; on
  Ship and Scale usage beyond it is billed at $0.50 per 1,000 predictions. This project's plan is not recorded in the repo:
  check the LiveKit Cloud dashboard (Settings, Project) for the plan and the remaining allowance.
- **Fallback is never silent:** the SDK logs one warning when it falls back. The agent also logs
  `turn detector fell back: turn-detector-v1 -> turn-detector-v1-mini (noticed at …)` and writes the `turn_detector` section of
  the run report: `requested`, `model_at_start`, `model_at_end`, `fell_back`, `fallback_at_s` (only after a fallback) and
  `cloud_predictions`. The model is read from the detector's public `model` after each session event and once more at
  shutdown, so a fallback is noticed within one event; it cannot be read in the middle of a prediction.
- The agent logs `turn detection: requested=v1, local_fallback=on, model=turn-detector-v1, endpointing min=3.0s max=6.0s` once
  at the start. An explicit `v1` needs `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`: without them the session setup stops with an
  error instead of starting on `v1-mini`.

### Live checklist for the end of turn (real microphone, your keys, no automated test covers this)

Why live: the offline tests only prove the configuration and the fallback bookkeeping; they do not run VAD, STT or the detector
on real audio. Use `POC_AVATAR=off` (audio only, no Anam minutes) for tuning; the avatar does not change the turn logic. One
session has two candidate turns, so two sessions cover four cases. The figures come from `.runs/session-<time>.json`:
`user_stopped_to_avatar_audio_s` per turn, and the `turn_detector` section. (`end_of_utterance_delay_s` was absent from the
reports of the 2026-11-15 runs.) Each session uses roughly 20–60 of the 7,500 monthly `v1` predictions.

Run from `interview_poc/` (PowerShell), terminal 1, then terminal 2 as in "Run":

```powershell
& $py -m pytest tests -q                       # offline first
$env:POC_AVATAR = "off"; & $py agent.py start  # terminal 1; `Remove-Item Env:POC_AVATAR` afterwards
& $py token_server.py                          # terminal 2, then open http://127.0.0.1:8787/
```

1. **Start check.** In the agent log, find
   `turn detection: requested=v1, local_fallback=on, model=turn-detector-v1, endpointing min=3.0s max=6.0s`.
   If the agent stops with an error naming `LIVEKIT_API_KEY`, the credentials are missing from `interview_poc/.env`.
2. **Session 1, answer 1, pause inside the answer.** Say one clause, stay silent for about one second (count "하나, 둘"),
   then finish the sentence. Pass: the interviewer says nothing during the pause, and the page shows **one** candidate line
   with both parts. Fail: a follow-up starts, or the answer is split in two (the second half is dropped).
3. **Session 1, answer 2, clean ending.** Answer in full, end on a clear sentence ending and stay silent. Time it with a
   stopwatch. Pass: the interviewer's voice starts about 5 s after your last word (3 s of silence, the LLM, then speech); the
   report shows `user_stopped_to_avatar_audio_s` of about 4.3–4.4 s (it was 2.83–2.86 s at 1.5 s).
4. **Session 2, answer 1, long pause inside the answer.** Say one clause, stay silent for about **2.5 s**, then finish the
   sentence. Pass: one candidate line (2.5 s is inside the 3.0 s window). A pause of 3.5 s or more is expected to end the turn.
5. **Session 2, answer 2, trailing off.** Stop mid-thought ("그래서 멱등성은 …") and stay silent. Pass: the turn does not end
   before about 3 s, and ends by about 6 s after your last word.
6. **After each session, read the report.** In `turn_detector`: `model_at_end` must be `turn-detector-v1` with
   `fell_back: false` and `cloud_predictions` above 0. If `fell_back` is true, part of that session ran on `v1-mini`
   (`fallback_at_s` says when, and the agent log has the line `turn detector fell back: …`): do not count it as a `v1` result,
   and look for the SDK's own warning just above it (a timeout, a connection error or a used-up quota). If `cloud_predictions`
   is 0 with `fell_back: false`, no prediction was answered: check the log for `turn detection transport latency is too high`.
7. **Repeat the one-second pause (step 2) two more times** if it passed; three of three is the bar. Record per turn: the model,
   `user_stopped_to_avatar_audio_s`, and pass or fail.

If a turn is still split, find out why before changing anything: restart the agent with `--log-level debug` and save it
(`& $py agent.py start --log-level debug 2>&1 | Tee-Object .runs\agent-debug.log`; `.runs/` is git-ignored, delete the file
afterwards, see the privacy table), repeat the same pause, and read the lines `eot prediction` (probability, threshold and the
delay used) and `user turn committed` (`delay_completed`, `end_of_turn_probability`). A probability above the threshold means
the detector called the pause complete and the wait ended at `min_delay`; a probability below it means the wait ran to
`max_delay` (real silence for 6 s). If it feels too slow instead, lower both delays in `config.py` (for example 2.5 s / 5.0 s)
and update `tests/test_agent_wiring.py`. Change nothing else (interruption, VAD, STT) before this evidence is in.

## Files

| File | Purpose |
|---|---|
| `agent.py` | LiveKit agent: STT node masking, turn hook, avatar start, `record=False`, shutdown |
| `conductor.py` | The interview flow, timers and ending (no LiveKit; unit-tested) |
| `groq_llm.py` | `VoiceGroq`: the Groq plugin's LLM with the PoC defaults (token budget, explicit reasoning effort); `complete_text` |
| `guards.py` | PII masking and the output screens |
| `prompts.py` | The Korean script and the two LLM prompts |
| `metrics.py` | Timing report (numbers only) |
| `config.py` | Settings (environment variables, this folder's `.env` only) |
| `token_server.py` | Static page server and mic-only LiveKit token endpoint (127.0.0.1) |
| `check_livekit.py`, `verify_llm.py` | Live checks for Tasks 3 and 5 |
| `web/` | The static meeting page (`livekit-client` 2.24.1 from a pinned CDN URL with an SRI hash) |
| `tests/` | Offline tests |
| `requirements.txt`, `requirements.lock.txt` | Direct pins and the full resolved set |

## Known limits

- Anam Free plan: 30 minutes per month, 3 minutes per session, one session at a time (the token server allows one).
- No Korean Cartesia voice is documented; Korean voice quality and avatar Korean lip-sync are unverified until tried.
- The Groq model has not been called yet: its Korean quality, its time to first token with reasoning, and whether 1024 tokens
  is enough for reasoning plus the answer are unverified until `verify_llm.py` and a live run. The plugin does not report a
  `length` stop, so an answer cut at the limit would reach the output screen as it is.
- `tests/test_agent_pipeline.py` runs a real `AgentSession` offline (scripted STT, fake microphone) and proves that masking sits
  on the audio path (STT node → turn hook → conductor). It does not cover VAD, the real STT/TTS services, the avatar or the
  browser; those need a live run. (Text input skips `on_user_turn_completed`, so text-mode tests cannot cover this path.)
- The end-of-turn setup (`v1`, 3.0 s / 6.0 s) comes from the SDK source, LiveKit's documentation and run reports; it is not yet
  confirmed with real audio (see the live checklist). `v1` is not measured for Korean or for non-native speech, and a long pause
  (about 3 s or more) still ends a turn. A candidate who keeps talking after a premature end of turn is not recovered: the
  interviewer's speech is not interruptible and audio during it is discarded.
- `v1` needs the LiveKit project's development allowance (7,500 predictions a month) and the LiveKit plan is not recorded
  here; after the allowance the Build plan falls back to `v1-mini`, which the run report shows (`turn_detector.fell_back`).
- `livekit-api` stays below 2 because `livekit-agents` 1.8.12 requires it.
