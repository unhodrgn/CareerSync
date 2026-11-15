"""Task 3: basic LiveKit connectivity check. No AI, no agent dispatch, no avatar: it only proves that the URL, key and secret
work (list rooms over HTTP) and that a client can join and leave a room (WebRTC). Uses a throw-away room name.

Run:  python check_livekit.py        (needs LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in interview_poc/.env)
"""
from __future__ import annotations

import asyncio
import re
import secrets
import sys

from livekit import api, rtc

from config import ConfigError, load_env_file, load_settings


async def main() -> int:
    load_env_file()
    try:
        settings = load_settings(role="token")
    except ConfigError as e:
        print(f"[check] {e}", file=sys.stderr)
        return 2

    http_url = re.sub(r"^ws", "http", settings.livekit_url)
    lk = api.LiveKitAPI(http_url, settings.livekit_api_key, settings.livekit_api_secret)
    try:
        rooms = await lk.room.list_rooms(api.ListRoomsRequest())
        print(f"[check] API credentials work (rooms listed: {len(rooms.rooms)})")
    except Exception as e:  # noqa: BLE001
        print(f"[check] API call failed: {type(e).__name__} (check LIVEKIT_URL, key and secret)", file=sys.stderr)
        return 1
    finally:
        await lk.aclose()

    room_name = f"poc-check-{secrets.token_hex(4)}"
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(f"check-{secrets.token_hex(4)}")
        .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=False))
        .to_jwt()
    )
    room = rtc.Room()
    try:
        await room.connect(settings.livekit_url, token)
        print(f"[check] joined room {room.name}; connection state: {rtc.ConnectionState.Name(room.connection_state)}")
    except Exception as e:  # noqa: BLE001
        print(f"[check] could not join a room: {type(e).__name__}", file=sys.stderr)
        return 1
    finally:
        await room.disconnect()
    print("[check] left the room. LiveKit connectivity is OK.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
