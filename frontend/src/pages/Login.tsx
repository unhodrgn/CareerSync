import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { homeFor, useAuth } from "../auth/AuthContext";
import { ErrorBox, Field, errorText } from "../components/ui";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      navigate(homeFor(await login(email, password)), { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <div className="brand brand-lg">CareerSync</div>
        <p className="muted">기업 맞춤 평가 기준으로 지원자와 공고를 연결합니다.</p>
        <ErrorBox>{error}</ErrorBox>
        <Field label="이메일">
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <Field label="비밀번호">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "로그인 중…" : "로그인"}
        </button>
        <p className="muted center-text">
          계정이 없나요? <Link to="/register">회원가입</Link>
        </p>
        <p className="field-hint center-text">데모 계정: hr@nextcode.test(기업) · seeker@demo.test(구직자) / demo1234</p>
      </form>
    </div>
  );
}
