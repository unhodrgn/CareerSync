"""The frontend's required criteria gate (docs/DECISIONS.md D50, Phase 1c) against the backend contract and the D50 rules.

The frontend has no test runner, so like test_band_thresholds_frontend.py and test_ko_particles.py this reads its
source: the TypeScript types mirror backend/app/schemas/gate.py and the response schemas, every gate text goes through
t() with the D50 wording in every locale file, the anonymous talent card reads only the status, the apply panel never
depends on the gate, and the applicant list sends the filter to the API instead of hiding rows itself."""
import re
import typing
from pathlib import Path

import pytest

from app.schemas import application, gate, recommendation, talent

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
I18N = SRC / "i18n"

# The D50 wording (Long's decision E); the frontend must show exactly these
D50_TEXT = {
    "gate.status.PASS": "최소 경력 조건 충족",
    "gate.status.FAIL": "최소 경력 조건 미충족",
    "gate.status.REVIEW": "경력 정보 확인 필요",
    "gate.seeker.fail": "AI 확인: 최소 경력 조건에 미달하는 것으로 표시됩니다. 직접 지원은 가능하며, 최종 자격은 채용 담당자가 확인합니다.",
    "editor.minExperienceGate": (
        "입력한 최소 경력은 AI 추천에서 필수 조건으로 적용됩니다. 경력 정보가 부족하거나 불일치하는 경우 확인이 필요할 수 "
        "있습니다. 이 조건은 직접 지원을 제한하지 않으며, 최종 채용 판단은 담당자가 합니다."
    ),
}
# Words that would say the AI decided against someone; none may appear in a gate text
REJECTION_WORDS = ("탈락 처리", "불합격", "거절되었", "지원 불가", "지원할 수 없")


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"\{/\*.*?\*/\}", "", code, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", code)


def ts_interface(source: str, name: str) -> dict[str, str]:
    """Fields of `interface name { ... }`: {field: type text}, `?` kept on the name."""
    m = re.search(rf"interface {name}\b[^{{]*\{{(.*?)\n\}}", source, re.S)
    assert m, f"interface {name} not found"
    body = strip_comments(m.group(1))
    return {f: ty.strip().rstrip(";") for f, ty in re.findall(r"^\s*(\w+\??)\s*:\s*([^\n]+)", body, re.M)}


def ts_union(source: str, name: str) -> set[str]:
    m = re.search(rf"export type {name}\s*=\s*([^;]+);", source)
    assert m, f"type {name} not found"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def locale_files() -> list[Path]:
    return [p for p in I18N.glob("*.ts") if p.name != "index.ts"]


def messages(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    # 'key': 'value' or 'key':\n    'value' (long values wrap onto the next line)
    return {k: v for k, v in re.findall(r"'([\w.]+)':\s*'((?:[^'\\]|\\.)*)'", text)}


# ── API types mirror the backend ──

GATE_TS = read("types/gate.ts")


@pytest.mark.parametrize(
    "model, interface",
    [(gate.RequiredGateOut, "RequiredGateOut"), (gate.RequirementCheckOut, "RequirementCheckOut"), (gate.RequiredGateBrief, "RequiredGateBrief")],
)
def test_gate_interfaces_have_the_backend_fields(model, interface):
    assert set(ts_interface(GATE_TS, interface)) == set(model.model_fields)


def test_gate_enums_match_the_backend():
    assert ts_union(GATE_TS, "GateStatusT") == set(typing.get_args(gate.GateStatusT))
    assert ts_union(GATE_TS, "GateBasisT") == set(typing.get_args(gate.GateBasisT))


def test_nullable_fields_stay_nullable():
    check = ts_interface(GATE_TS, "RequirementCheckOut")
    assert check["candidate_months"] == "number | null" and check["basis"] == "GateBasisT | null"
    assert ts_interface(GATE_TS, "RequiredGateOut")["basis"] == "GateBasisT | null"


@pytest.mark.parametrize(
    "file, interface, model, ts_type, py_type",
    [
        ("types/application.ts", "ApplicantRow", application.ApplicantRow, "RequiredGateOut | null", gate.RequiredGateOut),
        ("types/application.ts", "EvaluationOut", application.EvaluationOut, "RequiredGateOut | null", gate.RequiredGateOut),
        ("types/recommendation.ts", "RecommendedJob", recommendation.RecommendedJob, "RequiredGateOut | null", gate.RequiredGateOut),
        ("types/recommendation.ts", "JobMatch", recommendation.JobMatch, "RequiredGateOut | null", gate.RequiredGateOut),
        ("types/talent.ts", "TalentCandidate", talent.TalentCandidate, "RequiredGateBrief | null", gate.RequiredGateBrief),
    ],
)
def test_responses_carry_an_optional_nullable_gate(file, interface, model, ts_type, py_type):
    # Optional (older responses lack it) and nullable (the backend sends null where there is no gate)
    assert ts_interface(read(file), interface)["required_gate?"] == ts_type
    field = model.model_fields["required_gate"]
    assert field.default is None and set(typing.get_args(field.annotation)) == {py_type, type(None)}


def test_the_applicant_filter_reaches_the_api():
    assert ts_interface(read("types/application.ts"), "ApplicantFilters")["required_gate?"] == "GateStatusT"
    assert "search.append('required_gate', filters.required_gate)" in read("api/client.ts")


# ── Wording: t(), D50 text, every locale ──


def gate_keys_used() -> set[str]:
    keys = set()
    for path in SRC.rglob("*.tsx"):
        code = path.read_text(encoding="utf-8")
        keys |= set(re.findall(r"t\(\s*'((?:gate|editor\.minExperienceGate)[\w.]*)'", code))
        for prefix in re.findall(r"t\(\s*`(gate\.[\w.]+\.)\$\{", code):
            keys |= {f"{prefix}{s}" for s in typing.get_args(gate.GateStatusT)}
    return keys


def test_every_gate_text_exists_in_every_locale():
    used = gate_keys_used()
    assert set(D50_TEXT) <= used | {"gate.status.PASS", "gate.status.FAIL", "gate.status.REVIEW"}
    files = locale_files()
    assert files, "no locale file"
    for path in files:
        missing = sorted(used - set(messages(path)))
        assert not missing, f"{path.name} lacks {missing}"


def test_d50_wording_is_used_verbatim():
    ko = messages(I18N / "ko.ts")
    for key, text in D50_TEXT.items():
        assert ko[key] == text, key


def test_no_gate_text_reads_as_a_rejection():
    ko = messages(I18N / "ko.ts")
    for key, text in ko.items():
        if key.startswith("gate.") or key == "editor.minExperienceGate":
            assert not any(w in text for w in REJECTION_WORDS), key


def test_gate_component_has_no_hardcoded_text():
    code = strip_comments(read("components/common/RequiredGate.tsx"))
    assert not re.search(r"[가-힣]", code)


# ── Rules of D50 in the UI ──


def test_the_talent_card_reads_only_the_status():
    code = strip_comments(read("pages/company/Talent.tsx"))
    uses = re.findall(r"required_gate\??\.(\w+)", code)
    assert uses and set(uses) == {"status"}
    assert "GateDetail" not in code


def test_applying_never_depends_on_the_gate():
    code = read("pages/public/JobDetail.tsx")
    panel = re.search(r"\nfunction ApplyPanel\(.*?(?=\n(?:function|async function|interface|export) )", code, re.S)
    assert panel, "ApplyPanel not found"
    assert not re.search(r"gate", panel.group(0), re.I)


def test_the_applicant_list_never_hides_or_reorders_rows_itself():
    code = strip_comments(read("pages/company/Applicants.tsx"))
    # The filter goes to the API (D22: applied after ranking on the server); rows are never filtered or sorted by it here
    assert "required_gate: gateFilter" in code
    assert not re.search(r"\.(filter|sort)\([^)]*required_gate", code)


def test_the_gate_display_cannot_change_anything():
    # Display only: no API call, no control, so a gate label can never change an application's status (AI rule 5)
    code = strip_comments(read("components/common/RequiredGate.tsx"))
    assert "@/api" not in code and "api." not in code
    assert not re.search(r"<button|onClick|onChange|<select|<input", code)


def test_the_editor_explains_the_minimum():
    assert "t('editor.minExperienceGate')" in read("pages/company/JobEditor.tsx")


# ── E2E P1 fixes: stated experience and the FAIL job detail message ──


def test_p1_wording():
    ko = messages(I18N / "ko.ts")
    assert ko["apl.experienceStated"] == "이력서 기재 경력 {value} · 근무 기간 미확인"
    assert ko["match.gateFail"] == "최소 경력 조건 미충족으로 AI 추천 분석이 진행되지 않습니다. 직접 지원은 가능합니다."
    for key in ("apl.experienceStated", "match.gateFail"):
        assert not any(w in ko[key] for w in REJECTION_WORDS), key


def test_applicant_list_and_detail_share_one_experience_format():
    # Both go through applicantExperience (stated total when the gate used it, the period value otherwise)
    for rel in ("pages/company/Applicants.tsx", "components/company/ApplicantDetail.tsx"):
        code = strip_comments(read(rel))
        assert "applicantExperience(" in code, rel
        assert "t('apl.experience'" not in code, rel
    helper = strip_comments(read("components/common/RequiredGate.tsx"))
    assert "t('apl.experienceStated'" in helper and "t('apl.experience'" in helper


def test_job_detail_uses_the_match_view_and_keeps_the_fail_notice():
    code = strip_comments(read("pages/public/JobDetail.tsx"))
    assert "matchView(" in code and "t('match.gateFail')" in code
    assert "audience=\"seeker\"" in code  # GateDetail, which carries the D50 FAIL notice, stays
    assert "gate.seeker.fail" in strip_comments(read("components/common/RequiredGate.tsx"))
