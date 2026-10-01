import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { EMPLOYMENT_LABEL, type JobListItem } from "../../api/types";
import { DemoBanner, ErrorBox, Meter, errorText } from "../../components/ui";
import { demoMatch } from "../../mock/data";

export default function Recommended() {
  const [query, setQuery] = useState("");
  const [jobs, setJobs] = useState<JobListItem[] | null>(null);
  const [error, setError] = useState("");
  const [liked, setLiked] = useState<Set<number>>(new Set());

  useEffect(() => {
    const timer = setTimeout(() => {
      api
        .publicJobs(query.trim())
        .then((page) => {
          setError("");
          setJobs([...page.items].sort((a, b) => demoMatch(b.id) - demoMatch(a.id)));
        })
        .catch((err) => setError(errorText(err)));
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const toggle = (id: number) =>
    setLiked((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <>
      <input
        className="search"
        placeholder="관심 직무를 검색해 보세요. (예: 백엔드, 데이터, AI…)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <h1 className="h1" style={{ margin: 0 }}>나에게 추천하는 채용공고</h1>
      <DemoBanner>
        공고는 실제 게시된 공고입니다. 추천 API가 아직 없어 매칭도는 예시 값입니다.
      </DemoBanner>
      <ErrorBox>{error}</ErrorBox>
      {jobs === null && !error && <p className="muted">불러오는 중…</p>}
      {jobs?.length === 0 && <p className="card muted">조건에 맞는 공고가 없습니다.</p>}
      {jobs?.map((job) => {
        const match = demoMatch(job.id);
        return (
          <div key={job.id} className="card card-tight job-card">
            <Link to={`/seeker/jobs/${job.id}`} style={{ color: "inherit", flex: 1 }}>
              <div className="job-title">{job.title}</div>
              <div className="muted" style={{ fontSize: 14 }}>
                {job.company_name} · {job.min_experience_years === null ? "신입 가능" : `경력 ${job.min_experience_years}년 이상`} ·{" "}
                {job.location || "근무지 미정"}
              </div>
              <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
                <span className="chip">{EMPLOYMENT_LABEL[job.employment_type]}</span>
                {job.deadline && <span className="chip chip-gray">마감 {job.deadline}</span>}
              </div>
            </Link>
            <div className="match">
              <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
                <span className="match-num">매칭도 {match}%</span>
                <button
                  className="btn btn-ghost btn-small"
                  aria-label="관심 공고"
                  style={{ color: liked.has(job.id) ? "var(--red)" : undefined, fontSize: 18 }}
                  onClick={() => toggle(job.id)}
                >
                  {liked.has(job.id) ? "♥" : "♡"}
                </button>
              </div>
              <Meter value={match} />
            </div>
          </div>
        );
      })}
    </>
  );
}
