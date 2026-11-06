// Mirrors backend/app/schemas/recommendation.py.
import type { Category, Importance } from './criteria';
import type { EmploymentType } from './job';

/** The band shown with the match score (D16, D42). */
export type MatchLevel = '매우 적합' | '적합' | '참고';

/**
 * Where the bands start on the match score, for the score guide's wording only (the band itself always comes from
 * the API). Mirrors D16 and backend config: RECO_BAND_HIGH, RECO_BAND_MID and the lowest banded score
 * (RECO_FIT_WEIGHT · RECO_MIN_FIT + RECO_PREF_WEIGHT · RECO_MIN_PREF); below `reference` there is no band (D42).
 * backend/tests/test_band_thresholds_frontend.py fails if these drift from the backend.
 */
export const BAND_THRESHOLDS = { veryGood: 80, good: 60, reference: 40 } as const;

/** Plain mean (no weights) of the job's criterion scores in one category, rounded down (D42). */
export interface CategoryScore {
  category: Category;
  score: number;
}

/** Scores a seeker sees (D42): never weights, Fit as its own number, reasons or evidence. */
export interface MatchScores {
  /** Final rounded down, 0–100. */
  match_score: number;
  /** Null below 40: the number is shown without a band. */
  match_level: MatchLevel | null;
  /** Pref rounded down, 0–100. */
  preference_score: number;
  categories: CategoryScore[];
}

export interface RecommendedJob extends MatchScores {
  job_id: number;
  title: string;
  company_name: string;
  location: string;
  employment_type: EmploymentType;
  deadline: string | null;
  /** Recommended jobs always have a band (Final ≥ 40). */
  match_level: MatchLevel;
}

export interface RecommendationList {
  items: RecommendedJob[];
  /** Jobs that passed the Pref filter but whose evaluation is not done yet; not in `items`. */
  pending_count: number;
  notice: string;
}

/** GET /api/recommendations/matches: only the listed jobs that already have scores (D43). */
export interface JobScore extends MatchScores {
  job_id: number;
}

export interface JobScoreList {
  items: JobScore[];
  notice: string;
}

/** One criterion's score on the job detail page (D42). */
export interface CriterionMatch {
  criterion_id: number;
  name: string;
  category: Category;
  importance: Importance;
  score: number;
}

/** GET /api/jobs/{job_id}/match (D43). Scores are null unless `done`. */
export interface JobMatch {
  job_id: number;
  status: 'done' | 'pending' | 'none';
  match_score: number | null;
  match_level: MatchLevel | null;
  preference_score: number | null;
  categories: CategoryScore[];
  criteria: CriterionMatch[];
  notice: string;
}
