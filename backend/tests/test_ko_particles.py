"""Korean particles never attach to a placeholder in frontend/src/i18n/ko.ts.

Particles such as 은/는, 이/가, 을/를, 과/와 and (으)로 change with the last sound of the word before them, and a
placeholder's value is not known when the string is written: "‘{status}’로" is right for 보류 but wrong for 합격
(합격으로), and "버전 {v}로" is wrong for 3, 6 and 10. Strings attach such particles to a fixed noun instead
("‘{status}’ 상태로", "새 버전(버전 {v})으로") or use one that never changes (에, 에서, 까지, 부터). This test reads
ko.ts, like test_band_thresholds_frontend.py, and fails on any placeholder directly followed by a variable particle,
optionally after a closing quote. Counters ({n}개, {n}명), invariant particles, particles after a parenthesis (they
attach to the noun before it) and the copula ({n}입니다, {n}이고) are not flagged."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "frontend" / "src" / "i18n" / "ko.ts"

# A placeholder, optional closing quotes, then a variable particle that ends the word (no Hangul right after it, so
# 이고 / 이다 / 입니다 and counters such as 개 or 명 never match).
_VARIABLE = re.compile(r"\{\w+\}[’'\"」』]*(?:으로|로|은|는|이|가|을|를|과|와)(?![가-힣])")


def variable_particles(text: str) -> list[str]:
    """The places in `text` where a value-dependent particle follows a placeholder."""
    return [m.group(0) for m in _VARIABLE.finditer(text)]


def _strings(source: str) -> list[tuple[int, str]]:
    """The string literals of ko.ts with their line numbers; comments are skipped."""
    found = []
    for number, line in enumerate(source.splitlines(), start=1):
        if line.lstrip().startswith("//"):
            continue
        found.extend((number, s) for s in re.findall(r"'((?:[^'\\]|\\.)*)'", line))
    return found


def test_flags_value_dependent_particles():
    for text in [
        "‘{status}’로 바꿨습니다.",
        "버전 {v}로 남습니다.",
        "거절하면 {company}는 다시 제안할 수 없습니다.",
        "{name}이 지원했습니다.",
        "{name}가 지원했습니다.",
        "{skill}을 배우세요.",
        "{skill}를 배우세요.",
        "{a}과 {b}",
        "{a}와 함께",
        "{status}으로 바꿨습니다.",
        "{company}은 제안할 수 없습니다.",
        '"{q}"로 찾은 결과',
    ]:
        assert variable_particles(text), text


def test_leaves_safe_constructions_alone():
    for text in [
        "‘{status}’ 상태로 바꿨습니다.",  # particle on a fixed noun
        "저장하면 새 버전(버전 {v})으로 남습니다.",  # particle after a parenthesis, on 새 버전
        "이 버전(버전 {v})이 쓰입니다.",
        "이름({name})과 이메일({email})이 공개됩니다.",
        "거절하면 {company}에서 제안할 수 없습니다.",  # invariant particles
        "{company}에 공개됩니다.",
        "{date}까지 답변",
        "{date}부터 공개 중",
        "공고 {n}개 가운데 {shown}개를 보여 줍니다.",  # counters, also with a particle after them
        "지원자 {n}명이 있습니다.",
        "{n}점 이상",
        "{rank}위 {name}",
        "{position}번째 지원자",
        "지금 {n}입니다.",  # copula
        "참고 {low}~{midBelow}이고",
        "{name} 기준 삭제",  # a space before the next word
    ]:
        assert not variable_particles(text), text


def test_ko_strings_attach_no_variable_particle_to_a_placeholder():
    offenders = [
        f"ko.ts:{number}: {match}  ←  {text}"
        for number, text in _strings(SOURCE.read_text(encoding="utf-8"))
        for match in variable_particles(text)
    ]
    assert not offenders, "Attach the particle to a fixed noun or use an invariant one:\n" + "\n".join(offenders)
