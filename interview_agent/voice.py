"""The LiveKit voice worker of the Interview Agent, audio only (M5 S4; docs/DECISIONS.md D52, D54, D55, D56, D62, D80).

Run, from the repository root with the agent's virtual environment and the environment variables of `interview_agent/README.md`:

    python -m interview_agent.voice start      the worker, waits for jobs (what the backend's join token dispatches)
    python -m interview_agent.voice dev        the same with reload (deprecated by the SDK in favor of `lk agent dev`)
    python -m interview_agent.voice console    talk to a session through this machine's microphone and speakers, no browser; the session
                                               is `INTERVIEW_AGENT_CONSOLE_SESSION_ID` (a console job carries no metadata)

What it is: a thin transport around `VoiceController` and `InterviewRunner`. The engine decides every line; the runner stores a line before it
is spoken; the controller says who may talk when. This module only connects them to a room:

    candidate microphone -> LiveKit Inference speech recognition (Korean) -> mask personal data (the STT node, again in the hook)
      -> turn detection (the audio turn detector `v1`, with the local `v1-mini` as the fallback) -> VoiceController.submit
      -> runner.answer: the engine, the per-turn Groq call or the rules, two posts to the backend -> LiveKit Inference speech synthesis

Rules kept here (and tested offline in interview_agent/tests):

- **The session has no LLM.** `AgentSession` is built without `llm`: with none, the SDK still runs `on_user_turn_completed` and then skips
  the reply. So no transcript can reach a model except through `turn_model` (D52, rule 2 of CLAUDE.md, D83). LiveKit's speech services
  (recognition, synthesis, turn detection, voice activity detection) are not LLMs and are governed by D80 and Q35.
- **No recording.** `session.start(record=False)`: nothing is uploaded to LiveKit Cloud (audio, transcript, traces, logs). Only the microphone
  is subscribed (`AutoSubscribe.AUDIO_ONLY`, no video input), and the token of the page allows a microphone track only.
- **Masked text only.** Every transcript, interim and final, is masked in the STT node before anything else sees it, and again in the hook.
- **Not interruptible, no preemptive reply.** The interviewer's lines are spoken with `allow_interruptions=False`; a reply never starts on an
  unfinished transcript (`preemptive_generation` off). While the interviewer speaks, the SDK does not deliver the candidate's turn.
- **Stops on a departure.** The candidate leaving for ANY reason (a dropped connection is not among the SDK's `close_on_disconnect` reasons)
  makes the runner post the aborted end; the room is deleted when the session closes, so a new join creates a room and dispatches again.
- **A failed setup deletes the room.** Any error before the session starts ends the job (`setup_failed`) and deletes the room, so the candidate
  can join the same session again within its join time (a new dispatch, no quota). Nothing was stored, and the backend cannot end a `created`
  session, so no end event is posted (Q in docs/DECISIONS.md).
- **Silence is not an error.** The tick is the controller's: nudge, skip, wrap-up, and the status poll of the session.

Written against livekit-agents 1.8.12 (D79). Nothing here runs without a LiveKit project; the offline tests cover the wiring and the audio
path with a scripted recognizer and a fake microphone, and the live checklist of `interview_agent/README.md` covers the rest.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any

import httpx
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, AutoSubscribe, JobContext, JobProcess, cli, inference, room_io
from livekit.agents.llm import StopResponse
from livekit.plugins import anam, silero

from ai.interview import mask_spoken
from interview_agent.backend_client import SessionClient
from interview_agent.config import TURN_DETECTOR_VERSION, ConfigError, VoiceSettings, agent_name_from_env, load_voice_settings
from interview_agent.controller import VoiceController
from interview_agent.rooms import session_id_from_metadata
from interview_agent.runner import InterviewRunner, Stopped
from interview_agent.timing import SessionTiming
from interview_agent.turn_model import GroqTurnClient  # at the top: imports the Groq plugin on the main thread when the worker starts

log = logging.getLogger("interview_agent.voice")

READY_ATTRIBUTE = "cs_ready"  # page -> agent: the browser is attached and can hear the interviewer
READY_TIMEOUT_SECONDS = 15.0
CLOSE_TIMEOUT_SECONDS = 15.0
TICK_SECONDS = 1.0
AVATAR_IDENTITY = "anam-avatar-agent"
PUBLISH_ON_BEHALF = "lk.publish_on_behalf"


def is_avatar_participant(participant: Any) -> bool:
    """True when participant is the Anam avatar worker rather than the candidate."""
    attrs = getattr(participant, "attributes", None) or {}
    return getattr(participant, "identity", None) == AVATAR_IDENTITY or bool(attrs.get(PUBLISH_ON_BEHALF))


def mask_event(event: Any, names: Iterable[str] = ()) -> int:
    """Mask the text of a speech recognizer event in place. Returns how many alternatives changed. A changed alternative loses its word
    timings, which would still hold the raw words."""
    names = tuple(names)
    changed = 0
    for alternative in getattr(event, "alternatives", None) or []:
        masked = mask_spoken(alternative.text, names).text
        if masked != alternative.text:
            alternative.text = masked
            if getattr(alternative, "words", None):
                alternative.words = None
            changed += 1
    return changed


class InterviewerAgent(Agent):
    """The agent object. It generates no reply: the controller speaks what the engine says, and this class only masks what is heard and hands
    each finished answer over."""

    def __init__(self, names: tuple[str, ...] = ()) -> None:
        super().__init__(instructions="Practice interviewer. Every line is produced by the interview engine, not by this prompt.")
        self.names = names
        self.on_turn: Callable[[str], object] | None = None

    async def stt_node(self, audio, model_settings):
        """Mask every transcript, interim and final, before anything else sees it: the events, the history, the logs."""
        async for event in Agent.default.stt_node(self, audio, model_settings):
            mask_event(event, self.names)
            yield event

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # Defence in depth: the STT node already masked this text. There is no LLM to reply (the session has none): the engine answers.
        masked = mask_spoken(new_message.text_content or "", self.names).text
        new_message.content = [masked]
        if self.on_turn is not None:
            self.on_turn(masked)
        raise StopResponse()


def build_session(settings: VoiceSettings, vad) -> AgentSession:
    return AgentSession(
        stt=inference.STT(settings.stt_model, language=settings.language),
        tts=inference.TTS(settings.tts_model, voice=settings.tts_voice, language=settings.language),
        vad=vad,
        # No `llm`: see the module docstring. The per-turn model call is `turn_model`'s, through the engine's `ask`.
        turn_handling={
            # The multi-language audio turn detector (supports English and Korean), asked for by version: without `version`, `start` would run the local v1-mini. v1 streams
            # the candidate's audio to LiveKit Inference a second time (Q35). With `local_fallback=True` a failure, a timeout or a used-up
            # allowance moves the session to v1-mini for the rest of it instead of ending turns on the delay alone; the report shows it.
            "turn_detection": inference.TurnDetector(version=TURN_DETECTOR_VERSION, local_fallback=True),
            # Give a candidate time to think between clauses. Both delays are set because the SDK fills a missing key with its shorter defaults.
            "endpointing": {"mode": "fixed", "min_delay": settings.endpoint_min, "max_delay": settings.endpoint_max},
            "preemptive_generation": {"enabled": False},
        },
    )


def room_options(*, avatar_active: bool = False) -> room_io.RoomOptions:
    return room_io.RoomOptions(
        audio_input=True,
        video_input=False,  # the candidate's camera is never used (and the token does not allow it)
        text_input=False,
        text_output=False,  # no automatic transcription topic: the page reads the stored, masked transcript from the backend
        # When Anam is active, TTS audio goes through the avatar worker; on fallback/audio-only the agent publishes directly (D90)
        audio_output=not avatar_active,
        close_on_disconnect=True,  # only for CLIENT_INITIATED, ROOM_DELETED, USER_REJECTED: the departure handler covers the rest
        delete_room_on_close=True,  # the room goes as soon as the session ends, so a new join dispatches again
    )


async def start_avatar(
    session: AgentSession,
    ctx: JobContext,
    settings: VoiceSettings,
    vad: Any,
    timing: SessionTiming,
) -> tuple[AgentSession, bool]:
    """Start Anam Avatar if enabled; rebuild a fresh AgentSession for audio-only on failure or missing keys (D90)."""
    mode = settings.avatar_mode
    if ctx.is_fake_job():
        timing.note_avatar(mode=mode, active=False, fallback_reason="console_mode")
        return session, False
    if not settings.avatar_requested:
        timing.note_avatar(mode=mode, active=False, fallback_reason="disabled")
        return session, False
    if not settings.avatar_enabled:
        if mode == "on":
            log.warning("avatar requested (INTERVIEW_AGENT_AVATAR=on) without ANAM_API_KEY/ANAM_AVATAR_ID; falling back to audio-only")
        timing.note_avatar(mode=mode, active=False, fallback_reason="missing_credentials")
        return session, False

    avatar = anam.AvatarSession(
        persona_config=anam.PersonaConfig(name="AI Interviewer", avatarId=settings.anam_avatar_id),
        session_options=anam.SessionOptions(show_ai_avatar_disclosure=True),
        api_key=settings.anam_api_key,
        avatar_participant_identity=AVATAR_IDENTITY,
    )
    started = time.monotonic()
    try:
        await avatar.start(session, room=ctx.room)
        await avatar.wait_for_join(timeout=settings.avatar_join_timeout)
    except Exception as error:  # noqa: BLE001  (audio-only fallback per D90; log type/status only, never key)
        code = f"avatar_{type(error).__name__}"
        log.warning(
            "avatar setup failed (%s, status=%s); falling back to audio-only",
            type(error).__name__,
            getattr(error, "status_code", None),
        )
        with contextlib.suppress(Exception):
            await avatar.aclose()
        # Rebuild a clean AgentSession so any partial DataStreamAudioOutput or listener hooked by start() is discarded
        fresh = build_session(settings, vad)
        timing.note_avatar(mode=mode, active=False, fallback_reason=code)
        return fresh, False
    timing.note_avatar(mode=mode, active=True, start_to_join_s=time.monotonic() - started)
    return session, True


def turn_detection_label(session: AgentSession) -> str:
    """The end-of-turn detector this session runs right now: `turn-detector-v1` (cloud) or `turn-detector-v1-mini` (local). The detector's
    public `model` follows a fallback: the SDK swaps it in place."""
    detector = session.turn_detection
    return str(getattr(detector, "model", detector))


async def wait_candidate_ready(room: rtc.Room, timeout: float = READY_TIMEOUT_SECONDS) -> bool:
    """Wait until a normal participant (the candidate) sets READY_ATTRIBUTE, so that the greeting is not spoken to nobody."""
    ready = asyncio.Event()

    def check(*_: Any) -> None:
        for participant in room.remote_participants.values():
            if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD and participant.attributes.get(READY_ATTRIBUTE) == "1":
                ready.set()

    room.on("participant_attributes_changed", check)
    room.on("participant_connected", check)
    try:
        check()
        await asyncio.wait_for(ready.wait(), timeout)
        return True
    except TimeoutError:
        log.warning("the candidate page did not report ready within %.0f s; starting anyway", timeout)
        return False
    finally:
        room.off("participant_attributes_changed", check)
        room.off("participant_connected", check)


def make_clients(agent_settings, loop: asyncio.AbstractEventLoop) -> tuple[httpx.AsyncClient, GroqTurnClient | None]:
    """The backend's HTTP client and, in the model mode, the Groq client. Runs in a worker thread: the plugin is already registered."""
    http = httpx.AsyncClient(base_url=agent_settings.backend_url, timeout=10.0)
    if not agent_settings.uses_model:
        return http, None
    model = GroqTurnClient(
        model=agent_settings.llm_model, timeout=agent_settings.llm_timeout, loop=loop,
        api_key=agent_settings.groq_api_key, reasoning_effort=agent_settings.reasoning_effort,
    )
    return http, model


async def run_voice_interview(ctx: JobContext) -> None:
    try:
        settings = load_voice_settings()
    except ConfigError as error:
        log.error("%s", error)
        ctx.shutdown(reason="configuration error")
        return
    fake = ctx.is_fake_job()  # `console`: no room, no metadata, no browser
    session_id = settings.console_session_id if fake else session_id_from_metadata(ctx.job.metadata)
    if session_id is None:
        log.error("the job names no session (metadata of a console job: set INTERVIEW_AGENT_CONSOLE_SESSION_ID)")
        ctx.shutdown(reason="no session id")
        return

    agent_settings = settings.agent
    # Both clients make an SSL context (0.2-0.6 s of blocking work): built in a thread while the room connects, not on the job's event loop
    clients = asyncio.create_task(asyncio.to_thread(make_clients, agent_settings, asyncio.get_running_loop()))
    timing = SessionTiming(session_id)
    timing.settings = {
        "stt_model": settings.stt_model, "tts_model": settings.tts_model, "endpointing_min_s": settings.endpoint_min,
        "endpointing_max_s": settings.endpoint_max, "turn_detector": TURN_DETECTOR_VERSION, "ai_mode": agent_settings.ai_mode,
        "llm_timeout_s": agent_settings.llm_timeout if agent_settings.uses_model else None, "console": fake,
    }
    runner: InterviewRunner | None = None
    controller: VoiceController | None = None
    session: AgentSession | None = None  # built after the runner has opened; the shutdown callback may run before

    async def on_shutdown(reason: str) -> None:
        timing.outcome = (controller.outcome if controller is not None else None) or reason or "job_shutdown"
        if runner is not None:
            timing.note_llm(runner.timings)
        if session is not None:
            timing.note_detector(requested=TURN_DETECTOR_VERSION, now=turn_detection_label(session))
        path = timing.write()
        log.info("timing report written to %s", path)
        log.info("session summary: %s", json.dumps(timing.summary(), ensure_ascii=False))  # numbers and codes only
        with contextlib.suppress(Exception):  # the clients may have failed to build: then there is nothing to close
            http, _model = await clients
            await http.aclose()
        try:
            await ctx.delete_room()  # the browser sees the end; a new join creates the room again and dispatches again
        except Exception:  # noqa: BLE001
            log.debug("room already gone", exc_info=True)

    ctx.add_shutdown_callback(on_shutdown)  # before anything that can fail, so a failed setup still deletes the room
    try:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        http, model = await clients
        client = SessionClient(http, agent_settings.secret, session_id, room=None if fake else ctx.room.name)
        runner = InterviewRunner(client, data_dir=agent_settings.data_dir, model=model, llm_timeout=agent_settings.llm_timeout)
        try:
            await runner.open()  # nothing is spoken for a session that is gone, over, or not joinable
        except Stopped as stop:
            log.info("not started: %s", stop.reason)
            ctx.shutdown(reason=f"not started: {stop.reason}")
            return

        vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
        session = build_session(settings, vad)
        session, avatar_active = await start_avatar(session, ctx, settings, vad, timing)
        agent = InterviewerAgent(runner.names)
        closed = asyncio.Event()
        background: set[asyncio.Task] = set()

        def spawn(coro) -> None:
            task = asyncio.create_task(coro)
            background.add(task)
            task.add_done_callback(background.discard)

        async def say(text: str) -> bool:
            try:
                handle = session.say(text, allow_interruptions=False, add_to_chat_ctx=False)
            except RuntimeError:
                log.warning("the session is closing; not speaking")
                return False
            try:
                await handle.wait_for_playout()
            except Exception:  # noqa: BLE001
                log.warning("speech failed", exc_info=True)
                return False
            return not handle.interrupted and handle.exception() is None

        controller = VoiceController(
            runner, say=say, interrupt=lambda: session.interrupt(force=True), status_poll_seconds=settings.status_poll, timing=timing
        )
        agent.on_turn = lambda text: (timing.mark("turn_committed"), controller.submit(text))
        timing.note_detector(requested=TURN_DETECTOR_VERSION, at_start=turn_detection_label(session))
        log.info(
            "voice session %s: stt=%s tts=%s detector=%s endpointing min=%.1fs max=%.1fs ai_mode=%s avatar=%s",
            session_id, settings.stt_model, settings.tts_model, turn_detection_label(session), settings.endpoint_min, settings.endpoint_max, agent_settings.ai_mode, "anam" if avatar_active else "audio_only",
        )

        def watch_detector(where: str) -> None:
            before = timing.detector.get("model_at_end") or timing.detector.get("model_at_start")
            now = turn_detection_label(session)
            timing.note_detector(requested=TURN_DETECTOR_VERSION, now=now)
            if before and now != before:
                log.warning("turn detector fell back: %s -> %s (noticed at %s); the rest of this session runs on the local model", before, now, where)

        @session.on("user_state_changed")
        def _user_state(event) -> None:
            watch_detector("user_state")
            controller.set_candidate_speaking(event.new_state == "speaking")
            if event.old_state == "speaking" and event.new_state != "speaking":
                timing.mark("user_stopped")

        @session.on("user_input_transcribed")
        def _transcribed(event) -> None:
            if event.is_final:
                timing.mark("stt_final")

        @session.on("agent_state_changed")
        def _agent_state(event) -> None:
            watch_detector("agent_state")
            if event.new_state == "speaking":
                timing.agent_started_speaking()

        @session.on("error")
        def _error(event) -> None:
            log.error("session error from %s: %s", type(event.source).__name__, type(event.error).__name__)  # types only: a message can quote data

        @session.on("close")
        def _close(event) -> None:
            closed.set()
            if not controller.done.is_set():
                spawn(controller.candidate_left(f"session_closed:{getattr(event.reason, 'value', event.reason)}"))

        def on_participant_disconnected(participant) -> None:
            if is_avatar_participant(participant):
                log.warning("avatar participant disconnected mid-session")
                if timing.avatar:
                    timing.avatar["disconnected_mid_session"] = True
                return
            if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD:
                spawn(controller.candidate_left("candidate_left"))

        ctx.room.on("participant_disconnected", on_participant_disconnected)

        await session.start(agent=agent, room=ctx.room, room_options=room_options(avatar_active=avatar_active), record=False)
    except Exception as error:
        # Nothing was spoken or stored yet, and the backend cannot end a `created` session. Deleting the room (the shutdown callback) lets the
        # candidate join the same session again within its join time, which dispatches a new job and takes no quota.
        log.exception("setup failed (%s); the room is deleted so that the candidate can join the same session again", type(error).__name__)
        if runner is not None:
            with contextlib.suppress(Exception):
                await runner.leave("agent_error")  # posts the aborted end only if a turn was stored, so never a second end event
        ctx.shutdown(reason=f"setup_failed: {type(error).__name__}")
        return
    if not fake:
        await wait_candidate_ready(ctx.room)

    async def watchdog() -> None:
        while not controller.done.is_set():
            await asyncio.sleep(TICK_SECONDS)
            try:
                await controller.tick()
            except Exception:  # noqa: BLE001
                log.exception("the tick failed")

    watchdog_task = asyncio.create_task(watchdog())
    opening_task = asyncio.create_task(controller.run_opening())
    await controller.done.wait()
    for task in (watchdog_task, opening_task):
        if not task.done():
            task.cancel()
    session.shutdown(drain=True)  # a request; the `close` event confirms it
    try:
        await asyncio.wait_for(closed.wait(), CLOSE_TIMEOUT_SECONDS)
    except TimeoutError:
        log.warning("no session close event within %.0f s", CLOSE_TIMEOUT_SECONDS)
    ctx.shutdown(reason=f"interview ended: {controller.outcome}")


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=agent_name_from_env())
async def entrypoint(ctx: JobContext) -> None:
    await run_voice_interview(ctx)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("dev", "start", "console", "connect"):
        try:
            load_voice_settings()
        except ConfigError as error:
            print(f"[interview_agent] {error}", file=sys.stderr)
            sys.exit(2)
    cli.run_app(server)
