"""What PostgreSQL does with the JSON and the text of an interview, and what never reaches it (M4 PostgreSQL QA, N4 and N5): PostgreSQL only.

N4, JSONB. A plan is stored with its SHA-256, which every later event checks. PostgreSQL does not keep the JSON as written (it parses it
and gives it back with its own key order and spacing), so the digest must not depend on either: the stored plan keeps its digest when it is
read back, when PostgreSQL's own text of it is parsed, and when the same plan is written again with reversed keys, escaped Korean and line
breaks (and the ingestion, which checks the digest on every event, still accepts the session). Then the characters that are not text. A surrogate
code point (0xD800 to 0xDFFF, which Python allows in a `str` and UTF-8 does not) in a candidate answer, an interviewer line or the closing line is
a 422 `INTERVIEW_BAD_TURN`, field `text`, exactly like a NUL, whether it is alone, after text, or two halves side by side as two code points, with
nothing stored and the sequence number still free (test_interview_surrogate.py has every case on SQLite; here the same three paths run through
this fixture, and every surrogate is built with `chr`, never written as an escape, which a tool can rewrite into the character). A character
outside the basic plane, which is one code point, must round-trip. The feedback a model wrote is a different matter and is not covered by that
refusal: a JSON column writes a lone surrogate as an escape in ASCII text, which SQLite stores and jsonb is expected to refuse. The last three
tests of the section are diagnostics of exactly that, kept apart from the application: what jsonb does with a serialized lone surrogate, and that
it keeps an astral character that is serialized as a pair of escapes.

N5, NUL (U+0000), which PostgreSQL TEXT and JSONB cannot hold (test_interview_nul_postgres.py has the text of a turn, the plan and the
feedback). Here every other place that a NUL could travel from an event into a stored column: the agent's lines, the method, the echoed topic,
a masked-kind key, every key and value of the analysis, the status keys, the point ids and the end reason of the coverage, the closing line
(its text, topic and method) and the final coverage of the end event. Each is a 422 with a code and a field, with nothing stored, the stored
coverage as it was, and the sequence number still free; a quote with a NUL is dropped (it cannot be in the masked answer) and the turn is
stored without it; an end reason with a NUL is stored as `agent_ended`. Whatever slipped through would be a raw `DataError` here.

They need `TEST_DATABASE_URL` on PostgreSQL (see db_safety.py) and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77)."""
import copy
import json

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError
from app.models import InterviewSession, User
from app.services import interview_feedback_service as fb
from app.services import interview_ingest_service as ingest
from app.services.interview_plan_service import plan_digest

from .interview_feedback_fixtures import SpyLLM, askable_session, install
from .interview_feedback_fixtures import row as feedback_row
from .interview_fixtures import Clock, build_world, new_session, turn_rows
from .test_interview_ingest_concurrency import PG
from .test_interview_ingest_end import closing, end, end_ev, final, ready, refuse_end, still_live
from .test_interview_ingest_turns import ANSWER, cov, ev, plan_of, rec, refuse, row, started

NUL = "\x00"
ASTRAL = chr(0x1F600)  # one code point (a pair only in UTF-16, and in the JSON text that escapes it)
SURROGATES = {
    "a high surrogate": chr(0xD800),
    "a low surrogate after text": "답변" + chr(0xDC00),
    "a high and a low code point side by side": chr(0xD83D) + chr(0xDE00),  # two code points: not the emoji, and not combined
}


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def point(plan, index=0) -> str:
    return plan.items[index].rubric[0].id


def reverse_keys(value):
    if isinstance(value, dict):
        return {key: reverse_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


def outcome(call):
    """("ok", the result) or ("refused", status, code). Anything else is a raw error that reached the caller: the test fails, naming its type."""
    try:
        return "ok", call()
    except AppError as error:
        return "refused", error.status_code, error.code
    except Exception as error:  # noqa: BLE001
        pytest.fail(f"a raw {type(error).__name__} reached the caller")


# ── N4: the JSONB round trip ──


@PG
def test_postgres_a_stored_plan_keeps_its_digest_whatever_key_order_and_spacing_jsonb_gives_it(db, world, clock):
    sid = new_session(db, world, clock)
    stored = row(db, sid)
    original = copy.deepcopy(stored.plan)
    assert stored.plan_sha256 == plan_digest(stored.plan)  # read back from jsonb
    raw = db.execute(text("SELECT plan::text FROM interview_sessions WHERE id = :id"), {"id": sid}).scalar()
    assert plan_digest(json.loads(raw)) == stored.plan_sha256  # PostgreSQL's own text of it
    scrambled = json.dumps(reverse_keys(original), ensure_ascii=True, indent=1)  # reversed keys, \uXXXX for Korean, line breaks
    assert scrambled != json.dumps(original, ensure_ascii=False, sort_keys=True)
    db.execute(text("UPDATE interview_sessions SET plan = CAST(:plan AS jsonb) WHERE id = :id"), {"plan": scrambled, "id": sid})
    db.commit()
    again = row(db, sid)
    assert again.plan == original and plan_digest(again.plan) == again.plan_sha256
    assert rec(db, sid, ev(plan_of(db, sid)), clock).outcome == "stored"  # the ingestion checks the digest of what PostgreSQL gives back


# ── N4: characters that are not text ──


@PG
@pytest.mark.parametrize("value", SURROGATES.values(), ids=SURROGATES.keys())
def test_postgres_a_surrogate_in_a_candidate_answer_is_a_422_and_nothing_reaches_the_database(db, world, clock, value):
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    refuse(db, sid, ev(plan, 2, "candidate", "answer", text=f"저는 {value} Java를 썼습니다."), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert [t.seq for t in turn_rows(db, sid)] == [1] and row(db, sid).coverage == cov(plan)  # nothing stored, the coverage as it was
    assert rec(db, sid, ev(plan, 2, "candidate", "answer"), clock).outcome == "stored"  # and the sequence number is free


@PG
@pytest.mark.parametrize("value", SURROGATES.values(), ids=SURROGATES.keys())
def test_postgres_a_surrogate_in_an_interviewer_line_is_a_422_and_nothing_reaches_the_database(db, world, clock, value):
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    refuse(db, sid, ev(plan, 2, "agent", "follow_up", text=f"조금 더 {value} 설명해 주세요."), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert [t.seq for t in turn_rows(db, sid)] == [1] and row(db, sid).coverage == cov(plan)
    assert rec(db, sid, ev(plan, 2, "agent", "follow_up"), clock).outcome == "stored"


@PG
@pytest.mark.parametrize("value", SURROGATES.values(), ids=SURROGATES.keys())
def test_postgres_a_surrogate_in_the_closing_line_is_a_422_and_the_interview_can_still_end(db, world, clock, value):
    sid = new_session(db, world, clock)
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, end_ev(plan, seq, text=f"수고하셨습니다 {value}"), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    still_live(db, sid, 2)  # live, no closing line, nothing changed
    assert end(db, sid, end_ev(plan, seq), clock).outcome == "ended"  # and a clean end event still ends it, with its closing line at the same number


@PG
@pytest.mark.parametrize("value", SURROGATES.values(), ids=SURROGATES.keys())
def test_postgres_a_surrogate_in_a_model_feedback_ends_as_a_report_and_never_a_raw_error(db, world, clock, monkeypatch, value):
    """Not covered by the refusal of the ingestion, and not changed by it: the feedback service has no check of its own for a surrogate. SQLite
    stores a JSON column's escape of a lone surrogate, so this passes there; whether PostgreSQL's jsonb refuses it at the store is what the
    diagnostics below say, and this test is where it would show as a raw error (a follow-up risk of the PostgreSQL QA, not a decision yet)."""
    sid, uid = askable_session(db, world, clock), world.user.id
    reply = {"strengths": [], "gaps": [], "improvements": [f"답변은 상황과 역할,{value} 해결 과정과 결과의 순서로 구성해 보세요."], "practice_questions": []}
    install(monkeypatch, SpyLLM(reply=reply))
    result = outcome(lambda: fb.ensure(db, db.get(User, uid), sid, clock=clock))
    assert result[0] == "ok", result
    stored = feedback_row(db, sid)
    assert stored.feedback_lease_token is None  # no lease is left behind, whatever the report was


@PG
def test_postgres_a_character_outside_the_basic_plane_round_trips(db, world, clock):
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    assert rec(db, sid, ev(plan, 2, "candidate", "answer", text="Java로 API를 만들었습니다 " + ASTRAL), clock).outcome == "stored"
    assert ASTRAL in turn_rows(db, sid)[1].text


# Diagnostics, as test_pg_jsonb_cannot_hold_a_nul_character is for U+0000: what the database does, with no service in between. A JSON column is
# written as text, and `json.dumps` writes a surrogate in it as an escape, in ASCII, so the driver never fails to encode it and SQLite takes it.


@PG
@pytest.mark.parametrize("value", [chr(0xD800), chr(0xDC00)], ids=["a lone high surrogate", "a lone low surrogate"])
def test_postgres_jsonb_cannot_hold_a_serialized_lone_surrogate(db, world, clock, value):
    """The hazard behind the follow-up risk of the feedback and the plan, which are JSON that a model took part in. If PostgreSQL accepts it, this
    fails, and says that nothing is at risk there."""
    sid = new_session(db, world, clock)
    sessions = InterviewSession.__table__
    before = copy.deepcopy(row(db, sid).plan)
    assert json.dumps({"q": value}).isascii()  # what is sent: an escape, not the character
    with pytest.raises(DBAPIError):
        db.execute(update(sessions).where(sessions.c.id == sid).values(plan={"items": [{"question": f"질문{value}"}]}))
        db.flush()
    db.rollback()
    assert row(db, sid).plan == before  # the plan that was there is untouched


@PG
def test_postgres_jsonb_keeps_an_astral_character_that_is_serialized_as_a_pair_of_escapes(db, world, clock):
    """The same serialization of a valid character: `json.dumps` writes it as two escapes, and jsonb must read them back as the one character."""
    sid = new_session(db, world, clock)
    sessions = InterviewSession.__table__
    plan = {"items": [{"question": "질문 " + ASTRAL}]}
    assert json.dumps(plan).isascii() and ASTRAL not in json.dumps(plan)  # sent as escapes
    db.execute(update(sessions).where(sessions.c.id == sid).values(plan=plan))
    db.commit()
    assert row(db, sid).plan == plan and ASTRAL in row(db, sid).plan["items"][0]["question"]


# ── N5: a NUL anywhere else in an event ──


def status_key(plan, closing_phase=False):
    coverage = final(plan) if closing_phase else cov(plan)
    topic = next(iter(coverage["status"]))
    coverage["status"] = {(f"{key}{NUL}" if key == topic else key): value for key, value in coverage["status"].items()}
    return coverage


TURN_CASES = {
    "an interviewer line": (lambda p: ev(p, 2, "agent", "follow_up", text=f"조금 더 설명해 주세요{NUL}"), "INTERVIEW_BAD_TURN", {"field": "text"}),
    "the method of the event": (lambda p: ev(p, 2, "agent", "follow_up", method=f"rules{NUL}"), "INTERVIEW_BAD_TURN", {"field": "method"}),
    "the topic echoed": (lambda p: ev(p, 2, "agent", "follow_up", topic_id=f"{p.items[0].topic_id}{NUL}"), "INTERVIEW_BAD_TURN", {"field": "topic_id"}),
    "a key of the masked kinds": (lambda p: ev(p, 2, "agent", "follow_up", masked_kinds={f"phone{NUL}": 1}), "INTERVIEW_BAD_TURN", {"field": "masked_kinds"}),
    "a key of the analysis": (lambda p: ev(p, 2, "candidate", "answer", analysis={**ANSWER, f"x{NUL}": 1}), "INTERVIEW_BAD_TURN", {"field": "analysis"}),
    "the answer type of the analysis": (lambda p: ev(p, 2, "candidate", "answer", analysis={**ANSWER, "answer_type": f"answered{NUL}"}), "INTERVIEW_BAD_TURN", {"field": "analysis"}),
    "the method of the analysis": (lambda p: ev(p, 2, "candidate", "answer", analysis={**ANSWER, "method": f"rules{NUL}"}), "INTERVIEW_BAD_TURN", {"field": "analysis"}),
    "the id of a rubric point in the analysis": (
        lambda p: ev(p, 2, "candidate", "answer", analysis={**ANSWER, "points": {f"{point(p)}{NUL}": "demonstrated"}}),
        "INTERVIEW_BAD_TURN",
        {"field": "analysis"},
    ),
    "a status key of the coverage": (lambda p: ev(p, 2, "agent", "follow_up", coverage=status_key(p)), "INTERVIEW_BAD_COVERAGE", {"field": "topics"}),
    "a point id in the levels of the coverage": (
        lambda p: ev(p, 2, "agent", "follow_up", coverage=cov(p, levels={p.items[0].topic_id: {f"{point(p)}{NUL}": "demonstrated"}})),
        "INTERVIEW_BAD_COVERAGE",
        {"field": "levels"},
    ),
    "the end reason of the coverage of a turn": (
        lambda p: ev(p, 2, "agent", "follow_up", coverage=cov(p, end_reason=f"time{NUL}")),
        "INTERVIEW_BAD_COVERAGE",
        {"field": "end_reason"},
    ),
}  # fmt: skip


@PG
@pytest.mark.parametrize("build, code, extra", TURN_CASES.values(), ids=TURN_CASES.keys())
def test_postgres_a_nul_anywhere_in_a_turn_event_is_a_422_and_never_reaches_the_database(db, world, clock, build, code, extra):
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    refuse(db, sid, build(plan), clock, 422, code, **extra)
    assert len(turn_rows(db, sid)) == 1 and row(db, sid).coverage == cov(plan)  # nothing stored, the coverage as it was
    assert rec(db, sid, ev(plan, 2, "agent", "follow_up"), clock).outcome == "stored"  # and the sequence number is free


@PG
def test_postgres_a_quote_with_a_nul_is_dropped_and_the_turn_is_stored_without_it(db, world, clock):
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    result = rec(db, sid, ev(plan, 2, "candidate", "answer", analysis={**ANSWER, "quotes": [f"Java{NUL}"]}), clock)
    assert (result.outcome, result.dropped_quotes) == ("stored", 1)  # it cannot be in the masked answer, so the check drops it
    assert turn_rows(db, sid)[1].analysis["quotes"] == []


END_CASES = {
    "the text of the closing line": (lambda p, seq: end_ev(p, seq, text=f"수고하셨습니다{NUL}"), "INTERVIEW_BAD_TURN", {"field": "text"}),
    "the topic of the closing line": (lambda p, seq: end_ev(p, seq, topic_id=f"x{NUL}"), "INTERVIEW_BAD_TURN", {"field": "topic_id"}),
    "the method of the closing line": (lambda p, seq: end_ev(p, seq, method=f"rules{NUL}"), "INTERVIEW_BAD_TURN", {"field": "method"}),
    "a status key of the final coverage": (lambda p, seq: ingest.EndEvent(status_key(p, closing_phase=True), closing(p, seq)), "INTERVIEW_BAD_COVERAGE", {"field": "topics"}),
}  # fmt: skip


@PG
@pytest.mark.parametrize("build, code, extra", END_CASES.values(), ids=END_CASES.keys())
def test_postgres_a_nul_in_an_end_event_is_a_422_and_the_interview_can_still_end(db, world, clock, build, code, extra):
    sid = new_session(db, world, clock)
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, build(plan, seq), clock, 422, code, **extra)
    still_live(db, sid, 2)  # live, no closing line, nothing changed
    assert end(db, sid, end_ev(plan, seq), clock).outcome == "ended"  # and a clean end event still ends it


@PG
def test_postgres_an_end_reason_with_a_nul_is_stored_as_agent_ended(db, world, clock):
    sid = new_session(db, world, clock)
    plan, seq = ready(db, sid, clock)
    result = end(db, sid, end_ev(plan, seq, reason=f"plan_exhausted{NUL}"), clock)
    assert (result.outcome, result.status, result.end_reason) == ("ended", "completed", "agent_ended")
    stored = row(db, sid)
    assert (stored.end_reason, stored.coverage["end_reason"]) == ("agent_ended", "agent_ended")
