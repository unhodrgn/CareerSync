import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import {
  APPLICATION_STATUS_LABEL,
  CATEGORY_LABEL,
  EMPLOYMENT_LABEL,
  type ApplicationOut,
  type Importance,
  type Job,
  type SeekerCriteriaSetOut,
} from "../../api/types";
import { ErrorBox, errorText } from "../../components/ui";

const IMPORTANCE_CHIP: Record<Importance, string> = { 높음: "chip-red", 보통: "chip-amber", 낮음: "chip-gray" };

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [criteria, setCriteria] = useState<SeekerCriteriaSetOut | null>(null);
  const [applied, setApplied] = useState<ApplicationOut | null>(null);
  const [error, setError] = useState("");
  const [applyError, setApplyError] = useState("");
  const [applying, setApplying] = useState(false);
  const [needCv, setNeedCv] = useState(false);

  useEffect(() => {
    Promise.all([api.job(Number(id)), api.seekerCriteria(Number(id)), api.myApplications()])
      .then(([j, c, mine]) => {
        setJob(j);
        setCriteria(c);
        setApplied(mine.find((a) => a.job_id === j.id) ?? null);
      })
      .catch((err) => setError(errorText(err)));
  }, [id]);

  async function apply() {
    if (!job || !window.confirm(`"${job.title}" 공고에 확인된 최신 이력서로 지원할까요?`)) return;
    setApplying(true);
    setApplyError("");
    setNeedCv(false);
    try {
      setApplied(await api.apply(job.id));
    } catch (err) {
      setApplyError(errorText(err));
      if (err instanceof ApiError && err.code === "CV_NOT_CONFIRMED") setNeedCv(true);
    } finally {
      setApplying(false);
    }
  }

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!job) return <p className="muted center-text">불러오는 중…</p>;

  return (
    <>
      <Link to="/seeker">← 추천 공고</Link>
      <section className="card stack">
        <div>
          <h1 className="h1" style={{ marginBottom: 4 }}>{job.title}</h1>
          <p className="muted">
            {job.company_name} · {EMPLOYMENT_LABEL[job.employment_type]} · {job.location || "근무지 미정"} ·{" "}
            {job.min_experience_years === null ? "신입 가능" : `경력 ${job.min_experience_years}년 이상`}
            {job.salary_note && ` · ${job.salary_note}`}
            {job.deadline && ` · 마감 ${job.deadline}`}
          </p>
        </div>
        <div style={{ whiteSpace: "pre-wrap" }}>{job.description}</div>
      </section>

      <section className="card stack">
        <div>
          <h2 className="h2">이 공고의 평가 기준</h2>
          <p className="muted" style={{ fontSize: 14 }}>기업이 지원자를 평가할 때 보는 항목과 중요도입니다.</p>
        </div>
        <table className="table">
          <thead>
            <tr><th>평가 항목</th><th>분류</th><th className="num">중요도</th></tr>
          </thead>
          <tbody>
            {criteria?.items.map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td className="muted">{CATEGORY_LABEL[c.category]}</td>
                <td className="num"><span className={`chip ${IMPORTANCE_CHIP[c.importance]}`}>{c.importance}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {applyError && (
          <ErrorBox>
            {applyError}
            {needCv && (
              <>
                {" "}
                <Link to="/seeker/resume">내 이력서로 가기</Link>
              </>
            )}
          </ErrorBox>
        )}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          {applied ? (
            <span className="chip chip-green">
              지원 완료 · {applied.created_at.slice(0, 10)} · {APPLICATION_STATUS_LABEL[applied.status]}
            </span>
          ) : (
            <button className="btn btn-primary" disabled={applying || job.expired || job.status !== "published"} onClick={apply}>
              {applying ? "지원 중…" : job.expired || job.status !== "published" ? "마감된 공고" : "지원하기"}
            </button>
          )}
        </div>
        <p className="field-hint" style={{ textAlign: "right" }}>
          지원하면 이 공고의 평가 기준으로 AI가 이력서를 분석합니다. 결과는 참고용이며 채용 여부는 기업이 판단합니다.
        </p>
      </section>
    </>
  );
}
