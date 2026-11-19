"""Rules-mode interviewing: rubric points, answer analysis and the fixed Korean lines (docs/DECISIONS.md D51, D52, D54).

Everything here is deterministic keyword work on masked text. It is the whole interview in `AI_MODE=rules`, and the
fallback when a model call fails or times out (D54), so it never needs a key, a network or a model. Its judgement is
crude on purpose: it checks for cue words, not for correctness, and the feedback says what it found, nothing more.
"""
import math
import re

from ai.embedding.skills import SkillDictionary
from ai.interview.guards import verified_quotes
from ai.interview.sensitive import for_model_block, is_sensitive
from ai.interview.types import (
    LEVEL_RANK,
    MAX_RUBRIC_POINTS,
    MIN_ANSWER_CHARS,
    MIN_ANSWER_WORDS,
    MIN_RUBRIC_POINTS,
    AnswerType,
    PlanItem,
    PointLevel,
    RubricPoint,
    TurnAnalysis,
)
from ai.scoring.retrieval import keywords

# ── Fixed lines (Korean, spoken). None contains a verdict word, a URL or a placeholder: tests screen every one. ──

CLARIFY_TEXT = "죄송합니다, 잘 듣지 못했습니다. 한 번 더 말씀해 주시겠어요?"  # nothing was said
ELABORATE_TEXT = "조금 더 자세히 말씀해 주시겠어요? 아시는 만큼 편하게 말씀해 주세요."  # something was said, but very little
NUDGE_TEXT = "천천히 생각하셔도 됩니다. 준비되시면 말씀해 주세요."
BRIDGE_TEXT = "답변 감사합니다. 다음 질문입니다."
SKIP_BRIDGE_TEXT = "괜찮습니다. 다음 질문으로 넘어가겠습니다."
GENERIC_FOLLOW_UP = "방금 말씀하신 내용에서 조금 더 구체적인 사례를 들어 설명해 주시겠어요?"
GENERIC_REPHRASE = "조금 쉽게 다시 여쭤볼게요. 알고 계신 만큼 편하게 말씀해 주세요."
GENERIC_REDIRECT = "질문은 방금 드린 내용에 관한 것이었습니다. 관련된 경험이나 생각을 말씀해 주시겠어요?"
CLOSINGS = {
    "plan_exhausted": "준비한 질문은 여기까지입니다. 답변해 주셔서 감사합니다. 잠시 후 연습 피드백이 준비됩니다.",
    "time": "준비된 시간이 다 되어 여기서 마치겠습니다. 참여해 주셔서 감사합니다. 잠시 후 연습 피드백이 준비됩니다.",
    "empty_plan": "오늘은 준비된 질문이 없어 여기서 마치겠습니다. 참여해 주셔서 감사합니다.",
}


def closing_text(reason: str) -> str:
    return CLOSINGS.get(reason, CLOSINGS["plan_exhausted"])


def follow_up_text(point: RubricPoint) -> str:
    return f"{point.text}에 대해 조금 더 자세히 말씀해 주시겠어요?"


def rephrase_text(item_name: str | None, kind: str) -> str:
    if item_name:
        return f"조금 쉽게 다시 여쭤볼게요. {item_name}에 대해 알고 계신 내용이나 경험을 편하게 말씀해 주세요."
    if kind == "behavioral":
        return "조금 쉽게 다시 여쭤볼게요. 비슷한 경험이 있다면 상황과 본인이 한 일을 편하게 말씀해 주세요."
    return "조금 쉽게 다시 여쭤볼게요. 이력서에 적으신 이 경험에서 맡으신 역할을 편하게 말씀해 주세요."


def redirect_text(item_name: str | None) -> str:
    if item_name:
        return f"질문은 '{item_name}'에 관한 것이었습니다. 관련된 경험이나 생각을 말씀해 주시겠어요?"
    return GENERIC_REDIRECT


def fallback_question(name: str) -> str:
    """A neutral question for a criterion that has none in the question bank (or whose bank question was screened out)."""
    return f"'{name}'와(과) 관련된 경험이나 지식을 구체적인 사례와 함께 설명해 주세요."


def warmup_question(quote: str) -> str:
    # No particle after the quote: which one is right depends on the quote's last syllable
    return f"이력서에 적으신 '{quote}' 경험에서 맡으신 역할과 가장 기억에 남는 점을 말씀해 주세요."


# ── Rubric points ──

# Generic points per category: (text with {name}, cue words, hits needed). One cue hit is only "partial": the cues are
# common words, so a single one proves little.
_GENERIC: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "skill": (
        ("{name}의 핵심 개념과 동작 방식", ("개념", "원리", "동작", "구조", "정의", "의미", "역할", "이란", "라고")),
        ("{name}을(를) 실제로 사용한 사례", ("사용", "적용", "구현", "개발", "프로젝트", "실무", "경험", "사례", "만들", "구축")),
        ("{name}의 장단점이나 주의할 점", ("장점", "단점", "주의", "한계", "대신", "반면", "문제", "이슈", "고려", "trade")),
    ),
    "experience": (
        ("맡은 역할과 당시 상황", ("역할", "담당", "맡", "팀", "상황", "배경", "목표", "프로젝트")),
        ("직접 한 일과 해결 과정", ("구현", "설계", "개발", "해결", "개선", "도입", "진행", "작업", "수행", "분석")),
        ("결과와 배운 점", ("결과", "성과", "개선", "감소", "증가", "향상", "단축", "배웠", "배운", "달성", "%")),
    ),
    "education": (
        ("전공 내용 중 직무와 연결되는 부분", ("전공", "수업", "과목", "배운", "학습", "연구", "졸업", "과제")),
        ("관련 프로젝트나 과제 경험", ("프로젝트", "실습", "적용", "활용", "과제", "경험")),
    ),
    "certificate": (
        ("준비하며 익힌 지식", ("공부", "준비", "학습", "개념", "배운", "익힌")),
        ("그 지식을 직무에 적용하는 방법", ("적용", "활용", "실무", "프로젝트", "업무")),
    ),
    "other": (
        ("당시의 상황", ("상황", "때", "당시", "경우", "팀", "프로젝트")),
        ("본인이 한 행동", ("제가", "했습니다", "했어요", "해결", "조율", "설득", "제안", "노력", "진행")),
        ("결과와 배운 점", ("결과", "그래서", "배웠", "배운", "개선", "성과", "깨달")),
    ),
}
_GENERIC["project"] = _GENERIC["experience"]
_CLAUSE_SPLIT = re.compile(r"[\n;·/]|,\s*|\s+(?:및|그리고|또는)\s+|(?<=[다요음함])\.\s+")
_ENDINGS = re.compile(r"(하고|하는|하며|하여|하면|하기|했던|했고|했다|한다|합니다|해서|되는|되어|적인|에서|으로|까지|부터|처럼|보다|라는|들)$")
_HANGUL = re.compile(r"[가-힣]")
_MAX_CLAUSE_CHARS = 60


def _stem(word: str) -> str:
    """A cue that still matches an inflected answer: 설계하고 -> 설계 (so 설계했습니다 counts)."""
    if _HANGUL.search(word) and len(word) >= 3:
        stem = _ENDINGS.sub("", word)
        if len(stem) >= 2:
            return stem
    return word


def cues(text: str, skills: SkillDictionary | None = None, limit: int = 6) -> tuple[str, ...]:
    """Lower-case cue words of a short text: its keywords as stems, plus the dictionary skills it names and their
    one-word aliases, so a spoken "자바요" or "스프링으로" counts as content for a Java or Spring question."""
    out: list[str] = []
    for word in keywords(text):
        word = _stem(word)
        if word.isdigit() or len(word) < 2 or word in out:
            continue
        out.append(word)
    if skills is not None:
        for skill in skills.find_in_text(text):
            if skill.lower() not in out:
                out.append(skill.lower())
            for alias, canonical in skills.alias_to_skill.items():
                if canonical == skill and " " not in alias and len(alias) >= 2 and alias.lower() not in out:
                    out.append(alias.lower())
    return tuple(out[:limit])


def min_hits(n: int) -> int:
    """Cue hits needed to count a point with `n` cues as demonstrated."""
    return min(2, max(1, math.ceil(n / 2)))


def make_rubric(name: str, category: str, description: str = "", skills: SkillDictionary | None = None) -> tuple[RubricPoint, ...]:
    """2 to 4 expectations for one item: up to three clauses of the criterion's own description, topped up with generic
    points of its category. They are AI-generated expectations, not company requirements (`RubricPoint.source`)."""
    points: list[RubricPoint] = []
    seen: set[str] = set()
    for clause in _CLAUSE_SPLIT.split(for_model_block(description)):  # what touches age, gender or military service is cut first
        clause = clause.strip().rstrip(".").strip()
        key = re.sub(r"\W+", "", clause.lower())
        if len(clause) < 3 or len(clause) > _MAX_CLAUSE_CHARS or key in seen or is_sensitive(clause):
            continue
        found = cues(clause, skills)
        if not found:
            continue
        seen.add(key)
        points.append(RubricPoint(f"p{len(points) + 1}", clause, found, min_hits(len(found))))
        if len(points) == 3:
            break
    if len(points) < MIN_RUBRIC_POINTS:  # too little of its own: top up to three with generic points of the category
        for text, words in _GENERIC.get(category, _GENERIC["other"]):
            if len(points) >= 3:
                break
            points.append(RubricPoint(f"p{len(points) + 1}", text.format(name=name), words, 2))
    return tuple(points[:MAX_RUBRIC_POINTS])


def topic_keywords(*texts: str, skills: SkillDictionary | None = None) -> tuple[str, ...]:
    """What an on-topic answer is about, from the criterion's name and description (or the CV line behind a warm-up).
    Not from the question text: its boilerplate ("설명해 주세요") would make any answer look on topic."""
    out: list[str] = []
    for text in texts:
        for word in cues(text or "", skills, limit=8):
            if word not in out:
                out.append(word)
    return tuple(out)


# ── Answer analysis ──

_FILLERS = frozenset({"음", "으음", "음음", "어", "어어", "아", "아아", "에", "그", "저", "흠", "그게", "저기", "뭐", "뭐랄까", "um", "uh", "hmm"})
_REPEAT = re.compile(
    r"다시\s*(?:한\s*번)?\s*(?:말씀|질문|읽어|들려|얘기|이야기)|한\s*번\s*더|질문(?:이|을)?\s*(?:뭐|무엇|무슨|다시)|못\s*들었|"
    r"뭐라고(?:\s*(?:요|하셨|하신|말씀)|[?？]|$)|"  # "뭐라고요?" asks to repeat; "뭐라고 해야 할지" is a hesitation
    r"\brepeat\b|say (?:that )?again|once more|one more time|pardon",
    re.IGNORECASE,
)
_CLARIFY = re.compile(
    r"무슨\s*(?:뜻|의미|말)|어떤\s*(?:의미|뜻)|이해(?:가|를)?\s*(?:잘\s*)?(?:안|못)|좀\s*더\s*쉽게|"
    r"what do you mean|don'?t understand|clarify",
    re.IGNORECASE,
)
_DONT_KNOW = re.compile(
    r"모르겠|모릅니다|몰라요|잘\s*모르|기억(?:이|은)?\s*(?:잘\s*)?(?:안|나지)|생각(?:이)?\s*(?:안|나지)|(?:해본|써본|사용해본)\s*(?:적|경험)?(?:이|은)?\s*없|"
    r"i don'?t know|no idea|not sure|don'?t remember|never (?:used|done)",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[\W_]+")
_CLAUSE_END = re.compile(r"[.!?。]+\s*|(?<=[다요죠])\s+")
_REQUEST_MAX_CHARS = 40  # a request to repeat is short; a long answer that happens to say "다시" is an answer
_DONT_KNOW_REST_CHARS = 25  # a "don't know" followed by more than this is a partial answer, not a refusal
_MAX_QUOTE = 120


def _content(text: str) -> str:
    return _PUNCT.sub("", text)


def _words(text: str) -> list[str]:
    return [w for w in (_PUNCT.sub("", t.lower()) for t in text.split()) if w and w not in _FILLERS]


def _hit(cue: str, text: str) -> bool:
    if re.fullmatch(r"[a-z0-9+#.\-]+", cue):  # Latin cue: a whole word, so "java" does not match "javascript"
        return re.search(rf"(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])", text) is not None
    return cue in text


def _level(point: RubricPoint, text: str) -> PointLevel:
    matched = sum(_hit(c, text) for c in point.keywords)
    if matched >= point.min_hits:
        return "demonstrated"
    return "partial" if matched >= 1 else "not_shown"


def _quote_for(point: RubricPoint, answer: str) -> str | None:
    for clause in _CLAUSE_END.split(answer):
        clause = clause.strip()
        if 4 <= len(clause) <= _MAX_QUOTE and not is_sensitive(clause) and any(_hit(c, clause.lower()) for c in point.keywords):
            return clause
    return None


def analyze(answer: str, item: PlanItem) -> TurnAnalysis:
    """Classify one masked answer and mark each rubric point of `item`. Order: empty, a request, "don't know", too short,
    off topic, then coverage.

    Length is a soft heuristic (MIN_ANSWER_CHARS, MIN_ANSWER_WORDS), never a verdict: a short answer that contains a cue
    of the question's topic ("멱등성이요") is analysed like any other. Only a short answer with no content cue at all is
    "too short"."""
    text = answer.lower()
    words = _words(answer)
    short = len(_content(answer)) <= _REQUEST_MAX_CHARS
    if not words:
        return TurnAnalysis(AnswerType.EMPTY)
    if short and _REPEAT.search(text):
        return TurnAnalysis(AnswerType.REPEAT_REQUEST)
    if short and _CLARIFY.search(text):
        return TurnAnalysis(AnswerType.CLARIFICATION_REQUEST)
    if (m := _DONT_KNOW.search(text)) and len(_content(text[: m.start()] + text[m.end() :])) <= _DONT_KNOW_REST_CHARS:
        return TurnAnalysis(AnswerType.DONT_KNOW)
    topic = [*item.topic_keywords, *(c for p in item.rubric for c in p.keywords)]
    on_topic = any(_hit(c, text) for c in topic)
    if (len(_content(answer)) < MIN_ANSWER_CHARS or len(words) < MIN_ANSWER_WORDS) and not on_topic:
        return TurnAnalysis(AnswerType.TOO_SHORT)
    levels = {p.id: _level(p, text) for p in item.rubric}
    if item.kind != "behavioral" and topic and not on_topic:
        return TurnAnalysis(AnswerType.OFF_TOPIC)
    quotes = []
    for point in item.rubric:
        if levels[point.id] != "not_shown" and (quote := _quote_for(point, answer)) and quote not in quotes:
            quotes.append(quote)
    answer_type = AnswerType.ANSWERED if all(level != "not_shown" for level in levels.values()) else AnswerType.PARTIAL
    return TurnAnalysis(answer_type, levels, verified_quotes(quotes, answer))


def best_levels(*level_maps: dict[str, PointLevel]) -> dict[str, PointLevel]:
    """Per rubric point, the strongest level seen over several answers."""
    out: dict[str, PointLevel] = {}
    for levels in level_maps:
        for pid, level in levels.items():
            if pid not in out or LEVEL_RANK[level] > LEVEL_RANK[out[pid]]:
                out[pid] = level
    return out
