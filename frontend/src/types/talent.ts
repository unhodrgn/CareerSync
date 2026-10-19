// Mirrors backend/app/schemas/talent.py and offer.py (seeker side; the company's types come with the company pages).
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
