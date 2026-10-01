// Mirrors backend/app/schemas. Keep in sync with /openapi.json.

export type Role = "seeker" | "company";
export type EmploymentType = "full_time" | "contract" | "intern";
export type JobStatus = "draft" | "published" | "closed";
export type Category = "skill" | "experience" | "project" | "certificate" | "education" | "other";
export type Importance = "높음" | "보통" | "낮음";

export interface User {
  id: number;
  email: string;
  role: Role;
  display_name: string;
  company_id: number | null;
  consent_version: string | null;
  created_at: string;
}

export interface RegisterBody {
  email: string;
  password: string;
  role: Role;
  display_name: string;
  company_name?: string | null;
  consent_privacy: boolean;
  consent_ai: boolean;
}

export interface Company {
  id: number;
  name: string;
  intro: string;
  talent_profile: string;
}

export interface Job {
  id: number;
  company_id: number;
  company_name: string;
  title: string;
  description: string;
  employment_type: EmploymentType;
  min_experience_years: number | null;
  location: string;
  salary_note: string;
  deadline: string | null;
  expired: boolean;
  status: JobStatus;
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
  status: JobStatus;
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

export interface JobInput {
  title: string;
  description: string;
  employment_type: EmploymentType;
  min_experience_years: number | null;
  location: string;
  salary_note: string;
  deadline: string | null;
}

export interface CriterionIn {
  id?: number | null;
  name: string;
  description: string;
  category: Category;
  weight: number;
}

export interface CriterionOut {
  id: number;
  name: string;
  description: string;
  category: Category;
  weight: number;
  position: number;
  importance: Importance;
}

export interface CriteriaSetOut {
  job_id: number;
  items: CriterionOut[];
  total_weight: number;
  blocklist_version: string;
}

export interface SeekerCriterionOut {
  name: string;
  category: Category;
  importance: Importance;
}

export interface SeekerCriteriaSetOut {
  job_id: number;
  items: SeekerCriterionOut[];
}

export interface GuardrailHit {
  index: number | null;
  field: string;
  rule_id: string;
  category: string;
  matched: string;
  reason: string;
  law_ref: string;
}

export interface CheckResult {
  allowed: boolean;
  hits: GuardrailHit[];
  blocklist_version: string;
}

export const EMPLOYMENT_LABEL: Record<EmploymentType, string> = {
  full_time: "정규직",
  contract: "계약직",
  intern: "인턴",
};

export const STATUS_LABEL: Record<JobStatus, string> = {
  draft: "작성 중",
  published: "게시 중",
  closed: "마감",
};

export const CATEGORY_LABEL: Record<Category, string> = {
  skill: "기술",
  experience: "경력",
  project: "프로젝트",
  certificate: "자격증",
  education: "학력(전공·학위)",
  other: "기타",
};
