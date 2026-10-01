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

// ── CV (schema cv_profile.v1) ──

export interface Experience {
  org: string;
  role: string;
  start: string | null; // YYYY-MM
  end: string | null; // YYYY-MM, null if current
  description: string;
  source: string;
}

export interface Project {
  name: string;
  role: string;
  tech: string[];
  description: string;
  source: string;
}

export interface Education {
  school: string;
  major: string;
  degree: string;
  source: string;
}

export interface Certificate {
  name: string;
  date: string | null;
  source: string;
}

export interface CvProfile {
  skills: string[];
  experiences: Experience[];
  projects: Project[];
  education: Education[];
  certificates: Certificate[];
  summary: string;
}

export interface CvOut {
  id: number;
  document_id: number;
  file_name: string;
  pages: number;
  version: number;
  profile: CvProfile;
  method: string; // "rules", "llm:<model>" or "seeker"
  confirmed: boolean;
  confirmed_at: string | null;
  masked_kinds: string[];
  total_experience_months: number;
  created_at: string;
}

export const MASKED_LABEL: Record<string, string> = {
  email: "이메일",
  phone: "전화번호",
  url: "URL",
  rrn: "주민등록번호",
  birth: "생년월일",
  address: "주소",
  name: "이름",
};

// ── Applications and evaluations ──

export type ApplicationStatus = "submitted" | "reviewing" | "interview" | "on_hold" | "passed" | "rejected";
export type EvaluationStatus = "pending" | "done" | "failed";

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  submitted: "검토 전",
  reviewing: "서류 검토",
  interview: "면접 예정",
  on_hold: "보류",
  passed: "합격",
  rejected: "불합격",
};

export const EVALUATION_STATUS_LABEL: Record<EvaluationStatus, string> = {
  pending: "AI 분석 중",
  done: "분석 완료",
  failed: "분석 실패",
};

export interface ApplicationOut {
  id: number;
  job_id: number;
  job_title: string;
  company_name: string;
  status: ApplicationStatus;
  evaluation_status: EvaluationStatus | null;
  created_at: string;
}

export interface CriterionBrief {
  id: number;
  name: string;
  category: Category;
  weight: number; // effective weight used for Fit
}

export interface ExcludedBrief {
  id: number;
  name: string;
}

export interface ApplicantRow {
  application_id: number;
  rank: number | null;
  name: string;
  email: string;
  status: ApplicationStatus;
  applied_at: string;
  experience_months: number;
  evaluation_status: EvaluationStatus;
  fit: number | null;
  strong_count: number;
  scores: { criterion_id: number; score: number }[];
}

export interface ApplicantList {
  job_id: number;
  job_title: string;
  criteria: CriterionBrief[];
  excluded_criteria: ExcludedBrief[];
  items: ApplicantRow[];
  notice: string;
}

export interface CriterionEvaluation {
  criterion_id: number;
  name: string;
  description: string;
  category: Category;
  weight: number;
  score: number;
  level: number;
  reason: string;
  evidence: string[];
  method: string;
}

export interface EvaluationOut {
  application_id: number;
  job_id: number;
  name: string;
  status: EvaluationStatus;
  error: string;
  fit: number | null;
  summary: string;
  items: CriterionEvaluation[];
  excluded_criteria: ExcludedBrief[];
  llm_model: string;
  embedding_model: string;
  prompt_version: string;
  finished_at: string | null;
  notice: string;
}
