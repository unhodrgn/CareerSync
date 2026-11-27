"""Masking spoken personal data (ai/interview/spoken_pii.py, D39, D53, AI rule 3): the kinds speech has, the account name
and its spellings, no damage to technical talk, and the CV masking left exactly as it was."""
import pytest

from ai.interview import mask_spoken
from ai.interview.spoken_pii import BIRTH, EMAIL, PHONE, RRN, URL
from ai.parsing.pii import NAME_TOKEN, mask_pii

NAMES = ["김지원"]


def masked(text: str, names=NAMES) -> str:
    return mask_spoken(text, names).text


def test_the_tokens_are_the_ones_of_the_cv_masking():
    assert (EMAIL, URL, RRN, PHONE, BIRTH, NAME_TOKEN) == ("[EMAIL]", "[URL]", "[RRN]", "[PHONE]", "[DOB]", "[NAME]")


@pytest.mark.parametrize(
    ("spoken", "secret", "token"),
    [
        ("제 이메일은 jiwon.kim@example.com 입니다", "jiwon.kim@example.com", EMAIL),
        ("메일 주소는 jiwon 골뱅이 example 점 com 이에요", "골뱅이", EMAIL),
        ("연락처는 010-1234-5678 입니다", "1234", PHONE),
        ("번호는 010 1234 5678 이에요", "5678", PHONE),
        ("공일공 일이삼사 오육칠팔 입니다", "일이삼사", PHONE),
        ("공 일 공 일 이 삼 사 오 육 칠 팔", "육 칠", PHONE),
        ("주민번호는 970512-2345678 입니다", "2345678", RRN),
        ("생년월일은 1997년 5월 12일 입니다", "1997", BIRTH),
        ("블로그는 https://blog.example.com/jiwon 입니다", "blog.example.com", URL),
        ("저는 박서준입니다", "박서준", NAME_TOKEN),
        ("제 이름은 홍길동이고 개발자입니다", "홍길동", NAME_TOKEN),
        ("이름은 이영희입니다", "이영희", NAME_TOKEN),
        ("my name is John Smith and I build APIs", "John Smith", NAME_TOKEN),
    ],
)
def test_personal_data_is_masked(spoken, secret, token):
    out = masked(spoken)
    assert secret not in out and token in out, out


@pytest.mark.parametrize("spoken", ["김지원입니다", "김 지 원 이라고 합니다", "Jiwon Kim 이라고 합니다", "Kim Ji-won 입니다", "KIM JIWON"])
def test_the_account_name_is_masked_in_its_spellings(spoken):
    out = masked(spoken)
    assert NAME_TOKEN in out and "지원" not in out and "jiwon" not in out.lower() and "ji-won" not in out.lower(), out


def test_the_account_name_is_masked_inside_a_sentence():
    assert masked("팀장님은 김지원 씨가 아니라 다른 분이었습니다") == f"팀장님은 {NAME_TOKEN} 씨가 아니라 다른 분이었습니다"


def test_only_the_names_given_are_masked():
    assert masked("저는 김지원입니다", names=[]) == f"저는 {NAME_TOKEN}입니다"  # an introduction is found without any account name
    assert masked("김지원 이라고 합니다", names=[]) == "김지원 이라고 합니다"  # a name nobody introduced stays (best effort, D39)


@pytest.mark.parametrize(
    "technical",
    [
        "REST API의 리소스 주소는 URI로 표현합니다",
        "변수 이름은 camelCase로 짓고 클래스 이름은 PascalCase로 짓습니다",
        "저는 백엔드 개발자입니다",
        "저는 백엔드입니다",
        "저는 신입입니다",
        "저는 박사입니다",
        "저는 설계자입니다",
        "저는 주니어입니다",
        "저는 마케터가 아니라 개발자입니다",
        "멱등성이란 같은 요청을 여러 번 보내도 결과가 같은 성질입니다",
        "Spring Boot 3.2에서 Java 17을 사용했고 처리량이 40% 늘었습니다",
        "2023년 3월부터 2024년 2월까지 결제 서비스를 운영했습니다",
    ],
)
def test_technical_talk_is_left_alone(technical):
    result = mask_spoken(technical, NAMES)
    assert result.text == technical and not result.changed


def test_a_given_name_alone_is_not_found_which_is_the_documented_limit():
    assert masked("지원 씨가 말했습니다") == "지원 씨가 말했습니다"  # D39: a given name or a surname alone is never masked


def test_masking_is_idempotent_and_counts_kinds_not_text():
    text = "제 이메일은 a@b.co 이고 번호는 010-1234-5678, 저는 박서준입니다. 김지원입니다."
    once = mask_spoken(text, NAMES)
    assert mask_spoken(once.text, NAMES).text == once.text
    assert once.kinds == {"email": 1, "phone": 1, "name": 2} and once.changed
    assert all(isinstance(v, int) for v in once.kinds.values())  # numbers only: nothing from the text is kept


def test_whitespace_is_normalized_and_empty_input_is_fine():
    assert masked("  음   제가\n했습니다  ") == "음 제가 했습니다"
    assert mask_spoken("", NAMES).text == "" and mask_spoken(None, NAMES).text == ""  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("spoken", "secret", "token"),
    [
        ("My email is alice.park at example dot com and I built APIs", "alice.park", EMAIL),
        ("You can reach me at 555-234-5678 anytime", "555-234-5678", PHONE),
        ("My number is five five five two three four five six seven eight", "six seven eight", PHONE),
        ("My name is Alice Park and I worked on Kafka", "Alice Park", NAME_TOKEN),
        ("I'm Jordan Lee, I built distributed caches", "Jordan Lee", NAME_TOKEN),
        ("Call me Alex when we discuss Spring Boot", "Alex", NAME_TOKEN),
    ],
)
def test_english_spoken_pii_is_masked_and_prose_survives(spoken, secret, token):
    out = masked(spoken, ("Jordan Lee",))
    assert secret not in out and token in out


@pytest.mark.parametrize(
    "prose",
    [
        "I am a backend developer working on Spring Boot at node.js services",
        "I'm sorry, I have not deployed that in production yet",
        "We scaled from one instance to two nodes in Seoul",
        "My name is John and I built REST APIs",  # check below: "John" is masked, "and I built" stays!
    ],
)
def test_english_technical_prose_is_not_overmasked(prose):
    if "John" in prose:
        out = masked(prose, ())
        assert out == f"My name is {NAME_TOKEN} and I built REST APIs"
    else:
        assert masked(prose, ()) == prose


def test_the_cv_masking_is_unchanged_and_still_handles_what_speech_must_not():
    # mask_pii keeps masking everything after 주소 and a label's name; the speech masker must not do that to an answer
    cv = mask_pii("이름: 김지원\n주소: 서울시 강남구 테헤란로 1\n이메일: jiwon.kim@example.com", ["김지원"])
    assert "[ADDRESS]" in cv.text and "[NAME]" in cv.text and "[EMAIL]" in cv.text and "테헤란로" not in cv.text
    assert masked("리소스 주소는 URI입니다 그리고 이름은 짓기 나름입니다") == "리소스 주소는 URI입니다 그리고 이름은 짓기 나름입니다"
