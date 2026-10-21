// Mirrors backend/app/schemas/application.py.

export type ApplicationStatus = 'submitted' | 'reviewing' | 'interview' | 'on_hold' | 'passed' | 'rejected';
export type EvaluationStatus = 'pending' | 'done' | 'failed';

export const APPLICATION_STATUSES: ApplicationStatus[] = ['submitted', 'reviewing', 'interview', 'on_hold', 'passed', 'rejected'];

export interface ApplicationOut {
  id: number;
  job_id: number;
  job_title: string;
  company_name: string;
  status: ApplicationStatus;
  evaluation_status: EvaluationStatus | null;
  created_at: string;
}

// Recruiter side

export interface CriterionBrief {
  id: number;
  name: string;
  category: string;
  /** Effective weight used for Fit (criteria a newer blocklist blocks are left out and the rest rescaled). */
  weight: number;
}

export interface ScoreBrief {
  criterion_id: number;
  score: number;
}

export interface ApplicantRow {
  application_id: number;
  /** null while the evaluation is pending or failed. */
  rank: number | null;
  name: string;
  email: string;
  status: ApplicationStatus;
  applied_at: string;
  experience_months: number;
  evaluation_status: EvaluationStatus;
  fit: number | null;
  /** Criteria scored at or above the strong level (75). */
  strong_count: number;
  scores: ScoreBrief[];
}

export interface ExcludedBrief {
  id: number;
  name: string;
}

export interface ApplicantList {
  job_id: number;
  job_title: string;
  criteria: CriterionBrief[];
  excluded_criteria: ExcludedBrief[];
  /** Applicants before the quick filters; ranks are over all of them (D22). */
  total_count: number;
  items: ApplicantRow[];
  notice: string;
}

export interface ApplicantFilters {
  status?: ApplicationStatus[];
  min_fit?: number;
  evaluation_status?: EvaluationStatus;
}

export interface CriterionEvaluation {
  criterion_id: number;
  name: string;
  description: string;
  category: string;
  weight: number;
  score: number;
  /** Nearest of 0, 25, 50, 75, 100. */
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
