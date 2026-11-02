// Mirrors the seeker side of backend/app/schemas/application.py.

export type ApplicationStatus = 'submitted' | 'reviewing' | 'interview' | 'on_hold' | 'passed' | 'rejected'
export type EvaluationStatus = 'pending' | 'done' | 'failed'

/** One application; its status changes only by a recruiter action (AI rule 5). There is no score (D1, D44). */
export interface ApplicationOut {
  id: number
  job_id: number
  job_title: string
  company_name: string
  status: ApplicationStatus
  evaluation_status: EvaluationStatus | null
  created_at: string
}
