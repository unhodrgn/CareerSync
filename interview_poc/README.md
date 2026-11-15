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
| No raw PII on disk or in logs | Transcript is masked, kept in memory, shown on the page. Logs and the run report hold timings and counts only. |
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
and "응답 지연"), total session length (`total_session_seconds`).

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
- `livekit-api` stays below 2 because `livekit-agents` 1.8.12 requires it.
