"""Scoring quality with the demo embedding intfloat/multilingual-e5-base (docs/DECISIONS.md D26, D27).

Skipped unless the model is already in the Hugging Face cache: tests never download it. The backend container
has it in the model-cache volume:

    docker compose exec -T backend sh -c "cd /app && python -m pytest -q ai/tests/test_e5_quality.py"
"""
import os

import pytest

from ai.parsing.extract import analyze_jd_rules
from ai.scoring.fit import score_candidate
from ai.scoring.retrieval import cv_chunks, retrieve
from ai.scoring.types import Criterion, JobContext
from ai.tests.helpers import SKILLS
from ai.tests.test_scoring import PHOTOSHOP_CV, TODAY, candidate

MODEL = "intfloat/multilingual-e5-base"


def _cached() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(MODEL, "config.json"), str)


pytestmark = pytest.mark.skipif(not _cached(), reason=f"{MODEL} is not in the Hugging Face cache")


@pytest.fixture(scope="module")
def e5():
    previous = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"  # use the cache only
    try:
        from ai.embedding.model import E5Embedder

        yield E5Embedder(MODEL)
    finally:
        if previous is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous


def _score(c: Criterion, embedder, job: JobContext | None = None):
    job = job or JobContext(title="백엔드 개발자", company_name="Acme")
    return score_candidate([c], candidate(), job, skills=SKILLS, embedder=embedder, llm=None, today=TODAY)[0]


def test_e5_is_really_used(e5):
    assert e5.name == MODEL
    a, b = e5.embed(["Java", "Photoshop"])
    assert sum(x * y for x, y in zip(a, b, strict=True)) > 0.8  # e5 rates unrelated skill names as similar


def test_unrelated_skill_in_the_dictionary_gets_no_partial_credit(e5):
    # Before D27 e5 similarity gave Figma 50 ("유사 기술 JPA")
    r = _score(Criterion(1, "Figma 활용", "", "skill", 100), e5)
    assert (r.score, r.reason) == (0, "Figma 경험 확인 안 됨")


@pytest.mark.parametrize("skill", ["Excel", "Photoshop"])
def test_skills_outside_the_dictionary_missing_from_the_cv_score_zero(e5, skill):
    # Not in data/skills.yaml and not on the CV: 0, never "유사"/"계열" and never the neutral score (D28)
    r = _score(Criterion(1, f"{skill} 활용", "", "skill", 100), e5)
    assert (r.score, r.reason) == (0, "이력서에서 확인되지 않음")


def test_skill_outside_the_dictionary_on_the_cv_scores_higher(e5):
    c = Criterion(1, "Photoshop 활용", "", "skill", 100)
    with_it = score_candidate(
        [c], candidate(PHOTOSHOP_CV), JobContext(title="디자이너"), skills=SKILLS, embedder=e5, llm=None, today=TODAY
    )[0]
    without = _score(c, e5)
    assert with_it.score >= 50 and with_it.score > without.score
    assert any("Photoshop" in line for line in with_it.evidence)


def test_contact_block_is_never_retrieved_for_a_project_criterion(e5):
    # Before issue 32's mitigation e5 ranked "[이름] 연락처 …" (0.805) above the project chunk (0.801)
    cand = candidate()
    query = "프로젝트 경험. 직무와 관련된 프로젝트 경험과 본인의 역할"
    passages = retrieve(query, cv_chunks(cand.text), e5, k=10, prefer=("project", "experience"))
    assert passages and all("[이메일]" not in p.chunk.text and "[전화번호]" not in p.chunk.text for p in passages)
    assert passages[0].chunk.section in ("project", "experience")


def test_related_group_credit_does_not_depend_on_the_embedder(e5):
    r = _score(Criterion(1, "PostgreSQL 활용", "", "skill", 100), e5)
    assert (r.score, r.reason) == (50, "PostgreSQL 직접 경험은 없으나 같은 계열 기술 MySQL 보유")


def test_default_project_criterion_from_analyze_is_not_zero(e5):
    jd = "주요 업무\n- 추천 API 개발\n\n자격 요건\n- Python, FastAPI 실무 경험\n- 경력 3년 이상\n"
    analysis = analyze_jd_rules("백엔드 개발자", jd, None, SKILLS)
    [project] = [c for c in analysis.criteria if c.category == "project"]
    c = Criterion(1, project.name, project.description, "project", 100)
    r = _score(c, e5, JobContext(title="백엔드 개발자", description=jd, company_name="Acme"))
    assert r.score > 0 and r.method == "rule:project" and r.evidence
