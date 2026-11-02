// Backend job DTOs → the view models the pages show (types/index.ts). Only labels and dates are derived here;
// nothing is invented (the match score comes from its own endpoints, D42–D44). Tags come from the API (D45).
import type { Job, JobDetail } from '../types'
import type { CriterionView } from '../types/criteria'
import type { EmploymentType, JobListItem, JobOut } from '../types/job'

export const EMPLOYMENT_LABEL: Record<EmploymentType, string> = { full_time: '정규직', contract: '계약직', intern: '인턴' }
// Logo colour classes from App.css, picked by company so one company always looks the same
const COLORS = ['blue', 'orange', 'green', 'yellow', 'black', 'cyan']

export const experienceLabel = (years: number | null) => years === null || years === 0 ? '신입 가능' : `경력 ${years}년 이상`

/** Days from today to the deadline, counted on local calendar dates. */
function daysLeft(deadline: string, today: Date): number {
  const [y, m, d] = deadline.split('-').map(Number)
  const end = Date.UTC(y, m - 1, d)
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((end - start) / 86_400_000)
}

/** `ended`: the deadline passed or the job was closed. */
export function dDayLabel(deadline: string | null, ended: boolean, today = new Date()): string {
  if (ended)
    return '마감'
  if (!deadline)
    return '상시 채용'
  const days = daysLeft(deadline, today)
  if (days < 0)
    return '마감'
  return days === 0 ? 'D-day' : `D-${days}`
}

export function toJob(item: JobListItem | JobOut): Job {
  return {
    id: item.id,
    companyId: item.company_id,
    company: item.company_name,
    logo: item.company_name.trim().slice(0, 1) || '·',
    color: COLORS[item.company_id % COLORS.length],
    title: item.title,
    location: item.location,
    employment: EMPLOYMENT_LABEL[item.employment_type],
    experience: experienceLabel(item.min_experience_years),
    deadline: item.deadline,
    // A closed job (seen in saved jobs) reads as 마감 like an expired one
    dDay: dDayLabel(item.deadline, item.expired || item.status === 'closed'),
    tags: item.tags,
  }
}

export function toJobDetail(job: JobOut, criteria: CriterionView[]): JobDetail {
  return { ...toJob(job), description: job.description, salaryNote: job.salary_note, expired: job.expired, criteria }
}
