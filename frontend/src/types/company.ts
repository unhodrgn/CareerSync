// Mirrors backend/app/schemas/company.py.

export interface CompanyOut {
  id: number;
  name: string;
  intro: string;
  /** 인재상 */
  talent_profile: string;
}

export interface CompanyProjectOut {
  id: number;
  name: string;
  description: string;
  techs: string[];
  created_at: string;
  updated_at: string;
}

/** Public company profile with its running projects (D23). */
export interface CompanyPublicOut extends CompanyOut {
  projects: CompanyProjectOut[];
}
