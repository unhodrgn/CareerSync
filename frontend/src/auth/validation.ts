// Client checks that mirror backend/app/schemas/auth.py (RegisterIn, LoginIn), so most errors show before the
// request; the server stays the authority and its 422 is mapped back onto the same fields.
import { ApiError, issueText } from '@/api/client';
import type { MessageKey } from '@/i18n';
import type { Role } from '@/types/common';

export type RegisterField = 'email' | 'password' | 'confirm' | 'name' | 'company' | 'consent';

export interface RegisterValues {
  email: string;
  password: string;
  confirm: string;
  name: string;
  company: string;
  privacy: boolean;
  ai: boolean;
}

// Same pattern as the backend's _EMAIL
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function emailError(email: string): MessageKey | null {
  const v = email.trim();
  if (!v) return 'auth.error.emailRequired';
  if (v.length > 255) return 'auth.error.emailTooLong';
  if (!EMAIL.test(v)) return 'auth.error.emailFormat';
  return null;
}

export function validateRegister(v: RegisterValues, role: Role): Partial<Record<RegisterField, MessageKey>> {
  const errors: Partial<Record<RegisterField, MessageKey>> = {};
  const email = emailError(v.email);
  if (email) errors.email = email;

  if (!v.password) errors.password = 'auth.error.passwordRequired';
  else if (v.password.length < 8) errors.password = 'auth.error.passwordShort';
  else if (v.password.length > 128) errors.password = 'auth.error.passwordLong';
  else if (!(/[A-Za-z]/.test(v.password) && /\d/.test(v.password))) errors.password = 'auth.error.passwordMix';

  if (v.confirm !== v.password || (!v.confirm && v.password)) errors.confirm = 'auth.error.passwordMismatch';

  const name = v.name.trim();
  if (!name) errors.name = 'auth.error.nameRequired';
  else if (name.length > 50) errors.name = 'auth.error.nameTooLong';

  if (role === 'company') {
    const company = v.company.trim();
    if (!company) errors.company = 'auth.error.companyRequired';
    else if (company.length > 100) errors.company = 'auth.error.companyTooLong';
  }

  if (!(v.privacy && v.ai)) errors.consent = 'auth.error.consentRequired';
  return errors;
}

/** Backend body field → form field. */
const SERVER_FIELD: Record<string, RegisterField> = {
  email: 'email',
  password: 'password',
  display_name: 'name',
  company_name: 'company',
  consent_privacy: 'consent',
  consent_ai: 'consent',
};

/**
 * A 422 from the server spread over the form: per field, the backend's own Korean text for custom rules
 * (`value_error`), else a generic prompt; issues without a field go to the form-level list.
 */
export function serverIssues(error: ApiError): { fields: Partial<Record<RegisterField, string>>; form: string[] } {
  const fields: Partial<Record<RegisterField, string>> = {};
  const form: string[] = [];
  for (const [name, issue] of Object.entries(error.fields)) {
    const field = SERVER_FIELD[name];
    const text = issue.type === 'value_error' ? issueText(issue) : null;
    if (field) fields[field] ??= text ?? '';
    else form.push(text ?? name);
  }
  for (const issue of error.form) form.push(issueText(issue));
  return { fields, form };
}
