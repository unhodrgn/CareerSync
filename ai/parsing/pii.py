"""Mask personal data before any LLM call (CLAUDE.md AI rule 3: the LLM sees only masked text).

The masked text is also what evidence quotes are checked against, so evidence never carries PII.

Names are masked on a best-effort basis (docs/DECISIONS.md D39): the seeker's own name (the account name and its
spellings: spaces between syllables, no diacritics, family name first or last, romanized Korean), the value of a
labeled line (이름/성명/Name; 추천인/담당자/Reference for other people) and a name-shaped line at the top of the CV.
Every name found is masked wherever it appears. A given name or a surname alone is never masked, and neither are
school or company names.
"""
import re
import unicodedata
from dataclasses import dataclass
from itertools import product

from ai.embedding.skills import SkillDictionary
from ai.parsing.sections import heading_key

_PATTERNS: tuple[tuple[str, str, re.Pattern], ...] = (
    ("email", "[이메일]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("url", "[링크]", re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)),
    # Resident registration number (주민등록번호) before phone, since both are digit runs
    ("rrn", "[주민번호]", re.compile(r"\b\d{6}\s*-\s*[1-4]\d{6}\b")),
    ("phone", "[전화번호]", re.compile(r"(?:\+82[\s-]?)?0\d{1,2}[\s.-]?\d{3,4}[\s.-]?\d{4}\b")),
    # Birth date lines (생년월일 / 출생) keep the label but drop the date; the end must not eat the
    # line break, or the next line (often a section heading such as 경력) merges into this one
    ("birth", "[생년월일]", re.compile(r"(?<=생년월일)\s*[:：]?\s*\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}(?:[ \t]*일)?")),
    ("address", "[주소]", re.compile(r"(?<=주소)\s*[:：]?\s*[^\n]+")),
)
NAME_TOKEN = "[이름]"

# ── Names: tables ──

# Korean surnames and their common romanizations; compound surnames first
_SURNAMES: dict[str, tuple[str, ...]] = {
    "남궁": ("namgoong", "namgung", "namkung"), "제갈": ("jegal", "chegal"), "선우": ("sunwoo", "seonu", "sunwu"),
    "황보": ("hwangbo",), "독고": ("dokgo", "tokko"), "사공": ("sagong",), "서문": ("seomun",),
    "김": ("kim", "gim"), "이": ("lee", "yi", "rhee", "rhie"), "박": ("park", "pak", "bak"), "최": ("choi", "choe"),
    "정": ("jung", "jeong", "chung"), "강": ("kang", "gang"), "조": ("cho", "jo"), "윤": ("yoon", "yun"),
    "장": ("jang", "chang"), "임": ("lim", "im", "yim"), "한": ("han",), "오": ("oh",), "서": ("seo", "suh"),
    "신": ("shin", "sin"), "권": ("kwon", "gwon"), "황": ("hwang",), "안": ("ahn", "an"), "송": ("song",),
    "류": ("ryu", "yoo", "yu"), "유": ("yoo", "yu"), "전": ("jeon", "jun", "chun"), "홍": ("hong",),
    "고": ("ko", "go"), "문": ("moon", "mun"), "양": ("yang",), "손": ("son", "sohn"), "배": ("bae",),
    "백": ("baek", "paik", "baik"), "허": ("heo", "huh", "hur"), "남": ("nam",), "심": ("shim", "sim"),
    "노": ("noh", "roh"), "하": ("ha",), "곽": ("kwak", "gwak"), "성": ("sung", "seong"), "차": ("cha",),
    "주": ("joo", "ju"), "우": ("woo", "wu"), "구": ("koo", "ku", "gu"), "민": ("min",), "진": ("jin",),
    "지": ("ji", "jee"), "엄": ("eom", "um", "uhm"), "채": ("chae",), "원": ("won",), "천": ("cheon", "chun"),
    "방": ("bang",), "공": ("kong", "gong"), "현": ("hyun", "hyeon"), "함": ("ham",), "변": ("byun", "byeon"),
    "염": ("yeom", "yum"), "여": ("yeo", "yuh"), "추": ("choo", "chu"), "석": ("seok", "suk"), "선": ("sun", "seon"),
    "설": ("seol", "sul"), "길": ("gil", "kil"), "연": ("yeon", "yun"), "위": ("wi", "wee"), "표": ("pyo",),
    "명": ("myung", "myeong"), "도": ("do",), "기": ("ki", "gi"), "마": ("ma",), "왕": ("wang",), "탁": ("tak",),
}
# Surnames a name found by a label or at the top of the CV may start with: the common ones only, since many
# Korean words start with a rare surname's syllable (마케터, 기획자, 도메인)
_DETECT_SURNAMES = frozenset(_SURNAMES) - {"도", "기", "마", "왕", "탁"}
_COMPOUND = tuple(s for s in _SURNAMES if len(s) == 2)

# Revised Romanization per jamo, with the common alternative spellings of names (eo/u/o, eu/u, i/ee, ...)
_INITIALS = ("g|k", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_MEDIALS = (
    "a", "ae", "ya", "yae", "eo|u|o", "e", "yeo|yo|you|yu", "ye", "o", "wa", "wae", "oe|wi", "yo", "u|oo",
    "wo|weo", "we", "wi", "yu|yoo", "eu|u", "ui|eui", "i|ee",
)
_FINALS = (
    "", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p|b", "p", "t", "t",
    "ng", "t", "t", "k", "t", "p", "t",
)

_OWN_LABELS = ("이름", "성명", "성 명", "한글 이름", "영문 이름", "영문명", "영문 성명", "name", "full name", "english name")
_OTHER_LABELS = ("추천인", "추천자", "담당자", "지도교수", "references", "reference", "referee")

# Words that look like a name at the top of a CV or after a label but are not one
_HANGUL_STOP = frozenset(
    "이력서 이력 지원서 지원자 구직자 자기소개서 경력기술서 포트폴리오 인적사항 기본정보 개인정보 성명 이름 "
    "이메일 주소 주소지 연락처 전화 전화번호 휴대폰 휴대전화 생년월일 주민번호 링크 백엔드 프론트엔드 풀스택 "
    "개발자 엔지니어 디자이너 기획자 연구원 인턴 신입 신입생 경력직 정규직 계약직 지원 고객 고객사 서비스 "
    "전문가 주니어 시니어 한국어 영어 추천인 추천자 담당자 지도교수 팀장 부장 과장 대리 사원 대표 학생 대학생 "
    "졸업 졸업예정 최종학력 최적화 정보처리 하드웨어 소프트웨어 문서화 변호사 설계자 연락처 안녕하세요 홍보팀 "
    "성별 국적 병역 병역사항 장애 조직도 운영자 관리자 교육생 수료생 모듈 서버 배포 설계 구현 구축 성능 문서 유지 "
    "정보 장애 조회 전략 신규 안정 공통 연동 인프라 송금 배치".split()
)
_LATIN_STOP = frozenset(
    "resume résumé cv curriculum vitae portfolio profile cover letter developer engineer designer manager "
    "scientist analyst architect intern student backend back-end frontend front-end fullstack full-stack software "
    "data web mobile senior junior lead principal product project devops machine learning research researcher "
    "consultant specialist administrator tester qa contact email phone address github linkedin blog korea seoul "
    "university college school inc corp co ltd company team the and of for at in professor dr mr mrs ms "
    "service services system api server experience projects skills education reference references".split()
)
_TITLE_SUFFIXES = ("선생님", "본부장", "센터장", "연구원", "교수님", "교수", "팀장", "부장", "과장", "차장", "대리", "사원",
                   "이사", "대표", "실장", "책임", "선임", "수석", "매니저", "님")
_HEADER_LINES = 3

_LATIN = "A-Za-zÀ-ÖØ-öø-ɏḀ-ỿ"
_LATIN_WORD = re.compile(rf"[{_LATIN}][{_LATIN}'’\-]*")
_LATIN_GAP = re.compile(r",?[ \t]+")
_HANGUL_WORD = re.compile(r"[가-힣]+")
_SPACED_SYLLABLES = re.compile(r"(?<![가-힣])[가-힣](?:[ \t][가-힣]){1,3}(?![가-힣])")
_PLACEHOLDER = re.compile(r"\[[^\]\n]{1,10}\]")
_LABEL_WORD = re.compile(r"[^\s:：|/]+\s*[:：]")
_NEXT_LABEL = re.compile(r"\s+[^\s:：]+\s*[:：]")
_SEGMENT = re.compile(r"[|/·•,()\[\]<>]|\s{2,}")


def _label_line(labels: tuple[str, ...]) -> re.Pattern:
    alternatives = "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True))
    return re.compile(
        rf"^[ \t•\-*·▪■◦○●]*(?P<label>{alternatives})(?:[ \t]*\([^)\n]{{0,10}}\))?(?P<sep>[ \t]*[:：][ \t]*|[ \t]+)(?P<value>[^\n]*)$",
        re.IGNORECASE | re.MULTILINE,
    )


_OWN_LABEL_LINE = _label_line(_OWN_LABELS)
_OTHER_LABEL_LINE = _label_line(_OTHER_LABELS)


@dataclass(frozen=True)
class MaskResult:
    text: str
    # Kinds of data that were found and masked, e.g. ("email", "phone")
    masked: tuple[str, ...]


def mask_pii(text: str, names: list[str] | None = None, skills: SkillDictionary | None = None) -> MaskResult:
    """`names`: the account name(s), always masked. `skills` keeps dictionary skills from being taken for a name
    found by a label or at the top of the CV."""
    found = []
    for kind, token, pattern in _PATTERNS:
        text, n = pattern.subn(token if kind not in ("birth", "address") else " " + token, text)
        if n:
            found.append(kind)
    for name in names or []:
        name = name.strip()
        if len(name) < 2:
            continue
        # Korean names are often written with spaces between syllables on CVs ("김 지 원")
        spaced = r"\s*".join(map(re.escape, name.replace(" ", "")))
        text, n = re.subn(spaced, NAME_TOKEN, text)
        if n and "name" not in found:
            found.append("name")
    # Then the other spellings of the account name, and the names a label or the top of the CV gives
    account = [n.strip() for n in names or [] if len(n.strip()) >= 2]
    detected = _labeled_names(text, skills) + _header_names(text, skills)
    for pattern in _name_patterns(account, detected):
        text, n = pattern.subn(NAME_TOKEN, text)
        if n and "name" not in found:
            found.append("name")
    return MaskResult(text=text, masked=tuple(found))


# ── Names: detection ──


def _strip_title(word: str) -> str:
    for suffix in _TITLE_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            return word[: -len(suffix)]
    return word


def _hangul_name(word: str, min_len: int) -> bool:
    surname_ok = word[:2] in _COMPOUND or word[0] in _DETECT_SURNAMES
    return min_len <= len(word) <= 4 and surname_ok and word not in _HANGUL_STOP


def _latin_runs(s: str) -> list[tuple[int, int, str]]:
    """(start, end, text) of each run of 2–4 capitalized words that are not stop words."""
    runs, run = [], []

    def close():
        if 2 <= len(run) <= 4:
            runs.append((run[0].start(), run[-1].end(), s[run[0].start() : run[-1].end()]))
        run.clear()

    for m in _LATIN_WORD.finditer(s):
        word = m.group()
        if not word[0].isupper() or _fold(word) in _LATIN_STOP:
            close()
            continue
        if run and not _LATIN_GAP.fullmatch(s[run[-1].end() : m.start()]):
            close()
        run.append(m)
    close()
    return runs


def _plausible(name: str, skills: SkillDictionary | None) -> bool:
    """The guards for a name found by a label or at the top of the CV."""
    if any(ch.isdigit() for ch in name) or heading_key(name) is not None:
        return False
    return skills is None or not skills.find_in_text(name)


def _first_name(value: str, min_hangul: int) -> str | None:
    """The first name in a labeled value: Hangul (also spaced syllables, a title such as 팀장 dropped) or Latin."""
    value = _PLACEHOLDER.sub(" ", value)
    hits = [(m.start(), m.group().replace(" ", "").replace("\t", "")) for m in _SPACED_SYLLABLES.finditer(value)]
    hits += [(m.start(), _strip_title(m.group())) for m in _HANGUL_WORD.finditer(value)]
    hits = [(pos, word) for pos, word in hits if _hangul_name(word, min_hangul)]
    hits += [(start, run) for start, _end, run in _latin_runs(value)]
    return min(hits)[1] if hits else None


def _labeled_names(text: str, skills: SkillDictionary | None) -> list[str]:
    out = []
    for pattern, min_hangul in ((_OWN_LABEL_LINE, 2), (_OTHER_LABEL_LINE, 3)):
        for m in pattern.finditer(text):
            colon = re.search(r"[:：]", m.group("sep")) is not None
            # Latin labels need a colon: "Name Service API" is not a labeled line
            if m.group("label").isascii() and not colon:
                continue
            value = _NEXT_LABEL.split(m.group("value"), maxsplit=1)[0]
            name = _first_name(value, min_hangul)
            # Without a colon the value must be the name alone (form style "성 명  최 유 진"), so "이름 변경 API" is not one
            if name and not colon and re.sub(r"\s", "", value) != re.sub(r"\s", "", name):
                continue
            if name and _plausible(name, skills):
                out.append(name)
    return out


def _header_names(text: str, skills: SkillDictionary | None) -> list[str]:
    """A name-shaped segment of the first lines, before the first section heading; heading lines are never touched."""
    out, seen = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if seen >= _HEADER_LINES or heading_key(line) is not None:
            break
        seen += 1
        if _OWN_LABEL_LINE.match(line) or _OTHER_LABEL_LINE.match(line):
            continue  # a labeled line is read by _labeled_names
        cleaned = _LABEL_WORD.sub(" | ", _PLACEHOLDER.sub(" | ", line))
        for segment in (s.strip() for s in _SEGMENT.split(cleaned)):
            if not segment:
                continue
            compact = re.sub(r"[ \t]", "", segment) if _SPACED_SYLLABLES.fullmatch(segment) else segment
            if _HANGUL_WORD.fullmatch(compact):
                name = compact if _hangul_name(compact, 3) else None
            else:
                runs = _latin_runs(segment)
                name = runs[0][2] if len(runs) == 1 and runs[0][2] == segment else None
            if name and _plausible(name, skills):
                out.append(name)
    return out


# ── Names: spellings → patterns ──


def _fold(s: str) -> str:
    """Lower case without diacritics (đ → d, which Unicode does not decompose)."""
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").casefold()


def _letter_classes() -> dict[str, str]:
    """a → [aàáạăắ…]: every Latin letter that folds to the base letter, so spellings match with or without marks."""
    letters = {chr(c): {chr(c)} for c in range(ord("a"), ord("z") + 1)}
    for cp in [*range(0x00C0, 0x0250), *range(0x1E00, 0x1F00)]:
        low = chr(cp).lower()
        if len(low) == 1 and (base := _fold(low)) in letters:
            letters[base].add(low)
    return {base: "[" + "".join(sorted(chars)) + "]" for base, chars in letters.items()}


_LETTERS = _letter_classes()


def _bounded(body: str) -> re.Pattern:
    return re.compile(rf"(?<![0-9{_LATIN}]){body}(?![0-9{_LATIN}])", re.IGNORECASE)


def _latin_word(word: str) -> str:
    parts = [p for p in re.split(r"[-'’]", _fold(word)) if p]
    return r"[-'’\s]?".join("".join(_LETTERS.get(c, re.escape(c)) for c in part) for part in parts)


def _latin_orders(words: list[str]) -> list[list[str]]:
    """Family name first or last, and for three or more words the short form (given + family, family + given)."""
    orders = [words, words[1:] + words[:1], words[-1:] + words[:-1]]
    if len(words) >= 3:
        orders += [[words[-1], words[0]], [words[0], words[-1]]]
    unique = []
    for o in orders:
        if o not in unique:
            unique.append(o)
    return sorted(unique, key=len, reverse=True)  # longest first, so a short form never splits a full name


def _syllable(ch: str) -> str:
    code = ord(ch) - 0xAC00
    initial, medial, final = code // 588, code % 588 // 28, code % 28
    initials = _INITIALS[initial].split("|")
    medials = _MEDIALS[medial].split("|")
    if initial == 11 and medial == 13:  # 우 → woo
        medials += ["woo", "wu"]
    if initial == 9 and medial == 20:  # 시 → shi
        initials += ["sh"]
    spellings = {i + m + f for i, m, f in product(initials, medials, _FINALS[final].split("|"))}
    return "(?:" + "|".join(sorted(spellings, key=len, reverse=True)) + ")"


def _romanized(name: str) -> list[re.Pattern]:
    """Kim Jiwon, KIM JI-WON, Jiwon Kim, Ji Won Kim, Kim, Jiwon … for a Korean name (full names only)."""
    name = name.replace(" ", "")
    if not 2 <= len(name) <= 5 or not all("가" <= ch <= "힣" for ch in name):
        return []
    family = name[:2] if name[:2] in _COMPOUND and len(name) >= 3 else name[0]
    family_alternatives = _SURNAMES.get(family)
    family_re = (
        "(?:" + "|".join(sorted(family_alternatives, key=len, reverse=True)) + ")"
        if family_alternatives
        else r"[-\s]?".join(_syllable(ch) for ch in family)
    )
    given_re = r"[-'’\s]?".join(_syllable(ch) for ch in name[len(family) :])
    return [_bounded(rf"{family_re},?\s+{given_re}"), _bounded(rf"{given_re}\s+{family_re}")]


def _name_patterns(account: list[str], detected: list[str]) -> list[re.Pattern]:
    patterns, seen = [], set()
    for name in account + detected:
        key = _fold(name)
        if key in seen:
            continue
        seen.add(key)
        if _HANGUL_WORD.fullmatch(name.replace(" ", "")):
            if name not in account:  # the account name's own Hangul spelling is masked above
                patterns.append(re.compile(r"\s*".join(map(re.escape, name.replace(" ", "")))))
            patterns += _romanized(name)
        elif len(words := [w for w in _LATIN_GAP.split(name.strip()) if w]) >= 2:
            patterns += [_bounded(r",?\s+".join(_latin_word(w) for w in order)) for order in _latin_orders(words)]
    return patterns
