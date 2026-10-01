import { useEffect, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import { ErrorBox, Field, errorText } from "../../components/ui";

export default function CompanyProfile() {
  const [form, setForm] = useState({ name: "", intro: "", talent_profile: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .myCompany()
      .then(({ name, intro, talent_profile }) => setForm({ name, intro, talent_profile }))
      .catch((err) => setError(errorText(err)))
      .finally(() => setLoading(false));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await api.updateCompany(form);
      setSaved(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="muted center-text">불러오는 중…</p>;

  return (
    <form className="card stack" onSubmit={submit}>
      <h1 className="h1" style={{ margin: 0 }}>기업 프로필</h1>
      <ErrorBox>{error}</ErrorBox>
      {saved && <div className="alert alert-ok">저장했습니다.</div>}
      <Field label="회사명">
        <input value={form.name} maxLength={100} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </Field>
      <Field label="회사 소개">
        <textarea value={form.intro} maxLength={1000} onChange={(e) => setForm({ ...form, intro: e.target.value })} />
      </Field>
      <Field label="인재상" hint="구직자에게 공개되는 회사의 인재상입니다.">
        <textarea value={form.talent_profile} maxLength={1000} onChange={(e) => setForm({ ...form, talent_profile: e.target.value })} />
      </Field>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-primary" disabled={busy}>{busy ? "저장 중…" : "저장"}</button>
      </div>
    </form>
  );
}
