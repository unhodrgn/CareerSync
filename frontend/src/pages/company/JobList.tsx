import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { EMPLOYMENT_LABEL, STATUS_LABEL, type JobListItem } from "../../api/types";
import { ErrorBox, errorText } from "../../components/ui";

export default function JobList() {
  const [jobs, setJobs] = useState<JobListItem[] | null>(null);
  const [error, setError] = useState("");

  const load = () =>
    api
      .myJobs()
      .then(setJobs)
      .catch((err) => setError(errorText(err)));

  useEffect(() => {
    load();
  }, []);

  async function remove(job: JobListItem) {
    if (!window.confirm(`"${job.title}" 공고를 삭제할까요?`)) return;
    try {
      await api.deleteJob(job.id);
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <>
      <div className="row-between">
        <h1 className="h1" style={{ margin: 0 }}>채용공고 관리</h1>
        <Link className="btn btn-primary" to="/company/jobs/new">+ 새 공고 등록</Link>
      </div>
      <ErrorBox>{error}</ErrorBox>
      {jobs === null && !error && <p className="muted">불러오는 중…</p>}
      {jobs?.length === 0 && <p className="card muted">등록한 공고가 없습니다. 새 공고를 등록해 보세요.</p>}
      {jobs?.map((job) => (
        <div className="card card-tight row-between wrap" key={job.id}>
          <div>
            <div className="job-title">{job.title}</div>
            <div className="muted" style={{ fontSize: 14 }}>
              {EMPLOYMENT_LABEL[job.employment_type]} · {job.location || "근무지 미정"} ·{" "}
              {job.min_experience_years === null ? "신입 가능" : `경력 ${job.min_experience_years}년 이상`} · 평가 항목 {job.criteria_count}개
              {job.deadline && ` · 마감 ${job.deadline}`}
            </div>
          </div>
          <div className="row">
            <span className={`chip ${job.status === "published" ? "chip-green" : "chip-gray"}`}>
              {job.status === "published" && job.expired ? "기간 만료" : STATUS_LABEL[job.status]}
            </span>
            <Link className="btn btn-small" to={`/company/jobs/${job.id}/edit`}>
              {job.status === "draft" ? "이어서 작성" : "보기·수정"}
            </Link>
            {job.status === "draft" && (
              <button className="btn btn-small btn-danger" onClick={() => remove(job)}>삭제</button>
            )}
          </div>
        </div>
      ))}
    </>
  );
}
