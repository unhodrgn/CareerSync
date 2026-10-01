import { useAuth } from "../../auth/AuthContext";

export default function MyPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
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
  );
}
