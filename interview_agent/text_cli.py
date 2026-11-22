"""Text driver of the Interview Agent: a developer tool, not a seeker feature (M5 S2; docs/DECISIONS.md D79 (1)).

It runs the same runner the voice worker will run, with typed lines instead of speech. Two ways to start, from the repository root, in the
agent's virtual environment (or the backend's: the rules mode needs no LiveKit package):

    python -m interview_agent.text_cli --session-id 12
        an existing `created` session (made through the seeker API).
    python -m interview_agent.text_cli --job-id 3 --email seeker2@demo.test --consent
        logs in as that seeker (password from INTERVIEW_DEMO_PASSWORD, or asked), shows the transcript consent text, creates a session
        with it (`--consent` says you accept it), then runs the interview. Use synthetic accounts only.

While it runs: type an answer and press Enter. `/silence 25` says nothing for 25 seconds, `/quit` (or end of input) leaves. Before every
answer the runner checks the session (a deletion or the seeker's End stops it). Settings: `config.py` (`INTERVIEW_AGENT_SECRET` is
required; `AI_MODE=llm` with `GROQ_API_KEY` uses Groq per turn). Nothing is logged but timings and codes; the typed text is not written
anywhere but the backend.
"""
import argparse
import asyncio
import getpass
import logging
import os
import sys

import httpx

from interview_agent.backend_client import SessionClient
from interview_agent.config import ConfigError, load_settings
from interview_agent.runner import InterviewRunner, Stopped

GREETING = "안녕하세요. 저는 CareerSync의 AI 면접관입니다. 이 모의 면접은 연습용이며 채용 결정에 쓰이지 않습니다."


def parse_command(line: str) -> tuple[str, float | str]:
    """("answer", text), ("silence", seconds) or ("quit", "")."""
    stripped = line.strip()
    if stripped in ("/quit", "/exit"):
        return "quit", ""
    if stripped.startswith("/silence"):
        parts = stripped.split()
        try:
            seconds = float(parts[1]) if len(parts) > 1 else 20.0
        except ValueError:
            seconds = 20.0
        return "silence", max(0.0, seconds)
    return "answer", line


async def create_session(http: httpx.AsyncClient, job_id: int, email: str, password: str, consent: bool) -> int:
    login = await http.post("/api/auth/login", json={"email": email, "password": password})
    if login.status_code != 200:
        raise SystemExit(f"login failed: HTTP {login.status_code}")
    seeker = {"Authorization": f"Bearer {login.json()['access_token']}"}
    text = (await http.get("/api/interview-consent", headers=seeker)).json()
    print(f"[{text['title']}] (version {text['version']})")
    for item in text["items"]:
        print(f"  - {item['text']}")
    if not consent:
        raise SystemExit("not created: pass --consent to accept the consent text above")
    created = await http.post(
        f"/api/jobs/{job_id}/interview-sessions", json={"consent_transcript": True, "consent_version": text["version"]}, headers=seeker
    )
    if created.status_code != 201:
        raise SystemExit(f"session not created: HTTP {created.status_code} {created.json().get('code')}")
    return created.json()["session"]["id"]


async def run(args: argparse.Namespace, read=input, write=print) -> int:
    settings = load_settings()
    async with httpx.AsyncClient(base_url=settings.backend_url, timeout=10.0) as http:
        session_id = args.session_id
        if session_id is None:
            password = os.environ.get("INTERVIEW_DEMO_PASSWORD") or getpass.getpass("password: ")
            session_id = await create_session(http, args.job_id, args.email, password, args.consent)
            if args.create_only:  # for `python -m interview_agent.voice console`: a created session that nobody has joined yet
                write(f"created session {session_id}; INTERVIEW_AGENT_CONSOLE_SESSION_ID={session_id}")
                return 0
        model = None
        if settings.uses_model:
            from interview_agent.turn_model import GroqTurnClient

            model = GroqTurnClient(
                model=settings.llm_model, timeout=settings.llm_timeout, loop=asyncio.get_running_loop(),
                api_key=settings.groq_api_key, reasoning_effort=settings.reasoning_effort,
            )
        runner = InterviewRunner(SessionClient(http, settings.secret, session_id), data_dir=settings.data_dir, model=model, llm_timeout=settings.llm_timeout)
        write(f"session {session_id} (AI_MODE={settings.ai_mode})")
        try:
            await runner.open()
            write(f"면접관> {GREETING}")
            for line in await runner.start():
                write(f"면접관> {line}")
            while not runner.finished:
                try:
                    typed = await asyncio.to_thread(read, "지원자> ")
                except EOFError:
                    typed = "/quit"
                kind, value = parse_command(typed)
                if kind == "quit":
                    await runner.leave("candidate_left")
                    break
                await runner.check()
                lines = await (runner.silence(value) if kind == "silence" else runner.answer(value))
                for line in lines:
                    write(f"면접관> {line}")
        except Stopped as stop:
            write(f"[stopped: {stop.reason}]")
        write(f"[session {session_id}: {runner.stopped}] model calls: {[(o, round(s, 2)) for o, s in runner.timings]}")
        return 0 if runner.stopped in ("completed", "candidate_left", "aborted") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m interview_agent.text_cli", description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--session-id", type=int)
    target.add_argument("--job-id", type=int)
    parser.add_argument("--email", help="the seeker to log in as, with --job-id")
    parser.add_argument("--consent", action="store_true", help="accept the transcript consent text, with --job-id")
    parser.add_argument("--create-only", action="store_true", help="with --job-id: create the session, print its id and stop (for the voice worker's console mode)")
    args = parser.parse_args(argv)
    if args.job_id is not None and not args.email:
        parser.error("--job-id needs --email")
    if args.create_only and args.job_id is None:
        parser.error("--create-only goes with --job-id")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        return asyncio.run(run(args))
    except ConfigError as e:
        print(f"[interview_agent] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
