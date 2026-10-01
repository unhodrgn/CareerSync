import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { CATEGORY_LABEL, EMPLOYMENT_LABEL, type Importance, type Job, type SeekerCriteriaSetOut } from "../../api/types";
import { ErrorBox, errorText } from "../../components/ui";

const IMPORTANCE_CHIP: Record<Importance, string> = { 높음: "chip-red", 보통: "chip-amber", 낮음: "chip-gray" };

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [criteria, setCriteria] = useState<SeekerCriteriaSetOut | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.job(Number(id)), api.seekerCriteria(Number(id))])
      .then(([j, c]) => {
        setJob(j);
        setCriteria(c);
      })
      .catch((err) => setError(errorText(err)));
  }, [id]);

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
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn btn-primary" disabled title="지원 기능은 준비 중입니다.">지원하기 (준비 중)</button>
        </div>
      </section>
    </>
  );
}
