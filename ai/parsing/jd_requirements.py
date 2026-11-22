"""Source-grounded requirement extraction for the no-LLM JD fallback."""
import re
from ai.parsing.profile import JdRequirement, SuggestedCriterion

BULLET = re.compile(r"^\s*(?:[-*•▪■□●○]|[0-9]+[.)])\s*")
GROUPS = {
    "required": ("자격요건", "자격 요건", "지원자격", "지원 자격", "필수요건", "필수 요건", "requirements", "qualifications"),
    "preferred": ("우대사항", "우대 사항", "우대조건", "우대 조건", "preferred", "nice to have"),
    "responsibility": ("담당업무", "담당 업무", "주요업무", "주요 업무", "responsibilities"),
    "ignore": ("복리후생", "혜택 및 복지", "전형절차", "유의사항", "모집요강", "근무조건", "회사소개", "benefits"),
}
HEADINGS = {name.lower(): kind for kind, names in GROUPS.items() for name in names}
STRIP = re.compile(r"^[\s#*■□●○◆◇▶▷•\-\[\]【】<>()]+|[\s:：\[\]【】<>()]+$")
OR_FRAMEWORK = re.compile(r"\b(Vue|React)\s*(?:또는|or|/|혹은)\s*(React|Vue)\b", re.I)


def extract_requirements(text: str) -> list[JdRequirement]:
    """Read complete bullet statements without turning alternatives into AND."""
    found: list[JdRequirement] = []
    kind: str | None = None
    pending: list[str] = []

    def flush() -> None:
        if pending and kind in ("required", "preferred", "responsibility"):
            source = " ".join(pending).strip()[:500]
            match = OR_FRAMEWORK.search(source)
            alternatives = [match.group(1), match.group(2)] if match else []
            if source and not any(r.kind == kind and r.source == source for r in found):
                found.append(JdRequirement(kind=kind, text=source, source=source, alternatives=alternatives))
        pending.clear()

    for raw in text.splitlines():
        line = raw.strip()
        heading = HEADINGS.get(STRIP.sub("", line).strip().lower())
        if heading is not None:
            flush()
            kind = heading
        elif not line:
            flush()
        elif kind in ("required", "preferred", "responsibility"):
            if BULLET.match(raw):
                flush()
                pending.append(BULLET.sub("", line).strip())
            elif pending:
                pending.append(line)
    flush()
    return found[:60]


def label_and_category(source: str) -> tuple[str, str]:
    s = source.lower()
    if ("vue" in s or "react" in s) and "typescript" in s:
        return "Vue/React·TypeScript 개발", "skill"
    if "api" in s or "비동기" in s or "상태 관리" in s:
        return "API·비동기·상태 관리", "skill"
    if "ai" in s and ("코딩" in s or "도구" in s or "생성" in s):
        return "AI 코딩 도구 활용·검증", "skill"
    if "요구사항" in s or "스펙" in s:
        return "요구사항·스펙 관리", "project"
    if "테스트" in s or "브라우저" in s or "실패 상황" in s:
        return "테스트·문제 해결", "project"
    if "nuxt" in s or "vue 2" in s or "vue 3" in s:
        return "Vue/Nuxt 개발·전환", "skill"
    if "기획자" in s or "디자이너" in s or "다른 직군" in s:
        return "직군 간 협업", "project"
    if "자동화" in s or "코드 리뷰" in s:
        return "개발 품질·자동화", "project"
    if "프로젝트" in s:
        return "프로젝트 수행 경험", "project"
    if "경력" in s:
        return "직무 관련 경력", "experience"
    if "자격증" in s:
        return "관련 자격증", "certificate"
    if "학력" in s or "전공" in s:
        return "관련 전공", "education"
    return (re.sub(r"\s+", " ", source).strip(" .")[:32] or "직무 역량"), "other"


def criteria_from_requirements(requirements: list[JdRequirement]) -> list[SuggestedCriterion]:
    """Consolidate repeated labels; keep required items before preferred ones."""
    items: dict[str, tuple[SuggestedCriterion, int]] = {}
    priority = {"required": 3, "responsibility": 2, "preferred": 1}
    for requirement in requirements:
        label, category = label_and_category(requirement.text)
        weight = priority[requirement.kind]
        if label in items and items[label][1] >= weight:
            continue
        reason = {"required": "공고의 필수 조건", "preferred": "공고의 우대 조건",
                  "responsibility": "담당업무에 명시됨"}[requirement.kind]
        items[label] = (SuggestedCriterion(
            name=label[:50], description=requirement.text[:500], category=category, weight=1,
            source=requirement.source, reason=reason,
        ), weight)
    selected = sorted(items.values(), key=lambda item: -item[1])[:10]
    if not selected:
        return []
    total = sum(w for _, w in selected)
    weights = [max(1, round(w * 100 / total)) for _, w in selected]
    weights[0] += 100 - sum(weights)
    return [item.model_copy(update={"weight": weight}) for (item, _), weight in zip(selected, weights, strict=True)]
