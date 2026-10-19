// Mirrors backend/app/schemas/job.py.

export type EmploymentType = 'full_time' | 'contract' | 'intern';
export type JobStatusName = 'draft' | 'published' | 'closed';

export interface JobOut {
  id: number;
  company_id: number;
  company_name: string;
  title: string;
  description: string;
  employment_type: EmploymentType;
  /** null = 신입 가능. */
  min_experience_years: number | null;
  location: string;
  salary_note: string;
  /** `YYYY-MM-DD` or null (상시 채용). */
  deadline: string | null;
  /** The deadline has passed (shown as 마감); status is unchanged. */
  expired: boolean;
  status: JobStatusName;
  criteria_count: number;
  published_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobListItem {
  id: number;
  company_id: number;
  company_name: string;
  title: string;
  employment_type: EmploymentType;
  min_experience_years: number | null;
  location: string;
  deadline: string | null;
  status: JobStatusName;
  expired: boolean;
  criteria_count: number;
  published_at: string | null;
}

export interface JobPage {
  items: JobListItem[];
  total: number;
  limit: number;
  offset: number;
}

export const EMPLOYMENT_TYPES: EmploymentType[] = ['full_time', 'contract', 'intern'];

export interface JobCreate {
  title: string;
  description: string;
  employment_type: EmploymentType;
  min_experience_years: number | null;
  location: string;
  salary_note: string;
  deadline: string | null;
}

/** Partial update: only the fields sent change. After publish only deadline, location and salary_note. */
export type JobUpdate = Partial<JobCreate>;

export interface SuggestedCriterion {
  name: string;
  description: string;
  category: string;
  weight: number;
}

export interface BlockedSuggestion {
  name: string;
  /** CRITERIA_BLOCKED (legal guardrail) or CRITERIA_MAJOR_REQUIRED (education without a major, D13). */
  code: string;
  reason: string;
}

export interface JdAnalysisOut {
  job_id: number;
  analysis: { profile: Record<string, unknown>; criteria: SuggestedCriterion[] };
  blocked: BlockedSuggestion[];
  method: string;
  notice: string;
}

export interface JdDraftIn {
  keywords: string[];
  notes: string;
  project_ids: number[];
}

export interface JdDraftOut {
  job_id: number;
  /** The assembled JD text. */
  description: string;
  sections: { intro: string; responsibilities: string[]; requirements: string[]; preferred: string[] };
  dropped: { text: string; reason: string }[];
  method: string;
  limited: boolean;
  notice: string;
}
