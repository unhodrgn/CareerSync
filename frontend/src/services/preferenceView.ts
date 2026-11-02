// GET/PUT /api/preferences/me ↔ the profile form. The talent-pool opt-in (profile_public) is not on this form:
// it is sent back exactly as stored, so saving the profile never turns it on or off.
import type { EmploymentType } from '../types/job'
import type { ExperienceLevel, PreferenceIn, PreferenceOut } from '../types/preference'

export interface PreferenceForm {
  jobKeywords: string[]
  locations: string[]
  employmentTypes: EmploymentType[]
  /** '' = not chosen. Display only (D46). */
  experienceLevel: ExperienceLevel | ''
  /** Display only (D46). */
  skills: string[]
}

export function toPreferenceForm(prefs: PreferenceOut | null): PreferenceForm {
  return {
    jobKeywords: prefs?.job_keywords ?? [],
    locations: prefs?.locations ?? [],
    employmentTypes: prefs?.employment_types ?? [],
    experienceLevel: prefs?.experience_level ?? '',
    skills: prefs?.skills ?? [],
  }
}

/** Trimmed, empty items dropped. Both display-only fields are always sent, so clearing them works. */
export function toPreferenceIn(form: PreferenceForm, stored: PreferenceOut | null): PreferenceIn {
  const clean = (items: string[]) => items.map(s => s.trim()).filter(Boolean)
  return {
    locations: clean(form.locations),
    employment_types: form.employmentTypes,
    job_keywords: clean(form.jobKeywords),
    profile_public: stored?.profile_public ?? false,
    experience_level: form.experienceLevel || null,
    skills: clean(form.skills),
  }
}
