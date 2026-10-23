"""The demo CV (data/demo/demo_cv.pdf, built by scripts/make_demo_cv.py) reads back as written and parses into
every CV section, so the seed and a live upload get a full profile. No network, key or database."""
import importlib.util
from pathlib import Path

from ai.parsing.extract import structure_cv
from ai.parsing.pdf import extract_text
from ai.parsing.pii import mask_pii
from ai.parsing.sections import split_sections
from ai.tests.helpers import SKILLS

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "make_demo_cv.py"


def _generator():
    spec = importlib.util.spec_from_file_location("make_demo_cv", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_cv_pdf_reads_back_and_parses_into_every_section():
    gen = _generator()
    data = gen.CV_PATH.read_bytes()
    # Every line of the generator's text survives extraction, from the committed PDF and from a fresh build
    # (bytes are not compared: they differ between PyMuPDF versions)
    assert gen.missing_lines(data, gen.CV_TEXT) == []
    assert gen.missing_lines(gen.build_pdf(gen.CV_TEXT), gen.CV_TEXT) == []

    pdf = extract_text(data)
    assert pdf.pages == 1
    masked = mask_pii(pdf.text, [gen.CV_NAME])
    assert set(masked.masked) == {"email", "phone", "name"}
    for secret in (gen.CV_NAME, "doyun.han@example.com", "010-0000-0000"):
        assert secret not in masked.text

    sections = {s.key for s in split_sections(masked.text)}
    assert {"experience", "project", "skill", "education", "certificate"} <= sections

    profile, method = structure_cv(masked.text, SKILLS, None)
    assert method == "rules"
    assert len(profile.experiences) == 1 and profile.experiences[0].end is None  # 현재
    assert len(profile.projects) == 3
    assert [(e.major, e.degree) for e in profile.education] == [("컴퓨터공학과", "학사")]
    assert [c.name for c in profile.certificates] == ["정보처리기사"]
    assert {"Java", "Spring", "JPA", "PostgreSQL", "Python"} <= set(profile.skills)
    # The data engineer job's skills stay missing, so the roadmap has gaps to show
    assert not {"AWS", "Airflow", "Spark"} & set(profile.skills)
