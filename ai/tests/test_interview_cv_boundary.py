"""The CV boundary of the practice interview (ai/interview/cv_context.py, sensitive.py; docs/DECISIONS.md D62).

Synthetic CVs only, FakeLLM only, no network. The stored masked CV still holds age, gender and military-service text
(Q24), so these tests prove that none of it can reach a model-bound input through any interview path: the planning prompt,
the plan and its warm-up, the per-turn model input, `TurnContext.to_text()` used directly, the rubric request, and every
line the interviewer may speak. The structure layer is proved with canary lines that no vocabulary could ever match,
so a pass cannot be the vocabulary alone; the professional lines of the same CVs must survive."""
import json
from types import SimpleNamespace

import pytest

from ai.career.interview import CriterionInfo, Question
from ai.interview import (
    ActionKind,
    AnswerType,
    InterviewEngine,
    PlanCriterion,
    TurnAnalysis,
    build_plan,
    clean_cv,
    cut_sensitive,
    evidence_lines,
    for_model,
    is_sensitive,
    make_bank,
    prepare_turn,
    rubric_request,
    screen_spoken,
)
from ai.interview.types import TurnContext
from ai.parsing.pii import mask_pii
from ai.parsing.sections import split_sections
from ai.scoring.retrieval import cv_chunks
from ai.tests.helpers import EMBEDDER, SKILLS, FakeLLM
from ai.tests.interview_helpers import BLOCKLISTS, CRITERIA, GOOD, PARTIAL_JAVA

# ── Synthetic CVs. The CANARY lines are in places the structure removes and use no word the vocabulary knows. ──

CV_KO = """김지원
CANARY-HEADER 지원 직무 백엔드
성별: 여 | 나이: 만 27세 | 1997년생 (스물일곱 살)
이메일: jiwon.kim@example.com  연락처: 010-1234-5678
생년월일: 1997.05.12

인적사항
국적: 대한민국
결혼여부: 미혼
CANARY-PERSONAL 비고 기록 7788

경력
(주)넥스트코드 | 백엔드 개발자 2021.03 ~ 2023.02
- Java, Spring Boot 기반 주문 API 개발
- MySQL 인덱스 튜닝으로 조회 속도 40% 개선
- 육군 복무 중 통신 장비 정비 경험을 살려 장애 대응 체계를 구축
에이비씨소프트 | 서버 개발 2023.03 ~ 현재 | 병역특례
- Kotlin, Spring, Redis로 결제 서비스 운영

프로젝트
쇼핑몰 추천 시스템 2022.05 ~ 2022.09
- Python, FastAPI로 추천 API 설계 및 팀 리드
- Docker, AWS 배포

학력
한국대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02 (군 휴학 2017~2019)

신상정보
CANARY-MID 기록 번호 3344

자격증
정보처리기사 2020.08
SQLD 2021.06

병역사항
육군 병장 만기전역 (2017.03 ~ 2019.01)
2017.03 ~ 2019.01 제3사단 통신대
CANARY-LAST 부대 기록 4455
"""

CV_EN = """Jiwon Kim
CANARY-HEADER Target role backend
Gender: Female | Age: 27 | 27 years old | Date of birth: 1997-05-12
Email: jiwon.kim@example.com  Phone: 010-1234-5678

Personal Information
Nationality: Korean
Marital status: Single
CANARY-PERSONAL record 7788

Experience
NextCode Inc. | Backend Developer 2021.03 ~ 2023.02
- Built order APIs with Java and Spring Boot
- Tuned MySQL indexes and cut query time by 40%
- Served 21 months in the Korean Army as a signal corps sergeant, maintained field communications
ABC Soft | Server Engineer 2023.03 ~ present
- Operated a payment service with Kotlin, Spring and Redis

Projects
Shopping recommendation system 2022.05 ~ 2022.09
- Designed the recommendation API with Python and FastAPI and led the team

Education
Korea University, B.S. Computer Science 2015.03 ~ 2021.02 (military leave 2017-2019)

Personal details
CANARY-MID record 3344

Certifications
Engineer Information Processing 2020.08

Military Service
Completed (ROK Army, Sergeant, 2017-2019)
CANARY-LAST unit record 4455
"""

LANGS = {
    "ko": SimpleNamespace(
        cv=CV_KO,
        names=["김지원"],
        sensitive=[
            "성별", "만 27세", "27세", "1997년생", "스물일곱", "생년월일", "1997.05.12", "미혼", "병역", "군필", "육군", "병장",
            "만기전역", "군 휴학", "병역특례", "복무", "사단", "통신대",
        ],
        professional=[
            "Java, Spring Boot 기반 주문 API 개발", "MySQL 인덱스 튜닝으로 조회 속도 40% 개선", "Python, FastAPI로 추천 API 설계 및 팀 리드",
            "Docker, AWS 배포", "Kotlin, Spring, Redis로 결제 서비스 운영", "정보처리기사 2020.08", "SQLD 2021.06",
            "한국대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02", "(주)넥스트코드 | 백엔드 개발자 2021.03 ~ 2023.02",
            "에이비씨소프트 | 서버 개발 2023.03 ~ 현재",
        ],
        said="저는 스물일곱 살이고 육군 병장으로 만기전역했습니다. 성별은 여자입니다. ",
    ),
    "en": SimpleNamespace(
        cv=CV_EN,
        names=["Jiwon Kim"],
        sensitive=[
            "Gender", "Female", "Age:", "27 years old", "Date of birth", "1997-05-12", "Marital", "Military", "ROK", "Army", "Sergeant",
            "military leave",
        ],
        professional=[
            "Built order APIs with Java and Spring Boot", "Tuned MySQL indexes and cut query time by 40%",
            "Designed the recommendation API with Python and FastAPI and led the team", "Operated a payment service with Kotlin, Spring and Redis",
            "Korea University, B.S. Computer Science 2015.03 ~ 2021.02", "Engineer Information Processing 2020.08",
            "NextCode Inc. | Backend Developer 2021.03 ~ 2023.02",
        ],
        said="I am 27 years old and a female veteran of the Korean army. ",
    ),
}
CANARIES = ("CANARY-HEADER", "CANARY-PERSONAL", "CANARY-MID", "CANARY-LAST")
for _case in LANGS.values():
    _case.masked = mask_pii(_case.cv, _case.names, SKILLS).text  # the stored form: masked like an upload, nothing else removed


@pytest.fixture(params=sorted(LANGS))
def lang(request):
    return LANGS[request.param]


def leaks(text: str, fragments) -> list[str]:
    return [f for f in fragments if f.lower() in text.lower()]


def missing(text: str, fragments) -> list[str]:
    return [f for f in fragments if f not in text]


CRITERIA_INFO = [CriterionInfo(1, "백엔드 개발 경험", "experience", "Java Spring API 개발")]
BANK = {
    "questions": [
        {"question": f"질문 {i}번: 프로젝트에서 맡은 역할을 설명해 주세요.", "criterion_id": 1, "kind": "experience", "depth": (i % 3) + 1,
         "intent": "확인", "answer_tips": ["구체적으로"], "cv_quote": None}
        for i in range(5)
    ]
}


def raw_cv_lines(masked: str) -> list[str]:
    """Every line of the stored CV, the way an unsafe caller could hand them to `build_plan`."""
    return [line.strip().lstrip("-• ").strip() for line in masked.splitlines() if line.strip()]


# ── The premise (Q24) and the structure layer ──


def test_premise_the_stored_masked_cv_still_carries_the_topics(lang):
    """Q24: `mask_pii` is unchanged and does not remove these lines. If it ever does, update this test, keep the boundary."""
    stored = lang.masked
    assert leaks(stored, lang.sensitive[:3]) and leaks(stored, ["병역", "Military"]), "the stored CV no longer carries them (Q24 closed?)"
    assert all(c in stored for c in CANARIES)


def test_the_cleaned_cv_has_none_of_the_topics_and_keeps_the_professional_lines(lang):
    clean = clean_cv(lang.masked).text
    assert leaks(clean, lang.sensitive) == []
    assert missing(clean, lang.professional) == []
    assert not is_sensitive(clean)


def test_structure_alone_removes_the_header_and_the_personal_blocks(lang):
    """The canaries use no word the vocabulary knows, so only the structure layer can have removed them."""
    assert not any(is_sensitive(c) for c in CANARIES)
    assert not any(is_sensitive(line) for line in lang.masked.splitlines() if "CANARY" in line)
    clean = clean_cv(lang.masked).text
    assert leaks(clean, CANARIES) == []
    assert "Spring" in clean  # the sections between and after the blocks are still there


def test_a_block_ends_at_the_next_known_heading_and_not_before():
    cv = "경력\nJava 개발 3년 경력의 백엔드 업무\n병역사항\nCANARY-A 첫 줄\nCANARY-B 둘째 줄\n자격증\n정보처리기사 2020.08\n"
    clean = clean_cv(cv).text
    assert leaks(clean, ("CANARY-A", "CANARY-B")) == []
    assert "Java 개발 3년 경력의 백엔드 업무" in clean and "정보처리기사 2020.08" in clean


def test_text_before_the_first_heading_is_never_used():
    clean = clean_cv("CANARY-X 헤더 줄\n경력\nJava 개발 업무를 담당함\n")
    assert "CANARY-X" not in clean.text and "Java 개발 업무를 담당함" in clean.text


def test_a_cv_without_any_known_heading_gives_nothing():
    """The structure cannot tell what is personal in a flat text, so nothing of it is used: no warm-up, no excerpts."""
    assert not clean_cv("Java Spring 기반 주문 API 개발\n- MySQL 튜닝")
    assert not clean_cv("") and not clean_cv(None)
    assert not clean_cv("경력\n성별: 여\n병역: 군필")  # nothing but headings left


def test_cleaning_is_idempotent(lang):
    once = clean_cv(lang.masked)
    assert clean_cv(once.text).text == once.text  # `removed` is a record of what was taken out, not part of the text


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("한국대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02 (군 휴학 2017~2019)", "한국대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02"),
        ("에이비씨소프트 | 서버 개발 2023.03 ~ 현재 | 병역특례", "에이비씨소프트 | 서버 개발 2023.03 ~ 현재"),
        ("Korea University, B.S. Computer Science 2015-2021 (military leave 2017-2019)", "Korea University, B.S. Computer Science 2015-2021"),
        ("저는 스물일곱 살입니다. Java 백엔드 개발 3년 경력입니다.", "Java 백엔드 개발 3년 경력입니다."),
        ("- 육군 복무 중 통신 장비 정비 경험을 살려 장애 대응 체계를 구축", ""),
        ("병역: 군필 (육군 병장 만기전역, 2017.03 ~ 2019.01)", ""),
        ("Gender: Female", ""),
        ("제3사단 통신대 근무", ""),
    ],
)
def test_a_line_keeps_its_professional_rest(line, kept):
    assert cut_sensitive(line) == kept


@pytest.mark.parametrize(
    "text",
    [
        "3세대 아키텍처를 설계했습니다", "세션 관리를 구현했습니다", "나이브 베이즈 분류기를 사용했습니다", "전역 변수를 피하도록 리팩터링했습니다",
        "Redux로 전역 상태 관리를 도입했습니다", "제대로 된 테스트를 작성했습니다", "연령대별 추천 시스템을 개발했습니다", "생일 쿠폰 발급 기능을 개발했습니다",
        "사단법인 한국정보협회에서 근무했습니다", "Spring Boot 기반 주문 API 개발", "Managed a team of five engineers",
    ],
)
def test_professional_text_that_only_looks_like_the_topics_is_kept(text):
    assert not is_sensitive(text) and for_model(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "나이: 만 27세", "저는 스물일곱 살입니다", "1997년생", "27 years old", "age 27", "성별: 여", "Gender: Female", "여성 개발자", "a woman engineer",
        "병역: 군필", "육군 병장 만기전역", "제3사단 통신대", "군 휴학 2년", "병역특례 요원", "Military service: completed", "ROK Army sergeant",
        "served in the army", "honorable discharge", "산업기능요원으로 근무", "복무 기간 2년", "예비역 중위",
    ],
)
def test_the_topics_are_recognized_in_both_languages(text):
    assert is_sensitive(text) and for_model(text) == ""


# ── 1. The planning prompt (the D21 bank, reused by the interview plan) ──


def test_the_planning_prompt_carries_the_cleaned_cv_only(lang):
    llm = FakeLLM(BANK)
    questions, method = make_bank("백엔드 개발자", "Java Spring API 개발", CRITERIA_INFO, lang.masked, EMBEDDER, BLOCKLISTS, llm)
    assert method == "llm:fake-llm" and len(questions) == 5
    system, user = llm.calls[0]
    assert leaks(user, lang.sensitive) == [] and leaks(user, CANARIES) == []
    assert any(p in user for p in lang.professional), "the planning prompt must still carry professional evidence"
    assert "<cv_excerpts>" in user


def test_the_planning_wrapper_without_a_model_is_the_template(lang):
    questions, method = make_bank("백엔드 개발자", "Java Spring API 개발", CRITERIA_INFO, lang.masked, EMBEDDER, BLOCKLISTS, None)
    assert method == "rules" and questions
    assert not any(is_sensitive(q.question) or is_sensitive(q.intent) for q in questions)


def test_a_quote_the_planner_takes_from_a_removed_line_is_not_a_quote(lang):
    bad = "육군 병장 만기전역 (2017.03 ~ 2019.01)" if "병역" in lang.sensitive else "Completed (ROK Army, Sergeant, 2017-2019)"
    bank = {"questions": [dict(q, cv_quote=bad) if i == 0 else q for i, q in enumerate(BANK["questions"])]}
    questions, _ = make_bank("백엔드 개발자", "Java Spring API 개발", CRITERIA_INFO, lang.masked, EMBEDDER, BLOCKLISTS, FakeLLM(bank))
    assert all(q.cv_quote is None for q in questions)  # verified against the cleaned CV, where the line does not exist


# ── 2. The plan and its warm-up ──


def _plan(lang, questions=(), lines=None):
    cv_lines = raw_cv_lines(lang.masked) if lines is None else lines
    return build_plan(CRITERIA, questions, lang.masked, cv_lines, BLOCKLISTS, skills=SKILLS)


def test_an_unsafe_caller_cannot_put_a_removed_line_into_the_plan(lang):
    """`cv_lines` here is every line of the stored CV, sensitive ones and canaries included, as a careless caller might pass."""
    plan = _plan(lang)
    dump = json.dumps(plan.to_dict(), ensure_ascii=False)
    assert leaks(dump, lang.sensitive) == [] and leaks(dump, CANARIES) == []
    assert plan.items and plan.items[0].topic_id == "warmup"
    assert " ".join(plan.items[0].cv_quote.split()) in " ".join(clean_cv(lang.masked).text.split())  # a line of the cleaned CV, verbatim


def test_only_removed_lines_ground_no_warm_up(lang):
    removed = [line for line in raw_cv_lines(lang.masked) if is_sensitive(line) or "CANARY" in line]
    plan = _plan(lang, lines=removed)
    assert [i.topic_id for i in plan.items][0] != "warmup"
    assert leaks(json.dumps(plan.to_dict(), ensure_ascii=False), CANARIES) == []


def test_evidence_lines_from_every_chunk_of_the_stored_cv_are_clean(lang):
    lines = evidence_lines([c.text for c in cv_chunks(lang.masked)])
    assert lines and not any(is_sensitive(line) for line in lines)


@pytest.mark.parametrize(
    "question",
    [
        "이력서에 적으신 병역 사항에 대해 말씀해 주세요.",
        "군 복무 중 가장 기억에 남는 경험은 무엇인가요?",
        "나이가 어떻게 되시나요?",
        "성별에 따라 업무 방식이 달랐던 경험이 있나요?",
        "Tell me about your military service listed on the CV.",
        "How old are you and when were you born?",
    ],
)
def test_a_planner_question_about_the_topics_is_used_nowhere_in_the_plan(lang, question):
    quote = "육군 병장 만기전역 (2017.03 ~ 2019.01)"
    bank = [
        Question(question, None, None, "experience", "확인", ("구체적으로",), quote),  # as the warm-up
        Question(question, 1, "백엔드 개발 경험", "experience", "확인", ("구체적으로",), None),  # as the criterion question
        Question(question, None, None, "behavioral", "확인", ("구체적으로",), None),  # as the closing question
    ]
    plan = _plan(lang, questions=bank)
    spoken = " ".join(i.question for i in plan.items)
    assert not is_sensitive(spoken) and question not in spoken
    assert plan.items[-1].topic_id == "behavioral" and plan.items[-1].question != question


@pytest.mark.parametrize(
    ("intent", "tips"),
    [
        ("병역 이행 여부 확인", ("구체적으로",)),
        ("확인", ("군필 여부를 먼저 말하기",)),
        ("Check military service", ("be specific",)),
        ("확인", ("Mention your gender first",)),
    ],
)
def test_a_planner_question_whose_intent_or_tips_are_about_the_topics_is_not_used(lang, intent, tips):
    """Nothing but the intent or a tip is about the topics here: the spoken question is innocent, so only the plan-time
    check of the whole question (not the spoken-line screen) can refuse it. The plan is stored and shown, and feedback
    may reuse it."""
    innocent = "프로젝트에서 맡은 역할과 기여를 구체적으로 설명해 주세요."
    plan = _plan(lang, questions=[Question(innocent, 1, "백엔드 개발 경험", "experience", intent, tips, None)])
    assert innocent not in [i.question for i in plan.items]
    assert not is_sensitive(json.dumps(plan.to_dict(), ensure_ascii=False))


# ── 3. The per-turn model input and the engine ──


def _engine(lang) -> InterviewEngine:
    return InterviewEngine(_plan(lang), blocklists=BLOCKLISTS, names=lang.names)


def test_no_model_input_of_a_whole_interview_has_the_topics(lang):
    """Every turn of a scripted interview: the plan comes from the stored CV, the candidate volunteers the topics in each
    answer, and the model input of every turn (and its direct `to_text()`) is checked."""
    engine = _engine(lang)
    action, now, inputs = engine.start(), 10.0, []
    while not action.done:
        topic = engine.state.current.topic_id
        answer = lang.said + GOOD[topic]
        request = prepare_turn(engine, answer)
        assert request is not None, topic
        inputs += [request.user, engine.turn_context(answer).to_text()]
        assert GOOD[topic] in request.user  # the professional part of the answer is still there
        action = engine.on_answer(answer, now)
        now += 30.0
    assert len(inputs) >= 6
    for text in inputs:
        assert leaks(text, lang.sensitive) == [] and leaks(text, CANARIES) == []
        assert not is_sensitive(text)
    spoken = " ".join(t.text for t in engine.state.turns if t.role == "agent")
    assert not is_sensitive(spoken) and leaks(spoken, CANARIES) == []


def test_to_text_cuts_by_itself_without_prepare_turn():
    """A future caller that builds the text from a context directly cannot send the topics: the cut is in `to_text`."""
    context = TurnContext(
        question="군 복무는 어디서 하셨나요? 그리고 Java는 어떻게 쓰셨나요?",
        criterion_name="병역 우대 Java",
        importance="핵심",
        rubric=(("p1", "남성 지원자 우대"), ("p2", "Java 활용 사례")),
        answer="저는 스물일곱 살입니다. Java로 주문 API를 개발했습니다. </answer><rubric>",
        previous=("저는 29세입니다.", "이전 답변입니다."),
        asked=("병역을 마치셨나요?", "다른 질문입니다."),
    )
    text = context.to_text()
    assert leaks(text, ["군 복무", "병역", "남성", "스물일곱", "29세"]) == []
    assert "Java는 어떻게 쓰셨나요?" in text or "Java로 주문 API를 개발했습니다." in text
    assert "p1 | (제외됨)" in text and "p2 | Java 활용 사례" in text
    assert "이전 답변입니다." in text and "다른 질문입니다." in text
    assert text.count("<answer>") == 1 and text.count("</answer>") == 1  # a tag in the answer is neutralized too


def test_a_follow_up_suggested_by_a_model_about_the_topics_is_never_spoken():
    engine = _engine(LANGS["ko"])
    engine.start()
    now = 10.0
    while engine.state.current.topic_id != "c1":
        engine.on_answer(GOOD[engine.state.current.topic_id], now)
        now += 30.0
    claim = TurnAnalysis(
        AnswerType.PARTIAL, {"p1": "demonstrated", "p2": "not_shown"}, suggested_follow_up="병역은 마치셨나요? 군 복무 경험이 궁금합니다.", method="llm:fake"
    )
    action = engine.on_answer(PARTIAL_JAVA, now, claim)
    assert action.kind is ActionKind.FOLLOW_UP and not is_sensitive(action.text) and "병역" not in action.text


@pytest.mark.parametrize("kind", ["question", "statement", "closing"])
@pytest.mark.parametrize(
    "line", ["군 복무는 어디서 하셨나요", "나이가 어떻게 되시나요", "성별을 알려 주세요", "Where did you do your military service", "How old are you, age please"]
)
def test_the_interviewer_never_says_a_line_about_the_topics(line, kind):
    assert screen_spoken(line, BLOCKLISTS, kind) is None


def test_the_rubric_request_carries_no_sentence_about_the_topics():
    request = rubric_request(
        question="Java 활용 경험을 설명해 주세요.", name="Java 활용 능력", category="skill",
        description="Spring Boot 사용 경험. 병역필 우대. 남성 선호.", importance="핵심", blocklists=BLOCKLISTS,
    )
    assert request is not None and "Spring Boot 사용 경험." in request.user
    assert leaks(request.user, ["병역", "남성"]) == []
    assert rubric_request(question="병역 사항을 말씀해 주세요.", name="Java", category="skill", description="", importance="핵심", blocklists=BLOCKLISTS) is None


# ── M2.1: heading prefixes, unknown personal sections, two-line label/value layouts, mixed lines ──
#
# Every canary below uses no word of the vocabulary, so only the structure or the label rules can have removed it.

PRO_AFTER = "자격증\n정보처리기사 2020.08\n"
PRO_BEFORE = "경력\n- Java, Spring Boot 기반 주문 API 개발\n"


def _block_cv(heading: str, body: str = "CANARY-B1 기록 일\nCANARY-B2 기록 이") -> str:
    return f"{PRO_BEFORE}{heading}\n{body}\n{PRO_AFTER}"


@pytest.mark.parametrize(
    "heading",
    [
        "병역사항", "병역사항 (필)", "병역사항:", "[ 병역 ]", "■ 병역 및 보훈", "1. 인적사항", "인 적 사 항", "신상 정보", "개인 정보", "개인신상",
        "기본 인적사항", "추가 정보", "추가사항", "기타", "기타 사항", "비고", "참고사항", "가족사항", "취미/특기", "종교",
        "Personal Profile", "Personal Details", "PERSONAL INFORMATION", "Personal Data", "Military Service Record", "Military",
        "Demographics", "Additional Information", "Additional Info", "Others", "Family", "Hobbies & Interests", "References",
    ],
)
def test_a_personal_or_catch_all_heading_starts_a_block_by_prefix(heading):
    clean = clean_cv(_block_cv(heading)).text
    assert "CANARY-B1" not in clean and "CANARY-B2" not in clean, heading
    assert "Java, Spring Boot 기반 주문 API 개발" in clean and "정보처리기사 2020.08" in clean  # before the block and after the next known heading


def test_a_personal_projects_heading_is_not_a_personal_block():
    """`Personal` is a prefix of the personal headings, but not of a heading about the candidate's own projects."""
    cv = f"{PRO_BEFORE}Personal Projects\n- Built a demo shop with Java and Spring Boot\n"
    assert "Built a demo shop with Java and Spring Boot" in clean_cv(cv).text


@pytest.mark.parametrize(
    "label_value",
    [
        ("생년월일", "1997.05.12"), ("성별", "여"), ("나이", "27"), ("국적", "대한민국"), ("혈액형", "O형"), ("본적", "서울 종로"),
        ("Date of birth", "1997-05-12"), ("Gender", "Female"), ("Age", "27"), ("Nationality", "Korean"), ("Marital status", "Single"),
        ("Blood type", "O"),
    ],
)
def test_a_label_alone_on_a_line_takes_its_value_line_with_it(label_value):
    label, value = label_value
    cv = f"자기소개\n{label}\n{value}\nJava 백엔드 개발 3년 경력의 개발자입니다. Spring 기반 API를 개발했습니다.\n"
    clean = clean_cv(cv).text
    assert label not in clean and f"\n{value}" not in clean, label
    assert "Java 백엔드 개발 3년 경력의 개발자입니다." in clean  # the professional line after the value stays


@pytest.mark.parametrize(
    "line", ["국적: 대한민국", "국적 대한민국", "혈액형 O형", "Nationality: Korean", "Nationality Korean", "Marital status: Single", "기타: 봉사활동 안내 기록"]
)
def test_a_label_with_its_value_on_one_line_goes_whole(line):
    clean = clean_cv(f"자기소개\n{line}\nSpring 기반 API를 개발했습니다.\n").text
    assert line not in clean and "Spring 기반 API를 개발했습니다." in clean


def test_a_table_of_labels_then_values_is_removed_together():
    cv = "자기소개\n성별\n나이\n국적\n여\n27\n대한민국\nSpring 기반 API를 개발했습니다.\n"
    clean = clean_cv(cv).text
    assert clean == "자기소개\nSpring 기반 API를 개발했습니다."


def test_a_value_line_that_is_long_prose_is_not_taken_as_a_value():
    cv = "자기소개\n생년월일\nSpring Boot와 JPA로 주문 도메인을 설계하고 개발한 3년 차 백엔드 개발자입니다.\n"
    assert "Spring Boot와 JPA로 주문 도메인을 설계하고 개발한 3년 차 백엔드 개발자입니다." in clean_cv(cv).text


@pytest.mark.parametrize(
    "line",
    [
        "통신병으로 근무했습니다", "2017.03~2019.01 통신병 근무", "20대 후반의 개발자입니다", "소대장 경험으로 팀을 이끌었습니다", "면제 판정을 받았습니다",
        "Gender: Female | Age: 27 | Nationality: Korean", "I am a mother of two", "Girls Who Code mentor", "In my late twenties I changed careers",
    ],
)
def test_lines_from_the_audit_that_the_first_vocabulary_missed_are_removed(line):
    cv = f"경력\n{line}\n- Java, Spring Boot 기반 주문 API 개발\n"
    clean = clean_cv(cv).text
    assert line not in clean
    assert "Java, Spring Boot 기반 주문 API 개발" in clean


def test_mixed_lines_keep_their_professional_part():
    cv = (
        "경력\n"
        "- 저는 27살이고 Java로 주문 API를 개발했습니다\n"
        "- Built order APIs with Spring Boot (female engineer, age 27)\n"
        "NextCode | Backend Developer 2021 | Korean Army sergeant\n"
    )
    clean = clean_cv(cv).text
    assert "Java로 주문 API를 개발했습니다" in clean and "27" not in clean
    assert "Built order APIs with Spring Boot" in clean and "female" not in clean.lower()
    assert "NextCode | Backend Developer 2021" in clean and "sergeant" not in clean.lower()


def test_a_unrecognized_non_personal_heading_is_kept_as_a_known_limit():
    """Pinned limit (PROJECT_DOCUMENTATION.md §6.2): a heading that is neither known nor personal-looking cannot be told from
    a company line, so its body stays and depends on the vocabulary alone."""
    assert "CANARY-V1" in clean_cv(f"{PRO_BEFORE}Volunteer Work\nCANARY-V1 활동 기록\n").text


def test_removed_lines_are_remembered_for_the_plan_check(lang):
    clean = clean_cv(lang.masked)
    assert any("canary-personal" in line for line in clean.removed)
    assert clean.mentions_removed("질문: CANARY-PERSONAL 비고 기록 7788 에 대해") or clean.mentions_removed("Q: CANARY-PERSONAL record 7788 about")
    assert not clean.mentions_removed("Java로 주문 API를 설계한 경험을 설명해 주세요.")
    assert all(len(line) >= 10 for line in clean.removed)  # short removed lines would match ordinary words
