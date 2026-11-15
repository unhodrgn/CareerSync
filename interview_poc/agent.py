"""LiveKit agent of the standalone AI avatar interview PoC (a seeker practice interview, not a hiring tool).

Run (from interview_poc/, with its own virtualenv):  python agent.py start   (`dev` also works in 1.8.12 but is deprecated;
`python agent.py download-files` once, if a first run asks for it)

Pipeline: candidate microphone -> LiveKit Inference STT (Korean) -> [mask personal data] -> conductor -> Groq (openai/gpt-oss-120b
by default) through the LiveKit Groq plugin (only masked text, screened output) -> LiveKit Inference TTS (Korean) -> Anam avatar (lip-synced
audio and video published into the room). Privacy rules enforced here:
- `record=False`: no audio, transcript, trace or log upload to LiveKit Cloud (the default would follow a project setting).
- no audio or video is stored by this code; the transcript is masked, kept in memory and shown on the page only;
- only the microphone is subscribed (`AutoSubscribe.AUDIO_ONLY`, no video input); the camera is never published by the page;
- the Anam watermark (`show_ai_avatar_disclosure=True`) and a spoken disclosure tell the candidate they talk to an AI avatar.

Written against livekit-agents 1.8.12. Calls marked "unverified live" were checked in the SDK source, not in a running room.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, AutoSubscribe, JobContext, JobProcess, cli, inference, room_io
from livekit.agents.llm import StopResponse
from livekit.plugins import anam, silero

from conductor import Hooks, InterviewConductor, SayOutcome
from config import (
    AGENT_NAME,
    AVATAR_JOIN_TIMEOUT_SECONDS,
    LANGUAGE,
    RUNS_DIR,
    STT_MODEL,
    TTS_MODEL,
    ConfigError,
    Settings,
    load_env_file,
    load_settings,
)
from groq_llm import LlmResult, VoiceGroq, complete_text
from guards import mask_speech_event, mask_spoken_pii
from metrics import RunMetrics

log = logging.getLogger("interview_poc.agent")

EVENT_TOPIC = "poc.event"  # agent -> page: masked transcript lines, status, end/error
READY_ATTRIBUTE = "poc_ready"  # page -> agent: the browser is attached and can hear the avatar
READY_TIMEOUT_SECONDS = 15.0
CLOSE_TIMEOUT_SECONDS = 15.0


class PracticeInterviewer(Agent):
    """The agent object. It generates no replies itself: the conductor speaks, the hooks below feed it masked turns."""

    def __init__(self, names: tuple[str, ...] = ()) -> None:
        super().__init__(instructions="Practice interviewer. Replies are produced by the interview conductor, not by this prompt.")
        self.names = names
        self.conductor: InterviewConductor | None = None
        self._tasks: set[asyncio.Task] = set()

    async def stt_node(self, audio, model_settings):
        """Mask every transcript (interim and final) before anything else sees it: preemptive generation, history, display."""
        async for event in Agent.default.stt_node(self, audio, model_settings):
            mask_speech_event(event, self.names)
            yield event

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        # Defence in depth: the STT node already masked this text. No default LLM reply is wanted (the conductor answers).
        masked = mask_spoken_pii(new_message.text_content or "", self.names).text
        new_message.content = [masked]
        if self.conductor is not None:
            task = asyncio.create_task(self.conductor.on_candidate_turn(masked))
            self._tasks.add(task)
            task.add_done_callback(self._task_done)
        raise StopResponse()

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("candidate turn handling failed", exc_info=task.exception())


async def wait_candidate_ready(room: rtc.Room, timeout: float = READY_TIMEOUT_SECONDS) -> bool:
    """Wait until a normal participant (the candidate) sets READY_ATTRIBUTE, so the disclosure is not spoken to nobody."""
    ready = asyncio.Event()

    def check(*_: Any) -> None:
        for p in room.remote_participants.values():
            if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD and p.attributes.get(READY_ATTRIBUTE) == "1":
                ready.set()

    room.on("participant_attributes_changed", check)  # unverified live: event name checked in the rtc SDK source
    room.on("participant_connected", check)
    try:
        check()
        await asyncio.wait_for(ready.wait(), timeout)
        return True
    except asyncio.TimeoutError:
        log.warning("the candidate page did not report ready within %.0f s; starting anyway", timeout)
        return False
    finally:
        room.off("participant_attributes_changed", check)
        room.off("participant_connected", check)


def build_session(settings: Settings, vad) -> tuple[AgentSession, VoiceGroq]:
    llm = VoiceGroq(model=settings.llm_model, api_key=settings.groq_api_key, reasoning_effort=settings.reasoning_effort)
    session = AgentSession(
        stt=inference.STT(STT_MODEL, language=LANGUAGE),
        llm=llm,
        tts=inference.TTS(TTS_MODEL, voice=settings.tts_voice, language=LANGUAGE),
        vad=vad,
        # A preemptive reply could start on an unfinished transcript; the conductor decides every reply itself
        turn_handling={"preemptive_generation": {"enabled": False}},
    )
    return session, llm


def room_options(settings: Settings) -> room_io.RoomOptions:
    return room_io.RoomOptions(
        audio_input=True,
        video_input=False,  # the candidate's camera is never used by the agent (and never published by the page)
        text_input=False,
        text_output=False,  # no automatic transcription topic: the page gets only the masked lines of EVENT_TOPIC
        # With the avatar, agent audio goes to the avatar worker, not to the room (Anam/LiveKit docs)
        audio_output=not settings.avatar_enabled,
        close_on_disconnect=True,  # documented: only for CLIENT_INITIATED, ROOM_DELETED, USER_REJECTED (see candidate_left_handler)
        delete_room_on_close=True,  # documented: delete the room as soon as the session ends instead of after departure_timeout
    )


def candidate_left_handler(conductor: InterviewConductor, spawn):
    """End the interview when the candidate leaves for ANY reason.

    `close_on_disconnect` only closes the session for CLIENT_INITIATED, ROOM_DELETED and USER_REJECTED. A dropped
    connection is not in that list, and the billed avatar would keep running until the watchdog's hard stop.
    """

    def handler(participant) -> None:
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD:
            spawn(conductor.abort("candidate_left"))

    return handler


async def run_interview(ctx: JobContext) -> None:
    load_env_file()
    metrics = RunMetrics()
    state = {"ended": False}
    closed = asyncio.Event()
    background: set[asyncio.Task] = set()  # keep a reference to fire-and-forget tasks so they are not garbage collected

    def spawn(coro) -> None:
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    async def send_event(payload: dict[str, Any]) -> None:
        if not ctx.room.isconnected():
            return
        try:
            await ctx.room.local_participant.send_text(json.dumps(payload, ensure_ascii=False), topic=EVENT_TOPIC)
        except Exception:  # noqa: BLE001  (display only: never let it break the interview)
            log.debug("could not send a page event", exc_info=True)

    async def on_shutdown(reason: str) -> None:
        metrics.finish(reason or "job_shutdown")
        path = metrics.write(RUNS_DIR)
        log.info("session report written to %s", path)
        log.info("session summary: %s", json.dumps(metrics.summary(), ensure_ascii=False))
        try:
            await ctx.delete_room()  # the browser sees the end; the avatar worker leaves with the room
        except Exception:  # noqa: BLE001
            log.debug("room already gone", exc_info=True)

    try:
        settings = load_settings(role="agent")
    except ConfigError as e:
        log.error("%s", e)
        ctx.shutdown(reason="configuration error")
        return

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    ctx.add_shutdown_callback(on_shutdown)

    session, llm = build_session(settings, ctx.proc.userdata["vad"])
    agent = PracticeInterviewer(settings.mask_names)

    async def say(text: str, step: str, n: int | None) -> SayOutcome:
        try:
            handle = session.say(text, allow_interruptions=False, add_to_chat_ctx=False)
        except RuntimeError:
            log.warning("session is closing; not speaking (step=%s)", step)
            return SayOutcome(False)
        metrics.mark("say_called", step=step, n=n, speech_id=handle.id)
        try:
            await handle.wait_for_playout()
        except Exception:  # noqa: BLE001
            log.warning("speech failed (step=%s)", step, exc_info=True)
            return SayOutcome(False, handle.id)
        return SayOutcome(not handle.interrupted and handle.exception() is None, handle.id)

    async def show(role: str, text: str, n: int | None) -> None:
        if role == "status":
            await send_event({"type": "status", "stage": text})
        else:
            await send_event({"type": "line", "role": role, "text": text, "turn": n})

    async def complete(system: str, user: str) -> LlmResult:
        return await complete_text(llm, system=system, user=user)

    async def end(reason: str) -> None:
        if state["ended"]:
            return
        state["ended"] = True
        await send_event({"type": "end", "reason": reason})
        session.shutdown(drain=True)  # a request; the `close` event below confirms it
        try:
            await asyncio.wait_for(closed.wait(), CLOSE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            log.warning("no session close event within %.0f s", CLOSE_TIMEOUT_SECONDS)
        ctx.shutdown(reason=f"interview ended: {reason}")

    conductor = InterviewConductor(Hooks(say=say, show=show, complete=complete, end=end, clock=time.monotonic), metrics, names=settings.mask_names)
    agent.conductor = conductor

    @session.on("agent_state_changed")
    def _agent_state(ev) -> None:
        if ev.new_state == "speaking":
            metrics.mark("agent_speaking")

    @session.on("user_state_changed")
    def _user_state(ev) -> None:
        metrics.mark("user_state", state=ev.new_state)
        conductor.set_candidate_speaking(ev.new_state == "speaking")

    @session.on("metrics_collected")
    def _metrics(ev) -> None:
        metrics.note_sdk_metric(ev.metrics)

    @session.on("error")
    def _error(ev) -> None:
        log.error("session error from %s: %s (recoverable=%s)", type(ev.source).__name__, type(ev.error).__name__, getattr(ev.error, "recoverable", None))

    @session.on("close")
    def _close(ev) -> None:
        closed.set()
        if not state["ended"]:
            spawn(conductor.abort(f"session_closed:{getattr(ev.reason, 'value', ev.reason)}"))

    ctx.room.on("participant_disconnected", candidate_left_handler(conductor, spawn))

    if settings.avatar_enabled:
        avatar = anam.AvatarSession(
            persona_config=anam.PersonaConfig(name="AI Interviewer", avatarId=settings.anam_avatar_id),
            session_options=anam.SessionOptions(show_ai_avatar_disclosure=True),
            api_key=settings.anam_api_key,
        )
        metrics.mark("avatar_start")
        try:
            await avatar.start(
                session,
                room=ctx.room,
                livekit_url=settings.livekit_url,
                livekit_api_key=settings.livekit_api_key,
                livekit_api_secret=settings.livekit_api_secret,
            )
            await avatar.wait_for_join(timeout=AVATAR_JOIN_TIMEOUT_SECONDS)
        except Exception as e:  # noqa: BLE001  (bad key, plan limit, timeout: say so on the page and leave)
            code = f"avatar_{type(e).__name__}"
            log.error("avatar did not start: %s (status=%s)", type(e).__name__, getattr(e, "status_code", None))
            await send_event({"type": "error", "code": code})
            await conductor.abort(code)
            ctx.shutdown(reason=code)
            return
        metrics.mark("avatar_joined")

    await session.start(agent=agent, room=ctx.room, room_options=room_options(settings), record=False)
    await wait_candidate_ready(ctx.room)

    async def watchdog() -> None:
        while not state["ended"]:
            await asyncio.sleep(1.0)
            try:
                await conductor.tick()
            except Exception:  # noqa: BLE001
                log.exception("watchdog tick failed")

    watchdog_task = asyncio.create_task(watchdog())
    opening_task = asyncio.create_task(conductor.run_opening())
    await closed.wait()
    for task in (watchdog_task, opening_task):
        if not task.done():
            task.cancel()


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    await run_interview(ctx)


if __name__ == "__main__":
    load_env_file()
    if len(sys.argv) > 1 and sys.argv[1] in ("dev", "start", "console", "connect"):
        try:
            load_settings(role="agent")
        except ConfigError as e:
            print(f"[interview_poc] {e}", file=sys.stderr)
            sys.exit(2)
    cli.run_app(server)
