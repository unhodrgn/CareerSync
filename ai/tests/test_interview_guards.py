"""The guards (ai/interview/guards.py, D51, D54): what an interviewer may say, duplicate detection, and the one gate every
analysis passes (verified quotes, known rubric points, screened follow-ups)."""
import pytest

from ai.interview import AnswerType, TurnAnalysis, is_duplicate, sanitize_analysis, screen_spoken, verified_quotes
from ai.interview.guards import MAX_QUESTION_CHARS, VERDICT_WORDS
from ai.tests.interview_helpers import BLOCKLISTS, make_plan

OK = "Java를 실무에서 어떻게 사용했는지 사례와 함께 설명해 주세요."


def test_a_normal_question_passes_and_is_cleaned():
    assert screen_spoken(OK, BLOCKLISTS, "question") == OK
    assert screen_spoken('  "Java를   설명해\n주세요."  ', BLOCKLISTS) == "Java를 설명해 주세요."  # a wrapping pair of quotes goes
    template = "'프로젝트 경험'와(과) 관련해 진행한 프로젝트에서 맡은 역할과 성과를 설명해 주세요."
    assert screen_spoken(template, BLOCKLISTS, "question") == template  # a quote that only starts the line is content


@pytest.mark.parametrize("word", VERDICT_WORDS)
def test_verdict_words_are_never_spoken(word):
    assert screen_spoken(f"이번 면접의 {word} 여부를 알려 드리겠습니다.", BLOCKLISTS) is None


@pytest.mark.parametrize(
    "text",
    ["자세한 내용은 https://example.com/jobs 에서 보세요", "www.example.com 을 참고하세요", "docs.example.io/guide 를 읽어 보세요", "메일은 kim@example.com 으로 주세요"],
)
def test_urls_and_emails_are_rejected(text):
    assert screen_spoken(text, BLOCKLISTS) is None


@pytest.mark.parametrize("text", ["[이름] 님의 경험을 말씀해 주세요", "연락처 [전화번호] 로 확인하겠습니다", "```print(1)```", "[링크]"])
def test_placeholders_and_code_are_rejected(text):
    assert screen_spoken(text, BLOCKLISTS) is None


@pytest.mark.parametrize("text", ["결혼 계획이 있으신가요?", "나이가 어떻게 되시나요?", "종교가 있으신가요?", "고향이 어디신가요?", "건강 상태는 어떠신가요?"])
def test_protected_topics_are_rejected_by_the_interview_blocklist(text):
    assert screen_spoken(text, BLOCKLISTS) is None


def test_without_blocklists_only_the_form_checks_apply():
    assert screen_spoken("결혼 계획이 있으신가요?", []) is not None  # the lists are the caller's to pass
    assert screen_spoken("합격입니다", []) is None


def test_empty_and_overlong_lines_are_rejected():
    assert screen_spoken("", BLOCKLISTS) is None and screen_spoken("   ", BLOCKLISTS) is None
    assert screen_spoken("가" * (MAX_QUESTION_CHARS + 1), BLOCKLISTS, "question") is None
    assert screen_spoken("가" * MAX_QUESTION_CHARS, BLOCKLISTS, "question") is not None
    assert screen_spoken("가" * 201, BLOCKLISTS, "statement") is None


def test_a_closing_line_is_never_a_question():
    assert screen_spoken("수고하셨습니다. 더 하실 말씀 있으세요?", BLOCKLISTS, "closing") is None
    assert screen_spoken("더 하실 말씀 있으세요?", BLOCKLISTS, "question") is not None


def test_duplicates_ignore_spacing_case_and_punctuation():
    assert is_duplicate("Java를 설명해 주세요.", ["java를설명해주세요"])
    assert not is_duplicate("Spring을 설명해 주세요.", ["Java를 설명해 주세요."], ratio=1.0)
    assert is_duplicate("", ["무엇이든"])  # nothing to say counts as a repeat


def test_close_rewordings_are_duplicates_only_with_the_fuzzy_ratio():
    old = "멱등성이 무엇이고 왜 중요한지 사례와 함께 설명해 주세요."
    new = "멱등성이 무엇이고 왜 중요한지 사례와 함께 설명해 주시겠어요?"
    assert is_duplicate(new, [old])  # a model rephrased what was already asked
    assert not is_duplicate(new, [old], ratio=1.0)  # equality only: the template mode


def test_template_lines_that_differ_in_the_topic_word_are_not_duplicates():
    a = "기술 3을(를) 실무나 프로젝트에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요."
    b = "기술 4을(를) 실무나 프로젝트에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요."
    assert not is_duplicate(b, [a], ratio=1.0)


def test_quotes_must_appear_in_the_text_and_are_limited():
    text = "Java 17과 Spring Boot를 사용해 주문 API를 개발했습니다. 배포는 Docker로 했습니다. 결과가 좋았습니다."
    assert verified_quotes(["Spring Boot를 사용해 주문 API를 개발했습니다", "이 문장은 답변에 없습니다 전혀"], text) == (
        "Spring Boot를 사용해 주문 API를 개발했습니다",
    )
    assert len(verified_quotes(["Java 17과 Spring Boot", "Docker로 했습니다", "결과가 좋았습니다"], text)) == 2  # at most two
    assert verified_quotes(["가" * 121], "가" * 200) == ()  # too long to be a quote


ITEM = make_plan().items[1]


def analysis(**kw):
    return TurnAnalysis(kw.pop("answer_type", AnswerType.PARTIAL), **kw)


def test_unknown_rubric_points_and_levels_are_dropped():
    clean = sanitize_analysis(analysis(points={"p1": "demonstrated", "p9": "demonstrated", "p2": "excellent"}), ITEM, "답변", [], BLOCKLISTS)
    assert clean.points == {"p1": "demonstrated"}


def test_unverifiable_quotes_are_dropped():
    answer = "Java 17과 Spring Boot를 사용해 주문 API를 개발했습니다."
    clean = sanitize_analysis(analysis(quotes=("Spring Boot를 사용해 주문 API를 개발했습니다", "지어낸 문장입니다 정말로")), ITEM, answer, [], BLOCKLISTS)
    assert clean.quotes == ("Spring Boot를 사용해 주문 API를 개발했습니다",)


@pytest.mark.parametrize(
    "suggestion",
    ["결혼 계획이 있으신가요?", "합격하려면 무엇을 준비하셨나요?", "https://example.com 을 보셨나요?", "[이름] 님은 어떻게 하셨나요?", "Java를 실무에서 어떻게 사용했는지 사례와 함께 설명해 주세요."],
)
def test_a_follow_up_that_fails_a_screen_or_repeats_a_question_is_dropped(suggestion):
    asked = [OK]
    assert sanitize_analysis(analysis(suggested_follow_up=suggestion), ITEM, "답변", asked, BLOCKLISTS).suggested_follow_up is None


def test_a_clean_new_follow_up_is_kept():
    clean = sanitize_analysis(analysis(suggested_follow_up="그때 가장 어려웠던 점은 무엇이었나요?"), ITEM, "답변", [OK], BLOCKLISTS)
    assert clean.suggested_follow_up == "그때 가장 어려웠던 점은 무엇이었나요?"
