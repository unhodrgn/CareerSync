// Mirrors backend/app/schemas/preference.py.
import type { EmploymentType } from './job'

/** Self-declared 경력 수준; display only, never scored (D46). */
export type ExperienceLevel = 'new' | 'junior' | 'mid' | 'senior'

export interface PreferenceIn {
  locations: string[]
  employment_types: EmploymentType[]
  job_keywords: string[]
  /** The talent-pool opt-in; this page sends back the stored value unchanged. */
  profile_public: boolean
  /** Display only (D46); left out = unchanged. */
  experience_level?: ExperienceLevel | null
  /** Display only (D46), at most 20; the server normalizes them with data/skills.yaml. Left out = unchanged. */
  skills?: string[]
}

export interface PreferenceOut {
  locations: string[]
  employment_types: EmploymentType[]
  job_keywords: string[]
  profile_public: boolean
  profile_public_at: string | null
  updated_at: string | null
  experience_level: ExperienceLevel | null
  skills: string[]
}
