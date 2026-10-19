// Mirrors backend/app/schemas/preference.py.
import type { EmploymentType } from './job';

/** Max items per list (PreferenceIn MAX_ITEMS). */
export const PREFERENCE_MAX_ITEMS = 10;

export interface PreferenceIn {
  locations: string[];
  employment_types: EmploymentType[];
  job_keywords: string[];
  /** Opt-in to appear anonymously in talent recommendation. */
  profile_public: boolean;
}

export interface PreferenceOut extends PreferenceIn {
  profile_public_at: string | null;
  updated_at: string | null;
}
