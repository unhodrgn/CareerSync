import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import {
  MASKED_LABEL,
  type Certificate,
  type CvOut,
  type CvProfile,
  type Education,
  type Experience,
  type Project,
} from "../../api/types";
import { ErrorBox, errorText } from "../../components/ui";

type Tab = "skills" | "experience" | "project" | "education";

const EMPTY_EXPERIENCE: Experience = { org: "", role: "", start: null, end: null, description: "", source: "" };
const EMPTY_PROJECT: Project = { name: "", role: "", tech: [], description: "", source: "" };
const EMPTY_EDUCATION: Education = { school: "", major: "", degree: "", source: "" };
const EMPTY_CERTIFICATE: Certificate = { name: "", date: null, source: "" };
const DEGREES = ["", "고졸", "전문학사", "학사", "석사", "박사"];

function months(total: number): string {
  const y = Math.floor(total / 12);
  const m = total % 12;
  if (!total) return "확인된 경력 없음";
  return y ? `${y}년${m ? ` ${m}개월` : ""}` : `${m}개월`;
}

function methodLabel(method: string): string {
  if (method === "seeker") return "본인 수정";
  if (method.startsWith("llm:")) return "AI 분석";
  return "규칙 기반 분석";
}

/** Drop rows the seeker left completely empty, and blank tech entries. */
function cleaned(p: CvProfile): CvProfile {
  return {
    ...p,
    skills: p.skills.map((s) => s.trim()).filter(Boolean),
    experiences: p.experiences.filter((e) => e.org.trim() || e.role.trim() || e.description.trim()),
    projects: p.projects
      .map((x) => ({ ...x, tech: x.tech.map((t) => t.trim()).filter(Boolean) }))
      .filter((x) => x.name.trim() || x.description.trim()),
    education: p.education.filter((e) => e.school.trim() || e.major.trim()),
    certificates: p.certificates.filter((c) => c.name.trim()),
  };
}

export default function Resume() {
  const [cv, setCv] = useState<CvOut | null>(null);
  const [draft, setDraft] = useState<CvProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"" | "upload" | "save">("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [tab, setTab] = useState<Tab>("skills");
  const [skillInput, setSkillInput] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function load(out: CvOut) {
    setCv(out);
    setDraft(structuredClone(out.profile));
  }

  useEffect(() => {
    api
      .myCv()
      .then(load)
      .catch((err) => {
        if (!(err instanceof ApiError && err.code === "CV_NOT_FOUND")) setError(errorText(err));
      })
      .finally(() => setLoading(false));
  }, []);

  async function upload(file: File | undefined) {
    if (!file) return;
    if (cv && dirty && !window.confirm("저장하지 않은 수정 내용이 사라집니다. 새 이력서를 올릴까요?")) return;
    setBusy("upload");
    setError("");
    setSaved(false);
    try {
      load(await api.uploadCv(file));
      setTab("skills");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function save() {
    if (!cv || !draft) return;
    setBusy("save");
    setError("");
    try {
      load(await api.updateCv(cv.id, cleaned(draft), true));
      setSaved(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy("");
    }
  }

  const dirty = !!cv && !!draft && JSON.stringify(draft) !== JSON.stringify(cv.profile);
  const edit = (patch: Partial<CvProfile>) => {
    setSaved(false);
    setDraft((d) => (d ? { ...d, ...patch } : d));
  };

  function addSkill() {
    const s = skillInput.trim();
    if (draft && s && !draft.skills.includes(s)) edit({ skills: [...draft.skills, s] });
    setSkillInput("");
  }

  const uploadButton = (
    <>
      <input
        ref={fileRef}
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: "none" }}
        onChange={(e) => upload(e.target.files?.[0])}
      />
      <button
        className={`btn ${cv ? "btn-small" : "btn-primary"}`}
        disabled={busy !== ""}
        onClick={() => fileRef.current?.click()}
      >
        {busy === "upload" ? "분석 중…" : cv ? "새 이력서 업로드 (PDF)" : "이력서 업로드 (PDF)"}
      </button>
    </>
  );

  if (loading) return <p className="muted center-text">불러오는 중…</p>;

  if (!cv || !draft) {
    return (
      <>
        <h1 className="h1" style={{ margin: 0 }}>내 이력서</h1>
        <ErrorBox>{error}</ErrorBox>
        <section className="card stack" style={{ alignItems: "flex-start" }}>
          <h2 className="h2">이력서를 올려 주세요</h2>
          <p className="muted" style={{ fontSize: 14 }}>
            텍스트로 된 PDF(5페이지, 5MB 이하)를 올리면 AI가 기술·경력·프로젝트·학력·자격증을 정리합니다. 분석 결과를
            확인하고 저장하면 공고에 지원할 수 있습니다.
          </p>
          {uploadButton}
          <p className="field-hint">
            이름·이메일·전화번호·주소·생년월일 등 개인정보는 분석 전에 가려지며, 원본 PDF 파일은 저장하지 않습니다.
          </p>
        </section>
      </>
    );
  }

  const setExp = (i: number, patch: Partial<Experience>) =>
    edit({ experiences: draft.experiences.map((e, j) => (j === i ? { ...e, ...patch } : e)) });
  const setProject = (i: number, patch: Partial<Project>) =>
    edit({ projects: draft.projects.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const setEdu = (i: number, patch: Partial<Education>) =>
    edit({ education: draft.education.map((e, j) => (j === i ? { ...e, ...patch } : e)) });
  const setCert = (i: number, patch: Partial<Certificate>) =>
    edit({ certificates: draft.certificates.map((c, j) => (j === i ? { ...c, ...patch } : c)) });

  return (
    <>
      <h1 className="h1" style={{ margin: 0 }}>내 이력서</h1>
      <ErrorBox>{error}</ErrorBox>

      <div className="card card-tight row-between wrap">
        <div className="row wrap">
          {cv.confirmed && !dirty ? (
            <span className="chip chip-green">확인 완료 · 지원 가능</span>
          ) : (
            <span className="chip chip-amber">확인 필요</span>
          )}
          <span className="muted" style={{ fontSize: 14 }}>
            {cv.file_name} · {cv.pages}쪽 · {methodLabel(cv.method)} · 버전 {cv.version} · 경력 {months(cv.total_experience_months)}
          </span>
        </div>
        {uploadButton}
      </div>

      {!cv.confirmed && (
        <div className="alert alert-info">
          AI가 정리한 내용입니다. 빠지거나 틀린 부분을 고친 뒤 <strong>저장하고 확인</strong>을 누르면 지원할 수 있습니다.
        </div>
      )}
      {saved && !dirty && <div className="alert alert-ok">저장했습니다. 이제 이 이력서로 지원할 수 있습니다.</div>}

      <section className="card stack">
        <div className="tabs">
          <button className={tab === "skills" ? "on" : ""} onClick={() => setTab("skills")}>
            기술·요약
          </button>
          <button className={tab === "experience" ? "on" : ""} onClick={() => setTab("experience")}>
            경력 {draft.experiences.length}
          </button>
          <button className={tab === "project" ? "on" : ""} onClick={() => setTab("project")}>
            프로젝트 {draft.projects.length}
          </button>
          <button className={tab === "education" ? "on" : ""} onClick={() => setTab("education")}>
            학력·자격증
          </button>
        </div>

        {tab === "skills" && (
          <div className="stack">
            <div className="field">
              <span className="field-label">보유 기술</span>
              <div className="row wrap" style={{ gap: 6 }}>
                {draft.skills.length === 0 && <span className="muted">추출된 기술이 없습니다.</span>}
                {draft.skills.map((s) => (
                  <span key={s} className="chip chip-gray">
                    {s}{" "}
                    <button
                      className="btn-ghost"
                      aria-label={`${s} 삭제`}
                      onClick={() => edit({ skills: draft.skills.filter((x) => x !== s) })}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <div className="row" style={{ maxWidth: 360 }}>
                <input
                  value={skillInput}
                  maxLength={50}
                  placeholder="기술 추가 (예: Java)"
                  onChange={(e) => setSkillInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      addSkill();
                    }
                  }}
                />
                <button className="btn btn-small" style={{ whiteSpace: "nowrap" }} onClick={addSkill}>추가</button>
              </div>
            </div>
            <label className="field">
              <span className="field-label">요약</span>
              <textarea rows={3} maxLength={500} value={draft.summary} onChange={(e) => edit({ summary: e.target.value })} />
            </label>
          </div>
        )}

        {tab === "experience" && (
          <div className="stack">
            {draft.experiences.length === 0 && <p className="muted">추출된 경력이 없습니다. 신입이면 비워 두세요.</p>}
            {draft.experiences.map((e, i) => (
              <div key={i} className="card card-tight stack" style={{ gap: 8 }}>
                <div className="grid-2">
                  <input placeholder="회사·기관" maxLength={100} value={e.org} onChange={(x) => setExp(i, { org: x.target.value })} />
                  <input placeholder="직무·역할" maxLength={100} value={e.role} onChange={(x) => setExp(i, { role: x.target.value })} />
                </div>
                <div className="row wrap">
                  <input type="month" style={{ maxWidth: 180 }} value={e.start ?? ""} onChange={(x) => setExp(i, { start: x.target.value || null })} />
                  <span className="muted">~</span>
                  <input type="month" style={{ maxWidth: 180 }} value={e.end ?? ""} onChange={(x) => setExp(i, { end: x.target.value || null })} />
                  <span className="field-hint">종료일을 비우면 재직 중으로 봅니다.</span>
                </div>
                <textarea rows={3} placeholder="담당 업무" maxLength={2000} value={e.description} onChange={(x) => setExp(i, { description: x.target.value })} />
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <button className="btn btn-small btn-danger" onClick={() => edit({ experiences: draft.experiences.filter((_, j) => j !== i) })}>
                    삭제
                  </button>
                </div>
              </div>
            ))}
            <button className="btn btn-small" style={{ alignSelf: "flex-start" }} onClick={() => edit({ experiences: [...draft.experiences, { ...EMPTY_EXPERIENCE }] })}>
              + 경력 추가
            </button>
          </div>
        )}

        {tab === "project" && (
          <div className="stack">
            {draft.projects.length === 0 && <p className="muted">추출된 프로젝트가 없습니다.</p>}
            {draft.projects.map((p, i) => (
              <div key={i} className="card card-tight stack" style={{ gap: 8 }}>
                <div className="grid-2">
                  <input placeholder="프로젝트명" maxLength={200} value={p.name} onChange={(x) => setProject(i, { name: x.target.value })} />
                  <input placeholder="역할" maxLength={100} value={p.role} onChange={(x) => setProject(i, { role: x.target.value })} />
                </div>
                <input
                  placeholder="사용 기술 (쉼표로 구분)"
                  value={p.tech.join(", ")}
                  onChange={(x) => setProject(i, { tech: x.target.value.split(",").map((t) => t.trimStart()) })}
                />
                <textarea rows={3} placeholder="내용·성과" maxLength={2000} value={p.description} onChange={(x) => setProject(i, { description: x.target.value })} />
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <button className="btn btn-small btn-danger" onClick={() => edit({ projects: draft.projects.filter((_, j) => j !== i) })}>
                    삭제
                  </button>
                </div>
              </div>
            ))}
            <button className="btn btn-small" style={{ alignSelf: "flex-start" }} onClick={() => edit({ projects: [...draft.projects, { ...EMPTY_PROJECT }] })}>
              + 프로젝트 추가
            </button>
          </div>
        )}

        {tab === "education" && (
          <div className="stack">
            <h2 className="h2">학력</h2>
            <p className="field-hint">평가에는 전공만 사용하며 학교명은 평가하지 않습니다.</p>
            {draft.education.map((e, i) => (
              <div key={i} className="row wrap">
                <input style={{ maxWidth: 200 }} placeholder="학교" maxLength={100} value={e.school} onChange={(x) => setEdu(i, { school: x.target.value })} />
                <input style={{ maxWidth: 200 }} placeholder="전공" maxLength={100} value={e.major} onChange={(x) => setEdu(i, { major: x.target.value })} />
                <select style={{ maxWidth: 120 }} value={e.degree} onChange={(x) => setEdu(i, { degree: x.target.value })}>
                  {DEGREES.map((d) => (
                    <option key={d} value={d}>{d || "학위 선택"}</option>
                  ))}
                </select>
                <button className="btn btn-small btn-danger" onClick={() => edit({ education: draft.education.filter((_, j) => j !== i) })}>
                  삭제
                </button>
              </div>
            ))}
            <button className="btn btn-small" style={{ alignSelf: "flex-start" }} onClick={() => edit({ education: [...draft.education, { ...EMPTY_EDUCATION }] })}>
              + 학력 추가
            </button>

            <h2 className="h2">자격증</h2>
            {draft.certificates.map((c, i) => (
              <div key={i} className="row wrap">
                <input style={{ maxWidth: 260 }} placeholder="자격증명" maxLength={100} value={c.name} onChange={(x) => setCert(i, { name: x.target.value })} />
                <input type="month" style={{ maxWidth: 180 }} value={c.date ?? ""} onChange={(x) => setCert(i, { date: x.target.value || null })} />
                <button className="btn btn-small btn-danger" onClick={() => edit({ certificates: draft.certificates.filter((_, j) => j !== i) })}>
                  삭제
                </button>
              </div>
            ))}
            <button className="btn btn-small" style={{ alignSelf: "flex-start" }} onClick={() => edit({ certificates: [...draft.certificates, { ...EMPTY_CERTIFICATE }] })}>
              + 자격증 추가
            </button>
          </div>
        )}

        <div className="row-between wrap">
          <p className="field-hint" style={{ margin: 0 }}>
            {cv.masked_kinds.length > 0
              ? `개인정보 보호를 위해 ${cv.masked_kinds.map((k) => MASKED_LABEL[k] ?? k).join(", ")}을(를) 가린 뒤 분석했습니다.`
              : "개인정보는 분석 전에 가려집니다."}{" "}
            AI 분석 결과는 참고용입니다.
          </p>
          <div className="row">
            {dirty && (
              <button className="btn btn-small" disabled={busy !== ""} onClick={() => setDraft(structuredClone(cv.profile))}>
                되돌리기
              </button>
            )}
            <button className="btn btn-primary" disabled={busy !== "" || (cv.confirmed && !dirty)} onClick={save}>
              {busy === "save" ? "저장 중…" : "저장하고 확인"}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
