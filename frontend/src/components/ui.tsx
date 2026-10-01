import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "알 수 없는 오류가 발생했습니다.";
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return children ? <div className="alert alert-error">{children}</div> : null;
}

/** Marks screens whose data is not backed by the API yet. */
export function DemoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="alert alert-demo">
      <strong>데모 화면</strong> {children}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Meter({ value, tone = "blue" }: { value: number; tone?: "blue" | "green" }) {
  return (
    <div className="meter" aria-label={`${value}%`}>
      <div className={`meter-fill ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function ComingSoon({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card">
      <h1 className="h1">{title}</h1>
      <div className="muted">{children}</div>
    </section>
  );
}
