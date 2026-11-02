// Mirrors backend/app/schemas/recommendation.py.
import type { EmploymentType } from './job'

/** 매우 적합 / 적합 / 참고 (very good / good / reference), taken from the match score. */
export type MatchLevel = '매우 적합' | '적합' | '참고'

/**
 * One recommended job. `match_score` is Final rounded to an integer 0–100 (D42); Fit, Pref, per-criterion scores
 * and weights are never sent. Strengths and gaps (at most 3 each) are skills the job names that the CV text shows or
 * lacks, computed from text, not from scores (D43).
 */
export interface RecommendedJob {
  job_id: number
  title: string
  company_name: string
  location: string
  employment_type: EmploymentType
  /** `YYYY-MM-DD` or null (상시 채용, always open). */
  deadline: string | null
  match_score: number
  match_level: MatchLevel
  strengths: string[]
  gaps: string[]
}

export interface RecommendationList {
  items: RecommendedJob[]
  /** Jobs that passed the preferences but are still being scored; not in `items`. */
  pending_count: number
  notice: string
}

/** GET /api/jobs/{id}/match (D44): read only, never starts scoring. `none` also for applied jobs. */
export interface JobMatch {
  job_id: number
  match_score: number | null
  match_level: MatchLevel | null
  status: 'done' | 'pending' | 'none'
  notice: string
}
