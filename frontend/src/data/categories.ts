import type { JobCategory } from '../types/job'

// Job fields for the filter tabs (D45). `code` is what GET /api/jobs?category= takes; null = all jobs.
export const categories: { code: JobCategory | null, label: string }[] = [
  { code: null, label: '전체' },
  { code: 'dev', label: '개발 · IT' },
  { code: 'data_ai', label: '데이터 · AI' },
  { code: 'design', label: '디자인' },
  { code: 'marketing', label: '마케팅' },
  { code: 'planning', label: '기획 · 경영' },
]

// Region names GET /api/jobs?region= accepts, in the order of JOB_REGIONS in backend/app/core/config.py
// (서울 and 경기 first); an unknown name is answered with 422 REGION_INVALID
export const regions = ['서울', '경기', '인천', '부산', '대구', '광주', '대전', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
