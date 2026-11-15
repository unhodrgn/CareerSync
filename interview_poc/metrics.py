"""Timing of one PoC session. Numbers only: no transcript text and no audio is ever written (privacy rule of the PoC).

Marks are taken on a monotonic clock. `agent_speaking` is the moment the session reports the agent as speaking; with the
Anam plugin the audio output waits for the avatar's playback start (`wait_playback_start=True`), so this is the closest
server-side figure to the avatar's first audible sound (browser playout adds network and jitter-buffer time on top).
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


class RunMetrics:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.t0 = clock()
        self.started_at = datetime.now(UTC)
        self.marks: list[dict[str, Any]] = []
        self.eou: list[dict[str, float]] = []
        self.tts: dict[str, dict[str, float]] = {}
        self.avatar: list[dict[str, float | None]] = []
        self.end_reason: str | None = None
        self.t_end: float | None = None

    # ── recording ──

    def mark(self, name: str, **fields: Any) -> float:
        t = self._clock() - self.t0
        self.marks.append({"name": name, "t": t, **fields})
        return t

    def note_sdk_metric(self, metric: Any) -> None:
        """Keep the latency fields of a LiveKit metrics event (EOU, TTS, avatar); everything else is ignored."""
        kind = getattr(metric, "type", "")
        if kind == "eou_metrics":
            self.eou.append(
                {
                    "end_of_utterance_delay_s": float(metric.end_of_utterance_delay),
                    "transcription_delay_s": float(metric.transcription_delay),
                    "on_user_turn_completed_delay_s": float(metric.on_user_turn_completed_delay),
                }
            )
        elif kind == "tts_metrics" and getattr(metric, "speech_id", None):
            self.tts[metric.speech_id] = {"ttfb_s": float(metric.ttfb), "audio_duration_s": float(metric.audio_duration)}
        elif kind == "avatar_metrics":
            self.avatar.append(
                {
                    "playback_latency_s": float(metric.playback_latency),
                    "avatar_joined_time": metric.avatar_joined_time,
                    "session_started_time": metric.session_started_time,
                }
            )

    def finish(self, reason: str) -> None:
        if self.t_end is None:
            self.end_reason = reason
            self.t_end = self.mark("end", reason=reason)

    # ── derived figures ──

    def _first(self, name: str, *, after: float, **match: Any) -> float | None:
        for m in self.marks:
            if m["name"] == name and m["t"] >= after and all(m.get(k) == v for k, v in match.items()):
                return m["t"]
        return None

    def _last_before(self, name: str, *, before: float, **match: Any) -> float | None:
        found = None
        for m in self.marks:
            if m["t"] > before:
                break
            if m["name"] == name and all(m.get(k) == v for k, v in match.items()):
                found = m["t"]
        return found

    def _say_to_audio(self, say: dict[str, Any]) -> float | None:
        speaking = self._first("agent_speaking", after=say["t"])
        return None if speaking is None else speaking - say["t"]

    def summary(self) -> dict[str, Any]:
        end = self.t_end if self.t_end is not None else self._clock() - self.t0
        out: dict[str, Any] = {
            "started_at_utc": self.started_at.isoformat(timespec="seconds"),
            "total_session_seconds": _r(end),
            "end_reason": self.end_reason,
        }
        start, joined = self._first("avatar_start", after=0), self._first("avatar_joined", after=0)
        out["avatar_time_to_join_s"] = _r(None if start is None or joined is None else joined - start)
        out["avatar_sdk_metrics"] = self.avatar

        says = [m for m in self.marks if m["name"] == "say_called"]
        opening = next((m for m in says if m.get("step") == "opening"), None)
        out["time_to_first_avatar_audio_s"] = _r(None if opening is None else self._say_to_audio(opening))

        turns = []
        completed = [m for m in self.marks if m["name"] == "turn_completed"]
        for i, turn in enumerate(completed):
            n = turn.get("n", i + 1)
            record: dict[str, Any] = {"turn": n}
            if i < len(self.eou):
                record["stt_transcription_delay_s"] = _r(self.eou[i]["transcription_delay_s"])
                record["end_of_utterance_delay_s"] = _r(self.eou[i]["end_of_utterance_delay_s"])
            user_stopped = self._last_before("user_state", before=turn["t"], state="listening")
            llm = next((m for m in self.marks if m["name"] == "llm_done" and m.get("n") == n), None)
            if llm is not None:
                record["llm_ttft_s"] = _r(llm.get("ttft_s"))
                record["llm_total_s"] = _r(llm.get("total_s"))
            say = next((m for m in says if m.get("n") == n and m.get("step") in ("followup", "closing")), None)
            if say is not None:
                record["say_step"] = say["step"]
                record["say_to_avatar_audio_s"] = _r(self._say_to_audio(say))
                tts = self.tts.get(say.get("speech_id") or "")
                record["tts_ttfb_s"] = _r(tts["ttfb_s"]) if tts else None
                speaking = self._first("agent_speaking", after=say["t"])
                if speaking is not None and user_stopped is not None:
                    record["user_stopped_to_avatar_audio_s"] = _r(speaking - user_stopped)
            turns.append(record)
        out["turns"] = turns
        return out

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"session-{self.started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
