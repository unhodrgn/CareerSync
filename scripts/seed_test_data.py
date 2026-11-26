"""Seed the synthetic test data in test_data/ so every feature can be demoed with realistic, varied data.

Everything is English: the data is read from test_data/en/ (an English translation of the package, same IDs, file names and
structure) and everything the script writes itself (company names, intros, projects, offer message, locations) is English.
`--source original` reads the untranslated files of test_data/ instead.

Loads, through the app's services (so every guardrail and derived field stays correct):
- 15 fictional companies with a recruiter each (hr-<slug>@sample.test); the real company names of the data are replaced
  by the fictional ones below, also inside titles and job text (source URLs are never loaded);
- the 12 jobs of 01_model_input with criteria mapped from job_criteria_staging.csv, and the 33 Vietnamese-market jobs of
  04_old_VN_33_NOT_IN_TEST with criteria from the product's own JD analyzer (rules); every job is published,
  five of the 33 are then closed;
- 20 seekers (seeker-kr01@sample.test, ...), each with a fictional name that is also written on the CV's `Name:` line (so
  the name is masked), the CV text as a confirmed PDF and the preferences of the CSV, 10 of them in the talent pool;
- applications (all 14 test pairs and more) with their evaluations and a mix of statuses, job recommendations, talent offers
  in every state, running projects, roadmaps and interview questions.

Never read: 02_expected_results_HUMAN_ONLY, 03_source_reference_REVIEW_ONLY, expected labels, notes. test_data/ is gitignored.
The script never calls the LLM (AI_MODE=rules in its own process), never deletes anything and is safe to run again: what
exists is skipped, a run that stopped halfway is completed by the next one, and a status a recruiter already set is kept.
It uses the embedder the app is configured with, so scores match the demo. New accounts get the current consent version.

    python scripts/seed_test_data.py --dry-run     # print the plan, write nothing (reads the database to show what exists)
    python scripts/seed_test_data.py               # from the repo root, after `alembic upgrade head`
    python scripts/seed_test_data.py --skip-vn33   # without the 33 extra Vietnamese-market jobs
    python scripts/seed_test_data.py --source original   # the untranslated files
    python scripts/seed_test_data.py --check-source      # no database: test_data/en/ against the originals (IDs, skills, numbers)

Which database it writes to is printed first (the password is hidden). See docs/how-to/run-locally.md.
"""
import argparse
import csv
import os
import re
import sys
import textwrap
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "scripts")]

# Before anything asks for the LLM client (it reads AI_MODE on every call); also wins over .env
os.environ["AI_MODE"] = "rules"

import pymupdf  # noqa: E402
from sqlalchemy import func, or_, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Application, CareerContent, Company, Evaluation, JobPosting, TalentOffer, User  # noqa: E402
from app.models.application import EvaluationStatus  # noqa: E402
from app.models.job import JobStatus  # noqa: E402
from app.schemas.auth import RegisterIn  # noqa: E402
from app.schemas.company import CompanyProjectIn  # noqa: E402
from app.schemas.criteria import CriterionIn  # noqa: E402
from app.schemas.job import JobCreate  # noqa: E402
from app.schemas.offer import OfferCreate  # noqa: E402
from app.schemas.preference import PreferenceIn  # noqa: E402
from app.services import (  # noqa: E402
    ai_runtime,
    application_service,
    auth_service,
    career_service,
    company_project_service,
    criteria_service,
    cv_service,
    evaluation_service,
    gate_service,
    jd_service,
    job_service,
    offer_service,
    preference_service,
    recommendation_service,
    talent_service,
)
from make_demo_cv import build_pdf, missing_lines  # noqa: E402  (scripts/ is on sys.path)
from seed import PASSWORD  # noqa: E402  (the one demo password)

TEST_DATA = ROOT / "test_data"


@dataclass(frozen=True)
class Source:
    """Where the CSV and text files are: the 01_model_input folder and the 33-jobs CSV."""

    name: str
    core: Path
    vn33: Path


def _source(name: str, base: Path) -> Source:
    return Source(name, base / "01_model_input", base / "04_old_VN_33_NOT_IN_TEST" / "vietnam_jobs_33.csv")


SOURCES = {"en": _source("en", TEST_DATA / "en"), "original": _source("original", TEST_DATA)}

# ── Fictional companies ──
# slug → (name, intro, talent profile, running projects (name, description, technologies))
COMPANIES: dict[str, tuple[str, str, str, list[tuple[str, str, list[str]]]]] = {
    "starlight-insurance": (
        "Starlight Insurance", "A fictional property and casualty insurer that builds digital insurance products and policy systems.",
        "Developers who model complex domains simply",
        [("Policy review automation", "A project that turns insurance policy review rules into code and cuts processing time", ["Kotlin", "Spring Boot", "MySQL"]),
         ("DB operations automation", "A project that standardizes backup, recovery and incident response scripts", ["MySQL", "Terraform"])],
    ),
    "starlight-pay": (
        "Starlight Pay", "A fictional fintech company that builds easy payment and asset services.", "People who decide with data and see things through",
        [("Data platform API", "A high-performance query API that serves payment data fast", ["Kotlin", "Spring Boot", "Redis"]),
         ("Asset service web", "A frontend project that builds the asset overview screens", ["React", "TypeScript"])],
    ),
    "starlight-mobility": (
        "Starlight Mobility", "A fictional mobility company that builds navigation and geospatial services.", "Engineers who are not afraid of large-scale traffic",
        [("Navigation route service", "A rework of the real-time route search backend", ["Java", "Spring", "Redis"]),
         ("Geospatial information system", "A system that stores and queries map data", ["PostgreSQL", "Java"])],
    ),
    "lotus-build": (
        "Lotus Build Vietnam", "A fictional Vietnamese subsidiary that builds construction site management SaaS.",
        "Engineers with strong technical leadership and English communication",
        [("Site management platform", "A site management backend built on Go microservices", ["Go", "gRPC", "AWS"]),
         ("Admin web redesign", "A frontend project that redesigns the admin screens", ["React", "TypeScript"])],
    ),
    "mimosa-pay": (
        "Mimosa Pay", "A fictional Vietnamese fintech company that builds mobile payments and financial services.",
        "Platform engineers who dig into a problem until it is solved",
        [("Payment platform rework", "A rework of the payment API and platform services", ["Python", "PostgreSQL", "Redis"]),
         ("AI data team pipeline", "Building data pipelines and an analytics foundation", ["Python", "Kafka"])],
    ),
    "cedar-tech": (
        "Cedar Tech & Solution", "A fictional IT company that provides software development outsourcing and solutions.",
        "Full-stack developers who learn widely and adapt quickly",
        [("Logistics management system", "A logistics management backend built with Java and Go", ["Java", "Spring Boot", "Go"]),
         ("IoT monitoring", "A monitoring system that collects and shows equipment data", ["MQTT", "Grafana", "Kafka"])],
    ),
    "sunrise-softworks": ("Sunrise Softworks", "A fictional software house that builds software for the financial sector.", "Careful developers who enjoy collaboration", []),
    "verdant-bank": ("Verdant Bank", "A fictional bank that builds digital banking.", "Engineers who take care of both stability and speed", []),
    "tidal-tech": ("Tidal Tech Group", "A fictional IT services group that builds software for many industries.", "Developers who learn on their own and lead teams", []),
    "vela-digital": ("Vela Digital", "A fictional digital company that builds games and social services.", "Engineers who prove user experience with numbers", []),
    "kite-labs": ("Kite Labs Vietnam", "A fictional Vietnamese software house that develops software for US customers.", "Full-stack engineers who care about quality", []),
    "meridian-bank": ("Meridian Bank", "A fictional bank that builds mobile banking.", "Developers who handle customer data responsibly", []),
    "fjord-software": ("Fjord Software", "A fictional software house that builds software for global customers.", "Engineers who build data products end to end", []),
    "nimbus-innovation": ("Nimbus Innovation Centre Vietnam", "A fictional technology centre for banking services.", "Backend engineers who design in depth", []),
    "tidewater-bank": ("Tidewater Bank", "A fictional bank that builds digital finance.", "Engineers with both leadership and technical depth", []),
}
# Real company name in the data (English and original forms) → fictional company slug
COMPANY_OF = {
    "Kakao Pay Insurance": "starlight-insurance", "Kakao Pay": "starlight-pay", "Kakao Mobility": "starlight-mobility",
    "카카오페이손해보험": "starlight-insurance", "카카오페이": "starlight-pay", "카카오모빌리티": "starlight-mobility",
    "ANDPAD Vietnam": "lotus-build", "MoMo": "mimosa-pay", "M_Service (MoMo)": "mimosa-pay", "CMC Technology & Solution": "cedar-tech",
    "DOSOFTPRO": "sunrise-softworks", "VPBank": "verdant-bank", "TMA Solutions / TMA Tech Group": "tidal-tech", "VNG": "vela-digital",
    "KMS Technology": "kite-labs", "MB Bank": "meridian-bank", "FPT Software": "fjord-software",
    "NAB Innovation Centre Vietnam": "nimbus-innovation", "Techcombank": "tidewater-bank",
}
# Real names to scrub from titles and job text (longest first), with their replacement
_SCRUB = {
    "Kakao Pay Insurance": "Starlight Insurance", "Kakao Pay": "Starlight Pay", "Kakao Mobility": "Starlight Mobility", "Kakao": "Starlight",
    "카카오페이손해보험": "Starlight Insurance", "카카오페이": "Starlight Pay", "카카오모빌리티": "Starlight Mobility", "카카오": "Starlight",
    "ANDPAD Vietnam": "Lotus Build Vietnam", "ANDPAD": "Lotus Build", "M_Service (MoMo)": "Mimosa Pay", "M_Service": "Mimosa Pay",
    "MoMo": "Mimosa Pay", "CMC Technology & Solution": "Cedar Tech & Solution", "CMC": "Cedar Tech", "DOSOFTPRO": "Sunrise Softworks",
    "VPBank": "Verdant Bank", "TMA Solutions / TMA Tech Group": "Tidal Tech Group", "TMA Solutions": "Tidal Tech Group",
    "TMA Tech Group": "Tidal Tech Group", "TMA": "Tidal Tech", "VNGGames": "Vela Games", "VNG": "Vela Digital",
    "KMS Technology": "Kite Labs Vietnam", "KMS": "Kite Labs", "MB Bank": "Meridian Bank", "FPT Software": "Fjord Software",
    "FPT": "Fjord", "NAB Innovation Centre Vietnam": "Nimbus Innovation Centre Vietnam", "NAB": "Nimbus", "Techcombank": "Tidewater Bank",
}
_SCRUB_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in sorted(_SCRUB, key=len, reverse=True)) + r")(?![A-Za-z0-9])", re.IGNORECASE
)
_SCRUB_LOWER = {k.lower(): v for k, v in _SCRUB.items()}

# ── Mappings of the CSV values ──
LOCATION_OF_JOB = {  # the KR jobs only say "Korea (see the original posting for the exact work location)"
    "KR-J01": "Gangnam-gu, Seoul", "KR-J02": "Gangnam-gu, Seoul", "KR-J03": "Pangyo, Seongnam-si, Gyeonggi-do",
    "KR-J04": "Pangyo, Seongnam-si, Gyeonggi-do", "KR-J05": "Pangyo, Seongnam-si, Gyeonggi-do", "KR-J06": "Gangnam-gu, Seoul",
}
LOCATION_OF_CV = {  # preferred_locations tokens → text that the job locations contain
    "SEOUL": "Seoul", "PANGYO": "Pangyo", "HO_CHI_MINH": "Ho Chi Minh", "HA_NOI": "Ha Noi", "DA_NANG": "Da Nang", "REMOTE": "Remote",
}
EMPLOYMENT_OF_CV = {"FULLTIME": "full_time"}
DEADLINE_DAYS = (10, 30, 60)  # every third job gets one, relative to the run date; the rest stay open

# ── What to create ──
PUBLIC = {"KR02", "KR03", "KR05", "KR06", "KR07", "KR09", "VN01", "VN02", "VN05", "VN10"}  # talent pool (opt-in)
# (CV, job, status the recruiter sets); the first 14 are the test pairs of test_pairs_14.csv
APPLICATIONS: list[tuple[str, str, str]] = [
    ("KR02", "KR-J03", "passed"), ("KR03", "KR-J04", "interview"), ("KR03", "KR-J05", "reviewing"), ("KR04", "KR-J06", "interview"),
    ("KR05", "KR-J02", "interview"), ("VN01", "VN-J01", "submitted"), ("VN02", "VN-J06", "interview"), ("VN03", "VN-J03", "reviewing"),
    ("VN04", "VN-J04", "submitted"), ("VN05", "VN-J05", "reviewing"), ("VN08", "KR-J02", "reviewing"), ("KR07", "VN-J01", "passed"),
    ("KR08", "KR-J02", "rejected"), ("VN07", "KR-J04", "submitted"),
    # more applicants per job: high, medium and low Fit, every gate result, every status
    ("KR09", "KR-J01", "passed"), ("KR07", "KR-J01", "interview"), ("KR05", "KR-J01", "reviewing"), ("KR03", "KR-J01", "submitted"),
    ("KR02", "KR-J01", "rejected"), ("KR08", "KR-J01", "submitted"),
    ("KR06", "KR-J02", "submitted"), ("KR03", "KR-J02", "on_hold"),
    ("KR03", "KR-J03", "reviewing"), ("KR01", "KR-J03", "rejected"), ("KR05", "KR-J03", "submitted"), ("KR04", "KR-J03", "submitted"),
    ("KR02", "KR-J04", "reviewing"), ("KR07", "KR-J04", "on_hold"), ("KR10", "KR-J04", "rejected"),
    ("KR05", "KR-J05", "submitted"), ("KR01", "KR-J05", "submitted"), ("KR06", "KR-J05", "on_hold"),
    ("KR08", "KR-J06", "rejected"), ("KR03", "KR-J06", "submitted"), ("KR01", "KR-J06", "submitted"),
    ("KR09", "VN-J01", "reviewing"), ("VN02", "VN-J01", "submitted"), ("KR05", "VN-J01", "rejected"),
    ("KR09", "VN-J02", "reviewing"), ("KR07", "VN-J02", "submitted"), ("VN10", "VN-J02", "submitted"), ("VN01", "VN-J02", "on_hold"),
    ("KR03", "VN-J03", "interview"), ("KR07", "VN-J03", "submitted"), ("VN10", "VN-J03", "rejected"),
    ("KR04", "VN-J04", "reviewing"), ("KR08", "VN-J04", "rejected"), ("VN02", "VN-J04", "submitted"),
    ("KR02", "VN-J05", "submitted"), ("KR09", "VN-J05", "interview"), ("VN06", "VN-J05", "submitted"),
    ("VN09", "VN-J06", "submitted"), ("KR02", "VN-J06", "passed"), ("KR03", "VN-J06", "on_hold"), ("VN06", "VN-J06", "rejected"),
    # some of the 33 extra Vietnamese jobs
    ("VN10", "VN-JOB-001", "reviewing"), ("VN07", "VN-JOB-001", "submitted"), ("KR02", "VN-JOB-030", "interview"),
    ("VN07", "VN-JOB-030", "submitted"), ("VN01", "VN-JOB-014", "submitted"), ("VN01", "VN-JOB-027", "reviewing"),
    ("KR07", "VN-JOB-027", "rejected"), ("VN04", "VN-JOB-033", "submitted"), ("KR04", "VN-JOB-033", "reviewing"),
    ("VN06", "VN-JOB-031", "submitted"), ("KR06", "VN-JOB-031", "on_hold"),
]
# (job, seeker in the talent pool who has not applied to it, final state); a pair that is not eligible when the script runs
# (Pref, required gate or Fit below the thresholds) is reported and skipped
OFFERS: list[tuple[str, str, str]] = [
    ("KR-J01", "KR06", "pending"), ("KR-J02", "KR09", "pending"), ("KR-J04", "VN02", "pending"),
    ("KR-J02", "KR07", "accepted"), ("KR-J05", "KR02", "accepted"),
    ("KR-J03", "KR09", "rejected"), ("KR-J01", "VN05", "rejected"),
    ("VN-J03", "VN01", "cancelled"),
]
OFFER_MESSAGE = "Hello, your CV impressed us. We would like to ask whether you are interested in joining our team. (sample offer)"
RECOMMENDED = ["KR02", "KR03", "KR04", "KR07", "VN01", "VN02"]  # seekers whose job recommendations are computed up front
# The only two CVs of test_data/en/ that deliberately have no "Years of experience:" line, so that the required gate shows REVIEW
# ("experience cannot be confirmed") on their applications to jobs with a minimum; --check-source accepts exactly these two.
NO_YEARS_LINE = ("KR05", "VN10")
CAREER = [("KR01", "KR-J03"), ("KR08", "KR-J06"), ("VN01", "VN-J01"), ("VN07", "KR-J04"), ("KR05", "VN-J03"), ("KR10", "KR-J05")]


# ── Data ──


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"{path.relative_to(ROOT)} not found. test_data/ is gitignored: copy it from the test data package first"
                 + (" (test_data/en/ is the English translation, see docs/how-to/run-locally.md)." if "en" in path.parts else "."))
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def scrub(text: str) -> str:
    return _SCRUB_RE.sub(lambda m: _SCRUB_LOWER[m.group(1).lower()], text)


def fold(text: str) -> str:
    """ASCII Vietnamese, only for `--source original`: the built-in PDF font cannot write the diacritics of the original
    Vietnamese CVs, and no font file is added to the repo. The English CVs never need it."""
    text = text.replace("đ", "d").replace("Đ", "D")
    stripped = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", stripped)  # NFD also split the Hangul of the CV (한국어) into jamo


# English ("3+ years", "3-7 years", "entry-level") and original Korean forms
_EXPERIENCE = re.compile(r"\d+\s*(?:[~\-–]\s*\d+\s*)?\+?\s*(?:년|years?\b)|경력|신입|entry[- ]level", re.IGNORECASE)
_PROJECT = re.compile(r"프로젝트|설계|경험|개발|project|design|experience|development", re.IGNORECASE)


def classify(text: str, skills) -> str:
    """Criterion category of a requirement text: years of experience → experience, a skill of data/skills.yaml → skill,
    a described task → project, anything else (soft skills, languages) → other. No education/certificate in the data."""
    if _EXPERIENCE.search(text):
        return "experience"
    if skills.find_in_text(text):
        return "skill"
    if _PROJECT.search(text):
        return "project"
    return "other"


@dataclass
class _Item:
    name: str
    category: str
    preferred: bool
    units: int


def build_criteria(rows: list[dict], skills) -> list[CriterionIn]:
    """Required items weigh 3 units, preferred 1; at most CRITERIA_MAX_ITEMS items (neighbours of the same kind are merged
    into "A / B", keeping the larger weight); integer weights that total 100 (largest remainder)."""
    items, seen = [], set()
    for r in rows:
        name = scrub(r["requirement_text"].strip())[:50]
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        preferred = r["requirement_type"] == "PREFERRED"
        items.append(_Item(name, classify(name, skills), preferred, 1 if preferred else 3))
    while len(items) > settings.CRITERIA_MAX_ITEMS:
        # Preferred items are merged first; required ones only when at most one preferred item is left
        kind = sum(x.preferred for x in items) >= 2
        pairs = [i for i in range(len(items) - 1) if items[i].preferred == items[i + 1].preferred == kind]
        i = ([p for p in pairs if items[p].category == items[p + 1].category] or pairs)[-1]
        a, b = items[i], items[i + 1]
        category = a.category if a.category == b.category else "other"
        items[i : i + 2] = [_Item(f"{a.name} / {b.name}"[:50], category, a.preferred, max(a.units, b.units))]
    total = sum(x.units for x in items)
    exact = [100 * x.units / total for x in items]
    weights = [max(1, int(e)) for e in exact]
    by_remainder = sorted(range(len(items)), key=lambda i: exact[i] - int(exact[i]), reverse=True)
    for i in by_remainder[: 100 - sum(weights)] if sum(weights) < 100 else []:
        weights[i] += 1
    weights[weights.index(max(weights))] += 100 - sum(weights)  # only if the minimum of 1 overshot
    assert sum(weights) == 100 and all(w >= 1 for w in weights), (items, weights)
    return [CriterionIn(name=x.name, category=x.category, weight=w) for x, w in zip(items, weights)]


@dataclass
class JobSpec:
    key: str
    company: str  # slug
    title: str
    description: str
    min_years: int | None
    location: str
    criteria: list[CriterionIn] | None  # None: from the JD analyzer when the job is created
    closed: bool = False
    deadline: date | None = None


@dataclass
class SeekerSpec:
    cv_id: str
    email: str
    name: str
    text: str
    preferences: PreferenceIn


def core_jobs(skills, src: Source) -> list[JobSpec]:
    criteria = read_csv(src.core / "job_criteria_staging.csv")
    out = []
    for j in read_csv(src.core / "job_postings_staging_clean.csv"):
        rows = [r for r in criteria if r["job_id"] == j["id"]]
        lines = [f"This is the {scrub(j['title'])} position.", "", "Requirements", *[f"- {scrub(r['requirement_text'])}" for r in rows if r["requirement_type"] == "REQUIRED"]]
        if preferred := [r for r in rows if r["requirement_type"] == "PREFERRED"]:
            lines += ["", "Preferred qualifications", *[f"- {scrub(r['requirement_text'])}" for r in preferred]]
        if j["language"].strip():
            lines += ["", f"Language: {j['language'].strip()}"]
        out.append(JobSpec(
            key=j["id"], company=COMPANY_OF[j["company"]], title=scrub(j["title"])[:200], description="\n".join(lines),
            min_years=int(j["min_years"]) if j["min_years"].strip() else None,
            location=LOCATION_OF_JOB.get(j["id"], scrub(j["location"]).strip()[:100]), criteria=build_criteria(rows, skills),
        ))
    return out


def vn33_jobs(src: Source) -> list[JobSpec]:
    out = []
    for j in read_csv(src.vn33):
        years = j["min_experience_years"].strip()
        location = j["location"].strip()
        out.append(JobSpec(
            key=j["job_ref"], company=COMPANY_OF[j["company"]], title=scrub(j["title"])[:200], description=scrub(j["job_text"]),
            min_years=int(years) if years.isdigit() else None, location="Vietnam" if location.startswith("[") else location,
            criteria=None, closed=j["source_status"].startswith("Closed"),
        ))
    return out


def seekers(src: Source) -> list[SeekerSpec]:
    out = []
    for c in read_csv(src.core / "cv_profiles_staging_clean.csv"):
        text = (src.core / "cv_texts" / f"{c['cv_id']}_synthetic_cv.txt").read_text(encoding="utf-8")
        # The display name is the name written in the CV, so it is masked before any model call (AI rule 3)
        name = re.search(r"^(?:Name|이름|Họ tên):\s*(.+?)\s*(?:\(|$)", text, re.MULTILINE).group(1).strip()
        if src.name == "original" and c["country"] == "VN":
            text, name = fold(text), fold(name)
        out.append(SeekerSpec(
            c["cv_id"], f"seeker-{c['cv_id'].lower()}@sample.test", name, text,
            PreferenceIn(
                locations=[LOCATION_OF_CV[t] for t in c["preferred_locations"].split(";") if t],
                employment_types=[EMPLOYMENT_OF_CV[t] for t in c["employment_type"].split(";") if t],
                profile_public=c["cv_id"] in PUBLIC,
            ),
        ))
    return out


def _latin_pdf(text: str) -> tuple[str, bytes]:
    """(wrapped text, PDF) of an English CV in PyMuPDF's built-in Helvetica, which covers ASCII and the dash, so no font file is
    added. Lines are wrapped to the real text width: a sentence stays on one line where it fits (the CV parser reads line by
    line), and no text passes the right page edge, where extraction would lose it."""
    page, size, margin = pymupdf.paper_rect("a4"), 9, 50
    width = lambda s: pymupdf.get_text_length(s, fontname="helv", fontsize=size)  # noqa: E731
    # Helvetica has no dash glyph (extraction reads "·") and extraction collapses repeated spaces, so write what reads back
    text = re.sub(r" {2,}", " ", text.replace("—", "-").replace("–", "-"))
    lines = []
    for line in text.splitlines():
        current = ""
        for word in line.split(" "):
            trial = f"{current} {word}" if current else word
            if current and width(trial) > page.width - 2 * margin:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    if len(lines) * size * 1.2 > page.height - 2 * margin:
        raise ValueError("the CV does not fit on one page")
    wrapped = "\n".join(lines)
    doc = pymupdf.open()
    doc.set_metadata({})  # no creation date, so the same text gives the same bytes
    doc.new_page(width=page.width, height=page.height).insert_text((margin, margin + size), wrapped, fontname="helv", fontsize=size)
    return wrapped, doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def cv_pdf(text: str, src: Source) -> bytes:
    if src.name == "original":  # Korean and Vietnamese text: the built-in CJK font, 45 characters per line
        lines = []
        for line in text.splitlines():
            lines += textwrap.wrap(line, 45) or [""]
        wrapped = "\n".join(lines)
        pdf = build_pdf(wrapped)
    else:
        wrapped, pdf = _latin_pdf(text)
    if missing := missing_lines(pdf, wrapped):
        raise ValueError(f"the PDF does not read back these lines: {missing}")
    return pdf


def plan_jobs(args, skills) -> list[JobSpec]:
    jobs = core_jobs(skills, args.src) + ([] if args.skip_vn33 else vn33_jobs(args.src))
    for i, job in enumerate(jobs):
        if i % 3 == 0 and not job.closed:
            job.deadline = date.today() + timedelta(days=DEADLINE_DAYS[(i // 3) % 3])
    return jobs


# ── Database ──


class Seed:
    def __init__(self, db, src: Source):
        self.db = db
        self.src = src
        self.stats = Counter()
        self.problems: list[str] = []

    def problem(self, text: str, e: Exception | None = None) -> None:
        self.problems.append(f"{text}: {e.code if isinstance(e, AppError) else e}" if e else text)
        print(f"warn  {self.problems[-1]}")

    def user(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(func.lower(User.email) == email))

    def register(self, email: str, display_name: str, role: str, company_name: str | None = None) -> User:
        user = self.user(email)
        if user is not None:
            self.stats[f"{role} accounts skipped"] += 1
            return user
        user = auth_service.register(self.db, RegisterIn(
            email=email, password=PASSWORD, role=role, display_name=display_name, company_name=company_name,
            consent_privacy=True, consent_ai=True,
        ))
        self.stats[f"{role} accounts created"] += 1
        print(f"added {email}")
        return user

    def settle(self, ev: Evaluation, token) -> bool:
        """Run the evaluation like the background task does and make sure it ends `done` (one retry); False if it does not."""
        if token is not None:
            evaluation_service.evaluate(self.db, ev, token)
        for _ in range(2):
            self.db.refresh(ev)
            if ev.status == EvaluationStatus.DONE:
                return True
            token = evaluation_service.claim(self.db, ev, reset_attempts=True)
            self.db.commit()
            if token is None:
                break
            evaluation_service.evaluate(self.db, ev, token)
        self.db.refresh(ev)
        return ev.status == EvaluationStatus.DONE

    # companies and jobs

    def company(self, slug: str) -> User:
        name, intro, talent, projects = COMPANIES[slug]
        recruiter = self.register(f"hr-{slug}@sample.test", f"{name} Recruiting Team"[:50], "company", name)
        company = self.db.get(Company, recruiter.company_id)
        if not company.intro:
            company.intro, company.talent_profile = intro, talent
            self.db.commit()
        have = {p.name for p in company_project_service.list_for_company(self.db, company.id)}
        for project_name, description, techs in projects:
            if project_name not in have:
                company_project_service.create(self.db, recruiter, CompanyProjectIn(name=project_name, description=description, techs=techs))
                self.stats["company projects created"] += 1
        return recruiter

    def job(self, recruiter: User, spec: JobSpec) -> JobPosting | None:
        db = self.db
        job = db.scalar(select(JobPosting).where(JobPosting.company_id == recruiter.company_id, JobPosting.title == spec.title))
        try:
            if job is None:
                job = job_service.create(db, recruiter, JobCreate(
                    title=spec.title, description=spec.description, min_experience_years=spec.min_years, location=spec.location[:100],
                    deadline=spec.deadline,
                ))
                self.stats["jobs created"] += 1
            else:
                self.stats["jobs skipped"] += 1
            if not job.criteria:
                items = spec.criteria
                if items is None:  # the product's own rules analysis of the JD, as the company would get it
                    items = [CriterionIn(name=c.name[:50], description=c.description, category=c.category, weight=c.weight)
                             for c in jd_service.analyze(db, recruiter, job.id).analysis.criteria]
                criteria_service.replace_set(db, job, items)
                self.stats["criteria created"] += len(items)
            if job.status == JobStatus.DRAFT:
                job_service.publish(db, job)
            if spec.closed and job.status == JobStatus.PUBLISHED:
                job_service.close(db, job)
        except AppError as e:
            self.problem(f"job {spec.key} ({spec.title})", e)
            return None
        print(f"job   {spec.key} · {spec.title} ({job.status})")
        return job

    # seekers

    def seeker(self, spec: SeekerSpec) -> User:
        db = self.db
        user = self.register(spec.email, spec.name, "seeker")
        try:
            profile = cv_service.latest(db, user)
        except AppError:  # CV_NOT_FOUND
            profile = cv_service.upload(db, user, f"{spec.cv_id}_synthetic_cv.pdf", cv_pdf(spec.text, self.src))
            self.stats["CVs uploaded"] += 1
        if profile.confirmed_at is None:
            cv_service.update(db, user, profile.id, cv_service.to_profile_data(profile), confirm=True)
            self.stats["CVs confirmed"] += 1
        if preference_service.get_mine(db, user) is None:
            preference_service.replace_mine(db, user, spec.preferences)
            self.stats["preferences saved"] += 1
        return user

    # applications, recommendations, offers, career content

    def apply(self, seeker: User, recruiter: User, job: JobPosting, status: str) -> None:
        db = self.db
        try:
            app, ev, token = application_service.apply(db, seeker, job.id)
        except AppError as e:
            if e.code != "ALREADY_APPLIED":
                return self.problem(f"application {seeker.email} → {job.title}", e)
            self.stats["applications skipped"] += 1
            app = db.scalar(select(Application).where(Application.job_id == job.id, Application.seeker_id == seeker.id))
            ev = evaluation_service.ensure(db, job.id, app.cv_profile_id)
            db.commit()
            token = None
        else:
            self.stats["applications created"] += 1
            if status != "submitted":
                application_service.set_status(db, recruiter, app.id, status)
        if not self.settle(ev, token):
            self.problem(f"evaluation {seeker.email} → {job.title} did not finish ({ev.error[:80]})")

    def recommendations(self, user: User) -> None:
        for _ in range(20):  # only a few evaluations are queued per call; ask again until nothing is queued
            try:
                queued = recommendation_service.recommend(self.db, user, 20).queued
            except AppError as e:
                return self.problem(f"recommendations {user.email}", e)
            if not queued:
                return
            for evaluation_id, token in queued:
                ev = self.db.get(Evaluation, evaluation_id)
                if self.settle(ev, token):
                    self.stats["recommendation evaluations"] += 1
                else:
                    self.problem(f"recommendation evaluation {user.email} → job {ev.job_id} did not finish ({ev.error[:80]})")
        self.problem(f"recommendations {user.email}: evaluations were still being queued after 20 rounds")

    def offer(self, recruiter: User, job: JobPosting, seeker: User, final: str) -> None:
        db = self.db
        if db.scalar(select(TalentOffer.id).where(TalentOffer.company_id == job.company_id, TalentOffer.seeker_id == seeker.id,
                                                 TalentOffer.job_id == job.id)):
            self.stats["offers skipped"] += 1
            return
        try:
            profile = cv_service.latest_confirmed(db, seeker)
            ev = evaluation_service.ensure(db, job.id, profile.id)
            db.commit()
            if not self.settle(ev, None):
                return self.problem(f"offer {job.title} → {seeker.email}: evaluation did not finish")
            offer = offer_service.create(db, recruiter, OfferCreate(
                job_id=job.id, anonymous_id=talent_service.anonymous_id(job.company_id, seeker.id), message=OFFER_MESSAGE))
            if final in ("accepted", "rejected"):
                offer_service.respond(db, seeker, offer.id, final == "accepted")
            elif final == "cancelled":
                offer_service.cancel(db, recruiter, offer.id)
        except AppError as e:
            return self.problem(f"offer {job.title} → {seeker.email} not possible", e)
        self.stats["offers created"] += 1

    def career(self, user: User, job: JobPosting) -> None:
        count = lambda: self.db.scalar(select(func.count()).select_from(CareerContent))  # noqa: E731  (both calls return stored content on a repeat)
        before = count()
        try:
            career_service.roadmap(self.db, user, job.id)
            career_service.interview_questions(self.db, user, job.id)
            self.stats["roadmap + interview question sets" if count() > before else "roadmap + interview question sets skipped"] += 1
        except AppError as e:
            self.problem(f"career content {user.email} → {job.title}", e)


def summary(db) -> None:
    seekers_ = select(User.id).where(User.email.like("seeker-%@sample.test"))
    recruiters = select(User.company_id).where(User.email.like("hr-%@sample.test"))
    apps = list(db.scalars(select(Application).where(Application.seeker_id.in_(seekers_))))
    gates = Counter(gate_service.compute(a.cv_profile, db.get(JobPosting, a.job_id).min_experience_years).status for a in apps)
    # every evaluation of the seeded jobs: applications, recommendations and offers
    evs = Counter(db.scalars(select(Evaluation.status).join(JobPosting, JobPosting.id == Evaluation.job_id).where(JobPosting.company_id.in_(recruiters))))
    jobs = Counter(db.scalars(select(JobPosting.status).where(JobPosting.company_id.in_(recruiters))))
    offers = Counter(db.scalars(select(TalentOffer.status).where(TalentOffer.company_id.in_(recruiters))))
    reconsent = db.scalar(select(func.count()).select_from(User).where(
        User.email.like("%@sample.test"), or_(User.consent_version.is_(None), User.consent_version != settings.CONSENT_VERSION)))
    print("\n== Summary ==")
    print("jobs          ", dict(jobs))
    print("applications  ", dict(Counter(a.status for a in apps)), f"(total {len(apps)})")
    print("required gate ", dict(gates))
    print("evaluations   ", dict(evs))
    print("offers        ", dict(offers))
    print(f"consent       accounts that must re-consent (version is not {settings.CONSENT_VERSION}): {reconsent}"
          + (" (accounts from an older run: reset the database and seed again)" if reconsent else ""))


def print_target(args) -> None:
    print(f"database: {engine.url.render_as_string(hide_password=True)}   AI_MODE=rules   embedding: {os.getenv('EMBEDDING_MODEL', '(app default)')}"
          f"   source: {args.source}")


def dry_run(args, skills) -> None:
    jobs, people = plan_jobs(args, skills), seekers(args.src)
    exists = {"user": set(), "job": set()}
    try:
        with SessionLocal() as db:
            exists["user"] = {e for e in db.scalars(select(func.lower(User.email)))}
            exists["job"] = {(c, t) for c, t in db.execute(select(Company.name, JobPosting.title).where(Company.id == JobPosting.company_id))}
    except Exception as e:  # noqa: BLE001  (a dry run still prints the plan without a database)
        print(f"(database not readable, everything is shown as new: {type(e).__name__})")
    slugs = sorted({j.company for j in jobs})
    print(f"\ncompanies/recruiters: {len(slugs)}  (new: {sum(f'hr-{s}@sample.test' not in exists['user'] for s in slugs)})")
    for s in slugs:
        print(f"  hr-{s}@sample.test · {COMPANIES[s][0]}")
    print(f"\njobs: {len(jobs)}  (new: {sum((COMPANIES[j.company][0], j.title) not in exists['job'] for j in jobs)}, "
          f"closed after publish: {sum(j.closed for j in jobs)}, with a deadline: {sum(j.deadline is not None for j in jobs)})")
    for j in jobs:
        print(f"  {j.key} · {COMPANIES[j.company][0]} · {j.title} · {j.location} · min {j.min_years if j.min_years is not None else '-'}y" + (f" · deadline {j.deadline}" if j.deadline else ""))
        for c in j.criteria or []:
            print(f"      {c.weight:>3} {c.category:<10} {c.name}  [{criteria_service.importance_level(c.weight)}]")
        if j.criteria is None:
            print("      (criteria from the JD analyzer when the job is created)")
    print(f"\nseekers: {len(people)}  (new: {sum(p.email not in exists['user'] for p in people)}, talent pool: {sum(p.preferences.profile_public for p in people)})")
    for p in people:
        print(f"  {p.email} · {p.name} · {p.preferences.locations} {p.preferences.employment_types}" + (" · public" if p.preferences.profile_public else ""))
    keys = {j.key for j in jobs}
    wanted = [a for a in APPLICATIONS if a[1] in keys]
    print(f"\napplications planned: {len(wanted)}  {dict(Counter(a[2] for a in wanted))}")
    print(f"offers planned: {sum(o[0] in keys for o in OFFERS)}  {dict(Counter(o[2] for o in OFFERS if o[0] in keys))} (eligibility is checked when they are sent)")
    print(f"recommendations computed for: {', '.join(RECOMMENDED)}; roadmap + interview questions: {len(CAREER)} sets")
    print("\nDry run: nothing was written.")


def check_source(skills) -> int:
    """No database: test_data/en/ against the originals. Same IDs and rows, same non-text columns, same skills (as the
    app's skill dictionary finds them), same numbers, same stated years of experience, same criterion categories, criteria
    names that fit the 50-character limit, and no Hangul or Vietnamese letters left. Returns the number of problems."""
    from ai.parsing.extract import stated_experience

    en, orig = SOURCES["en"], SOURCES["original"]
    bad: list[str] = []

    def same(label, a, b):
        if a != b:
            bad.append(f"{label}: {a!r} != {b!r}")

    def same_text(label, original_text, english_text):
        # The skill matcher reads an accented Vietnamese word that starts with c ("công", "cơ") as the language C, so the
        # Vietnamese originals carry a spurious "C"; it is ignored here, the English text must not have it either way.
        accented = any(c.isalpha() and not c.isascii() and not "가" <= c <= "힣" for c in original_text)
        skip = {"C"} if accented else set()
        same(f"{label} skills", sorted(set(skills.find_in_text(original_text)) - skip), sorted(set(skills.find_in_text(english_text)) - skip))
        same(f"{label} numbers", sorted(re.findall(r"\d+", original_text)), sorted(re.findall(r"\d+", english_text)))

    def pair(name, translated=()):
        a, b = read_csv(orig.core / name), read_csv(en.core / name)
        same(f"{name} rows", len(a), len(b))
        keep = [k for k in a[0] if k not in translated]
        for x, y in zip(a, b):
            same(f"{name} {x[keep[0]]} columns", [x[k] for k in keep], [y[k] for k in keep])
        return a, b

    cvs, cvs_en = pair("cv_profiles_staging_clean.csv", translated=("candidate_label", "title", "experience", "project", "education",
                                                                    "languages", "work_authorization", "language"))
    for x, y in zip(cvs, cvs_en):
        cid = x["cv_id"]
        a = (orig.core / "cv_texts" / f"{cid}_synthetic_cv.txt").read_text(encoding="utf-8")
        b = (en.core / "cv_texts" / f"{cid}_synthetic_cv.txt").read_text(encoding="utf-8")
        # The old name line ("가상 지원자 KR01") repeated the ID; the new fictional names do not, so that line is left out
        without_name = lambda t: re.sub(r"^(?:Name|이름|Họ tên):.*$", "", t, flags=re.MULTILINE)
        deliberate = cid in NO_YEARS_LINE  # the English CV lacks the years line on purpose (the original must have it)
        a_text = re.sub(r"^(?:경력|Số năm kinh nghiệm):.*$", "", without_name(a), flags=re.MULTILINE) if deliberate else without_name(a)
        same_text(f"{cid} CV", a_text, without_name(b))
        if deliberate:
            same(f"{cid} (deliberately without years) original states its years", stated_experience(a) is not None, True)
        same(f"{cid} stated experience", None if deliberate else (stated_experience(a) or (None,))[0], (stated_experience(b) or (None,))[0])
        name = re.search(r"^Name:\s*(.+?)\s*\(", b, re.MULTILINE)
        same(f"{cid} Name line", name and name.group(1), y["candidate_label"])
    posts, posts_en = pair("job_postings_staging_clean.csv", translated=("company", "title", "location", "employment", "required",
                                                                           "preferred", "deadline"))
    for x, y in zip(posts, posts_en):
        for col in ("required", "preferred", "title"):
            same_text(f"{x['id']} {col}", x[col], y[col])
        same(f"{x['id']} deadline numbers", re.findall(r"\d+", x["deadline"]), re.findall(r"\d+", y["deadline"]))
        same(f"{x['id']} company known", y["company"] in COMPANY_OF, True)
        a = (orig.core / "job_texts_summary" / f"{x['id']}_job_summary.txt").read_text(encoding="utf-8")
        b = (en.core / "job_texts_summary" / f"{x['id']}_job_summary.txt").read_text(encoding="utf-8")
        same_text(f"{x['id']} summary", a, b)
    crit, crit_en = pair("job_criteria_staging.csv", translated=("requirement_text", "criterion_category", "review_status"))
    for x, y in zip(crit, crit_en):
        name, name_en = scrub(x["requirement_text"].strip()), scrub(y["requirement_text"].strip())
        same(f"{x['criterion_id']} category", classify(name, skills), classify(name_en, skills))
        same_text(f"{x['criterion_id']} text", name, name_en)
        same(f"{x['criterion_id']} name fits 50 characters", len(name_en) <= 50, True)
    a, b = read_csv(orig.vn33), read_csv(en.vn33)
    same("vietnam_jobs_33.csv rows", len(a), len(b))
    for x, y in zip(a, b):
        same(f"{x['job_ref']} columns", [v for k, v in x.items() if k not in ("title", "job_text", "content_language")],
             [v for k, v in y.items() if k not in ("title", "job_text", "content_language")])
        same_text(f"{x['job_ref']} title", x["title"], y["title"])
        same_text(f"{x['job_ref']} text", x["job_text"], y["job_text"])
    files = [p for p in (TEST_DATA / "en").rglob("*") if p.is_file()]
    for p in files:
        if left := sorted({c for c in p.read_text(encoding="utf-8-sig") if c.isalpha() and not c.isascii()}):
            bad.append(f"{p.relative_to(TEST_DATA)}: non-English letters left: {''.join(left)}")
    print(f"checked {len(files)} files of test_data/en/ against the originals: "
          f"{len(cvs)} CVs, {len(posts)} jobs, {len(crit)} criteria, {len(a)} Vietnamese-market jobs")
    for line in bad:
        print(f"  MISMATCH {line}")
    print(f"{len(bad)} problem(s)" if bad else "OK: same IDs and rows, same skills, numbers, stated experience and criterion categories; nothing left untranslated"
          f"\n    deliberate differences: no years line in {' and '.join(NO_YEARS_LINE)} (gate REVIEW cases)")
    return len(bad)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the synthetic test data (see the top of this file).")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument("--skip-vn33", action="store_true", help="leave out the 33 extra Vietnamese-market jobs")
    parser.add_argument("--source", choices=sorted(SOURCES), default="en", help="en (default): test_data/en/; original: the untranslated files")
    parser.add_argument("--check-source", action="store_true", help="no database: check test_data/en/ against the originals and exit")
    args = parser.parse_args()
    args.src = SOURCES[args.source]
    skills = ai_runtime.skills()
    if args.check_source:
        sys.exit(1 if check_source(skills) else 0)
    print_target(args)
    if args.dry_run:
        return dry_run(args, skills)

    jobs, people = plan_jobs(args, skills), seekers(args.src)
    db = SessionLocal()
    try:
        s = Seed(db, args.src)
        recruiters = {slug: s.company(slug) for slug in sorted({j.company for j in jobs})}
        posted = {j.key: (recruiters[j.company], s.job(recruiters[j.company], j)) for j in jobs}
        users = {p.cv_id: s.seeker(p) for p in people}
        for cv, key, status in APPLICATIONS:
            if key in posted and posted[key][1] is not None:
                s.apply(users[cv], posted[key][0], posted[key][1], status)
        for cv in RECOMMENDED:
            s.recommendations(users[cv])
        for key, cv, final in OFFERS:
            if key in posted and posted[key][1] is not None:
                s.offer(posted[key][0], posted[key][1], users[cv], final)
        for cv, key in CAREER:
            if key in posted and posted[key][1] is not None:
                s.career(users[cv], posted[key][1])
        print("\n== Created / skipped ==")
        for k, v in sorted(s.stats.items()):
            print(f"{k:<44}{v}")
        summary(db)
        if s.problems:
            print(f"\n{len(s.problems)} step(s) could not be done:")
            for p in s.problems:
                print(f"  - {p}")
        print(f"\nAll accounts (hr-starlight-pay@sample.test ..., seeker-kr01@sample.test ... seeker-vn10@sample.test) use the password: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
