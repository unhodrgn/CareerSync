"""Skill roadmap (D21): gaps from public job info vs the CV text, LLM output validated, resources only from YAML."""
import pytest

from ai.career.gaps import Gap, find_gaps
from ai.career.resources import load_resources
from ai.career.roadmap import MAX_STEPS, make_roadmap, roadmap_rules
from ai.llm.client import LLMError
from ai.tests.helpers import SAMPLE_CV, SKILLS, FakeLLM

RESOURCES = load_resources()
CRITERIA = ["Kubernetes 운영 경험 (skill): 클러스터 운영", "Java 활용 능력 (skill): Java 17"]
JD = "데이터 플랫폼 백엔드. Kafka, AWS, Docker 사용. SQLP 우대, 정보처리기사 우대"


def _roadmap(llm, gaps=None):
    gaps = gaps if gaps is not None else find_gaps(CRITERIA, JD, SAMPLE_CV, SKILLS)
    return make_roadmap(gaps, "백엔드 개발자", JD, CRITERIA, SKILLS.find_in_text(SAMPLE_CV), RESOURCES, llm)


# ── Gaps ──


def test_gaps_are_named_by_the_job_and_missing_from_the_cv_text():
    gaps = find_gaps(CRITERIA, JD, SAMPLE_CV, SKILLS)
    # Criteria first, then the JD; Java, AWS, Docker and 정보처리기사 are in the CV
    assert gaps == [Gap("Kubernetes", "skill"), Gap("Kafka", "skill"), Gap("SQLP", "certificate")]


def test_no_gaps_when_the_cv_has_everything():
    assert find_gaps(["Java 활용 능력 (skill): Spring Boot"], "Java, Spring", SAMPLE_CV, SKILLS) == []


# ── Resources ──


def test_resources_come_from_the_yaml_and_skip_unverified_entries(tmp_path):
    assert RESOURCES.for_gap("Kubernetes", "skill")[0].url == "https://kubernetes.io/docs/tutorials/kubernetes-basics/"
    assert RESOURCES.for_gap("MySQL", "skill") == []  # verified: false in the file
    assert RESOURCES.for_gap("정보보안기사", "certificate") == []
    assert RESOURCES.for_gap("Swift", "skill") == []  # no entry
    path = tmp_path / "res.yaml"
    path.write_text(
        'version: "x"\nskills:\n  Go: {title: "Go", url: "https://go.dev/doc/"}\n'
        '  Rust: {title: "Rust", url: "https://example.invalid/", verified: false}\ncertificates: {}\n',
        encoding="utf-8",
    )
    res = load_resources(path)
    assert set(res.skills) == {"Go"}


# ── Template (AI_MODE=rules) ──


def test_template_has_one_step_per_gap_with_yaml_resources():
    steps, method = _roadmap(None)
    assert method == "rules"
    assert [(s.order, s.skill, s.kind) for s in steps] == [(1, "Kubernetes", "skill"), (2, "Kafka", "skill"), (3, "SQLP", "certificate")]
    assert steps[0].goal and len(steps[0].activities) == 3 and "Kubernetes" in steps[0].activities[0]
    assert steps[2].goal == "SQLP 취득" and steps[2].resources[0].url == "https://www.dataq.or.kr/"
    assert all("http" not in s.goal + "".join(s.activities) for s in steps)


def test_template_caps_the_number_of_steps():
    gaps = [Gap(n, "skill") for n in ("Go", "Rust", "Kafka", "Redis", "GraphQL", "gRPC", "Terraform", "Airflow")]
    assert len(roadmap_rules(gaps, RESOURCES)) == MAX_STEPS


# ── LLM ──


def test_llm_steps_are_validated():
    llm = FakeLLM(
        {
            "steps": [
                {"skill": "kubernetes", "goal": "클러스터 배포 자동화 https://evil.example/x 익히기", "activities": ["k8s.io/docs 읽기", "Helm 차트 작성"]},
                {"skill": "Terraform", "goal": "공고에 없는 기술", "activities": ["학습"]},  # not a gap: dropped
                {"skill": "Kubernetes", "goal": "중복", "activities": ["중복"]},  # repeat: ignored
                {"skill": "SQLP", "goal": "SQLP 합격", "activities": ["기출 풀이", "www.example.com 참고"]},
            ]
        }
    )
    steps, method = _roadmap(llm)
    assert method == "llm:fake-llm"
    assert [s.skill for s in steps] == ["Kubernetes", "Kafka", "SQLP"]
    k8s, kafka, sqlp = steps
    assert k8s.goal == "클러스터 배포 자동화 익히기" and k8s.activities == ("읽기", "Helm 차트 작성")
    assert kafka.goal == "Kafka 실무 기초 역량 갖추기"  # skipped by the model: the template fills it
    assert sqlp.activities == ("기출 풀이", "참고")
    assert k8s.resources[0].url.startswith("https://kubernetes.io/")  # resources from the YAML, not the model


def test_llm_input_has_no_cv_text():
    llm = FakeLLM({"steps": [{"skill": "Kafka", "goal": "Kafka 활용", "activities": ["실습"]}]})
    _roadmap(llm)
    (system, user), = llm.calls
    assert "<gaps>" in user and "skill: Kubernetes" in user
    for cv_line in ("넥스트코드", "jiwon.kim@example.com", "010-1234-5678", "한국대학교"):
        assert cv_line not in user


@pytest.mark.parametrize(
    "response",
    [
        None,  # LLMError: no response
        {"steps": [{"skill": "Terraform", "goal": "x", "activities": ["y"]}]},  # nothing usable
    ],
)
def test_llm_failure_falls_back_to_the_template(response):
    llm = FakeLLM(*([response] if response else []))
    steps, method = _roadmap(llm)
    assert method == "rules" and [s.skill for s in steps] == ["Kubernetes", "Kafka", "SQLP"]


def test_no_gaps_means_no_llm_call():
    llm = FakeLLM()
    assert _roadmap(llm, gaps=[]) == ([], "rules") and llm.calls == []


def test_unusable_output_raises_inside_roadmap_llm():
    from ai.career.roadmap import roadmap_llm

    with pytest.raises(LLMError):
        roadmap_llm([Gap("Kafka", "skill")], "t", "jd", [], [], RESOURCES, FakeLLM({"steps": []}))
