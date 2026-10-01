import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import {
  APPLICATION_STATUS_LABEL,
  EVALUATION_STATUS_LABEL,
  type ApplicantList,
  type ApplicantRow,
  type ApplicationStatus,
  type EvaluationOut,
  type JobListItem,
} from "../../api/types";
import { ErrorBox, Meter, errorText } from "../../components/ui";

type Tab = "summary" | "scores" | "evidence";

// While an evaluation is still running, re-read the list this often
const POLL_MS = 4000;

function experience(months: number): string {
  if (!months) return "경력 없음";
  const y = Math.floor(months / 12);
  const m = months % 12;
  return y ? `경력 ${y}년${m ? ` ${m}개월` : ""}` : `경력 ${m}개월`;
}

function methodLabel(method: string): string {
  if (method.startsWith("rule:")) return "규칙";
  if (method.startsWith("llm:")) return "AI 루브릭";
  return "유사도 추정";
}

export default function Applicants() {
  const [params, setParams] = useSearchParams();
  const [jobs, setJobs] = useState<JobListItem[] | null>(null);
  const [list, setList] = useState<ApplicantList | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationOut | null>(null);
  const [tab, setTab] = useState<Tab>("scores");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const jobId = Number(params.get("job")) || null;

  useEffect(() => {
    api
      .myJobs()
      .then((all) => {
        const usable = all.filter((j) => j.status !== "draft");
        setJobs(usable);
        if (!jobId && usable.length) setParams({ job: String(usable[0].id) }, { replace: true });
      })
      .catch((err) => setError(errorText(err)));
  }, []);

  const loadList = useCallback(
    (id: number) =>
      api
        .applicants(id)
        .then((l) => {
          setList(l);
          setSelectedId((cur) => (cur && l.items.some((r) => r.application_id === cur) ? cur : l.items[0]?.application_id ?? null));
        })
        .catch((err) => setError(errorText(err))),
    [],
  );

  useEffect(() => {
    setList(null);
    setSelectedId(null);
    setEvaluation(null);
    setError("");
    if (jobId) loadList(jobId);
  }, [jobId, loadList]);

  // Poll while any evaluation is still running
  const pending = list?.items.some((r) => r.evaluation_status === "pending") ?? false;
  useEffect(() => {
    if (!pending || !jobId) return;
    const t = window.setTimeout(() => loadList(jobId), POLL_MS);
    return () => window.clearTimeout(t);
  }, [list, pending, jobId, loadList]);

  const selected = list?.items.find((r) => r.application_id === selectedId) ?? null;
  const selectedState = selected?.evaluation_status;
  useEffect(() => {
    if (!selectedId) return;
    api
      .evaluation(selectedId)
      .then(setEvaluation)
      .catch((err) => setError(errorText(err)));
  }, [selectedId, selectedState]);

  async function changeStatus(row: ApplicantRow, status: ApplicationStatus) {
    setBusy(true);
    try {
      const out = await api.setApplicationStatus(row.application_id, status);
      setList((l) =>
        l && { ...l, items: l.items.map((r) => (r.application_id === row.application_id ? { ...r, status: out.status } : r)) },
      );
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function retry(row: ApplicantRow) {
    setBusy(true);
    try {
      setEvaluation(await api.retryEvaluation(row.application_id));
      if (jobId) await loadList(jobId);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const evalFor = evaluation && selected && evaluation.application_id === selected.application_id ? evaluation : null;

  return (
    <>
      <div className="row-between wrap">
        <h1 className="h1" style={{ margin: 0 }}>지원자 평가 결과</h1>
        {jobs && jobs.length > 0 && (
          <select
            style={{ maxWidth: 360 }}
            value={jobId ?? ""}
            onChange={(e) => setParams({ job: e.target.value })}
            aria-label="공고 선택"
          >
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
                {j.status === "closed" ? " (마감)" : ""}
              </option>
            ))}
          </select>
        )}
      </div>
      <ErrorBox>{error}</ErrorBox>

      {jobs === null && !error && <p className="muted">불러오는 중…</p>}
      {jobs?.length === 0 && (
        <p className="card muted">
          게시한 공고가 없습니다. <Link to="/company/jobs">채용공고 관리</Link>에서 공고를 게시하면 지원자를 볼 수 있습니다.
        </p>
      )}

      {list && (
        <>
          <p className="muted" style={{ fontSize: 14, margin: 0 }}>
            공고: <strong>{list.job_title}</strong> · 지원자 {list.items.length}명 · 적합도 순
            {pending && " · AI 분석 중인 지원자가 있습니다"}
          </p>
          {list.excluded_criteria.length > 0 && (
            <div className="alert alert-info">
              변경된 차단 기준에 해당하는 항목({list.excluded_criteria.map((c) => c.name).join(", ")})은 적합도 계산에서
              제외하고 나머지 가중치를 다시 맞췄습니다.
            </div>
          )}
          {list.items.length === 0 && <p className="card muted">아직 지원자가 없습니다.</p>}
        </>
      )}

      {list && selected && (
        <div className="split">
          <div className="stack" style={{ gap: 8 }}>
            {list.items.map((a) => (
              <button
                key={a.application_id}
                className={`pick ${a.application_id === selected.application_id ? "on" : ""}`}
                onClick={() => setSelectedId(a.application_id)}
              >
                <div className="row-between">
                  <div className="row">
                    <span className="muted" style={{ width: 16 }}>{a.rank ?? "-"}</span>
                    <div>
                      <div style={{ fontWeight: 700 }}>{a.name}</div>
                      <div className="muted" style={{ fontSize: 13 }}>
                        {experience(a.experience_months)} · {APPLICATION_STATUS_LABEL[a.status]}
                      </div>
                    </div>
                  </div>
                  {a.fit !== null ? (
                    <span className="match-num" style={{ color: "var(--green)" }}>{Math.round(a.fit)}%</span>
                  ) : (
                    <span className={`chip ${a.evaluation_status === "failed" ? "chip-red" : "chip-amber"}`}>
                      {EVALUATION_STATUS_LABEL[a.evaluation_status]}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>

          <section className="card stack">
            <div className="row-between wrap">
              <div className="row">
                <div className="avatar">{selected.name[0]}</div>
                <div>
                  <div style={{ fontWeight: 700 }}>
                    {selected.name} <span className="muted" style={{ fontWeight: 400 }}>({selected.email})</span>
                  </div>
                  <div className="muted" style={{ fontSize: 14 }}>
                    {experience(selected.experience_months)} · 지원일 {selected.applied_at.slice(0, 10)}
                  </div>
                </div>
              </div>
              <div className="row">
                <select
                  style={{ maxWidth: 140 }}
                  value={selected.status}
                  disabled={busy}
                  aria-label="지원 상태"
                  onChange={(e) => changeStatus(selected, e.target.value as ApplicationStatus)}
                >
                  {(Object.keys(APPLICATION_STATUS_LABEL) as ApplicationStatus[]).map((s) => (
                    <option key={s} value={s}>{APPLICATION_STATUS_LABEL[s]}</option>
                  ))}
                </select>
                <span className="muted" style={{ fontSize: 14, whiteSpace: "nowrap" }}>적합도</span>
                <div className="score-ring">{selected.fit !== null ? `${Math.round(selected.fit)}%` : "-"}</div>
              </div>
            </div>

            {selected.evaluation_status === "pending" && (
              <div className="alert alert-info">AI가 이력서를 평가 기준별로 분석하고 있습니다. 완료되면 자동으로 표시됩니다.</div>
            )}
            {selected.evaluation_status === "failed" && (
              <div className="alert alert-error row-between wrap">
                <span>AI 분석에 실패했습니다.{evalFor?.error && ` (${evalFor.error})`}</span>
                <button className="btn btn-small" disabled={busy} onClick={() => retry(selected)}>다시 분석</button>
              </div>
            )}

            {selected.evaluation_status === "done" && evalFor && (
              <>
                <div className="tabs">
                  <button className={tab === "summary" ? "on" : ""} onClick={() => setTab("summary")}>평가 요약</button>
                  <button className={tab === "scores" ? "on" : ""} onClick={() => setTab("scores")}>항목별 점수</button>
                  <button className={tab === "evidence" ? "on" : ""} onClick={() => setTab("evidence")}>평가 근거</button>
                </div>

                {tab === "summary" && (
                  <div className="stack" style={{ gap: 10 }}>
                    {evalFor.items.map((c) => (
                      <div key={c.criterion_id} className="skill-row" style={{ gridTemplateColumns: "130px 1fr 48px" }}>
                        <span>{c.name}</span>
                        <Meter value={c.score} tone="green" />
                        <span className="muted" style={{ textAlign: "right" }}>{c.score}</span>
                      </div>
                    ))}
                  </div>
                )}

                {tab === "scores" && (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>평가 항목</th>
                        <th className="num">가중치</th>
                        <th className="num">점수(100점)</th>
                        <th>판단 이유</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evalFor.items.map((c) => (
                        <tr key={c.criterion_id}>
                          <td>{c.name}</td>
                          <td className="num muted">{c.weight}%</td>
                          <td className="num">{c.score}</td>
                          <td className="muted">{c.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                {tab === "evidence" && (
                  <div className="stack">
                    {evalFor.items.map((c) => (
                      <div key={c.criterion_id} className="card card-tight stack" style={{ gap: 6 }}>
                        <div className="row-between">
                          <strong>{c.name}</strong>
                          <span className="row" style={{ gap: 6 }}>
                            <span className="chip chip-gray">{methodLabel(c.method)}</span>
                            <span className="match-num">{c.score}점</span>
                          </span>
                        </div>
                        <div className="muted" style={{ fontSize: 14 }}>{c.reason}</div>
                        {c.evidence.length > 0 ? (
                          c.evidence.map((q, i) => (
                            <blockquote key={i} style={{ margin: 0, paddingLeft: 10, borderLeft: "3px solid var(--line)", fontSize: 14 }}>
                              {q}
                            </blockquote>
                          ))
                        ) : (
                          <span className="field-hint">이력서에서 근거 문장을 찾지 못했습니다.</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="alert alert-info">
                  <strong>종합 의견 (AI 분석)</strong>
                  <p style={{ marginTop: 4 }}>{evalFor.summary}</p>
                </div>
              </>
            )}
            <p className="field-hint">{list.notice}</p>
          </section>
        </div>
      )}
    </>
  );
}
