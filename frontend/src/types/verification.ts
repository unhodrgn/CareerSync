export interface VerificationQuestion {
  question: string;
  criterion_id: number;
  criterion_name: string;
  cv_quote: string;
  reason: string;
  check_points: string[];
}

export interface VerificationOut {
  application_id: number;
  cv_profile_id: number;
  method: string;
  questions: VerificationQuestion[];
  notice: string;
}
