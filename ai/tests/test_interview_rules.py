"""Rules-mode analysis (ai/interview/rules.py, D51, D52, D54): every answer type, per-point coverage, verified quotes,
rubric generation, and the fixed Korean lines."""
import pytest

from ai.interview import AnswerType, screen_spoken
from ai.interview import rules
from ai.interview.rules import analyze, best_levels, make_rubric
from ai.interview.types import MAX_RUBRIC_POINTS, MIN_RUBRIC_POINTS
from ai.tests.helpers import SKILLS
from ai.tests.interview_helpers import BLOCKLISTS, CV_LINES, GOOD, OFF_TOPIC, PARTIAL_JAVA, make_plan

PLAN = make_plan()
JAVA = next(i for i in PLAN.items if i.topic_id == "c1")
BEHAVIORAL = PLAN.items[-1]


def kind(text: str, item=JAVA) -> AnswerType:
    return analyze(text, item).answer_type


@pytest.mark.parametrize("text", ["", "   ", "음...", "어 음", "음음 어어 ..."])
def test_empty_answers(text):
    assert kind(text) is AnswerType.EMPTY


@pytest.mark.parametrize("text", ["네", "그렇습니다", "예 맞아요", "글쎄요", "음 그냥요"])
def test_too_short_answers_are_the_ones_with_no_content(text):
    assert kind(text) is AnswerType.TOO_SHORT


@pytest.mark.parametrize(
    "text",
    ["다시 한번 말씀해 주세요", "질문을 다시 읽어 주시겠어요", "한 번 더요", "Could you repeat that?", "뭐라고요?", "질문이 뭐였죠"],
)
def test_repeat_requests(text):
    assert kind(text) is AnswerType.REPEAT_REQUEST


@pytest.mark.parametrize("text", ["무슨 뜻인가요?", "질문을 이해가 잘 안 돼요", "What do you mean?", "좀 더 쉽게 말씀해 주세요"])
def test_clarification_requests(text):
    assert kind(text) is AnswerType.CLARIFICATION_REQUEST


@pytest.mark.parametrize("text", ["잘 모르겠습니다", "I don't know", "써본 적이 없습니다", "기억이 잘 안 나요", "모릅니다"])
def test_dont_know(text):
    assert kind(text) is AnswerType.DONT_KNOW


def test_a_hesitation_is_not_taken_for_a_request_to_repeat():
    assert kind("저기 그러니까 음 그게 참 뭐라고 해야 할지 모르겠지만 그냥 그렇습니다") is AnswerType.OFF_TOPIC
    assert kind("뭐라고 하셨죠") is AnswerType.REPEAT_REQUEST  # but "what did you say" still is one


def test_a_long_answer_that_mentions_repeating_is_still_an_answer():
    text = "실패하면 다시 시도하는 재시도 로직을 구현했고 Java 17과 Spring Boot를 사용했습니다. 한 번 더 확인하는 단계도 넣었습니다."
    assert kind(text) not in (AnswerType.REPEAT_REQUEST, AnswerType.CLARIFICATION_REQUEST)


def test_dont_know_followed_by_a_real_answer_is_a_partial_answer_not_a_refusal():
    text = "정확히는 모르겠지만 Java 17에서 Spring Boot로 주문 API를 개발하며 실무 프로젝트에서 사용했습니다."
    assert kind(text) in (AnswerType.PARTIAL, AnswerType.ANSWERED)


def test_off_topic_answers():
    assert kind(OFF_TOPIC) is AnswerType.OFF_TOPIC


def test_a_behavioral_question_is_never_judged_off_topic():
    assert BEHAVIORAL.kind == "behavioral" and kind(OFF_TOPIC, BEHAVIORAL) is not AnswerType.OFF_TOPIC


def test_a_complete_answer_shows_every_point():
    a = analyze(GOOD["c1"], JAVA)
    assert a.answer_type is AnswerType.ANSWERED
    assert a.points == {"p1": "demonstrated", "p2": "demonstrated"}


def test_a_partial_answer_shows_some_points_and_leaves_the_rest_missing():
    a = analyze(PARTIAL_JAVA, JAVA)
    assert a.answer_type is AnswerType.PARTIAL
    assert a.points["p1"] == "demonstrated" and a.points["p2"] == "not_shown"


def test_one_cue_word_is_only_partial_for_a_generic_point():
    item = next(i for i in PLAN.items if i.topic_id == "warmup")
    assert analyze("프로젝트 하나 했습니다 그냥 열심히 했어요", item).points["p1"] == "partial"  # one of two cues needed


def test_a_latin_cue_matches_whole_words_only():
    # "java" must not be found inside "javascript": that answer shows no Java cue at all (so it is off topic here)
    other = analyze("저는 JavaScript 프레임워크를 오래 다뤘고 프로젝트도 많이 했습니다", JAVA)
    assert other.points.get("p1") != "demonstrated" and other.answer_type is AnswerType.OFF_TOPIC
    assert analyze("저는 Java 언어를 오래 다뤘고 프로젝트도 많이 했습니다", JAVA).points["p1"] == "demonstrated"


def test_quotes_are_verbatim_parts_of_the_answer_and_at_most_two():
    answer = GOOD["c2"]
    a = analyze(answer, next(i for i in PLAN.items if i.topic_id == "c2"))
    assert 1 <= len(a.quotes) <= 2
    assert all(quote in answer and 4 <= len(quote) <= 120 for quote in a.quotes)


def test_a_rules_analysis_never_suggests_a_follow_up_or_claims_a_model():
    a = analyze(GOOD["c1"], JAVA)
    assert a.suggested_follow_up is None and a.method == "rules"


def test_best_levels_keeps_the_strongest_level_per_point():
    merged = best_levels({"p1": "partial", "p2": "not_shown"}, {"p1": "demonstrated", "p2": "partial"}, {"p3": "not_shown"})
    assert merged == {"p1": "demonstrated", "p2": "partial", "p3": "not_shown"}


@pytest.mark.parametrize("category", ["skill", "experience", "project", "education", "certificate", "other", "unknown"])
@pytest.mark.parametrize("description", ["", "Java 17", "Java 17, Spring Boot 사용 경험", "A 기술, B 기술, C 기술, D 기술, E 기술 모두", "---"])
def test_the_rubric_always_has_two_to_four_points(category, description):
    points = make_rubric("기술", category, description, SKILLS)
    assert MIN_RUBRIC_POINTS <= len(points) <= MAX_RUBRIC_POINTS
    assert len({p.id for p in points}) == len(points) and all(p.keywords and p.min_hits >= 1 for p in points)


def test_description_clauses_become_points_before_generic_ones():
    points = make_rubric("API", "skill", "REST 설계, 문서화 경험", SKILLS)
    assert [p.text for p in points] == ["REST 설계", "문서화 경험"]


def test_inflected_words_still_match_through_their_stem():
    [p1, *_] = make_rubric("API", "project", "REST API를 설계하고 문서화한 경험", SKILLS)
    assert "설계" in p1.keywords and "문서화" in p1.keywords  # 설계하고 -> 설계, so "설계했습니다" counts


FIXED_LINES = {
    "CLARIFY_TEXT": rules.CLARIFY_TEXT,
    "NUDGE_TEXT": rules.NUDGE_TEXT,
    "BRIDGE_TEXT": rules.BRIDGE_TEXT,
    "SKIP_BRIDGE_TEXT": rules.SKIP_BRIDGE_TEXT,
    "GENERIC_FOLLOW_UP": rules.GENERIC_FOLLOW_UP,
    "GENERIC_REPHRASE": rules.GENERIC_REPHRASE,
    "GENERIC_REDIRECT": rules.GENERIC_REDIRECT,
}


@pytest.mark.parametrize("name", FIXED_LINES)
def test_every_fixed_line_passes_the_spoken_guards(name):
    assert screen_spoken(FIXED_LINES[name], BLOCKLISTS) == FIXED_LINES[name], name


@pytest.mark.parametrize("reason", ["plan_exhausted", "time", "empty_plan", "anything else"])
def test_every_closing_line_passes_the_guards_and_is_not_a_question(reason):
    text = rules.closing_text(reason)
    assert screen_spoken(text, BLOCKLISTS, "closing") == text and "?" not in text


def test_generated_lines_pass_the_guards():
    lines = [rules.rephrase_text(None, "experience"), rules.rephrase_text(None, "behavioral"), rules.rephrase_text("REST API", "technical")]
    lines += [rules.redirect_text("REST API"), rules.redirect_text(None)]
    lines += [rules.follow_up_text(p) for item in PLAN.items for p in item.rubric]
    lines += [rules.fallback_question("REST API 설계"), *(rules.warmup_question(line) for line in CV_LINES)]
    assert lines and all(screen_spoken(line, BLOCKLISTS) is not None for line in lines), [
        line for line in lines if screen_spoken(line, BLOCKLISTS) is None
    ]
