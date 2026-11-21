"""Local server of the PoC: serves the static meeting page (web/) and mints LiveKit tokens. Listens on 127.0.0.1 only.

    POST /api/token   -> {url, token, room, identity, max_seconds, avatar}   (one session at a time)
    POST /api/end     -> deletes the room (best effort) and releases the session slot
    GET  /...         -> files of web/

The token is the only thing this server hands out. It lets the browser join ONE new room, publish ONLY a microphone track
(`can_publish_sources=["microphone"]`: a camera or screen track is refused by LiveKit even if the page tried), and it
dispatches the PoC agent. The identity is random and the display name is fixed, so no personal data is in the token. The
LiveKit key and secret stay in this process.

Run:  python token_server.py [--port 8787]   (from interview_poc/, with its own virtualenv)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import secrets
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from livekit import api

from config import AGENT_NAME, HARD_STOP_SECONDS, WEB_DIR, ConfigError, Settings, load_env_file, load_settings

log = logging.getLogger("interview_poc.token_server")

TOKEN_TTL = timedelta(minutes=10)
SESSION_WINDOW_SECONDS = HARD_STOP_SECONDS + 25.0  # a slot is held a little longer than the longest session
MAX_BODY_BYTES = 1024
ROOM_PATTERN = re.compile(r"^poc-[0-9a-f]{12}$")


@dataclass(frozen=True)
class IssuedToken:
    url: str
    token: str
    room: str
    identity: str
    max_seconds: float
    avatar: bool


def issue_token(settings: Settings) -> IssuedToken:
    """A token for one new room. Pure apart from randomness, so it is easy to test."""
    room = f"poc-{secrets.token_hex(6)}"
    identity = f"candidate-{secrets.token_hex(6)}"
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name("Candidate")
        .with_ttl(TOKEN_TTL)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
                can_update_own_metadata=True,  # the page sets one attribute: "ready"
                can_publish_sources=["microphone"],  # microphone only; never camera or screen
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                max_participants=3,  # candidate, agent, avatar worker
                empty_timeout=30,
                departure_timeout=30,
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)],
            )
        )
        .to_jwt()
    )
    return IssuedToken(settings.livekit_url, token, room, identity, HARD_STOP_SECONDS, settings.avatar_enabled)


class SessionGate:
    """One session at a time: the Anam Free plan allows one concurrent session and every minute costs money."""

    def __init__(self, window: float = SESSION_WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._window, self._clock = window, clock
        self._busy_until = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = self._clock()
            if now < self._busy_until:
                return False
            self._busy_until = now + self._window
            return True

    def release(self) -> None:
        with self._lock:
            self._busy_until = 0.0


async def _delete_room(settings: Settings, room: str) -> None:
    http_url = re.sub(r"^ws", "http", settings.livekit_url)  # wss:// -> https://
    lk = api.LiveKitAPI(http_url, settings.livekit_api_key, settings.livekit_api_secret)
    try:
        await lk.room.delete_room(api.DeleteRoomRequest(room=room))
    finally:
        await lk.aclose()


class Handler(SimpleHTTPRequestHandler):
    server_version = "InterviewPoc"
    sys_version = ""

    def __init__(self, *args, settings: Settings, gate: SessionGate, delete_room=_delete_room, **kwargs) -> None:
        self._settings, self._gate, self._delete_room = settings, gate, delete_room
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    # ── headers and quiet logging ──

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002  (request lines only; no bodies, no tokens)
        log.info("%s %s", self.address_string(), format % args)

    # ── static files: no directory listing, no dotfiles ──

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def do_GET(self) -> None:
        if any(part.startswith(".") for part in self.path.split("?")[0].split("/")):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    # ── API ──

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/token":
            self._token()
        elif path == "/api/end":
            self._end()
        else:
            self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if not 0 < length <= MAX_BODY_BYTES:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _token(self) -> None:
        if not self._gate.acquire():
            self._json(HTTPStatus.CONFLICT, {"code": "SESSION_BUSY", "message": "다른 연습 세션이 진행 중입니다. 잠시 후 다시 시도해 주세요."})
            return
        try:
            issued = issue_token(self._settings)
        except Exception:  # noqa: BLE001
            self._gate.release()
            log.exception("could not mint a token")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"code": "TOKEN_ERROR", "message": "토큰을 만들 수 없습니다."})
            return
        log.info("token issued for room %s (avatar=%s)", issued.room, issued.avatar)  # the token itself is never logged
        self._json(HTTPStatus.OK, asdict(issued))

    def _end(self) -> None:
        room = self._body().get("room")
        self._gate.release()
        if isinstance(room, str) and ROOM_PATTERN.match(room):
            try:
                asyncio.run(self._delete_room(self._settings, room))
            except Exception:  # noqa: BLE001  (the room may already be gone)
                log.debug("room %s not deleted", room, exc_info=True)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(settings: Settings, port: int = 8787, *, gate: SessionGate | None = None, delete_room=_delete_room) -> ThreadingHTTPServer:
    handler = partial(Handler, settings=settings, gate=gate or SessionGate(), delete_room=delete_room)
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    load_env_file()
    try:
        settings = load_settings(role="token")
    except ConfigError as e:
        print(f"[interview_poc] {e}", file=sys.stderr)
        sys.exit(2)
    server = make_server(settings, args.port)
    print(f"Meeting page: http://127.0.0.1:{args.port}/   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
