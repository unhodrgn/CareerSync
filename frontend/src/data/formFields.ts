import type { Category } from '../types/criteria'
import type { EmploymentType } from '../types/job'
import type { ExperienceLevel } from '../types/preference'

// Profile options: `code` is what the API takes, `label` is shown.
export const employmentTypeOptions: { code: EmploymentType, label: string }[] = [
  { code: 'full_time', label: '정규직' },
  { code: 'contract', label: '계약직' },
  { code: 'intern', label: '인턴' },
]
/** Self-declared 경력 수준; display only, never scored (D46). */
export const experienceLevelOptions: { code: ExperienceLevel, label: string }[] = [
  { code: 'new', label: '신입' },
  { code: 'junior', label: '주니어' },
  { code: 'mid', label: '미들' },
  { code: 'senior', label: '시니어' },
]
// Limits of PUT /api/preferences/me (backend/app/schemas/preference.py)
export const PREFERENCE_MAX_ITEMS = 10
export const PROFILE_MAX_SKILLS = 20

// Job form and criteria editor: limits of backend/app/schemas/job.py, schemas/criteria.py and CRITERIA_* in
// backend/app/core/config.py (the server checks them again)
export const JOB_TITLE_MAX = 200
export const JOB_DESCRIPTION_MAX = 10000
export const JOB_TEXT_MAX = 100 // location, salary_note
export const MIN_EXPERIENCE_MAX = 30
export const HEADCOUNT_MIN = 1
export const HEADCOUNT_MAX = 999
export const CRITERIA_MAX_ITEMS = 10
export const CRITERIA_WEIGHT_TOTAL = 100
export const CRITERION_NAME_MAX = 50
export const CRITERION_DESCRIPTION_MAX = 500

/** Criterion categories (backend/app/schemas/criteria.py) with what each one scores. */
export const criterionCategoryOptions: { code: Category, label: string, hint: string }[] = [
  { code: 'skill', label: '기술', hint: '이력서에 적힌 기술을 봅니다. 예: Java 활용 능력' },
  { code: 'experience', label: '경력', hint: '확인된 경력 기간을 봅니다. 예: 백엔드 개발 경력 3년' },
  { code: 'project', label: '프로젝트', hint: '프로젝트 경험을 봅니다. 예: API 서버 설계·배포 경험' },
  { code: 'certificate', label: '자격증', hint: '자격증을 봅니다. 예: 정보처리기사' },
  { code: 'education', label: '학력(전공)', hint: '전공만 봅니다. 평가할 전공을 꼭 적어 주세요. 예: 컴퓨터공학 전공' },
  { code: 'other', label: '기타', hint: '그 밖의 기준을 이력서에서 찾아봅니다.' },
]
