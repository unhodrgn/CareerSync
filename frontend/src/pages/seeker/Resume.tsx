import { useState } from "react";
import { DemoBanner, Meter } from "../../components/ui";
import { MOCK_RESUME } from "../../mock/data";

type Tab = "basic" | "skills" | "summary";

export default function Resume() {
  const [tab, setTab] = useState<Tab>("skills");
  const r = MOCK_RESUME;

  return (
    <>
      <h1 className="h1" style={{ margin: 0 }}>이력서 분석 결과</h1>
      <DemoBanner>이력서 업로드·분석 API가 아직 없어 예시 결과로 표시합니다.</DemoBanner>

      <div className="card card-tight row-between wrap">
        <div className="row">
          <span className="chip chip-green">✓</span>
          <span>이력서 분석이 완료되었습니다.</span>
          <span className="muted" style={{ fontSize: 14 }}>{r.fileName} · {r.analyzedAt}</span>
        </div>
        <button className="btn btn-small" disabled title="업로드 기능은 준비 중입니다.">새 이력서 업로드 (PDF)</button>
      </div>

      <section className="card stack">
        <div className="tabs">
          <button className={tab === "basic" ? "on" : ""} onClick={() => setTab("basic")}>기본 정보</button>
          <button className={tab === "skills" ? "on" : ""} onClick={() => setTab("skills")}>주요 역량</button>
          <button className={tab === "summary" ? "on" : ""} onClick={() => setTab("summary")}>분석 요약</button>
        </div>

        {tab === "basic" && (
          <table className="table">
            <tbody>
              {Object.entries(r.basic).map(([k, v]) => (
                <tr key={k}>
                  <td className="muted" style={{ width: 140 }}>{k}</td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab !== "basic" && (
          <div className="grid-2" style={{ alignItems: "start" }}>
            <div className="stack" style={{ gap: 12 }}>
              <h2 className="h2">추출된 주요 역량</h2>
              {r.skills.map((s) => (
                <div key={s.name} className="skill-row">
                  <span>{s.name}</span>
                  <Meter value={s.level} />
                  <span className="muted" style={{ textAlign: "right" }}>{s.years}년</span>
                </div>
              ))}
            </div>
            <div className="stack" style={{ gap: 8 }}>
              <h2 className="h2">분석 요약</h2>
              <p className="muted" style={{ fontSize: 14 }}>{r.summary}</p>
            </div>
          </div>
        )}

        <p className="field-hint">
          개인정보 보호를 위해 {r.masked.join(", ")}은(는) 분석 전에 가려집니다. AI 분석 결과는 참고용입니다.
        </p>
      </section>
    </>
  );
}
