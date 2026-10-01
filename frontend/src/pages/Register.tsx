import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Role } from "../api/types";
import { homeFor, useAuth } from "../auth/AuthContext";
import { ErrorBox, Field, errorText } from "../components/ui";

export default function Register() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>("seeker");
  const [form, setForm] = useState({ email: "", password: "", display_name: "", company_name: "" });
  const [privacy, setPrivacy] = useState(false);
  const [ai, setAi] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.register({
        email: form.email,
        password: form.password,
        role,
        display_name: form.display_name,
        company_name: role === "company" ? form.company_name : null,
        consent_privacy: privacy,
        consent_ai: ai,
      });
      navigate(homeFor(await login(form.email, form.password)), { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <div className="brand brand-lg">회원가입</div>
        <div className="segmented">
          <button type="button" className={role === "seeker" ? "on" : ""} onClick={() => setRole("seeker")}>
            구직자
          </button>
          <button type="button" className={role === "company" ? "on" : ""} onClick={() => setRole("company")}>
            기업
          </button>
        </div>
        <ErrorBox>{error}</ErrorBox>
        <Field label="이메일">
          <input type="email" value={form.email} onChange={set("email")} required />
        </Field>
        <Field label="비밀번호" hint="8자 이상, 영문과 숫자를 모두 포함">
          <input type="password" value={form.password} onChange={set("password")} minLength={8} required />
        </Field>
        <Field label={role === "company" ? "담당자 이름" : "이름"}>
          <input value={form.display_name} onChange={set("display_name")} maxLength={50} required />
        </Field>
        {role === "company" && (
          <Field label="회사명">
            <input value={form.company_name} onChange={set("company_name")} maxLength={100} required />
          </Field>
        )}
        <label className="check">
          <input type="checkbox" checked={privacy} onChange={(e) => setPrivacy(e.target.checked)} />
          <span>(필수) 개인정보 수집·이용에 동의합니다.</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={ai} onChange={(e) => setAi(e.target.checked)} />
          <span>(필수) AI 분석은 참고용이며 최종 판단은 기업이 한다는 안내를 확인했습니다.</span>
        </label>
        <button className="btn btn-primary btn-block" disabled={busy || !privacy || !ai}>
          {busy ? "가입 중…" : "가입하기"}
        </button>
        <p className="muted center-text">
          이미 계정이 있나요? <Link to="/login">로그인</Link>
        </p>
      </form>
    </div>
  );
}
