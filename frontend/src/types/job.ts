// Mirrors backend/app/schemas/job.py.

export type EmploymentType = 'full_time' | 'contract' | 'intern'
export type JobStatusName = 'draft' | 'published' | 'closed'
/** Job field for the public filter (D45); the Korean labels are in data/categories.ts. */
export type JobCategory = 'dev' | 'data_ai' | 'design' | 'marketing' | 'planning'

export interface JobOut {
  id: number
  company_id: number
  company_name: string
  title: string
  description: string
  employment_type: EmploymentType
  /** null = 신입 가능 (entry level). */
  min_experience_years: number | null
  location: string
  salary_note: string
  /** `YYYY-MM-DD` or null (상시 채용, always open). */
  deadline: string | null
  /** The deadline has passed (shown as 마감); status is unchanged. */
  expired: boolean
  status: JobStatusName
  criteria_count: number
  published_at: string | null
  closed_at: string | null
  created_at: string
  updated_at: string
  /** null for jobs published before categories existed. */
  category: JobCategory | null
  /** Skills the criteria and the JD name (data/skills.yaml); display and search only, never scored. */
  tags: string[]
  /** 모집 인원 (number of hires, D47); null = not stated. Never scored. */
  headcount: number | null
}

/** POST /api/jobs: always creates a draft. `category` and a non-empty `description` are needed to publish. */
export interface JobCreate {
  title: string
  description: string
  employment_type: EmploymentType
  /** 0–30; null = 신입 가능 (entry level). */
  min_experience_years: number | null
  location: string
  salary_note: string
  /** `YYYY-MM-DD`, today or later; null = 상시 채용 (always open). */
  deadline: string | null
  category: JobCategory | null
  /** 1–999; null = not stated. */
  headcount: number | null
}

/** PATCH /api/jobs/{id}: only the fields sent change. After publish only deadline, location and salary_note. */
export type JobUpdate = Partial<JobCreate>

export interface JobListItem {
  id: number
  company_id: number
  company_name: string
  title: string
  employment_type: EmploymentType
  min_experience_years: number | null
  location: string
  deadline: string | null
  status: JobStatusName
  expired: boolean
  criteria_count: number
  published_at: string | null
  category: JobCategory | null
  tags: string[]
}

export interface JobPage {
  items: JobListItem[]
  total: number
  limit: number
  offset: number
}
