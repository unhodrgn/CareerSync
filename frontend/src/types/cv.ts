// Mirrors backend/app/schemas/cv.py and ai/parsing/profile.py (cv_profile.v1).

export interface CvExperience {
  org: string;
  role: string;
  /** `YYYY-MM` */
  start: string | null;
  /** `YYYY-MM`, null while current. */
  end: string | null;
  description: string;
  /** The CV line this item was read from. */
  source: string;
}

export interface CvProject {
  name: string;
  role: string;
  tech: string[];
  description: string;
  source: string;
}

export interface CvEducation {
  school: string;
  major: string;
  degree: string;
  source: string;
}

export interface CvCertificate {
  name: string;
  date: string | null;
  source: string;
}

export interface CvProfile {
  skills: string[];
  experiences: CvExperience[];
  projects: CvProject[];
  education: CvEducation[];
  certificates: CvCertificate[];
  summary: string;
}

export interface CvOut {
  /** Profile (version) id. */
  id: number;
  document_id: number;
  file_name: string;
  pages: number;
  version: number;
  profile: CvProfile;
  /** "rules", "llm:<model>" or "seeker". */
  method: string;
  confirmed: boolean;
  confirmed_at: string | null;
  /** Personal data found and masked before analysis, e.g. ["email", "phone"]. */
  masked_kinds: string[];
  total_experience_months: number;
  created_at: string;
  notice: string;
}

export interface CvUpdate {
  profile: CvProfile;
  confirm: boolean;
}

export interface CvReviewItem {
  title: string;
  detail: string;
  /** A verified line of the masked CV, or null. */
  cv_quote: string | null;
  /** Rule findings that change what scoring can read; always listed first. */
  affects_scoring: boolean;
}

export interface CvReviewOut {
  profile_id: number;
  strengths: CvReviewItem[];
  improvements: CvReviewItem[];
  method: string;
  /** The daily LLM limit was reached and the rules review was returned. */
  limited: boolean;
  notice: string;
}
