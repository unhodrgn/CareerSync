// Mirrors backend/app/schemas/criteria.py.

export type Category = 'skill' | 'experience' | 'project' | 'certificate' | 'education' | 'other'
/** Criterion importance shown to signed-in seekers (docs/DECISIONS.md D30); derived from the weight on the server. */
export type Importance = '핵심' | '중요' | '일반'

/**
 * One row as the job detail page reads it. Guests get `name` only (D35); signed-in seekers also get `category`
 * and `importance` (D30); the owner company also gets weights, which this page never shows.
 */
export interface CriterionView {
  name: string
  category?: Category
  importance?: Importance
}

export interface CriteriaView {
  job_id: number
  items: CriterionView[]
}

/** One row of PUT /api/jobs/{job_id}/criteria. `id` keeps an existing row (required for every row after publish). */
export interface CriterionIn {
  id?: number | null
  /** 1–50 characters, unique in the set (case-insensitive). */
  name: string
  /** Rubric, at most 500 characters; an `education` criterion must name a major. */
  description: string
  category: Category
  /** Integer 1–100; the set must total 100. */
  weight: number
}

/** The owner's view (GET/PUT /api/jobs/{job_id}/criteria as the owning company). Weights never reach seekers. */
export interface CriterionOut {
  id: number
  name: string
  description: string
  category: Category
  weight: number
  position: number
  importance: Importance
}

export interface CriteriaSetOut {
  job_id: number
  items: CriterionOut[]
  total_weight: number
  blocklist_version: string
}

/** One legal-guardrail hit (data/blocklist.yaml); `index` is the row in a saved set. */
export interface GuardrailHit {
  index: number | null
  field: string
  rule_id: string
  category: string
  matched: string
  reason: string
  law_ref: string
}

/** POST /api/criteria/check: the live check while typing; saves nothing. */
export interface CheckResult {
  allowed: boolean
  hits: GuardrailHit[]
  blocklist_version: string
}
