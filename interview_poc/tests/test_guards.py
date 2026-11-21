"""Masking of spoken personal data and the screens on what the LLM writes."""
import pytest

from guards import (
    BIRTH,
    EMAIL,
    NAME,
    PHONE,
    RRN,
    URL,
    mask_speech_event,
    mask_spoken_pii,
    screen_closing,
    screen_followup,
)


def masked(text, names=()):
    return mask_spoken_pii(text, names).text


# ── masking ──


@pytest.mark.parametrize(
    "spoken, placeholder, leaked",
    [
        ("제 번호는 010-1234-5678입니다", PHONE, "1234"),
        ("연락처는 01012345678 입니다", PHONE, "12345678"),
        ("전화는 02-123-4567로 주세요", PHONE, "4567"),
        ("공일공 일이삼사 오육칠팔로 연락 주세요", PHONE, "일이삼사"),
        ("공 일 공 일 이 삼 사 오 육 칠 팔", PHONE, "삼 사"),
        ("메일은 hong.gildong@example.com 입니다", EMAIL, "example"),
        ("메일은 hong 골뱅이 example 점 com 입니다", EMAIL, "골뱅이"),
        ("제 깃허브는 https://github.com/hong 입니다", URL, "github"),
        ("주민번호는 900101-1234567 입니다", RRN, "1234567"),
        ("생년월일은 1998년 3월 15일입니다", BIRTH, "1998"),
        ("1998.03.15에 태어났습니다", BIRTH, "1998"),
    ],
)
def test_personal_data_is_replaced(spoken, placeholder, leaked):
    result = masked(spoken)
    assert placeholder in result
    assert leaked not in result


@pytest.mark.parametrize(
    "spoken, leaked",
    [
        ("제 이름은 김철수입니다", "김철수"),
        ("이름은 홍길동이에요", "홍길동"),
        ("성함은 이영희입니다", "이영희"),
        ("저는 김철수입니다", "김철수"),
        ("저는 박지민이라고 합니다", "박지민"),
        ("my name is John Smith and I like APIs", "John"),
    ],
)
def test_introduced_names_are_masked(spoken, leaked):
    result = masked(spoken)
    assert NAME in result
    assert leaked not in result


def test_configured_names_are_masked_wherever_they_occur():
    result = masked("박서준입니다. 박서준이 만든 서비스는 박 서준 팀의 것입니다", names=("박서준",))
    assert "박서준" not in result and NAME in result
    assert masked("안녕하세요 Alex 입니다", names=("alex",)).count(NAME) == 1


@pytest.mark.parametrize(
    "technical",
    [
        "멱등성은 같은 요청을 여러 번 보내도 결과가 같은 성질입니다. HTTP PUT과 DELETE는 멱등합니다.",
        "저는 개발자입니다. 2022년 3월 15일에 프로젝트를 마감했고 HTTP 200과 404를 구분했습니다.",
        "응답 시간이 120ms에서 80ms로 줄었고 요청은 초당 3000건이었습니다.",
    ],
)
def test_ordinary_answers_are_left_alone(technical):
    result = mask_spoken_pii(technical)
    assert result.text == technical and not result.changed


def test_masking_is_idempotent_and_reports_only_counts():
    once = mask_spoken_pii("제 이름은 김철수이고 010-1234-5678, kim@example.com 입니다")
    assert mask_spoken_pii(once.text).text == once.text
    assert once.kinds == {"email": 1, "phone": 1, "name": 1}
    assert all(isinstance(v, int) for v in once.kinds.values())  # logged by the conductor: counts, never the text


def test_empty_text_is_safe():
    assert mask_spoken_pii("").text == "" and mask_spoken_pii(None).text == ""  # type: ignore[arg-type]


def test_speech_events_are_masked_in_place():
    from livekit.agents import stt

    words = [object()]
    data = stt.SpeechData(language="ko", text="제 이름은 김철수입니다", words=words)  # type: ignore[arg-type]
    clean = stt.SpeechData(language="ko", text="멱등성은 중요합니다", words=words)  # type: ignore[arg-type]
    event = stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[data, clean])
    assert mask_speech_event(event) == 1
    assert event.alternatives[0].text == f"제 이름은 {NAME}입니다"
    assert event.alternatives[0].words is None  # raw word timings would still carry the name
    assert event.alternatives[1].words is words  # untouched alternatives keep their timings


# ── output screens ──


@pytest.mark.parametrize(
    "text",
    [
        "방금 말씀하신 멱등 키는 어떻게 만료 시간을 관리하나요?",
        '"요청이 중복으로 들어오면 서버는 어떻게 구분하나요?"',
        "  재시도 정책은 어떻게 설계하시겠어요？ ",
    ],
)
def test_good_followups_pass(text):
    assert screen_followup(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "멱등성을 설명해 주세요.",  # not a question
        "무엇이 중요한가요? 왜 그런가요?",  # two questions
        "결혼은 하셨나요?",  # protected topic
        "나이가 어떻게 되시나요?",
        "가족 구성원은 어떻게 되나요?",
        "이 답변이면 합격인가요?",  # verdict word
        "자세한 내용은 https://example.com 에서 설명해 주실 수 있나요?",
        "[이름]님은 어떻게 하셨나요?",  # a placeholder leaked into the question
        "첫 줄입니다.\n둘째 줄은 질문인가요?",
        "가" * 200 + "?",
    ],
)
def test_bad_followups_are_rejected(text):
    assert screen_followup(text) is None


def test_followup_is_cleaned():
    assert screen_followup('  "재시도는 어떻게 하나요?"  ') == "재시도는 어떻게 하나요?"


@pytest.mark.parametrize("text", ["멱등 키를 활용한 구체적인 방법까지 설명해 주셔서 감사합니다.", "사례를 들어 설명해 주신 점이 인상적이었습니다."])
def test_good_closings_pass(text):
    assert screen_closing(text) == text


@pytest.mark.parametrize(
    "text",
    ["", "다른 질문이 있나요?", "합격하실 것 같습니다.", "점수는 90점입니다.", "채용 여부는 곧 알려드리겠습니다.", "[이름]님 감사합니다.", "가" * 250],
)
def test_bad_closings_are_rejected(text):
    assert screen_closing(text) is None


# The reply that failed the first live Groq check (openai/gpt-oss-120b, verify_llm.py). The only rule that fired was the
# square-bracket rule: length, question marks, links, protected topics and verdict words were all fine.
LIVE_FAILED_CLOSING = "[이름]님, 결제 재시도 상황에서 멱등성을 강조한 설명이 인상적였습니다. 감사합니다."
PLACEHOLDERS = (NAME, EMAIL, PHONE, URL, RRN, BIRTH)


def test_the_closing_that_failed_the_live_check_is_rejected_for_its_placeholder_only():
    assert screen_closing(LIVE_FAILED_CLOSING) is None
    without_placeholder = LIVE_FAILED_CLOSING.replace(f"{NAME}님, ", "")
    assert "[" not in without_placeholder
    assert screen_closing(without_placeholder) == without_placeholder  # nothing else in the sentence is a problem


def test_a_natural_closing_without_placeholders_passes_unchanged():
    closing = "결제 재시도 상황에서 멱등성을 강조해 설명해 주신 점이 인상적이었습니다. 감사합니다."
    assert screen_closing(closing) == closing


@pytest.mark.parametrize("placeholder", PLACEHOLDERS)
def test_every_placeholder_in_a_closing_is_rejected_not_stripped(placeholder):
    assert screen_closing(f"{placeholder}님, 멱등 키 사례를 설명해 주셔서 감사합니다.") is None
    assert screen_closing(f"멱등 키 사례를 설명해 주셔서 감사합니다. {placeholder}") is None  # at the end too


@pytest.mark.parametrize("placeholder", PLACEHOLDERS)
def test_every_placeholder_in_a_followup_is_rejected_not_stripped(placeholder):
    assert screen_followup(f"{placeholder}님은 멱등 키를 어떻게 만료시키나요?") is None
    # a well-formed single question (ends with ?), so only the bracket rule can reject this one
    assert screen_followup(f"멱등 키는 {placeholder} 기준으로 어떻게 만료시키나요?") is None
    assert screen_followup("멱등 키는 어떤 기준으로 만료시키나요?") is not None  # same shape without a placeholder passes
