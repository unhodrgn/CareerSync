// Mirrors backend/app/schemas/talent.py and offer.py.
import type { EmploymentType } from './job';

export type OfferStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled' | 'expired';

export interface OfferJob {
  job_id: number;
  title: string;
  location: string;
  employment_type: EmploymentType;
}

/** What the seeker sees about an offer they received. */
export interface SeekerOffer {
  offer_id: number;
  company_name: string;
  job: OfferJob | null;
  message: string | null;
  status: OfferStatus;
  created_at: string;
  expires_at: string;
  responded_at: string | null;
}

// Company side: anonymous talent (D19) and sent offers (D20)

export interface TalentCriterionScore {
  criterion_id: number;
  name: string;
  score: number;
  level: number;
}

/** Only facts verified against the masked CV; never name, email, school, organisation or project names. */
export interface AnonymousProfile {
  skills: string[];
  experience_years: number;
  roles: string[];
  project_techs: string[];
  education: { degree: string; major: string }[];
  certificates: string[];
  desired: { locations: string[]; employment_types: string[]; job_keywords: string[] };
}

export interface TalentCandidate extends AnonymousProfile {
  anonymous_id: string;
  fit: number;
  criteria: TalentCriterionScore[];
  /** Latest offer from this company to this seeker. */
  offer_status: OfferStatus | null;
}

export interface TalentList {
  job_id: number;
  items: TalentCandidate[];
  pending_count: number;
  notice: string;
}

export interface OfferCreate {
  job_id: number;
  anonymous_id: string;
  message: string | null;
}

export interface SentOffer {
  offer_id: number;
  job_id: number | null;
  job_title: string | null;
  anonymous_id: string;
  message: string | null;
  status: OfferStatus;
  created_at: string;
  expires_at: string;
  responded_at: string | null;
  /** null while the seeker is not public. */
  candidate: AnonymousProfile | null;
  /** Only after the seeker accepted (D3, D20). */
  contact: { display_name: string; email: string } | null;
}
