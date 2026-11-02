import type { CriterionView } from './criteria'

export type Page = 'home' | 'jobs' | 'detail' | 'login' | 'signup' | 'register' | 'consent' | 'dashboard' | 'resume' | 'matches' | 'profile' | 'applications' | 'company' | 'post' | 'criteria' | 'candidates'
/** Fields of the registration form (AuthPage); mapped to RegisterIn in the store. */
export interface RegisterForm {
  role: 'seeker' | 'company'
  displayName: string
  companyName: string
  email: string
  password: string
  consentPrivacy: boolean
  consentAi: boolean
}

/** A job as the cards and lists show it; built from the backend DTOs by services/jobView.ts. */
export interface Job {
  id: number
  companyId: number
  company: string
  /** First letter of the company name (no logo images yet). */
  logo: string
  /** CSS colour class for the logo, stable per company. */
  color: string
  title: string
  location: string
  /** 정규직 / 계약직 / 인턴 (full time / contract / intern). */
  employment: string
  /** 신입 가능 (entry level) or 경력 N년 이상 (N+ years). */
  experience: string
  /** `YYYY-MM-DD`, or null when the job is always open. */
  deadline: string | null
  /** 상시 채용 (always open), D-day, D-N or 마감 (closed). */
  dDay: string
  /** Skills computed by the backend from the criteria and the JD (D45); may be empty. */
  tags: string[]
}

/** The job detail page: the job plus the JD text, salary note and criteria names. */
export interface JobDetail extends Job {
  description: string
  salaryNote: string
  expired: boolean
  /** Guests see names only (D35); signed-in seekers also the importance (D30). */
  criteria: CriterionView[]
}
