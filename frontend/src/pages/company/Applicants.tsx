import { useState } from "react";
import { DemoBanner, Meter } from "../../components/ui";
import { MOCK_APPLICANTS, MOCK_CRITERIA, MOCK_JOB_TITLE, fitScore } from "../../mock/data";

type Tab = "summary" | "scores" | "evidence";

export default function Applicants() {
  const ranked = [...MOCK_APPLICANTS].sort((a, b) => fitScore(b) - fitScore(a));
  const [selectedId, setSelectedId] = useState(ranked[0].id);
  const [tab, setTab] = useState<Tab>("scores");
  const applicant = ranked.find((a) => a.id === selectedId) ?? ranked[0];
  const fit = fitScore(applicant);

  return (
    <>
      <h1 className="h1" style={{ margin: 0 }}>지원자 평가 결과</h1>
      <DemoBanner>
        지원자 평가 API가 아직 없어 예시 데이터로 표시합니다. 점수는 평가 기준 가중치로 화면에서 계산합니다.
      </DemoBanner>
      <p className="muted" style={{ fontSize: 14 }}>
        공고: <strong>{MOCK_JOB_TITLE}</strong> · 지원자 {ranked.length}명 · 적합도 순
      </p>

      <div className="split">
        <div className="stack" style={{ gap: 8 }}>
          {ranked.map((a, i) => (
            <button key={a.id} className={`pick ${a.id === applicant.id ? "on" : ""}`} onClick={() => setSelectedId(a.id)}>
              <div className="row-between">
                <div className="row">
                  <span className="muted" style={{ width: 16 }}>{i + 1}</span>
                  <div>
                    <div style={{ fontWeight: 700 }}>{a.name}</div>
                    <div className="muted" style={{ fontSize: 13 }}>
                      {a.years === 0 ? "신입" : `경력 ${a.years}년`} · {a.status}
                    </div>
                  </div>
                </div>
                <span className="match-num" style={{ color: "var(--green)" }}>{fitScore(a)}%</span>
              </div>
            </button>
          ))}
        </div>

        <section className="card stack">
          <div className="row-between">
            <div className="row">
              <div className="avatar">{applicant.name[0]}</div>
              <div>
                <div style={{ fontWeight: 700 }}>
                  {applicant.name} <span className="muted" style={{ fontWeight: 400 }}>({applicant.email})</span>
                </div>
                <div className="muted" style={{ fontSize: 14 }}>
                  {applicant.years === 0 ? "신입" : `경력 ${applicant.years}년`} · {applicant.location}
                </div>
              </div>
            </div>
            <div className="row">
              <span className="muted" style={{ fontSize: 14 }}>적합도</span>
              <div className="score-ring">{fit}%</div>
            </div>
          </div>

          <div className="tabs">
            <button className={tab === "summary" ? "on" : ""} onClick={() => setTab("summary")}>평가 요약</button>
            <button className={tab === "scores" ? "on" : ""} onClick={() => setTab("scores")}>항목별 점수</button>
            <button className={tab === "evidence" ? "on" : ""} onClick={() => setTab("evidence")}>평가 근거</button>
          </div>

          {tab === "summary" && (
            <div className="stack" style={{ gap: 10 }}>
              {MOCK_CRITERIA.map((c) => (
                <div key={c.id} className="skill-row" style={{ gridTemplateColumns: "130px 1fr 48px" }}>
                  <span>{c.name}</span>
                  <Meter value={applicant.scores[c.id]?.score ?? 0} tone="green" />
                  <span className="muted" style={{ textAlign: "right" }}>{applicant.scores[c.id]?.score ?? 0}</span>
                </div>
              ))}
            </div>
          )}

          {tab !== "summary" && (
            <table className="table">
              <thead>
                <tr>
                  <th>평가 항목</th>
                  <th className="num">가중치</th>
                  <th className="num">점수(100점)</th>
                  {tab === "evidence" && <th>평가 근거(요약)</th>}
                </tr>
              </thead>
              <tbody>
                {MOCK_CRITERIA.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td className="num muted">{c.weight}%</td>
                    <td className="num">{applicant.scores[c.id]?.score ?? "-"}</td>
                    {tab === "evidence" && <td className="muted">{applicant.scores[c.id]?.evidence}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="alert alert-info">
            <strong>종합 의견 (AI 분석)</strong>
            <p style={{ marginTop: 4 }}>{applicant.summary}</p>
          </div>
          <p className="field-hint">AI 분석은 참고용입니다. 채용 여부는 기업이 최종 판단합니다.</p>
        </section>
      </div>
    </>
  );
}
