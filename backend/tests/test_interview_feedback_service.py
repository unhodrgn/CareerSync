"""The feedback service of a practice interview (M4 S3b): `stored` and `ensure`.

Real interviews are played through the real engine and the real ingest (`finished_session`), a hand-made session is used where the
stored plan has to be of our choosing, and the feedback model is a recording fake: no network and no key. The races (a second request
at the exact point between two statements, in the model call, where the service holds no transaction) run on one SQLite connection:
they show the logic and prove nothing about parallel requests, which test_interview_feedback_concurrency.py covers on PostgreSQL only."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from ai.interview import InterviewPlan
from ai.interview import feedback as feedback_module
from app.core.config import settings
from app.core.errors import AppError
from app.models import CvDocument, CvProfile, InterviewSession, InterviewTurn, User
from app.models.interview import QuotaKind
from app.services import interview_feedback_service as fb
from app.services import interview_service as svc
from app.services import recommendation_service

from .interview_feedback_fixtures import (
    ANSWER_TEXT,
    USABLE,
    Agent,
    Clock,
    Crash,
    SpyLLM,
    agent_turn,
    candidate_turn,
    covered,
    feedback_used,
    finished_session,
    hand_session,
    install,
    other_session,
    plan_item,
    row,
)
from .interview_fixtures import build_world, new_session, turn_rows

NOTE_ABORTED = feedback_module.NOTE_ABORTED
NOTE_NO_ANSWERS = feedback_module.NOTE_NO_ANSWERS


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return finished_session(db, world, clock)


@pytest.fixture(autouse=True)
def roomy_sessions(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 20)  # tests make several sessions of one seeker in a day


def refused(call, http, code, **extra) -> AppError:
    with pytest.raises(AppError) as error:
        call()
    assert (error.value.status_code, error.value.code) == (http, code), error.value.extra
    for key, value in extra.items():
        assert error.value.extra[key] == value
    return error.value


def unchanged(db, session_id, attempts=0):
    """The feedback columns of a session that no one stored anything for."""
    r = row(db, session_id)
    assert (r.feedback, r.feedback_method, r.feedback_prompt_version, r.feedback_at) == (None, None, None, None)
    assert (r.feedback_lease_until, r.feedback_lease_token) == (None, None)
    assert r.feedback_attempts == attempts


def three_items():
    return [plan_item(1, "Java"), plan_item(2, "Spring Boot"), plan_item(3, "협업", kind="behavioral")]


# ── Rules mode, no answers, and a stored report ──


def test_rules_mode_stores_the_rules_report_as_final_and_asks_for_no_quota(db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.limited, result.reason, result.method, result.prompt_version) == (True, False, None, "rules", "v2")
    assert result.attempts_used == 0 and result.generated_at == clock() and result.data["method"] == "rules"
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_prompt_version) == (result.data, "rules", "v2")
    assert (r.feedback_lease_until, r.feedback_lease_token, r.feedback_attempts) == (None, None, 0)
    assert feedback_used(db, world, clock) == 0


def test_a_stored_report_is_returned_without_a_model_a_lease_or_quota(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    first = fb.ensure(db, world.user, sid, clock=clock)
    assert first.final and first.method == "llm:spy-llm" and len(llm.calls) == 1
    clock.advance(500)
    again = fb.ensure(db, world.user, sid, clock=clock)
    assert (again.data, again.final, again.method, again.attempts_used) == (first.data, True, "llm:spy-llm", 1)
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1
    read = fb.stored(db, world.user, sid, clock=clock)
    assert read is not None and read.data == first.data and read.final


def test_stored_returns_none_when_nothing_was_stored_and_never_generates(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    assert fb.stored(db, world.user, sid, clock=clock) is None
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, sid)


def test_a_session_without_answers_gets_a_final_rules_report_with_no_model_and_no_quota(db, world, clock, monkeypatch):
    empty = new_session(db, world, clock)  # (planned in rules mode: the model is installed afterwards)
    svc.end(db, world.user, empty, clock=clock)  # ended before it started: aborted, a plan, no turns
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, empty, clock=clock)
    assert result.final and result.method == "rules" and NOTE_NO_ANSWERS in result.data["notes"]
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    r = row(db, empty)
    assert r.feedback == result.data and r.feedback_attempts == 0 and r.feedback_lease_token is None


# ── The model path: one call, the attempts, the quota ──


def test_a_usable_model_report_is_stored_with_its_method_and_prompt_version(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db, model="claude-test")
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.limited, result.reason, result.method, result.prompt_version) == (True, False, None, "llm:claude-test", "v2")
    assert result.attempts_used == 1 and result.data["improvements"] == USABLE["improvements"]
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_prompt_version, r.feedback_attempts) == (result.data, "llm:claude-test", "v2", 1)
    assert (r.feedback_lease_until, r.feedback_lease_token) == (None, None)
    assert len(llm.calls) == 1 and feedback_used(db, world, clock) == 1


def test_the_model_is_called_with_no_transaction_open(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    fb.ensure(db, world.user, sid, clock=clock)
    assert llm.in_transaction == [False]


def test_failures_on_attempts_one_and_two_are_provisional_the_third_stores_the_rules_report_and_nothing_asks_a_fourth_time(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db, fail=True)
    install(monkeypatch, llm)
    for attempt in (1, 2):
        result = fb.ensure(db, world.user, sid, clock=clock)
        assert (result.final, result.limited, result.reason, result.method) == (False, False, fb.REASON_MODEL_FAILED, "rules")
        assert (result.prompt_version, result.generated_at, result.attempts_used) == (None, None, attempt)
        r = row(db, sid)  # not stored, and the lease is free again: the seeker can ask at once
        assert (r.feedback, r.feedback_lease_until, r.feedback_lease_token, r.feedback_attempts) == (None, None, None, attempt)
    third = fb.ensure(db, world.user, sid, clock=clock)
    assert (third.final, third.method, third.attempts_used, third.reason) == (True, "rules", 3, None)
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_prompt_version, r.feedback_attempts) == (third.data, "rules", "v2", 3)
    assert r.feedback_lease_token is None
    fourth = fb.ensure(db, world.user, sid, clock=clock)
    assert fourth.final and fourth.data == third.data
    assert len(llm.calls) == 3 and feedback_used(db, world, clock) == 3


def test_a_reply_with_nothing_usable_counts_as_a_failure(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db, reply={"strengths": [], "gaps": [], "improvements": ["서울 본사의 요구 사항을 이해해 보세요."], "practice_questions": []})
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)  # a sentence about the company is dropped: nothing is left
    assert (result.final, result.reason, result.method) == (False, fb.REASON_MODEL_FAILED, "rules")
    assert row(db, sid).feedback is None and feedback_used(db, world, clock) == 1


def test_an_unexpected_error_after_the_reservation_frees_the_lease_and_keeps_the_attempt_and_the_quota(db, world, clock, sid, monkeypatch):
    install(monkeypatch, SpyLLM(db))
    monkeypatch.setattr(fb, "_model_report", lambda *a, **k: (_ for _ in ()).throw(ValueError("bug")))
    with pytest.raises(ValueError):
        fb.ensure(db, world.user, sid, clock=clock)
    unchanged(db, sid, attempts=1)
    assert feedback_used(db, world, clock) == 1


def test_the_daily_quota_is_shared_by_all_sessions_of_a_seeker_and_resets_on_the_next_kst_day(db, world, clock, monkeypatch):
    sessions = [finished_session(db, world, clock) for _ in range(4)]
    llm = SpyLLM(db, fail=True)
    install(monkeypatch, llm)
    for sid_ in sessions[:3]:
        assert fb.ensure(db, world.user, sid_, clock=clock).reason == fb.REASON_MODEL_FAILED
    assert feedback_used(db, world, clock) == 3 and len(llm.calls) == 3
    limited = fb.ensure(db, world.user, sessions[3], clock=clock)
    assert (limited.final, limited.limited, limited.reason, limited.method, limited.attempts_used) == (False, True, fb.REASON_QUOTA, "rules", 0)
    unchanged(db, sessions[3])  # the lease and the attempt were rolled back with the refused reservation
    assert feedback_used(db, world, clock) == 3 and len(llm.calls) == 3
    llm.fail = False
    clock.advance(24 * 3600)  # the next KST day
    again = fb.ensure(db, world.user, sessions[3], clock=clock)
    assert (again.final, again.limited, again.method) == (True, False, "llm:spy-llm") and feedback_used(db, world, clock) == 1


def test_a_refused_reservation_gives_a_provisional_report_and_nothing_is_kept(db, world, clock, sid, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 0)
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.limited, result.reason) == (False, True, fb.REASON_QUOTA)
    assert result.data["method"] == "rules" and llm.calls == []
    unchanged(db, sid)
    assert feedback_used(db, world, clock) == 0


# ── Who may ask, and when ──


def test_consent_withdrawal_blocks_every_new_generation_in_both_modes_and_keeps_a_stored_report_readable(db, world, clock, monkeypatch):
    done, fresh = finished_session(db, world, clock), finished_session(db, world, clock)
    install(monkeypatch, SpyLLM(db))
    stored_report = fb.ensure(db, world.user, done, clock=clock)
    world.user.consent_ai_at = None  # DELETE /api/users/me/consent/ai
    db.commit()
    for llm in (None, SpyLLM(db)):
        install(monkeypatch, llm)
        refused(lambda: fb.ensure(db, world.user, fresh, clock=clock), 409, fb.CONSENT_REQUIRED)
        unchanged(db, fresh)
        again = fb.ensure(db, world.user, done, clock=clock)
        assert again.final and again.data == stored_report.data
        read = fb.stored(db, world.user, done, clock=clock)
        assert read is not None and read.data == stored_report.data
        assert fb.stored(db, world.user, fresh, clock=clock) is None
    assert feedback_used(db, world, clock) == 1


def test_withdrawn_consent_blocks_a_provisional_report_too(db, world, clock, monkeypatch):
    install(monkeypatch, None)
    odd = hand_session(db, world, clock, three_items(), sha256="0" * 64)  # would be a provisional report: the digest does not match
    world.user.consent_ai_at = None
    db.commit()
    refused(lambda: fb.ensure(db, world.user, odd, clock=clock), 409, fb.CONSENT_REQUIRED)


def test_an_unconfirmed_new_cv_does_not_block_the_feedback_of_an_old_interview(db, world, clock, sid, monkeypatch):
    document = CvDocument(seeker_id=world.user.id, file_name="new.pdf", sha256="1" * 64, pages=1, masked_text="경력\n- Python")
    db.add(document)
    db.flush()
    db.add(CvProfile(cv_document_id=document.id, seeker_id=world.user.id, version=2, schema_version="cv_profile.v1", method="rules"))
    db.commit()
    with pytest.raises(AppError) as gate:  # the check of the other seeker features would refuse now
        recommendation_service.check_seeker(db, world.user)
    assert gate.value.code == "CV_NOT_CONFIRMED"
    install(monkeypatch, SpyLLM(db))
    assert fb.ensure(db, world.user, sid, clock=clock).final


def test_only_the_owner_reads_or_makes_feedback_and_companies_are_refused(db, world, clock, sid, monkeypatch):
    install(monkeypatch, SpyLLM(db))
    other = build_world(db, email="s2@interview.test")
    company = build_world(db, email="hr@interview.test", role="company")
    for call in (lambda: fb.ensure(db, other.user, sid, clock=clock), lambda: fb.stored(db, other.user, sid, clock=clock)):
        refused(call, 404, svc.NOT_FOUND)
    for call in (lambda: fb.ensure(db, company.user, sid, clock=clock), lambda: fb.stored(db, company.user, sid, clock=clock)):
        refused(call, 403, "SEEKER_ONLY")
    refused(lambda: fb.ensure(db, world.user, sid + 999, clock=clock), 404, svc.NOT_FOUND)
    unchanged(db, sid)
    clock.advance(31 * 24 * 3600)  # past the 30 days: hidden like a deleted one
    refused(lambda: fb.ensure(db, world.user, sid, clock=clock), 404, svc.NOT_FOUND)
    refused(lambda: fb.stored(db, world.user, sid, clock=clock), 404, svc.NOT_FOUND)


def test_the_other_seekers_report_is_never_returned(db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    fb.ensure(db, world.user, sid, clock=clock)
    other = build_world(db, email="s2@interview.test")
    refused(lambda: fb.stored(db, other.user, sid, clock=clock), 404, svc.NOT_FOUND)
    refused(lambda: fb.ensure(db, other.user, sid, clock=clock), 404, svc.NOT_FOUND)


def test_an_interview_that_is_not_over_has_no_feedback_yet(db, world, clock, monkeypatch):
    created = new_session(db, world, clock)
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    refused(lambda: fb.ensure(db, world.user, created, clock=clock), 409, fb.NOT_ENDED, status="created")
    install(monkeypatch, None)
    Agent(db, created, clock).start()
    install(monkeypatch, llm)
    refused(lambda: fb.ensure(db, world.user, created, clock=clock), 409, fb.NOT_ENDED, status="live")
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, created)


# ── The plan: the digest, the safe views, the topic mapping ──


def test_a_plan_that_does_not_match_its_digest_gives_a_provisional_rules_report_and_no_model_no_quota_no_attempt(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    stored_plan = row(db, sid).plan
    tampered = {**stored_plan, "items": [{**stored_plan["items"][0], "question": stored_plan["items"][0]["question"] + " "}, *stored_plan["items"][1:]]}
    db.execute(InterviewSession.__table__.update().where(InterviewSession.id == sid).values(plan=tampered))
    db.commit()
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.limited, result.reason, result.method, result.attempts_used) == (False, False, fb.REASON_PLAN_INVALID, "rules", 0)
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, sid)
    assert fb.ensure(db, world.user, sid, clock=clock).reason == fb.REASON_PLAN_INVALID  # and again: nothing is stored, ever


def test_a_missing_digest_is_provisional_and_no_plan_at_all_is_refused(db, world, clock, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    items = three_items()
    no_digest = hand_session(db, world, clock, items, sha256=None, coverage=covered(items, {}))
    assert fb.ensure(db, world.user, no_digest, clock=clock).reason == fb.REASON_PLAN_INVALID
    no_plan = hand_session(db, world, clock, items, plan_data=None, coverage=covered(items, {}))
    refused(lambda: fb.ensure(db, world.user, no_plan, clock=clock), 409, fb.PLAN_INVALID)
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, no_digest)
    unchanged(db, no_plan)


@pytest.mark.parametrize(
    "plan_data",
    [
        {"items": []},  # nothing to give feedback on
        {"items": [{"topic_id": "c1"}]},  # unreadable: a key is missing
        {"items": "oops"},
        {"nothing": 1},
    ],
)
def test_no_safe_view_of_the_plan_is_a_409_and_no_model_is_called(db, world, clock, monkeypatch, plan_data):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    broken = hand_session(db, world, clock, [], plan_data=plan_data)
    refused(lambda: fb.ensure(db, world.user, broken, clock=clock), 409, fb.PLAN_INVALID)
    assert llm.calls == [] and feedback_used(db, world, clock) == 0
    unchanged(db, broken)


def test_a_plan_whose_topic_ids_repeat_has_no_faithful_mapping_and_is_refused(db, world, clock, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    twice = hand_session(db, world, clock, [plan_item(1, "Java"), plan_item(1, "Java")])
    refused(lambda: fb.ensure(db, world.user, twice, clock=clock), 409, fb.PLAN_INVALID)
    assert llm.calls == []


def test_a_clean_hand_made_plan_is_a_fixed_point_of_the_validation(db, world, clock):
    """The fixtures of the mapping tests: with this plan the validation changes nothing, so a difference below is the test's doing."""
    from ai.interview import plan_view_from

    from app.services.career_service import interview_blocklists

    plan = InterviewPlan(tuple(three_items()), ())
    view = plan_view_from(plan, None, blocklists=interview_blocklists())
    assert view.issues == () and view.topic_ids == ("c1", "c2", "c3")


def mapping_session(db, world, clock):
    """Original plan [c1, c2, c3]; the validation drops c2 (a kind it does not know), so the validated plan is [c1, c3]. The turns point
    at item 0 (c1) and item 2 (c3); there is no turn for c2."""
    items = [plan_item(1, "Java"), plan_item(2, "Spring Boot", kind="bogus"), plan_item(3, "협업", kind="behavioral")]
    q1, q3 = "Java 트랜잭션 처리를 직접 설계했습니다", "팀원들과 코드 리뷰로 협업했습니다"
    turns = [
        agent_turn(1, 0, "Java를 실무에서 어떻게 사용했는지 설명해 주세요."),
        candidate_turn(2, 0, f"저는 {q1}. 그래서 장애가 줄었습니다.", q1),
        agent_turn(3, 2, "협업를 실무에서 어떻게 사용했는지 설명해 주세요."),
        candidate_turn(4, 2, f"저는 {q3}. 배운 점이 많았습니다.", q3),
    ]
    statuses = {"c1": "demonstrated", "c3": "demonstrated"}
    sid = hand_session(db, world, clock, items, turns=turns, coverage=covered(items, statuses))
    return sid, q1, q3


def test_topic_ids_come_from_the_original_plan_order_when_validation_drops_an_item(db, world, clock, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    seen = {}
    real = fb.rules_feedback

    def spy(safe_turns, safe_plan, **kwargs):
        seen["turns"], seen["plan"] = tuple(safe_turns), safe_plan
        return real(safe_turns, safe_plan, **kwargs)

    monkeypatch.setattr(fb, "rules_feedback", spy)
    sid, q1, q3 = mapping_session(db, world, clock)
    result = fb.ensure(db, world.user, sid, clock=clock)
    # The validated plan is [c1, c3]: the naive mapping would send item 2 nowhere and item 1 to c3
    assert seen["plan"].topic_ids == ("c1", "c3") and seen["plan"].issues
    assert [(t.seq, t.role, t.topic_id) for t in seen["turns"]] == [(1, "agent", "c1"), (2, "candidate", "c1"), (3, "agent", "c3"), (4, "candidate", "c3")]
    assert not any(t.topic_id == "c2" for t in seen["turns"])
    strengths = {s["topic_id"]: s["quotes"] for s in result.data["strengths"]}
    assert strengths == {"c1": [q1], "c3": [q3]}  # each strength has its own topic's quote and no other
    assert not [s for s in result.data["strengths"] if s["topic_id"] == "c2"]
    # Untrusted (the plan is not what it was): provisional, and never a model
    assert (result.final, result.reason) == (False, fb.REASON_PLAN_INVALID) and llm.calls == []
    unchanged(db, sid)


def test_the_model_gets_each_candidate_line_under_the_topic_of_its_item_index(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    fb.ensure(db, world.user, sid, clock=clock)
    topics = [i["topic_id"] for i in row(db, sid).plan["items"]]
    expected = [f"{topics[t.item_index]} | {'candidate' if t.role == 'candidate' else 'interviewer'}" for t in turn_rows(db, sid) if t.kind != "closing"]
    (system, user, _schema), = llm.calls
    block = user.split("<transcript>\n", 1)[1].split("\n</transcript>", 1)[0].splitlines()
    assert [line.rsplit(" | ", 1)[0] for line in block][: len(expected)] == expected


# ── An interrupted interview (a stale live session) ──


def test_a_stale_live_session_gets_feedback_with_an_interruption_note_and_no_changed_status(db, world, clock, monkeypatch):
    install(monkeypatch, None)
    sid = new_session(db, world, clock)
    agent = Agent(db, sid, clock)
    agent.start()
    agent.answer(ANSWER_TEXT)
    refused(lambda: fb.ensure(db, world.user, sid, clock=clock), 409, fb.NOT_ENDED, status="live")
    clock.advance(600 + settings.INTERVIEW_END_GRACE_SECONDS + 5)  # past the budget and the grace: stale for every reader
    before = row(db, sid)
    coverage = dict(before.coverage)
    assert before.status == "live" and coverage["phase"] == "listening"
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert result.final and NOTE_ABORTED in result.data["notes"]
    assert {t["topic_id"]: t["status"] for t in result.data["topics"]} == coverage["status"]  # no topic status was changed
    after = row(db, sid)
    assert (after.status, after.end_reason, after.coverage) == ("live", None, coverage)  # and the session itself was not settled by this


def test_the_interruption_note_is_the_same_after_the_session_is_settled_and_absent_for_a_completed_one(db, world, clock, monkeypatch):
    install(monkeypatch, None)
    sid = new_session(db, world, clock)
    agent = Agent(db, sid, clock)
    agent.start()
    agent.answer(ANSWER_TEXT)
    clock.advance(700)
    svc.settle(db, world.user.id, clock())
    assert row(db, sid).status == "aborted" and row(db, sid).end_reason == "stale_live"
    assert NOTE_ABORTED in fb.ensure(db, world.user, sid, clock=clock).data["notes"]
    done = finished_session(db, world, clock)
    assert NOTE_ABORTED not in fb.ensure(db, world.user, done, clock=clock).data["notes"]


# ── The lease ──


def test_a_request_while_a_valid_lease_is_held_gets_409_busy_with_the_seconds_to_wait_and_never_a_second_call(db, world, clock, sid, monkeypatch):
    seen = []

    def another_request(llm):
        second = other_session(db)
        try:
            for later in (0, 45):
                clock.advance(later)
                with pytest.raises(AppError) as busy:
                    fb.ensure(second, second.get(User, world.user.id), sid, clock=clock)
                seen.append((busy.value.status_code, busy.value.code, busy.value.extra["retry_after_seconds"]))
        finally:
            second.close()
            clock.advance(-45)

    llm = SpyLLM(db, on_call=another_request)
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert seen == [(409, fb.BUSY, 120), (409, fb.BUSY, 75)]
    assert result.final and len(llm.calls) == 1 and feedback_used(db, world, clock) == 1
    assert row(db, sid).feedback_attempts == 1


def test_a_worker_whose_lease_ran_out_loses_the_session_to_the_next_request_and_returns_its_stored_report(db, world, clock, sid, monkeypatch):
    b_llm = SpyLLM(db, model="llm-b")

    def worker_b(llm):
        clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)  # A's lease has run out
        second = other_session(db)
        try:
            taken = fb.ensure(second, second.get(User, world.user.id), sid, clock=clock)
        finally:
            second.close()
        assert (taken.final, taken.method, taken.attempts_used) == (True, "llm:llm-b", 2)

    a_llm = SpyLLM(db, model="llm-a", on_call=worker_b)
    llms = iter([a_llm, b_llm])
    monkeypatch.setattr(fb.ai_runtime, "llm", lambda: next(llms))
    a = fb.ensure(db, world.user, sid, clock=clock)
    # A finished after B stored: its own report was not stored and not returned; the winner's is
    assert (a.final, a.method, a.attempts_used) == (True, "llm:llm-b", 2)
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_attempts, r.feedback_lease_token) == (a.data, "llm:llm-b", 2, None)
    assert len(a_llm.calls) == len(b_llm.calls) == 1 and feedback_used(db, world, clock) == 2


def test_a_stale_worker_returns_its_own_report_provisionally_while_the_winner_still_holds_the_lease(db, world, clock, sid, monkeypatch):
    held = {}

    def worker_b_takes_over(llm):
        clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)
        second = other_session(db)
        try:
            claim = fb._claim(second, sid, world.user.id, clock())  # B's T1: B is now in its own model call
        finally:
            second.close()
        assert isinstance(claim, fb._Claimed) and claim.attempt == 2
        held["b"] = claim

    llm = SpyLLM(db, on_call=worker_b_takes_over)
    install(monkeypatch, llm)
    a = fb.ensure(db, world.user, sid, clock=clock)
    assert (a.final, a.reason, a.method, a.limited, a.generated_at, a.attempts_used) == (False, fb.REASON_LEASE_LOST, "llm:spy-llm", False, None, 1)
    assert a.data["improvements"] == USABLE["improvements"]  # its own report, whole
    r = row(db, sid)  # A changed nothing: B's lease, B's attempt, no report
    assert (r.feedback, r.feedback_lease_token, r.feedback_attempts) == (None, held["b"].token, 2)
    assert feedback_used(db, world, clock) == 2
    # and B can still finish
    db.rollback()
    assert fb._store(db, sid, world.user.id, fb.rules_feedback([], fb.plan_view_from(InterviewPlan.from_dict(r.plan), None)), clock(), token=held["b"].token)
    assert row(db, sid).feedback is not None


def test_a_stale_worker_cannot_release_the_lease_of_the_worker_that_took_over(db, world, clock, sid, monkeypatch):
    held = {}

    def worker_b_takes_over(llm):
        clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)
        second = other_session(db)
        try:
            held["b"] = fb._claim(second, sid, world.user.id, clock())
        finally:
            second.close()
        held["lease"] = row(db, sid).feedback_lease_until

    llm = SpyLLM(db, fail=True, on_call=worker_b_takes_over)  # A's model fails: A releases... and must find the lease is not its own
    install(monkeypatch, llm)
    a = fb.ensure(db, world.user, sid, clock=clock)
    assert (a.final, a.reason) == (False, fb.REASON_MODEL_FAILED)
    r = row(db, sid)
    assert (r.feedback_lease_token, r.feedback_lease_until, r.feedback_attempts, r.feedback) == (held["b"].token, held["lease"], 2, None)


def test_the_release_and_the_store_are_fenced_by_the_token(db, world, clock, sid):
    taken = fb._claim(db, sid, world.user.id, clock())
    assert isinstance(taken, fb._Claimed) and len(taken.token) == 32
    lease = row(db, sid).feedback_lease_until
    fb._release(db, sid, "f" * 32)  # not ours
    assert row(db, sid).feedback_lease_token == taken.token and row(db, sid).feedback_lease_until == lease
    report = fb.rules_feedback([], fb.plan_view_from(InterviewPlan.from_dict(row(db, sid).plan), None))
    assert fb._store(db, sid, world.user.id, report, clock(), token="f" * 32) is False
    assert row(db, sid).feedback is None
    assert fb._store(db, sid, world.user.id, report, clock(), token=taken.token) is True
    first = row(db, sid).feedback
    again = fb.rules_feedback([], fb.plan_view_from(InterviewPlan.from_dict(row(db, sid).plan), {"phase": "aborted"}))
    assert fb._store(db, sid, world.user.id, again, clock(), token=taken.token) is False  # a stored report is never overwritten
    assert fb._store(db, sid, world.user.id, again, clock(), token=None) is False
    assert row(db, sid).feedback == first


def test_a_slow_worker_that_nobody_replaced_can_still_store_after_its_lease_ran_out(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db, on_call=lambda _llm: clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 30))
    install(monkeypatch, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert result.final and result.method == "llm:spy-llm" and result.attempts_used == 1
    assert row(db, sid).feedback_attempts == 1 and feedback_used(db, world, clock) == 1


def test_a_session_deleted_during_generation_is_a_404_the_report_is_dropped_and_the_reservation_stays_spent(db, world, clock, sid, monkeypatch):
    def delete_it(llm):
        second = other_session(db)
        try:
            svc.delete(second, second.get(User, world.user.id), sid, clock=clock)
        finally:
            second.close()

    llm = SpyLLM(db, on_call=delete_it)
    install(monkeypatch, llm)
    refused(lambda: fb.ensure(db, world.user, sid, clock=clock), 404, svc.NOT_FOUND)
    db.rollback()
    assert db.get(InterviewSession, sid) is None
    assert db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == sid)).first() is None
    assert feedback_used(db, world, clock) == 1  # the ledger has no link to a session: nothing was given back
    assert len(llm.calls) == 1


# ── The third attempt crashes ──


def test_a_crashed_third_attempt_is_recovered_by_the_next_request_with_the_rules_report_and_no_model_call(db, world, clock, sid, monkeypatch):
    install(monkeypatch, SpyLLM(db, fail=True))
    for _ in range(2):
        fb.ensure(db, world.user, sid, clock=clock)
    monkeypatch.setattr(fb, "_release", lambda *a, **k: None)  # a process that dies does not release anything
    crash = SpyLLM(db, crash=True)
    install(monkeypatch, crash)
    with pytest.raises(Crash):
        fb.ensure(db, world.user, sid, clock=clock)
    r = row(db, sid)
    assert (r.feedback, r.feedback_attempts) == (None, 3) and r.feedback_lease_token is not None
    refused(lambda: fb.ensure(db, world.user, sid, clock=clock), 409, fb.BUSY, retry_after_seconds=120)  # its lease is still valid
    clock.advance(settings.INTERVIEW_FEEDBACK_LEASE_SECONDS + 1)
    after = SpyLLM(db)
    install(monkeypatch, after)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.reason, result.attempts_used) == (True, "rules", None, 3)
    r = row(db, sid)
    assert (r.feedback, r.feedback_method, r.feedback_attempts, r.feedback_lease_token) == (result.data, "rules", 3, None)
    assert after.calls == [] and len(crash.calls) == 1 and feedback_used(db, world, clock) == 3  # no fourth call, no fourth reservation
    assert fb.ensure(db, world.user, sid, clock=clock).data == result.data


def test_attempts_at_the_cap_with_a_dead_lease_are_recovered_without_a_model(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    db.execute(
        InterviewSession.__table__.update()
        .where(InterviewSession.id == sid)
        .values(feedback_attempts=3, feedback_lease_until=clock() - timedelta(seconds=1), feedback_lease_token="a" * 32)
    )
    db.commit()
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert result.final and result.method == "rules" and llm.calls == [] and feedback_used(db, world, clock) == 0
    assert row(db, sid).feedback_lease_token is None


def between_the_read_and_the_reservation(db, monkeypatch, act, llm):
    """Run `act` (another request, on a session of its own) after the service has read the session and before it reserves anything:
    the service takes its model client at exactly that point."""

    def take():
        second = other_session(db)
        try:
            act(second)
        finally:
            second.close()
        return llm

    monkeypatch.setattr(fb.ai_runtime, "llm", take)



def test_a_report_stored_between_the_read_and_the_reservation_is_returned_and_nothing_is_reserved(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)

    def another_request_stores(second):
        report = fb.rules_feedback([], fb.plan_view_from(InterviewPlan.from_dict(row(second, sid).plan), None))
        assert fb._store(second, sid, world.user.id, report, clock(), token=None)

    between_the_read_and_the_reservation(db, monkeypatch, another_request_stores, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.attempts_used) == (True, "rules", 0)
    assert llm.calls == [] and feedback_used(db, world, clock) == 0  # no lease, no attempt, no reservation, no model
    r = row(db, sid)
    assert (r.feedback, r.feedback_attempts, r.feedback_lease_token) == (result.data, 0, None)


def test_attempts_used_up_between_the_read_and_the_reservation_store_the_rules_report_and_ask_no_fourth_time(db, world, clock, sid, monkeypatch):
    llm = SpyLLM(db)

    def the_third_attempt_died(second):
        second.execute(
            InterviewSession.__table__.update()
            .where(InterviewSession.id == sid)
            .values(feedback_attempts=3, feedback_lease_until=clock() - timedelta(seconds=1), feedback_lease_token="b" * 32)
        )
        second.commit()

    between_the_read_and_the_reservation(db, monkeypatch, the_third_attempt_died, llm)
    result = fb.ensure(db, world.user, sid, clock=clock)
    assert (result.final, result.method, result.attempts_used) == (True, "rules", 3)
    r = row(db, sid)
    assert (r.feedback_attempts, r.feedback_lease_token, r.feedback_method) == (3, None, "rules")  # never a fourth attempt
    assert llm.calls == [] and feedback_used(db, world, clock) == 0


def test_the_rules_report_waits_for_a_valid_lease_instead_of_taking_it(db, world, clock, sid, monkeypatch):
    install(monkeypatch, None)
    taken = fb._claim(db, sid, world.user.id, clock())
    assert isinstance(taken, fb._Claimed)
    refused(lambda: fb.ensure(db, world.user, sid, clock=clock), 409, fb.BUSY, retry_after_seconds=120)
    assert row(db, sid).feedback is None and row(db, sid).feedback_lease_token == taken.token


# ── What reaches the model ──


def test_nothing_personal_or_of_the_cv_reaches_the_model(db, world, clock, monkeypatch):
    from .interview_fixtures import KEPT_LINES, REMOVED_LINES

    world.user.display_name = "홍길동"
    db.commit()
    spoken = "저는 홍길동이고 스물일곱 살입니다. 군필이고 연락처는 010-1234-5678입니다. " + ANSWER_TEXT + " 메일은 s1@interview.test 입니다."
    sid = finished_session(db, world, clock, text=spoken, names=("홍길동",))
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    fb.ensure(db, world.user, sid, clock=clock)
    assert len(llm.calls) == 1
    system, user, schema = llm.calls[0]
    sent = system + "\n" + user
    assert "Java" in user  # the professional part of what was said did go
    for secret in ("홍길동", "s1@interview.test", "010-1234-5678", "스물일곱", "군필", "서울특별시", *REMOVED_LINES, *KEPT_LINES):
        assert secret not in sent, secret
    for word in ("weight", "가중치", "masked_kinds", "answer_type", "analysis", "display_name", "email", "password"):
        assert word not in sent, word
    assert schema.__name__ == "FeedbackLlmOut"


def test_no_model_input_is_built_for_a_session_with_nothing_to_work_with(db, world, clock, monkeypatch):
    llm = SpyLLM(db)
    install(monkeypatch, llm)
    items = three_items()
    silent = hand_session(db, world, clock, items, turns=[agent_turn(1, 0, "Java를 실무에서 어떻게 사용했는지 설명해 주세요.")], coverage=covered(items, {}, phase="aborted", end_reason="candidate_left"))
    result = fb.ensure(db, world.user, silent, clock=clock)
    assert result.final and NOTE_NO_ANSWERS in result.data["notes"] and llm.calls == [] and feedback_used(db, world, clock) == 0
