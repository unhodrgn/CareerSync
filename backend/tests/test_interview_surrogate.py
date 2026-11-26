"""A surrogate code point is refused, never stripped, replaced or recombined, at the boundary of the practice interview (M4 hardening).

A `str` can hold a code point from 0xD800 to 0xDFFF, and UTF-8 cannot encode it: the line reached the INSERT and the database driver raised
UnicodeEncodeError, so the caller got a raw error and not an answer. `mask_spoken` passes every code point through, and there was no check, as there
is for U+0000 (test_interview_nul.py), so now there is one, at the same place and with the same answer: 422 `INTERVIEW_BAD_TURN`, field `text`.

What a surrogate is in a `str`: a valid pair is not two code points. Decoding JSON turns an escaped pair into one character (an emoji is one code
point), so any surrogate that reaches the service is a lone half, or two halves that nobody combined, and both are refused. Direct Python strings and
the text that `json.loads` gives for escaped forms are tested apart, and every surrogate here is built with `chr` (never written as an escape, which
a tool can rewrite into the character: it once turned a pair into an emoji in a test of this very case). The first test makes each fixture show the code
points its name says, and fails if an escape of a surrogate is ever written in this file.

For each of the three texts of an event (a candidate's answer, an interviewer's line, the closing line) and each refused input: 422 with the existing
fixed message and `extra == {"field": "text"}`; nothing of the text, nor a marker in it, in the error or the log; not one row of any table inserted or
changed; the session of a refused first turn is not started; the sequence number is free for the next, clean event; and no model, embedder, skill or
resource is asked for (tripwires, installed once the session exists, after the model is shown to be absent: rules mode). What is accepted is stored with
exactly the normalization it always had, `" ".join(text.split())`. Nothing here needs a database server: SQLite in memory, rules mode."""
import json
import logging
import re
import unicodedata
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.services import ai_runtime
from app.services import interview_ingest_service as ingest

from .interview_fixtures import Clock, build_world, new_session, turn_rows
from .test_interview_ingest_end import end, end_ev, ready, refuse_end
from .test_interview_ingest_turns import ev, plan_of, rec, refuse, row, started, unchanged

NUL = "\x00"
BACKSLASH = chr(92)
SECRET = "SECRET-MARKER-답변"
MESSAGE = "The interview event is invalid."  # the fixed message of every refusal of an event (`_bad`)
CLEAN = "Java로 API를 만들었습니다."
S, T, Q = InterviewSession.__table__, InterviewTurn.__table__, InterviewQuota.__table__


def points(text: str) -> list[int]:
    return [ord(char) for char in text]


def is_surrogate(char: str) -> bool:
    return 0xD800 <= ord(char) <= 0xDFFF


def has_surrogate(text: str) -> bool:
    return any(is_surrogate(char) for char in text)


def from_json(*units: int) -> str:
    """What a JSON decoder gives for a string made of these unicode escapes: a high half followed by a low half becomes one character."""
    return json.loads('"' + "".join(f"{BACKSLASH}u{unit:04x}" for unit in units) + '"')


# ── The inputs ──

REJECTED = {
    "a lone high surrogate": chr(0xD800),
    "a lone low surrogate": chr(0xDC00),
    "a high surrogate after ordinary text": "답변 Java " + chr(0xD800),
    "a low surrogate after ordinary text": "답변 Java " + chr(0xDC00) + " 이어서",
    "a reversed pair, low then high": chr(0xDE00) + chr(0xD83D),
    "a high surrogate followed by an astral character": chr(0xD83D) + chr(0x1F600),
    "a high surrogate followed by two code points of a pair": chr(0xD83D) + chr(0xD83D) + chr(0xDE00),
    "an astral character followed by a low surrogate": chr(0x1F600) + chr(0xDE00),
    "two code points of a pair followed by a low surrogate": chr(0xD83D) + chr(0xDE00) + chr(0xDE00),
    "a high and a low code point side by side": chr(0xD83D) + chr(0xDE00),
    "a high and a low code point side by side inside text": "저는 " + chr(0xD83D) + chr(0xDE00) + " Java",
    "the first code point of the range": "가" + chr(0xD800) + "나",
    "the last high surrogate": "가" + chr(0xDBFF) + "나",
    "the first low surrogate": "가" + chr(0xDC00) + "나",
    "the last code point of the range": "가" + chr(0xDFFF) + "나",
    "a NUL and a surrogate": "a" + NUL + chr(0xD800),
    "a surrogate and a NUL": chr(0xDC00) + NUL + "b",
    "a marker and a lone surrogate": SECRET + " " + chr(0xD800),
}
FROM_JSON = {
    "an escaped lone high surrogate": from_json(0xD800),
    "an escaped lone low surrogate": from_json(0xDC00),
    "an escaped high surrogate after text": "답변 " + from_json(0xD83D),
    "an escaped reversed pair": from_json(0xDE00, 0xD83D),
    "an escaped high surrogate followed by a valid pair": from_json(0xD83D, 0xD83D, 0xDE00),
    "an escaped valid pair followed by a low surrogate": from_json(0xD83D, 0xDE00, 0xDE00),
}
ALL_REJECTED = {**REJECTED, **{f"from JSON: {name}": text for name, text in FROM_JSON.items()}}

VIETNAMESE = unicodedata.normalize("NFC", "Tôi đã xây dựng API bằng Java và Spring Boot, tối ưu truy vấn và viết kiểm thử.")
ZWJ_FAMILY = chr(0x1F468) + chr(0x200D) + chr(0x1F469) + chr(0x200D) + chr(0x1F467)
ACCEPTED = {
    "ordinary Korean": "저는 Java와 Spring으로 주문 API를 개발했습니다.",
    "Vietnamese, precomposed": VIETNAMESE,
    "Vietnamese, decomposed": unicodedata.normalize("NFD", VIETNAMESE),
    "an emoji": "Java로 API를 만들었습니다 " + chr(0x1F600),
    "an emoji ZWJ sequence": "팀 " + ZWJ_FAMILY + " 협업",
    "CJK extension B": "표기 " + chr(0x20BB7) + " 확인",
    "a valid pair escaped in JSON, as json.loads decodes it": "저는 " + from_json(0xD83D, 0xDE00) + " Java를 썼습니다.",
    "the character just below the range": "가" + chr(0xD7FF) + "나",
    "the character just above the range": "가" + chr(0xE000) + "나",
    "the replacement character": "깨진 " + chr(0xFFFD) + " 문자",
    "white space, collapsed as it always was": "  Java   와\tSpring \n 사용  ",
    "a mix": f"{VIETNAMESE} 저는 {chr(0x1F600)} {ZWJ_FAMILY} {chr(0x20BB7)} {chr(0xD7FF)} {chr(0xE000)} {chr(0xFFFD)}",
}
KINDS = ["candidate answer", "interviewer line", "closing line"]
REPRESENTATIVE = [
    "a lone high surrogate",
    "a low surrogate after ordinary text",
    "a reversed pair, low then high",
    "a high and a low code point side by side",
    "a NUL and a surrogate",
    "a marker and a lone surrogate",
]


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


# ── Helpers ──


def snapshot(db):
    """Every column of every row of the three interview tables."""
    db.rollback()
    return (
        [tuple(r) for r in db.execute(select(S).order_by(S.c.id))],
        [tuple(r) for r in db.execute(select(T).order_by(T.c.session_id, T.c.seq))],
        [tuple(r) for r in db.execute(select(Q).order_by(Q.c.seeker_id, Q.c.kst_day, Q.c.kind))],
    )


def forbid_inference(monkeypatch) -> list[str]:
    """Rules mode is shown first (no model is configured); then anything that could reach a model, the embedder or the resources fails at once.
    The list says which were called, if the test did not stop on them."""
    assert ai_runtime.llm() is None, "a model is configured: these tests run in rules mode only"
    called: list[str] = []

    def tripwire(name):
        def fail(*args, **kwargs):
            called.append(name)
            raise AssertionError(f"ai_runtime.{name}() was called")

        return fail

    for name in ("llm", "embedder", "skills", "resources", "mode"):
        monkeypatch.setattr(ai_runtime, name, tripwire(name))
    return called


class Scene:
    """A session ready for one kind of event, and what to do with it."""

    def __init__(self, db, world, clock, kind):
        self.db, self.clock, self.kind = db, clock, kind
        self.sid = new_session(db, world, clock)
        if kind == "closing line":
            self.plan, self.seq = ready(db, self.sid, clock)  # live, with a question and an answer: the closing line is the third
        else:
            self.plan, self.seq = started(db, self.sid, clock), 2  # live, with the first question: the event is the second

    def event(self, text):
        if self.kind == "candidate answer":
            return ev(self.plan, self.seq, "candidate", "answer", text=text)
        if self.kind == "interviewer line":
            return ev(self.plan, self.seq, "agent", "follow_up", text=text)
        return end_ev(self.plan, self.seq, text=text)

    def refuse(self, text):
        call = refuse_end if self.kind == "closing line" else refuse
        return call(self.db, self.sid, self.event(text), self.clock, 422, "INTERVIEW_BAD_TURN", field="text")

    def send(self, text):
        call = end if self.kind == "closing line" else rec
        return call(self.db, self.sid, self.event(text), self.clock)

    def stored_text(self):
        return turn_rows(self.db, self.sid)[-1].text


# ── The fixtures are what their names say ──


def test_every_fixture_holds_the_code_points_its_name_says_and_no_surrogate_escape_is_written_in_this_file():
    assert points(REJECTED["a lone high surrogate"]) == [0xD800]
    assert points(REJECTED["a lone low surrogate"]) == [0xDC00]
    assert points(REJECTED["a reversed pair, low then high"]) == [0xDE00, 0xD83D]
    assert points(REJECTED["a high and a low code point side by side"]) == [0xD83D, 0xDE00]  # two code points, not the emoji
    assert points(REJECTED["a high surrogate followed by an astral character"]) == [0xD83D, 0x1F600]
    assert points(REJECTED["a high surrogate followed by two code points of a pair"]) == [0xD83D, 0xD83D, 0xDE00]
    assert points(REJECTED["an astral character followed by a low surrogate"]) == [0x1F600, 0xDE00]
    assert points(REJECTED["two code points of a pair followed by a low surrogate"]) == [0xD83D, 0xDE00, 0xDE00]
    assert [points(REJECTED[name])[1] for name in ("the first code point of the range", "the last high surrogate", "the first low surrogate", "the last code point of the range")] == [
        0xD800, 0xDBFF, 0xDC00, 0xDFFF,
    ]  # fmt: skip
    assert NUL in REJECTED["a NUL and a surrogate"] and NUL in REJECTED["a surrogate and a NUL"]
    # JSON decoding: a valid escaped pair is one character, and nothing else is combined
    assert points(from_json(0xD83D, 0xDE00)) == [0x1F600]
    assert points(from_json(0xD800)) == [0xD800] and points(from_json(0xDC00)) == [0xDC00]
    assert points(from_json(0xDE00, 0xD83D)) == [0xDE00, 0xD83D]
    assert points(from_json(0xD83D, 0xD83D, 0xDE00)) == [0xD83D, 0x1F600]
    assert points(from_json(0xD83D, 0xDE00, 0xDE00)) == [0x1F600, 0xDE00]
    assert points(FROM_JSON["an escaped high surrogate after text"]) == points("답변 ") + [0xD83D]
    for name, text in ALL_REJECTED.items():
        assert has_surrogate(text), name
    for name, text in ACCEPTED.items():
        assert not has_surrogate(text) and text.encode("utf-8"), name
    accepted = ACCEPTED
    assert accepted["Vietnamese, precomposed"] != accepted["Vietnamese, decomposed"]
    assert any(unicodedata.category(c) == "Mn" for c in accepted["Vietnamese, decomposed"])
    assert not any(unicodedata.category(c) == "Mn" for c in accepted["Vietnamese, precomposed"])
    assert unicodedata.normalize("NFC", accepted["Vietnamese, decomposed"]) == accepted["Vietnamese, precomposed"]
    assert points(accepted["an emoji"])[-1] == 0x1F600 and len(chr(0x1F600)) == 1
    assert points(accepted["an emoji ZWJ sequence"]).count(0x200D) == 2
    assert 0x20BB7 in points(accepted["CJK extension B"]) and 0xFFFD in points(accepted["the replacement character"])
    assert 0xD7FF in points(accepted["the character just below the range"]) and 0xE000 in points(accepted["the character just above the range"])
    assert points(accepted["a valid pair escaped in JSON, as json.loads decodes it"]).count(0x1F600) == 1
    source = Path(__file__).read_text(encoding="utf-8")
    assert not re.search(re.escape(BACKSLASH) + "u[dD][89a-fA-F][0-9a-fA-F]{2}", source)  # no escape of a surrogate, which a tool can rewrite


def test_the_inference_tripwires_fire(monkeypatch):
    called = forbid_inference(monkeypatch)
    for name in ("llm", "embedder", "skills", "resources", "mode"):
        with pytest.raises(AssertionError):
            getattr(ai_runtime, name)()
    assert called == ["llm", "embedder", "skills", "resources", "mode"]


# ── A refused text ──


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("text", ALL_REJECTED.values(), ids=ALL_REJECTED.keys())
def test_a_surrogate_is_refused_with_the_existing_422_writes_nothing_and_says_nothing_of_the_text(db, world, clock, caplog, monkeypatch, kind, text):
    scene = Scene(db, world, clock, kind)
    before = snapshot(db)
    called = forbid_inference(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        error = scene.refuse(text)
    assert (error.status_code, error.code, error.extra, error.message) == (422, "INTERVIEW_BAD_TURN", {"field": "text"}, MESSAGE)
    assert error.__cause__ is None and error.__context__ is None
    logged = [record.getMessage() for record in caplog.records]
    shown = " ".join([str(error), repr(error), *map(str, error.args), repr(error.extra), caplog.text, *logged])
    for secret in (SECRET, text, *{char for char in text if is_surrogate(char)}):
        assert secret not in shown
    assert [record.getMessage() for record in caplog.records if record.name == ingest.log.name] == ["interview turn refused: text"]  # the field, and no more
    assert snapshot(db) == before  # no row inserted or changed, in any table
    assert called == []
    clean = scene.send(CLEAN)  # the sequence number the refused event would have taken is free
    assert clean.outcome in ("stored", "ended") and scene.stored_text() == CLEAN


@pytest.mark.parametrize("who", ["the first question of the engine", "a candidate answer sent first"])
@pytest.mark.parametrize("name", REPRESENTATIVE)
def test_a_refused_first_turn_does_not_start_the_session(db, world, clock, sid, monkeypatch, who, name):
    plan = plan_of(db, sid)
    text = ALL_REJECTED[name]
    event = ev(plan, 1, "agent", "question", text=text) if who.startswith("the first") else ev(plan, 1, "candidate", "answer", text=text)
    before = snapshot(db)
    called = forbid_inference(monkeypatch)
    refuse(db, sid, event, clock, 422, "INTERVIEW_BAD_TURN", field="text")
    unchanged(db, sid)  # still `created`, no turn, no coverage
    assert row(db, sid).started_at is None and row(db, sid).active_until is not None  # not started: the join deadline is still the one it had
    assert snapshot(db) == before and called == []  # every column of every row, in all three tables
    assert rec(db, sid, ev(plan, 1, "agent", "question"), clock).outcome == "stored"  # the number is free: the session starts now
    assert row(db, sid).status == "live"


def test_the_refusal_comes_before_the_duplicate_the_conflict_and_the_gap_checks(db, world, clock, sid, monkeypatch):
    plan = started(db, sid, clock)
    clean = ev(plan, 2, "candidate", "answer", text=CLEAN)
    assert rec(db, sid, clean, clock).outcome == "stored"
    before = snapshot(db)
    called = forbid_inference(monkeypatch)
    for seq in (2, 3, 9):  # 2 holds another text (a conflict), 3 is the next number, 9 is a gap: the text is refused first in each
        refuse(db, sid, ev(plan, seq, "candidate", "answer", text=CLEAN + chr(0xD800)), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert snapshot(db) == before and called == []
    assert rec(db, sid, clean, clock).outcome == "duplicate"  # an exact repeat of a clean event is still a duplicate


# ── A surrogate is refused as a NUL is ──


@pytest.mark.parametrize("kind", KINDS)
def test_a_surrogate_is_refused_with_exactly_the_error_of_a_nul(db, world, clock, kind):
    scene = Scene(db, world, clock, kind)
    nul = scene.refuse("Java" + NUL + "를 썼습니다.")
    surrogate = scene.refuse("Java" + chr(0xD800) + "를 썼습니다.")
    both = scene.refuse("Java" + NUL + chr(0xD800) + "를 썼습니다.")
    shapes = [(e.status_code, e.code, e.message, e.extra) for e in (nul, surrogate, both)]
    assert shapes[0] == shapes[1] == shapes[2] == (422, "INTERVIEW_BAD_TURN", MESSAGE, {"field": "text"})


# ── What is valid is stored as it always was ──


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("text", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_valid_unicode_is_stored_with_exactly_the_normalization_it_always_had(db, world, clock, monkeypatch, kind, text):
    scene = Scene(db, world, clock, kind)
    called = forbid_inference(monkeypatch)
    assert scene.send(text).outcome in ("stored", "ended")
    stored = scene.stored_text()
    assert stored == " ".join(text.split())  # the existing normalization, nothing added
    assert not has_surrogate(stored) and stored.encode("utf-8")
    assert called == []


def test_a_pair_decoded_from_json_is_one_character_and_is_stored_and_the_same_pair_as_two_code_points_is_refused(db, world, clock, sid):
    plan = started(db, sid, clock)
    decoded, direct = from_json(0xD83D, 0xDE00), chr(0xD83D) + chr(0xDE00)
    assert points(decoded) == [0x1F600] and points(direct) == [0xD83D, 0xDE00] and decoded != direct
    refuse(db, sid, ev(plan, 2, "candidate", "answer", text=f"저는 {direct} Java"), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert [t.seq for t in turn_rows(db, sid)] == [1]  # nothing stored, no sequence number used
    assert rec(db, sid, ev(plan, 2, "candidate", "answer", text=f"저는 {decoded} Java"), clock).outcome == "stored"
    stored = turn_rows(db, sid)[1].text
    assert points(stored).count(0x1F600) == 1 and not has_surrogate(stored)  # one emoji, as the JSON said it
