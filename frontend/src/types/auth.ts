// Mirrors backend/app/schemas/auth.py.
import type { Role } from './common';

export interface RegisterIn {
  email: string;
  password: string;
  role: Role;
  display_name: string;
  /** Required when role is company; ignored for seekers. */
  company_name: string | null;
  consent_privacy: boolean;
  consent_ai: boolean;
}

export interface LoginIn {
  email: string;
  password: string;
}

export interface TokenOut {
  access_token: string;
  token_type: 'bearer';
  /** Seconds until the token expires. */
  expires_in: number;
}

export interface UserOut {
  id: number;
  email: string;
  role: Role;
  display_name: string;
  company_id: number | null;
  consent_version: string | null;
  created_at: string;
  /** The consent text version the server asks for now. */
  current_consent_version: string;
  /** True when the user must (re-)consent: AI consent withdrawn or given to an older version. */
  consent_required: boolean;
}

export interface ConsentIn {
  /** Must equal `current_consent_version`. */
  version: string;
  consent_privacy: boolean;
  consent_ai: boolean;
}
