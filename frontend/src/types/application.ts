// Mirrors backend/app/schemas/application.py (seeker side; the recruiter's types come with the company pages).

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
