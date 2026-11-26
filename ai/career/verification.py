"""Evidence-grounded recruiter interview questions, never hiring decisions.

Only professionally relevant quotes from the PII-masked and scrubbed CV are used.
The algorithm returns up to three questions and may legitimately return none.
"""
import logging
import re
from dataclasses import dataclass
from typing import Sequence

from pydantic import BaseModel, Field

from ai.career.interview import CriterionInfo, allowed
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.cv_clean import clean_cv
from ai.guardrails.evidence import verify_quotes
from ai.guardrails.sensitive import is_sensitive
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import PROMPT_DIR

log = logging.getLogger(__name__)
MAX_QUESTIONS = 3
_TERMS = re.compile(r"[A-Za-z][A-Za-z0-9.+#-]*|[가-힣]{2,}")
_CLAIM = re.compile(r"개선|최적화|구현|개발|구축|설계|운영|전환|리팩터링|develop|improv|migrat", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|ms|초|건|배|TPS|QPS|명)", re.I)
_STOP = {"경험", "능력", "프로젝트", "관련", "실무", "활용", "개발", "기술", "직무", "업무", "역량", "우대", "필수"}
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|io|dev|net|kr)/\S*", re.IGNORECASE)
_MASK_TOKEN = re.compile(r"\[(?:이름|이메일|전화번호|주민번호|주소|생년월일|링크)\]")


def _escape_tags(text: str) -> str:
    return text.replace("<", "‹").replace(">", "›")


def _safe_output(
    question: str,
    reason: str,
    check_points: Sequence[str],
    blocklists: Sequence[Blocklist],
) -> bool:
    if not allowed(question, reason, check_points, blocklists):
        return False
    return not any(
        is_sensitive(part) or _URL.search(part) or _MASK_TOKEN.search(part)
        for part in (question, reason, *check_points)
    )


@dataclass(frozen=True)
class VerificationQuestion:
    question: str
    criterion_id: int
    criterion_name: str
    cv_quote: str
    reason: str
    check_points: tuple[str, ...]


class _LlmQuestion(BaseModel):
    question: str = Field(min_length=10, max_length=300)
    criterion_id: int
    cv_quote: str = Field(min_length=8, max_length=300)
    reason: str = Field(min_length=5, max_length=220)
    check_points: list[str] = Field(default_factory=list, max_length=3)


class _LlmResult(BaseModel):
    questions: list[_LlmQuestion] = Field(max_length=MAX_QUESTIONS)


def _terms(text: str) -> set[str]:
    return {x.lower() for x in _TERMS.findall(text) if len(x) >= 2 and x.lower() not in _STOP}


def evidence_candidates(masked_cv: str, criteria: Sequence[CriterionInfo]) -> list[tuple[CriterionInfo, str]]:
    """Only scrubbed CV claims, associated with a relevant evaluation criterion."""
    safe = clean_cv(masked_cv)
    if not safe:
        return []
    # clean_cv converts `<`/`>` to `‹`/`›`; recover the exact masked_cv line so `<`/`>` claims still match verbatim
    unescape = {_escape_tags(line.strip()): line.strip() for line in (masked_cv or "").splitlines() if line.strip()}
    ranked: list[tuple[int, CriterionInfo, str]] = []
    for raw in safe.text.splitlines():
        cleaned = raw.strip()
        quote = unescape.get(cleaned, cleaned)
        if not 12 <= len(quote) <= 300 or not _CLAIM.search(quote):
            continue
        if quote not in masked_cv and not verify_quotes([quote], masked_cv):
            continue
        words = _terms(quote)
        for criterion in criteria:
            common = words & _terms(criterion.name + " " + criterion.description)
            if not common and criterion.category != "project":
                continue
            # A quantified result WITH explicit ownership is relatively well explained.
            if _NUMBER.search(quote) and re.search(r"직접|담당|제가|본인", quote):
                continue
            priority = len(common) * 10 + (5 if "개선" in quote or "최적화" in quote else 0)
            ranked.append((priority, criterion, quote))
    ranked.sort(key=lambda x: -x[0])
    found: list[tuple[CriterionInfo, str]] = []
    seen: set[tuple[int, str]] = set()
    for _, c, quote in ranked:
        key = (c.id, quote)
        if key not in seen:
            found.append((c, quote))
            seen.add(key)
        if len(found) >= 8:
            break
    return found


def _rules(items: list[tuple[CriterionInfo, str]]) -> list[VerificationQuestion]:
    questions: list[VerificationQuestion] = []
    seen_questions: set[str] = set()
    seen_quotes: set[str] = set()
    for criterion, quote in items:
        if any(word in quote for word in ("개선", "최적화", "성능")):
            question = f"{criterion.name} 관련 경험의 개선 전후 성능을 어떤 지표와 도구로 측정했으며, 본인이 직접 수정한 부분은 어디인가요?"
            reason = "성과의 측정 방식과 개인 기여 범위에 대한 근거가 부족합니다."
            checks = ("측정 지표와 비교 환경", "직접 담당한 코드", "성과 재현 방법")
        else:
            question = f"{criterion.name} 관련 경험에서 본인이 담당한 부분과 실제 구현 과정을 설명해 주세요."
            reason = "구체적인 역할 및 구현 과정은 이력서만으로 확인하기 어렵습니다."
            checks = ("개인 담당 범위", "구현 및 검증 과정", "문제와 해결 근거")
        if question in seen_questions or quote in seen_quotes:
            continue
        seen_questions.add(question)
        seen_quotes.add(quote)
        questions.append(VerificationQuestion(question, criterion.id, criterion.name, quote, reason, checks))
        if len(questions) >= MAX_QUESTIONS:
            break
    return questions


def generate_questions(
    job_title: str,
    job_description: str,
    criteria: Sequence[CriterionInfo],
    masked_cv: str,
    blocklists: Sequence[Blocklist],
    llm: LLMClient | None,
) -> tuple[list[VerificationQuestion], str]:
    candidates = evidence_candidates(masked_cv, criteria)
    if not candidates:
        return [], "rules"
    quote_set = {quote for _, quote in candidates}
    escaped_to_quote = {_escape_tags(quote): quote for quote in quote_set}
    valid_criteria = {c.id: c for c in criteria}
    if llm is not None:
        system = (PROMPT_DIR / "cv_verification.md").read_text(encoding="utf-8")
        criteria_lines = "\n".join(
            f"{c.id} | {_escape_tags(c.name)} | {c.category} | {_escape_tags(c.description)}"
            for c in criteria
        )
        excerpts = "\n".join(
            f"{c.id} | {_escape_tags(c.name)} | {_escape_tags(c.description)} | {_escape_tags(quote)}"
            for c, quote in candidates
        )
        user_prompt = (
            f"<job_title>{_escape_tags(job_title)}</job_title>\n"
            f"<jd>\n{_escape_tags(job_description[:4000])}\n</jd>\n"
            f"<criteria>\n{criteria_lines}\n</criteria>\n"
            f"이력서 인용문:\n<cv_quotes>\n{excerpts}\n</cv_quotes>"
        )
        try:
            output = llm.complete_json(system, user_prompt, _LlmResult, max_tokens=1500)
            valid: list[VerificationQuestion] = []
            seen_questions: set[str] = set()
            for q in output.questions:
                criterion = valid_criteria.get(q.criterion_id)
                quote = escaped_to_quote.get(q.cv_quote, q.cv_quote)
                if criterion is None or quote not in quote_set:
                    continue
                if not verify_quotes([quote], masked_cv):
                    continue
                if q.question in seen_questions or not _safe_output(q.question, q.reason, q.check_points, blocklists):
                    continue
                seen_questions.add(q.question)
                valid.append(
                    VerificationQuestion(q.question, criterion.id, criterion.name, quote, q.reason, tuple(q.check_points))
                )
            if valid:
                return valid[:MAX_QUESTIONS], f"llm:{llm.model}"
        except LLMError:
            # Never log the model response, quoted CV text, or other applicant data.
            log.warning("Recruiter question generation failed; falling back to rules")
    return [
        q
        for q in _rules(candidates)
        if _safe_output(q.question, q.reason, q.check_points, blocklists)
    ][:MAX_QUESTIONS], "rules"
