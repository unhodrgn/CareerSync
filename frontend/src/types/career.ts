// Mirrors backend/app/schemas/career.py.

export type GapKind = 'skill' | 'certificate';

/** A skill or certificate the job names that the CV text does not show (no scores, D1, D21). */
export interface CareerGap {
  name: string;
  kind: GapKind;
}

export interface LearningResource {
  title: string;
  url: string;
}

export interface RoadmapStep {
  order: number;
  skill: string;
  kind: GapKind;
  goal: string;
  activities: string[];
  /** Only from data/learning_resources.yaml. */
  resources: LearningResource[];
}

export interface RoadmapOut {
  job_id: number;
  method: string;
  gaps: CareerGap[];
  steps: RoadmapStep[];
  /** Set instead of steps when nothing is missing. */
  message: string | null;
  limited: boolean;
  notice: string;
}

export type QuestionKind = 'technical' | 'experience' | 'behavioral';

export interface InterviewQuestion {
  question: string;
  criterion_id: number | null;
  criterion_name: string | null;
  kind: QuestionKind;
  intent: string;
  answer_tips: string[];
  cv_quote: string | null;
}

export interface InterviewOut {
  job_id: number;
  method: string;
  questions: InterviewQuestion[];
  limited: boolean;
  notice: string;
}
