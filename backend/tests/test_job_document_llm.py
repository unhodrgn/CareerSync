"""PDF inspection tests: no external model key needed (fake structured LLM)."""

from pathlib import Path

import pymupdf
import pytest

from app.core.errors import AppError
from app.services.job_document_service import ModelScope, ModelScopes, discover_pdf, read_pdf_pages


class FakeLLM:
    model = "fake"

    def complete_json(self, system, user, schema, max_tokens=4000):
        assert "<page number=" in user
        assert schema is ModelScopes
        return ModelScopes(scopes=[ModelScope(
            title="프로젝트 A", company="A기업", roles=["개발자", "디자이너"],
            start_page=1, end_page=2
        )])


def test_scope_selection_uses_actual_pdf_pages():
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((72, 72), "React TypeScript API mobile UI requirements and testing.")
    content = doc.tobytes()
    doc.close()
    result = discover_pdf(content, "application/pdf", FakeLLM())
    assert result["pages"] == 2
    assert result["method"] == "llm:fake"
    assert result["scopes"][0]["roles"] == ["개발자", "디자이너"]
    assert "TypeScript" in result["scopes"][0]["excerpt"]


def test_llm_is_required_and_never_silently_falls_back():
    with pytest.raises(AppError) as caught:
        discover_pdf(b"%PDF-example", "application/pdf", None)
    assert caught.value.code == "JD_LLM_REQUIRED"


def test_real_complex_pdf_has_more_than_ten_pages_and_can_be_extracted():
    path = Path(__file__).resolve().parents[2] / "data" / "test_complex.pdf"
    if not path.is_file():
        pytest.skip("Optional local fixture only")
    pages = read_pdf_pages(path.read_bytes(), "application/pdf")
    assert len(pages) == 13
    assert "와이트론" in "\n".join(pages)
