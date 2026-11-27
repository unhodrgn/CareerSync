"""Build the synthetic demo CV (data/demo/demo_cv.pdf) and check that it reads back line for line.

The person, companies, school and contact details are made up. The CV fits the seed jobs: strong for the
NextCode backend job, no AWS/Airflow/Spark for the CloudLab data job (roadmap gaps), and one project without
technologies or numbers (CV self-check findings). The seeker accounts in scripts/seed.py use CV_NAME as their
display name, so the name in the CV is masked before any LLM call (CLAUDE.md AI rule 3).

The text uses PyMuPDF's built-in `helv` (Helvetica) font, which is not embedded. Text past the right page edge
is lost on extraction, so every line is checked against the page width, and the PDF is written only after
`ai.parsing.pdf.extract_text` reads back every line.

    python scripts/make_demo_cv.py          # from the repo root
"""
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.parsing.pdf import extract_text  # noqa: E402

CV_NAME = "Doyun Han"
CV_PATH = ROOT / "data" / "demo" / "demo_cv.pdf"
CV_TEXT = f"""{CV_NAME}
Email: doyun.han@example.com
Phone: 555-010-0000

Experience
Hanbit Commerce Inc. | Backend Developer 2021.03 ~ present
- Built order and settlement APIs with Java 17, Spring Boot, JPA
- Reduced response latency by 40% via PostgreSQL query tuning and indexes
- Cut API server load by 30% by introducing Redis caching

Projects
Settlement API Server Design and Deployment 2023.01 ~ 2023.08
- Designed and deployed with Spring Boot, PostgreSQL, and Docker
- Reduced daily settlement processing time from 2 hours to 25 minutes
Sales Report Automation 2022.03 ~ 2022.06
- Automated 12 sales report types with Python and pandas
Internal Code Review Study Group 2020.01 ~ 2020.12
- Led weekly code review sessions for junior developers

Skills
Java, Spring Boot, JPA, PostgreSQL, Redis
Python, Docker, Git

Education
Saebit University | B.S. in Computer Science | 2015.03 ~ 2021.02

Certificates
OCJP 2020.11
"""

FONT_NAME = "helv"
FONT_SIZE = 10
MARGIN = 50
PAGE = pymupdf.paper_rect("a4")


def too_wide(text: str) -> list[str]:
    """Lines that could pass the right margin."""
    return [
        line
        for line in text.splitlines()
        if MARGIN + pymupdf.get_text_length(line, fontname=FONT_NAME, fontsize=FONT_SIZE) > PAGE.width - MARGIN
    ]


def build_pdf(text: str) -> bytes:
    if wide := too_wide(text):
        raise ValueError(f"lines too long for the page: {wide}")
    doc = pymupdf.open()
    doc.set_metadata({})  # no creation date, so the same text gives the same bytes
    page = doc.new_page(width=PAGE.width, height=PAGE.height)
    page.insert_text((MARGIN, MARGIN + FONT_SIZE), text, fontname=FONT_NAME, fontsize=FONT_SIZE)
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def missing_lines(pdf: bytes, text: str) -> list[str]:
    """Non-blank lines of `text` that extract_text does not read back exactly."""
    got = [line.strip() for line in extract_text(pdf).text.splitlines() if line.strip()]
    return [line.strip() for line in text.splitlines() if line.strip() and line.strip() not in got]


def main() -> None:
    pdf = build_pdf(CV_TEXT)
    if missing := missing_lines(pdf, CV_TEXT):
        sys.exit("The PDF does not read back these lines (nothing written):\n" + "\n".join(missing))
    CV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CV_PATH.write_bytes(pdf)
    print(f"wrote {CV_PATH.relative_to(ROOT)} ({len(pdf)} bytes); every line reads back")


if __name__ == "__main__":
    main()
