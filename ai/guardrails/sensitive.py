"""Age, gender and military-service information in text, best effort (docs/DECISIONS.md D59, D61, D62, D85).

A leaf module: it imports nothing of the project, so the practice interview (`ai/interview/`) and any other feature that
uses the CV cleaner (`cv_clean.py`) apply the same vocabulary. `ai/interview/sensitive.py` re-exports it and adds what
only the interview uses (`for_model`, `SafeText`).

What it is: a list of terms, applied sentence by sentence and then clause by clause, so a mixed sentence ("27살이고 Java로
API를 개발했습니다") keeps its professional clause. What it is not: understanding. A disclosure that uses none of the
terms passes (docs/PROJECT_DOCUMENTATION.md §6.2 lists what is known to pass). Over-blocking is accepted: the terms skip
common compounds that are not about a person (3세대, 세션, 나이브 베이즈, 나이스, 제대로, 전역 변수, 연령대별, 사단법인).
"""
import re

_NOT_AGE = "대|션|계|기|상|금|탁|펴|아|림|리|려|짝"  # 3세대 (generation), 세션 (session), 살펴 (look into), …
_AGE_WORD = "스무|스물|서른|마흔|쉰|예순|일흔|여든|아흔"
_AGE_UNIT = "한|두|세|네|다섯|여섯|일곱|여덟|아홉"
_DECADES = "teens|twenties|thirties|forties|fifties|sixties"

# Age (digits, spoken numerals, decades, birth year, birth date), gender (Korean and English, also the "Sex:" form label and
# words that state it: mother, wife, Mr.) and military service (status, branch, rank, unit, specialty, discharge, exemption,
# alternative service, English terms).
_SENSITIVE = re.compile(
    # age: digits + 세/살, birth year, "27 years old"
    rf"\d{{1,2}}\s*(?:세|살)(?!{_NOT_AGE})|\d{{2,4}}\s*년\s*생|\d{{1,2}}[\s-]*year[\s-]*old"
    r"|나이(?!브|스)|연령(?!대)|연세|\bage\b|\byears?\s*old\b|\bborn\b|생년월일|출생|태어|\d{2}\s*학번"
    r"|\bdate\s*of\s*birth\b|\bbirth\s*date\b|\bd\.?o\.?b\b"
    r"|생일(?!\s*(?:알림|쿠폰|이벤트|축하|선물|메시지|기능))|\bbirthday\b(?!\s+(?:coupon|reminder|notification|email|promotion|campaign|gift|message|feature))"
    # age: spoken numerals (스물일곱 살, 서른이에요, 스물일곱입니다) and decades (20대 후반)
    rf"|(?:{_AGE_WORD})(?:{_AGE_UNIT})?\s*(?:살|이에요|입니다|예요|이고|이며|이라|이라서|인데|밖에|즈음|넘)"
    rf"|(?:이십|삼십|사십|오십|육십)[일이삼사오육칠팔구]?\s*세(?!{_NOT_AGE})"  # 이십칠 세 (not 오세요)
    r"|[1-6]0\s*대\s*(?:초|중|후)\s*반"
    r"|[1-6]0\s*대(?=\s*(?:입니다|이에요|예요|이고|이며|인데|이라|이었|였|때|선호|우대|이하|이상|위주|에\s*(?:입사|이직|취업|창업)|의\s*(?:남|여|청년|직장인|지원자|개발자)))"
    r"|만\s*\d{1,2}\s*(?:이에요|입니다|예요|이고|이라서|이며)|\b\d{2}\s*(?:이에요|입니다|예요)"
    rf"|\b(?:early|mid|late)[\s-]*(?:{_DECADES}|\d0s)\b|\bmy\s+(?:{_DECADES})\b|\b\d{{2}}\s*(?:yo|y/o|yrs?\s*old)\b|\baged?\s*\d{{2}}\b"
    r"|\b(?:twenty|thirty|forty|fifty|sixty)[\s-]*(?:one|two|three|four|five|six|seven|eight|nine)?[\s-]*(?:something|yo)\b"
    r"|\bi(?:'|’)?\s*a?m\s+\d{2}\b|\bturn(?:ed|ing)?\s+\d{2}\b"
    # gender
    r"|성별|남성|여성|남자|여자|남녀|여학생|남학생|(?<![가-힣])아내|남편|엄마|아빠|임신|출산|육아휴직|\bsex\s*[:：]"
    r"|\b(?:male|female|gender|woman|women|mother|father|mom|dad|wife|husband|mrs?|ms|miss|girls?|boys?|lady|ladies)\b"
    # military: status, service, discharge, exemption
    r"|병역|군필|미필|군\s*복무|군복무|복무|군\s*생활|군\s*휴학|군\s*경력|군대|군인|군번|군종|병과|입대|입영|예비역|현역병|징병|보충역|소집해제|보훈"
    r"|사회복무|공익근무|공익\s*(?:판정|요원|으로)|산업기능요원|전문연구요원|특례복무|상근예비역|의무경찰|(?<![가-힣])의경"
    r"|(?:병역|군)\s*면제|면제\s*(?:판정|를\s*받|받았|처분)|신체\s*등급|[1-7]급\s*(?:판정|현역|보충|공익|면제)"
    r"|만기\s*(?:전역|제대)|제대(?!로)|전역(?!\s*(?:변수|상태|스코프|함수|설정|캐시|검색|락|예외|에러|객체|적))"
    # military: branch, rank, unit, specialty
    r"|병장|이등병|일병|상병|이병|장병|훈련병|육군|해군|공군|해병|사단(?!법인)|훈련소|자대|학군단|카투사|학사장교|장교|부사관"
    r"|통신병|보병|포병|공병|기갑|취사병|운전병|행정병|정비병|의무병|수송병|전투병|경계병|분대장|소대장|중대장|대대장|소대|분대"
    # military: English
    r"|\b(?:military|army|navy|veteran|soldier|infantry|artillery|barracks|marines?|reservist|conscript\w*|enlist\w*|drafted"
    r"|sergeant|corporal|lieutenant|ROK|ROTC|KATUSA)\b|\bair\s*force\b|\bsignal\s*corps\b|\bboot\s*camp\b|\breserve\s+forces?\b"
    r"|national\s*service|mandatory\s*service|honorabl\w+\s+discharge",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?。])\s+|\n+|(?<=[다요죠])\s+")
_CLAUSE = re.compile(r"(?<=[고며서면])\s+|(?<=는데)\s+|(?<=지만)\s+|[,，;；]\s*|\s+(?:but|while|because)\s+", re.IGNORECASE)  # not "and": it also joins "Kotlin and Java"
_GROUP = re.compile(r"\([^()]*\)|（[^（）]*）|\[[^\[\]]*\]")
_BAR = re.compile(r"\s+\|\s+")
_MAX_PASSES = 4


def is_sensitive(text: str) -> bool:
    """True when the text states or asks about age, gender or military service (by the vocabulary above)."""
    return _SENSITIVE.search(text or "") is not None


def _strip_once(text: str) -> str:
    kept: list[str] = []
    for sentence in _SENTENCE.split(text or ""):
        if not sentence.strip():
            continue
        if not is_sensitive(sentence):
            kept.append(sentence)
            continue
        # A flagged parenthesis goes first ("백엔드 개발자 (20대 선호)" -> "백엔드 개발자")
        trimmed = " ".join(_GROUP.sub(lambda m: "" if is_sensitive(m.group(0)) else m.group(0), sentence).split())
        if trimmed and not is_sensitive(trimmed):
            kept.append(trimmed)
            continue
        # A mixed sentence keeps its other clauses ("27살이고 Java로 API를 개발했습니다" -> the second one)
        rest = " ".join(c for c in _CLAUSE.split(trimmed) if c and c.strip() and not is_sensitive(c))
        if rest.strip() and not is_sensitive(rest):
            kept.append(rest)
    return " ".join(kept)


def strip_sensitive(text: str) -> str:
    """The text without the sentences, or the clauses of a mixed sentence, that touch these topics (empty when nothing is
    left). Repeated until stable, because joining what is left must not make a new match across the seam."""
    out = text or ""
    for _ in range(_MAX_PASSES):
        new = _strip_once(out)
        if new == out:
            return "" if is_sensitive(new) else new
        out = new
    return "" if is_sensitive(out) else out


def cut_sensitive(line: str) -> str:
    """One CV line without what is about these topics, keeping the professional rest. A parenthesis that touches them is
    cut ("… 학사 2015.03 ~ 2021.02 (군 휴학 2017~2019)" keeps school and dates); of a ` | ` segment that still does, only
    what is not about them is kept (a segment of one clause goes whole). Empty when nothing is left."""
    cut = _GROUP.sub(lambda m: "" if is_sensitive(m.group(0)) else m.group(0), line or "")
    parts = []
    for part in _BAR.split(cut):
        part = " ".join(part.split())
        if part and is_sensitive(part):
            part = strip_sensitive(part)
        if part:
            parts.append(part)
    out = " | ".join(parts)
    return "" if is_sensitive(out) else out  # nothing is returned that the vocabulary still flags
