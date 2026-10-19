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
