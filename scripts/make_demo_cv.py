"""Build the synthetic demo CV (data/demo/demo_cv.pdf) and check that it reads back line for line.

The person, companies, school and contact details are made up. The CV fits the seed jobs: strong for the
넥스트코드 backend job, no AWS/Airflow/Spark for the 클라우드랩 data job (roadmap gaps), and one project without
technologies or numbers (CV self-check findings). The seeker accounts in scripts/seed.py use CV_NAME as their
display name, so the name in the CV is masked before any LLM call (CLAUDE.md AI rule 3).

The text uses PyMuPDF's built-in `korea` font, which is not embedded. Text past the right page edge is lost on
extraction, so every line is kept within the page at one em per character, and the PDF is written only after
`ai.parsing.pdf.extract_text` reads back every line.

    python scripts/make_demo_cv.py          # from the repo root
"""
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.parsing.pdf import extract_text  # noqa: E402

CV_NAME = "한도윤"
CV_PATH = ROOT / "data" / "demo" / "demo_cv.pdf"
CV_TEXT = f"""{CV_NAME}
이메일: doyun.han@example.com
연락처: 010-0000-0000

경력
(주)한빛커머스 | 백엔드 개발자 2021.03 ~ 현재
- Java 17, Spring Boot, JPA로 주문·정산 API 개발
- PostgreSQL 쿼리 튜닝, 인덱스 설계로 응답 40% 단축
- Redis 캐시 도입으로 API 서버 부하 30% 감소

프로젝트
정산 API 서버 설계 및 배포 2023.01 ~ 2023.08
- Spring Boot, PostgreSQL, Docker로 직접 설계·배포
- 일일 정산 처리 시간을 2시간에서 25분으로 단축
매출 리포트 자동화 2022.03 ~ 2022.06
- Python, pandas로 매출 리포트 12종 자동 생성
사내 코드 리뷰 스터디 운영 2020.01 ~ 2020.12
- 신입 개발자 대상 주간 코드 리뷰 스터디 진행

기술
Java, Spring Boot, JPA, PostgreSQL, Redis
Python, Docker, Git

학력
새빛대학교 컴퓨터공학과 학사 2015.03 ~ 2021.02

자격증
정보처리기사 2020.11
"""

FONT_SIZE = 10
MARGIN = 50
PAGE = pymupdf.paper_rect("a4")


def too_wide(text: str) -> list[str]:
    """Lines that could pass the right margin: one em per character is the widest the font sets them."""
    return [line for line in text.splitlines() if MARGIN + len(line) * FONT_SIZE > PAGE.width - MARGIN]


def build_pdf(text: str) -> bytes:
    if wide := too_wide(text):
        raise ValueError(f"lines too long for the page: {wide}")
    doc = pymupdf.open()
    doc.set_metadata({})  # no creation date, so the same text gives the same bytes
    page = doc.new_page(width=PAGE.width, height=PAGE.height)
    page.insert_text((MARGIN, MARGIN + FONT_SIZE), text, fontname="korea", fontsize=FONT_SIZE)
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
