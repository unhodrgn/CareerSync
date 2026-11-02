import type { ApplicationStatus } from '../types/application'

// Korean labels for backend codes (texts from the old frontend's ko.ts)

/** Application status, set only by the recruiter (AI rule 5). */
export const applicationStatusLabel: Record<ApplicationStatus, string> = {
  submitted: '검토 전',
  reviewing: '서류 검토',
  interview: '면접 예정',
  on_hold: '보류',
  passed: '합격',
  rejected: '불합격',
}

/** Kinds of personal data the backend found and masked before analysis (CvOut.masked_kinds, D39). */
export const maskedKindLabel: Record<string, string> = {
  name: '이름',
  email: '이메일',
  phone: '전화번호',
  url: '링크',
  rrn: '주민등록번호',
  birth: '생년월일',
  address: '주소',
}
