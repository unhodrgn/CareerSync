// Mirrors backend/app/schemas/criteria.py.

export type Category = 'skill' | 'experience' | 'project' | 'certificate' | 'education' | 'other';
/** Criterion importance shown to signed-in seekers (docs/DECISIONS.md D30); derived from the weight on the server. */
export type Importance = '핵심' | '중요' | '일반';

/** Owner company: full rows. */
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

/** Signed-in seeker: no weights or numbers (D1, D30). */
export interface SeekerCriterionOut {
  name: string;
  category: Category;
  importance: Importance;
}

export interface SeekerCriteriaSetOut {
  job_id: number;
  items: SeekerCriterionOut[];
}

/** Guest: the name only (D35). */
export interface GuestCriterionOut {
  name: string;
}

export interface GuestCriteriaSetOut {
  job_id: number;
  items: GuestCriterionOut[];
}

/** `GET /api/jobs/{job_id}/criteria` answers in one of three shapes, chosen by who asks. */
export type CriteriaView = CriteriaSetOut | SeekerCriteriaSetOut | GuestCriteriaSetOut;
