import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import {
  CATEGORY_LABEL,
  EMPLOYMENT_LABEL,
  STATUS_LABEL,
  type Category,
  type CriteriaSetOut,
  type EmploymentType,
  type GuardrailHit,
  type Job,
  type JobInput,
  type JobListItem,
} from "../../api/types";
import { ErrorBox, Field, errorText } from "../../components/ui";

const MAX_ITEMS = 10;
const WEIGHT_TOTAL = 100;
// Fields still editable after publish (backend: EDITABLE_AFTER_PUBLISH)
const OPEN_AFTER_PUBLISH = ["deadline", "location", "salary_note"] as const;

const EMPTY_JOB: JobInput = {
  title: "",
  description: "",
  employment_type: "full_time",
  min_experience_years: null,
  location: "",
  salary_note: "",
  deadline: null,
};

interface Row {
  key: string;
  id: number | null;
  name: string;
  description: string;
  category: Category;
  weight: number;
}

function rowsFrom(set: CriteriaSetOut): Row[] {
  return set.items.map((c) => ({
    key: `id-${c.id}`,
    id: c.id,
    name: c.name,
    description: c.description,
    category: c.category,
    weight: c.weight,
  }));
}

const jobToForm = (job: Job): JobInput => ({
  title: job.title,
  description: job.description,
  employment_type: job.employment_type,
  min_experience_years: job.min_experience_years,
  location: job.location,
  salary_note: job.salary_note,
  deadline: job.deadline,
});

export default function JobEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const step = Math.min(3, Math.max(1, Number(params.get("step")) || 1));
  const goStep = (n: number) => setParams({ step: String(n) }, { replace: true });

  const [job, setJob] = useState<Job | null>(null);
  const [form, setForm] = useState<JobInput>(EMPTY_JOB);
  const [rows, setRows] = useState<Row[]>([]);
  const [hits, setHits] = useState<Record<string, GuardrailHit[]>>({});
  const [others, setOthers] = useState<JobListItem[]>([]);
  const [copyFrom, setCopyFrom] = useState("");
  const [loading, setLoading] = useState(Boolean(id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const keySeq = useRef(0);
  const checked = useRef<Record<string, string>>({});

  const locked = job !== null && job.status !== "draft";
  const total = rows.reduce((sum, r) => sum + (Number.isFinite(r.weight) ? r.weight : 0), 0);

  useEffect(() => {
    api.myJobs().then((jobs) => setOthers(jobs.filter((j) => String(j.id) !== id && j.criteria_count > 0)));
    if (!id) return;
    Promise.all([api.job(Number(id)), api.criteria(Number(id))])
      .then(([j, set]) => {
        setJob(j);
        setForm(jobToForm(j));
        setRows(rowsFrom(set));
      })
      .catch((err) => setError(errorText(err)))
      .finally(() => setLoading(false));
  }, [id]);

  // Live guardrail check while typing (the server re-checks on save, this is for early feedback)
  useEffect(() => {
    const timer = setTimeout(async () => {
      for (const r of rows) {
        const signature = `${r.name}\u0000${r.description}`;
        if (checked.current[r.key] === signature) continue;
        checked.current[r.key] = signature;
        if (!r.name.trim()) {
          setHits((h) => ({ ...h, [r.key]: [] }));
          continue;
        }
        try {
          const res = await api.checkCriterion(r.name.trim(), r.description.trim());
          setHits((h) => ({ ...h, [r.key]: res.hits }));
        } catch {
          // the save call enforces the rule anyway
        }
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [rows]);

  const setField = <K extends keyof JobInput>(key: K, value: JobInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const fieldLocked = (key: keyof JobInput) => locked && !(OPEN_AFTER_PUBLISH as readonly string[]).includes(key);

  const updateRow = (key: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  function addRow() {
    keySeq.current += 1;
    setRows((rs) => [
      ...rs,
      { key: `new-${keySeq.current}`, id: null, name: "", description: "", category: "skill", weight: 0 },
    ]);
  }

  async function saveJob() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (!job) {
        const created = await api.createJob(form);
        navigate(`/company/jobs/${created.id}/edit?step=2`, { replace: true });
        return;
      }
      const updated = locked
        ? await api.updateJob(job.id, { deadline: form.deadline, location: form.location, salary_note: form.salary_note })
        : await api.updateJob(job.id, form);
      setJob(updated);
      goStep(2);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveCriteria() {
    if (!job) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const set = await api.saveCriteria(
        job.id,
        rows.map((r) => ({ id: r.id, name: r.name, description: r.description, category: r.category, weight: r.weight })),
      );
      setRows(rowsFrom(set));
      checked.current = {};
      setJob({ ...job, criteria_count: set.items.length });
      goStep(3);
    } catch (err) {
      if (err instanceof ApiError && err.code === "CRITERIA_BLOCKED") {
        const blocked = (err.extra.items ?? []) as GuardrailHit[];
        const next: Record<string, GuardrailHit[]> = {};
        for (const hit of blocked) {
          const row = hit.index !== null ? rows[hit.index] : undefined;
          if (row) next[row.key] = [...(next[row.key] ?? []), hit];
        }
        setHits((h) => ({ ...h, ...next }));
      }
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function importFrom() {
    if (!job || !copyFrom) return;
    setBusy(true);
    setError("");
    try {
      const set = await api.copyCriteria(job.id, Number(copyFrom));
      setRows(rowsFrom(set));
      checked.current = {};
      setNotice("다른 공고의 평가 기준을 불러왔습니다. 필요하면 수정한 뒤 저장하세요.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const published = await api.publishJob(job.id);
      setJob(published);
      setNotice("공고를 게시했습니다. 구직자에게 노출됩니다.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function close() {
    if (!job || !window.confirm("공고를 마감하면 되돌릴 수 없습니다. 마감할까요?")) return;
    setBusy(true);
    setError("");
    try {
      setJob(await api.closeJob(job.id));
      setNotice("공고를 마감했습니다.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="muted center-text">불러오는 중…</p>;

  const STEPS = ["기본 정보", "평가 기준 설정", "등록 완료"];
  const canGoCriteria = job !== null;

  return (
    <>
      <div className="row-between wrap">
        <h1 className="h1" style={{ margin: 0 }}>
          {job ? job.title || "채용공고 수정" : "새 채용공고 등록"}
          {job && <span className={`chip ${job.status === "published" ? "chip-green" : "chip-gray"}`} style={{ marginLeft: 10 }}>{STATUS_LABEL[job.status]}</span>}
        </h1>
        <Link to="/company/jobs">← 목록으로</Link>
      </div>

      <div className="steps">
        {STEPS.map((label, i) => {
          const n = i + 1;
          const state = n === step ? "on" : n < step ? "done" : "";
          const enabled = n === 1 || canGoCriteria;
          return (
            <div key={label} className="row">
              {i > 0 && <span className="step-line" />}
              <button
                className={`step ${state}`}
                style={{ background: "none", border: 0, cursor: enabled ? "pointer" : "default", font: "inherit" }}
                disabled={!enabled}
                onClick={() => goStep(n)}
              >
                <span className="dot">{n < step ? "✓" : n}</span>
                {label}
              </button>
            </div>
          );
        })}
      </div>

      <ErrorBox>{error}</ErrorBox>
      {notice && <div className="alert alert-ok">{notice}</div>}

      {step === 1 && (
        <section className="card stack">
          {locked && (
            <div className="alert alert-info">
              게시된 공고는 마감일·근무지·급여 안내만 수정할 수 있습니다. 나머지 항목은 공정한 평가를 위해 잠겨 있습니다.
            </div>
          )}
          <Field label="공고 제목">
            <input value={form.title} maxLength={200} disabled={fieldLocked("title")} onChange={(e) => setField("title", e.target.value)} />
          </Field>
          <div className="grid-2">
            <Field label="고용 형태">
              <select
                value={form.employment_type}
                disabled={fieldLocked("employment_type")}
                onChange={(e) => setField("employment_type", e.target.value as EmploymentType)}
              >
                {Object.entries(EMPLOYMENT_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label="최소 경력(년)" hint="비워두면 신입도 지원할 수 있습니다.">
              <input
                type="number"
                min={0}
                max={30}
                value={form.min_experience_years ?? ""}
                disabled={fieldLocked("min_experience_years")}
                onChange={(e) => setField("min_experience_years", e.target.value === "" ? null : Number(e.target.value))}
              />
            </Field>
            <Field label="근무지">
              <input value={form.location} maxLength={100} onChange={(e) => setField("location", e.target.value)} />
            </Field>
            <Field label="급여 안내">
              <input value={form.salary_note} maxLength={100} onChange={(e) => setField("salary_note", e.target.value)} />
            </Field>
            <Field label="마감일">
              <input type="date" value={form.deadline ?? ""} onChange={(e) => setField("deadline", e.target.value || null)} />
            </Field>
          </div>
          <Field label="직무 설명(JD)" hint="게시하려면 직무 설명이 필요합니다.">
            <textarea
              value={form.description}
              maxLength={10000}
              rows={8}
              disabled={fieldLocked("description")}
              onChange={(e) => setField("description", e.target.value)}
            />
          </Field>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-primary" disabled={busy || !form.title.trim() || job?.status === "closed"} onClick={saveJob}>
              {busy ? "저장 중…" : "저장하고 다음"}
            </button>
          </div>
        </section>
      )}

      {step === 2 && job && (
        <section className="card">
          <div className="row-between wrap" style={{ marginBottom: 8 }}>
            <div>
              <h2 className="h2">평가 기준 설정</h2>
              <p className="muted" style={{ fontSize: 14 }}>
                항목 1~{MAX_ITEMS}개, 가중치 합계 {WEIGHT_TOTAL}. 직무와 무관한 기준(신체 조건, 출신지, 혼인, 재산, 성별, 연령, 종교 등)은 법에 따라 입력할 수 없습니다.
              </p>
            </div>
            <div className={`total ${total === WEIGHT_TOTAL ? "ok" : "bad"}`}>
              합계 {total} / {WEIGHT_TOTAL}
            </div>
          </div>

          {locked && (
            <div className="alert alert-info" style={{ marginBottom: 8 }}>
              게시된 공고는 가중치와 순서만 바꿀 수 있습니다. 변경하면 점수가 즉시 다시 계산됩니다.
            </div>
          )}

          {!locked && others.length > 0 && (
            <div className="row wrap" style={{ margin: "12px 0" }}>
              <select style={{ maxWidth: 320 }} value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
                <option value="">다른 공고에서 평가 기준 복사…</option>
                {others.map((o) => (
                  <option key={o.id} value={o.id}>{o.title} ({o.criteria_count}개)</option>
                ))}
              </select>
              <button className="btn" disabled={!copyFrom || busy} onClick={importFrom}>불러오기</button>
            </div>
          )}

          <div>
            {rows.map((r, index) => (
              <div className="criterion" key={r.key}>
                <input
                  placeholder={`평가 항목 ${index + 1} (예: Java)`}
                  value={r.name}
                  maxLength={50}
                  disabled={locked}
                  onChange={(e) => updateRow(r.key, { name: e.target.value })}
                />
                <select value={r.category} disabled={locked} onChange={(e) => updateRow(r.key, { category: e.target.value as Category })}>
                  {Object.entries(CATEGORY_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                <div className="weight-box">
                  <input
                    type="range"
                    min={1}
                    max={100}
                    value={r.weight || 1}
                    onChange={(e) => updateRow(r.key, { weight: Number(e.target.value) })}
                  />
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={r.weight || ""}
                    onChange={(e) => updateRow(r.key, { weight: Math.round(Number(e.target.value)) })}
                  />
                </div>
                {locked ? (
                  <span />
                ) : (
                  <button className="btn btn-ghost" title="항목 삭제" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}>✕</button>
                )}
                <input
                  className="desc"
                  style={{ gridColumn: "1 / -1" }}
                  placeholder="평가 설명 (예: 백엔드 개발 경험)"
                  value={r.description}
                  maxLength={500}
                  disabled={locked}
                  onChange={(e) => updateRow(r.key, { description: e.target.value })}
                />
                {(hits[r.key] ?? []).map((hit, i) => (
                  <div className="hit" key={`${hit.rule_id}-${hit.field}-${i}`}>
                    “{hit.matched}” — {hit.reason}
                    <small>{hit.law_ref}</small>
                  </div>
                ))}
              </div>
            ))}
            {rows.length === 0 && <p className="muted" style={{ padding: "16px 0" }}>아직 평가 항목이 없습니다. 항목을 추가하세요.</p>}
          </div>

          <div className="row-between" style={{ marginTop: 12 }}>
            {!locked ? (
              <button className="btn" disabled={rows.length >= MAX_ITEMS} onClick={addRow}>+ 항목 추가</button>
            ) : (
              <span />
            )}
            <div className="row">
              <button className="btn" onClick={() => goStep(1)}>이전</button>
              <button className="btn btn-primary" disabled={busy || rows.length === 0 || total !== WEIGHT_TOTAL} onClick={saveCriteria}>
                {busy ? "저장 중…" : "저장하고 다음"}
              </button>
            </div>
          </div>
        </section>
      )}

      {step === 3 && job && (
        <section className="card stack">
          <div>
            <h2 className="h2">{job.title}</h2>
            <p className="muted" style={{ fontSize: 14 }}>
              {job.company_name} · {EMPLOYMENT_LABEL[job.employment_type]} · {job.location || "근무지 미정"} ·{" "}
              {job.min_experience_years === null ? "신입 가능" : `경력 ${job.min_experience_years}년 이상`}
            </p>
          </div>
          <table className="table">
            <thead>
              <tr><th>평가 항목</th><th>설명</th><th className="num">가중치(%)</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td>{r.name}</td>
                  <td className="muted">{r.description}</td>
                  <td className="num">{r.weight}</td>
                </tr>
              ))}
              <tr>
                <td colSpan={2} style={{ textAlign: "right", fontWeight: 700 }}>총합</td>
                <td className="num total">{total}%</td>
              </tr>
            </tbody>
          </table>
          <div className="row-between wrap">
            <button className="btn" onClick={() => goStep(2)}>이전</button>
            {job.status === "draft" && (
              <button className="btn btn-primary" disabled={busy} onClick={publish}>
                {busy ? "게시 중…" : "공고 게시하기"}
              </button>
            )}
            {job.status === "published" && (
              <div className="row">
                <Link className="btn" to="/company/jobs">목록으로</Link>
                <button className="btn btn-danger" disabled={busy} onClick={close}>공고 마감</button>
              </div>
            )}
            {job.status === "closed" && <span className="chip chip-gray">마감된 공고</span>}
          </div>
        </section>
      )}
    </>
  );
}
