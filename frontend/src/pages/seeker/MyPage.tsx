import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { APPLICATION_STATUS_LABEL, type ApplicationOut } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ErrorBox, errorText } from "../../components/ui";

export default function MyPage() {
  const { user } = useAuth();
  const [apps, setApps] = useState<ApplicationOut[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .myApplications()
      .then(setApps)
      .catch((err) => setError(errorText(err)));
  }, []);

  if (!user) return null;
  return (
    <>
      <section className="card stack">
        <h1 className="h1" style={{ margin: 0 }}>마이페이지</h1>
        <table className="table">
          <tbody>
            <tr><td className="muted" style={{ width: 140 }}>이름</td><td>{user.display_name}</td></tr>
            <tr><td className="muted">이메일</td><td>{user.email}</td></tr>
            <tr><td className="muted">가입일</td><td>{user.created_at.slice(0, 10)}</td></tr>
            <tr><td className="muted">동의 버전</td><td>{user.consent_version ?? "-"}</td></tr>
          </tbody>
        </table>
      </section>

      <section className="card stack">
        <h2 className="h2">지원 현황</h2>
        <ErrorBox>{error}</ErrorBox>
        {apps === null && !error && <p className="muted">불러오는 중…</p>}
        {apps?.length === 0 && <p className="muted">아직 지원한 공고가 없습니다.</p>}
        {apps && apps.length > 0 && (
          <table className="table">
            <thead>
              <tr><th>공고</th><th>회사</th><th>지원일</th><th className="num">상태</th></tr>
            </thead>
            <tbody>
              {apps.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/seeker/jobs/${a.job_id}`}>{a.job_title}</Link></td>
                  <td className="muted">{a.company_name}</td>
                  <td className="muted">{a.created_at.slice(0, 10)}</td>
                  <td className="num"><span className="chip chip-gray">{APPLICATION_STATUS_LABEL[a.status]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
