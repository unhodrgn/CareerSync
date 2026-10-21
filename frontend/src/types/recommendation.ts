// Mirrors backend/app/schemas/recommendation.py.
import type { EmploymentType } from './job';

/** The only fit information a seeker sees (D1, D16). */
export type MatchLevel = '매우 적합' | '적합' | '참고';

/** No Fit, Pref, Final, per-criterion scores or weights. */
export interface RecommendedJob {
  job_id: number;
  title: string;
  company_name: string;
  location: string;
  employment_type: EmploymentType;
  deadline: string | null;
  match_level: MatchLevel;
}

export interface RecommendationList {
  items: RecommendedJob[];
  /** Jobs that passed the Pref filter but whose evaluation is not done yet; not in `items`. */
  pending_count: number;
  notice: string;
}
