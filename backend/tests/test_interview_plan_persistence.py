"""The plan that is stored (M4 S2): the CV flow of `interview_plan_service` and the canonical form.

What the planning model is sent, what `build_plan` is given, what is dropped from the bank, that the stored plan is a fixed point of
the validation the engine applies and carries no CV quote, no raw or cleaned CV, no bank and no weight. Limits are documented
too: a paraphrase of a CV line is not detected."""
import json
from dataclasses import replace

import pytest

from ai.interview import InterviewPlan, PlanCriterion, boundary, clean_cv, validate_plan
from ai.parsing.extract import PROMPT_DIR
from app.services import ai_runtime, career_service
from app.services import interview_plan_service as plans
from app.services.interview_plan_service import PlanRefused, build_canonical_plan, plan_digest, seal

from .interview_fixtures import KEPT_LINES, REMOVED_LINES, SAMPLE_CV, PlanLLM

CRITERIA = [
    PlanCriterion(1, "Java", "skill", "Java 개발 경험", "핵심", 0),
    PlanCriterion(2, "Spring Boot", "skill", "Spring Boot 실무 경험", "핵심", 1),
    PlanCriterion(3, "협업", "other", "팀 협업 경험", "중요", 2),
]
STATIC_PROMPT = "interview_questions.md"


def make(llm=None, *, stored_cv=SAMPLE_CV, criteria=CRITERIA, **overrides):
    args = dict(
        stored_cv=stored_cv,
        job_title="Backend Engineer",
        job_text="Java/Spring 백엔드 API 개발",
        criteria=criteria,
        blocklists=career_service.interview_blocklists(),
        embedder=ai_runtime.embedder(),
        skills=ai_runtime.skills(),
        limits=plans.limits_from_settings(),
        llm=llm,
    )
    args.update(overrides)
    return build_canonical_plan(**args)


def strings(value):
    """Every string in a JSON-like value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def norm(text):
    return " ".join(text.split()).lower()


def long_cv_lines():
    return [norm(line) for line in KEPT_LINES if len(norm(line)) >= plans.MIN_CV_LINE_CHARS]


def holds_cv_line(text):
    return any(line in norm(text) for line in long_cv_lines())


def test_the_sample_cv_is_cleaned_as_these_tests_assume():
    clean = clean_cv(SAMPLE_CV)
    for line in KEPT_LINES:
        assert line in clean.text
    for line in REMOVED_LINES:
        assert line not in clean.text and norm(line) in clean.removed


# ── The plan of the rules and of the model ──


def test_a_rules_plan_is_canonical():
    sealed = make()
    assert sealed.method == "rules" and sealed.plan.bank_method == "rules"
    assert [i.topic_id for i in sealed.plan.items] == ["c1", "c2", "c3", "behavioral"]
    assert sealed.sha256 == plan_digest(sealed.data) and len(sealed.sha256) == 64
    assert json.loads(json.dumps(sealed.data)) == sealed.data  # what is stored is what comes back


def test_a_model_plan_is_canonical_and_names_its_method():
    llm = PlanLLM()
    sealed = make(llm)
    assert sealed.method == "llm:fake-llm" and sealed.data["bank_method"] == "llm:fake-llm"
    assert len(llm.calls) == 1 and "Java 관련 경험을 말씀해 주세요." in [i.question for i in sealed.plan.items]


@pytest.mark.parametrize("llm_factory", [lambda: None, lambda: PlanLLM(), lambda: PlanLLM(cv_quote=KEPT_LINES[0])], ids=["rules", "model", "model-with-quotes"])
def test_the_stored_plan_is_a_fixed_point_of_the_validation_the_engine_applies(llm_factory):
    sealed = make(llm_factory())
    again = validate_plan(sealed.plan, blocklists=career_service.interview_blocklists(), cv_text=None)
    assert again.issues == () and again.plan == sealed.plan
    reloaded = InterviewPlan.from_dict(json.loads(json.dumps(sealed.data)))  # from storage
    assert reloaded == sealed.plan
    assert validate_plan(reloaded, blocklists=career_service.interview_blocklists()).issues == ()


def test_no_cv_quote_is_stored_even_when_the_model_quotes_the_cv():
    llm = PlanLLM(cv_quote=KEPT_LINES[0])
    sealed = make(llm)
    assert all(item.cv_quote is None for item in sealed.plan.items)
    assert all(item["cv_quote"] is None for item in sealed.data["items"])
    assert not any(holds_cv_line(s) for s in strings(sealed.data))


def test_there_is_no_cv_grounded_warm_up():
    for llm in (None, PlanLLM(), PlanLLM(cv_quote=KEPT_LINES[1])):
        assert "warmup" not in [i.topic_id for i in make(llm).plan.items]


def test_the_stored_plan_has_no_cv_text_and_no_weight():
    sealed = make(PlanLLM(cv_quote=KEPT_LINES[0]))
    text = json.dumps(sealed.data, ensure_ascii=False)
    for line in (*REMOVED_LINES, *KEPT_LINES[:3]):
        assert line not in text
    assert SAMPLE_CV not in text and clean_cv(SAMPLE_CV).text not in text
    assert "weight" not in text and "weight" not in " ".join(strings(sealed.data)).lower()
    assert set(sealed.data) == {"items", "uncovered", "rubric_notice", "bank_method", "depth"}
    assert sealed.data["depth"] == 2
    assert {i["importance"] for i in sealed.data["items"]} <= {"핵심", "중요", "일반", None}


# ── The CV boundary ──


def test_the_model_gets_the_cleaned_cv_and_never_what_was_removed():
    llm = PlanLLM()
    make(llm)
    (system, user), = llm.calls
    assert user.count("<cv_excerpts>") == 1 and any(line in user for line in KEPT_LINES[:3])  # the cleaned CV reaches the model
    for line in REMOVED_LINES:
        assert line not in user and line not in system
    for word in ("홍길동", "서울특별시", "군필", "병장", "취미", "성별"):
        assert word not in user
    assert system == (PROMPT_DIR / STATIC_PROMPT).read_text(encoding="utf-8")  # the static prompt, with no CV text in it


def test_the_planning_call_goes_through_compose_and_ask(monkeypatch):
    calls = []
    real = boundary.ask

    def spy(llm, model_input):
        calls.append(model_input)
        return real(llm, model_input)

    monkeypatch.setattr(boundary, "ask", spy)
    llm = PlanLLM()
    make(llm)
    assert len(calls) == len(llm.calls) == 1
    assert isinstance(calls[0], boundary.ModelInput) and calls[0].purpose == "plan"
    assert calls[0].user == llm.calls[0][1]  # the model got exactly what was composed


def test_make_bank_gets_the_cleaned_text_and_build_plan_gets_the_stored_text(monkeypatch):
    seen = {}
    real_bank, real_plan = plans.make_bank, plans.build_plan

    def bank(title, text, infos, masked_cv, *args):
        seen["bank"] = masked_cv
        return real_bank(title, text, infos, masked_cv, *args)

    def plan(criteria, questions, masked_cv, *args):
        seen["plan"] = masked_cv
        return real_plan(criteria, questions, masked_cv, *args)

    monkeypatch.setattr(plans, "make_bank", bank)
    monkeypatch.setattr(plans, "build_plan", plan)
    make()
    assert seen["bank"] == clean_cv(SAMPLE_CV).text != SAMPLE_CV
    assert seen["plan"] == SAMPLE_CV  # so that CleanCv.removed exists inside build_plan (D62)


def test_the_stored_cv_is_not_sent_to_a_model_even_when_the_cleaned_one_is_empty():
    llm = PlanLLM()
    make(llm, stored_cv="이름: 홍길동\n성별: 남\n나이: 27세")  # no usable section: nothing of it may be sent
    for _system, user in llm.calls:
        assert "홍길동" not in user and "27" not in user and "성별" not in user


# ── The bank is pre-filtered, and build_plan still refuses a removed line ──


def copying(line):
    return lambda cid, name: f"{line} 에서 {name}를 맡으셨나요? 설명해 주세요." if cid == 1 else f"{name} 관련 경험을 말씀해 주세요."


def test_a_bank_question_that_repeats_a_cv_line_is_dropped_and_the_template_takes_its_place():
    sealed = make(PlanLLM(question=copying(KEPT_LINES[0])))
    questions = [i.question for i in sealed.plan.items]
    assert not any(KEPT_LINES[0] in q for q in questions)
    assert [i.topic_id for i in sealed.plan.items][:3] == ["c1", "c2", "c3"]  # the criterion still has a question
    assert not any(holds_cv_line(q) for q in questions)


def test_a_bank_question_that_repeats_a_removed_line_is_dropped():
    sealed = make(PlanLLM(question=copying(REMOVED_LINES[0])))
    assert not any(REMOVED_LINES[0] in i.question for i in sealed.plan.items)
    assert [i.topic_id for i in sealed.plan.items][:3] == ["c1", "c2", "c3"]


def test_prefilter_clears_every_quote_and_keeps_the_rest():
    from ai.career.interview import Question

    clean = clean_cv(SAMPLE_CV)
    bank = [Question("Java 경험을 말씀해 주세요.", 1, "Java", "technical", "경험", ("사례",), KEPT_LINES[0])]
    out = plans.prefilter_bank(bank, clean)
    assert out == [replace(bank[0], cv_quote=None)]
    copy = [Question(f"{KEPT_LINES[1]} 에 대해 말씀해 주세요.", 2, "Spring", "technical", "경험", ("사례",))]
    assert plans.prefilter_bank(copy, clean) == []
    tip_copy = [Question("Spring 경험을 말씀해 주세요.", 2, "Spring", "technical", "경험", (KEPT_LINES[2],))]
    assert plans.prefilter_bank(tip_copy, clean) == []  # the intent and the tips count too


def test_build_plan_refuses_a_removed_line_on_its_own_because_it_gets_the_stored_cv(monkeypatch):
    """With the prefilter off, only `build_plan` stands between a removed line and the plan. It cleans the stored text itself
    and keeps what was removed (D62). Given the cleaned text it would see nothing to compare with."""
    monkeypatch.setattr(plans, "prefilter_bank", lambda bank, clean: [replace(q, cv_quote=None) for q in bank])
    sealed = make(PlanLLM(question=copying(REMOVED_LINES[0])))
    assert not any(REMOVED_LINES[0] in i.question for i in sealed.plan.items)


# ── The last scan and the canonical checks ──


def test_the_final_scan_refuses_a_plan_that_repeats_a_cv_line(monkeypatch):
    monkeypatch.setattr(plans, "prefilter_bank", lambda bank, clean: [replace(q, cv_quote=None) for q in bank])  # prefilter off
    with pytest.raises(PlanRefused) as refused:
        make(PlanLLM(question=copying(KEPT_LINES[0])))
    assert refused.value.code == "cv_text"


def test_a_plan_without_questions_is_refused():
    clean = clean_cv(SAMPLE_CV)
    empty = InterviewPlan(())
    with pytest.raises(PlanRefused) as refused:
        seal(empty, clean, career_service.interview_blocklists())
    assert refused.value.code == "empty_plan"


def test_a_plan_that_still_has_a_cv_quote_is_not_canonical():
    sealed = make()
    quoted = replace(sealed.plan, items=(replace(sealed.plan.items[0], cv_quote=KEPT_LINES[0]), *sealed.plan.items[1:]))
    with pytest.raises(PlanRefused) as refused:
        seal(quoted, clean_cv(SAMPLE_CV), career_service.interview_blocklists())
    assert refused.value.code == "not_canonical"


def test_a_validation_that_reports_an_issue_or_does_not_settle_is_refused(monkeypatch):
    sealed = make()
    real = plans.validate_plan
    clean = clean_cv(SAMPLE_CV)
    blocklists = career_service.interview_blocklists()

    monkeypatch.setattr(plans, "validate_plan", lambda plan, **kw: replace_report(real(plan, **kw), issues=("c1:question",)))
    with pytest.raises(PlanRefused) as refused:
        seal(sealed.plan, clean, blocklists)
    assert refused.value.code == "not_canonical"

    calls = []

    def moving(plan, **kw):
        report = real(plan, **kw)
        calls.append(1)
        if len(calls) == 2:  # the second validation changes the plan
            items = (replace(report.plan.items[0], intent="바뀐 의도"), *report.plan.items[1:])
            return replace_report(report, plan=replace(report.plan, items=items))
        return report

    monkeypatch.setattr(plans, "validate_plan", moving)
    with pytest.raises(PlanRefused) as refused:
        seal(sealed.plan, clean, blocklists)
    assert refused.value.code == "not_a_fixed_point"


def replace_report(report, **changes):
    return replace(report, **changes)


def test_the_leak_scan_sees_cv_lines_and_removed_lines_and_nothing_else():
    sealed = make()
    clean = clean_cv(SAMPLE_CV)
    assert plans.leaks(sealed.plan, clean) is False
    spoken = replace(sealed.plan.items[0], question=f"{KEPT_LINES[0]} 를 설명해 주세요.")
    assert plans.leaks(replace(sealed.plan, items=(spoken, *sealed.plan.items[1:])), clean) is True
    removed = replace(sealed.plan.items[0], criterion_name=REMOVED_LINES[1])  # not a spoken text, but a removed line
    assert plans.leaks(replace(sealed.plan, items=(removed, *sealed.plan.items[1:])), clean) is True
    short = replace(sealed.plan.items[0], question="Java, Spring Boot 경험을 설명해 주세요.")  # a CV line is 12+ characters whole
    assert plans.leaks(replace(sealed.plan, items=(short, *sealed.plan.items[1:])), clean) is False


# ── What the plan cannot promise ──


def test_a_paraphrase_of_a_cv_line_is_not_detected_and_the_documentation_says_so():
    """The plan may hold professional questions that the model wrote from the cleaned CV, in its own words. Only a line
    repeated word for word is caught."""
    paraphrase = lambda cid, name: "Java와 Spring Boot를 사용해서 주문 API를 개발한 경험을 구체적으로 설명해 주세요." if cid == 1 else f"{name} 관련 경험을 말씀해 주세요."
    sealed = make(PlanLLM(question=paraphrase))
    assert any("주문 API를 개발한 경험" in i.question for i in sealed.plan.items)


def test_the_limits_are_stored_as_the_engine_runs_them():
    limits = plans.limits_from_settings()
    data = plans.limits_data(limits)
    assert data == {
        "max_questions": 5,
        "max_seconds": 600,
        "max_followups_per_item": 2,
        "max_clarifies_per_item": 1,
        "silence_nudge_seconds": 20,
        "silence_skip_seconds": 45,
        "turn_llm_deadline_seconds": 8,
        "wrap_reserve_seconds": 45,
    }
    assert plans.InterviewLimits(**data) == limits


def test_the_digest_is_of_the_canonical_json():
    assert plan_digest({"b": 1, "a": [1, "가"]}) == plan_digest({"a": [1, "가"], "b": 1})
    assert plan_digest({"a": 1}) != plan_digest({"a": 2})


def test_a_quote_is_refused_even_when_the_validation_does_not_notice_it(monkeypatch):
    """The explicit check stands on its own: here the validation reports the quoted plan as unchanged and issue-free."""
    from ai.interview import PlanReport

    sealed = make()
    quoted = replace(sealed.plan, items=(replace(sealed.plan.items[0], cv_quote=KEPT_LINES[0]), *sealed.plan.items[1:]))
    monkeypatch.setattr(plans, "validate_plan", lambda plan, **kw: PlanReport(plan, ()))
    with pytest.raises(PlanRefused) as refused:
        seal(quoted, clean_cv(SAMPLE_CV), career_service.interview_blocklists())
    assert refused.value.code == "cv_quote"


def test_a_cv_line_is_an_excerpt_from_twelve_characters_and_a_shorter_one_is_a_word():
    from ai.interview import CleanCv

    clean = CleanCv("경력\n- abcdefghijkl\n- abcdefghijk\n", ())  # 12 and 11 characters
    item = make().plan.items[0]
    plan = lambda question: replace(make().plan, items=(replace(item, question=question), *make().plan.items[1:]))
    assert plans.leaks(plan("앞 abcdefghijkl 뒤 설명해 주세요."), clean) is True
    assert plans.leaks(plan("앞 abcdefghijk 뒤 설명해 주세요."), clean) is False  # the 11-character line is not scanned
    skill = clean_cv("경력\n- Spring Boot\n- Java 개발\n")  # a skill name on its own line is a word, not a copied sentence
    assert plans.leaks(plan("Spring Boot 경험을 설명해 주세요."), skill) is False
