"""The timing report of one voice interview: numbers only (M5 S4; docs/DECISIONS.md D79).

It answers one question of the live run: for each answer, how long from the end of the candidate's speech to the first sound of the
interviewer's reply, and where the time went. For each candidate turn the voice worker marks, in this order:

| Mark | Meaning |
|---|---|
| `user_stopped` | the voice activity detector says the candidate stopped speaking |
| `stt_final` | the speech recognizer delivered its final transcript |
| `turn_committed` | the end-of-turn detection decided the answer is complete (the hook `on_user_turn_completed` ran) |
| `runner_done` | the engine, the model call (or the rules) and the posts to the backend are finished |
| `say_called` | the reply was handed to speech synthesis |
| `first_audio` | the agent started to speak |

and the report derives, per turn: `stt_delay_s` (stt_final − user_stopped), `endpointing_s` (turn_committed − user_stopped: the wait of the
turn detector and the endpointing delays), `processing_s` (say_called − turn_committed: the model call, the engine and two posts), `tts_start_s`
(first_audio − say_called) and the headline `gap_s` (first_audio − user_stopped). With the model call's own outcome and time (`ok`, `timeout`,
`error:<type>`, `rejected:<reason>`, `skipped` when the rules decided alone), so a Groq timeout that fell back to the rules shows as such.

Never in the report: a transcript, a name, a prompt, an answer, a key. Nothing here touches LiveKit or a clock of the SDK: the caller passes the
times, so the arithmetic is tested without a room."""
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

MARKS = ("user_stopped", "stt_final", "turn_committed", "runner_done", "say_called", "first_audio")
RUNS_DIR = Path(__file__).resolve().parent / ".runs"  # git-ignored (interview_agent/.gitignore)


def _delta(turn: dict, later: str, earlier: str) -> float | None:
    if later in turn and earlier in turn:
        return round(turn[later] - turn[earlier], 3)
    return None


class SessionTiming:
    def __init__(self, session_id: int, *, clock: Callable[[], float] = time.monotonic):
        self.session_id = session_id
        self.clock = clock
        self.started = clock()
        self.turns: list[dict] = []
        self.opening: dict = {}
        self.nudges = 0
        self.dropped_turns = 0
        self.speech_failures = 0
        self.llm: list[tuple[str, float]] = []
        self.detector: dict = {}
        self.settings: dict = {}
        self.outcome: str | None = None
        self._waiting_for_audio: dict | None = None  # the record whose reply has been handed to speech and has not started yet

    # ── What the worker marks ──

    def mark(self, name: str) -> None:
        """A mark of the current turn. `user_stopped` opens a turn: when the candidate pauses and goes on, the stop that counts is the last one
        before the answer is committed, so it replaces the earlier one of a turn that is not committed yet. `stt_final` is the last one too;
        the other marks keep the first time. A mark without an open turn is dropped."""
        assert name in MARKS, name
        now = self.clock() - self.started
        if name == "user_stopped":
            if self.turns and "turn_committed" not in self.turns[-1]:
                self.turns.pop()
            self.turns.append({})
        elif not self.turns:
            return
        if name in ("user_stopped", "stt_final"):
            self.turns[-1][name] = now
        else:
            self.turns[-1].setdefault(name, now)

    def runner_done(self, model: tuple[str, float] | None = None) -> None:
        """The runner finished this answer; `model`: the outcome and seconds of the model call made for it, None when the rules decided alone."""
        self.mark("runner_done")
        if self.turns and model is not None:
            self.turns[-1]["model"] = (model[0], round(model[1], 3))

    def reply_handed_to_speech(self, *, opening: bool = False, nudge: bool = False) -> None:
        """The first line of a reply goes to speech synthesis: `first_audio` will complete this record."""
        target = self.opening if opening else (None if nudge else (self.turns[-1] if self.turns else None))
        if nudge:
            self.nudges += 1
        if target is None:
            self._waiting_for_audio = None
            return
        target.setdefault("say_called", self.clock() - self.started)
        self._waiting_for_audio = target

    def agent_started_speaking(self) -> None:
        target, self._waiting_for_audio = self._waiting_for_audio, None
        if target is not None and "first_audio" not in target:
            target["first_audio"] = self.clock() - self.started

    def note_llm(self, timings: list[tuple[str, float]]) -> None:
        self.llm = [(outcome, round(seconds, 3)) for outcome, seconds in timings]

    def note_detector(self, *, requested: str, at_start: str | None = None, now: str | None = None) -> None:
        self.detector.setdefault("requested", requested)
        if at_start is not None:
            self.detector.setdefault("model_at_start", at_start)
        if now is not None:
            self.detector["model_at_end"] = now
        start, end = self.detector.get("model_at_start"), self.detector.get("model_at_end")
        self.detector["fell_back"] = bool(start and end and start != end)

    # ── The report ──

    def summary(self) -> dict:
        turns = []
        for index, turn in enumerate(self.turns, 1):
            model = turn.get("model")
            turns.append(
                {
                    "turn": index,
                    "model": {"outcome": model[0], "seconds": model[1]} if model else {"outcome": "skipped", "seconds": None},
                    "stt_delay_s": _delta(turn, "stt_final", "user_stopped"),
                    "endpointing_s": _delta(turn, "turn_committed", "user_stopped"),
                    "processing_s": _delta(turn, "say_called", "turn_committed"),
                    "tts_start_s": _delta(turn, "first_audio", "say_called"),
                    "gap_s": _delta(turn, "first_audio", "user_stopped"),
                }
            )
        gaps = sorted(t["gap_s"] for t in turns if t["gap_s"] is not None)
        return {
            "session_id": self.session_id,
            "outcome": self.outcome,
            "total_session_seconds": round(self.clock() - self.started, 1),
            "settings": self.settings,
            "turn_detector": self.detector,
            "opening": {"say_to_first_audio_s": _delta(self.opening, "first_audio", "say_called")},
            "turns": turns,
            "gap_s": {"count": len(gaps), "min": gaps[0] if gaps else None, "median": gaps[len(gaps) // 2] if gaps else None, "max": gaps[-1] if gaps else None},
            "llm_calls": [{"outcome": outcome, "seconds": seconds} for outcome, seconds in self.llm],
            "nudges": self.nudges,
            "dropped_turns": self.dropped_turns,
            "speech_failures": self.speech_failures,
        }

    def write(self, directory: Path = RUNS_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = directory / f"session-{self.session_id}-{stamp}.json"
        path.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
