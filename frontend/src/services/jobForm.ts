// Company job pages: the job form ↔ JobCreate, the criteria rows ↔ CriterionIn, and failed publish/criteria calls →
// a Korean sentence plus where to fix it. The server checks every rule again; these checks only explain early.
import { CRITERIA_MAX_ITEMS, CRITERIA_WEIGHT_TOTAL, CRITERION_NAME_MAX, HEADCOUNT_MAX, HEADCOUNT_MIN } from '../data/formFields'
import type { Category, CriteriaSetOut, CriterionIn, GuardrailHit } from '../types/criteria'
import type { EmploymentType, JobCategory, JobCreate, JobListItem, JobOut } from '../types/job'
import { ApiError, issueText } from './httpClient'
import { errorText } from './errors'

// The form has two text areas (F13); the JD is one text with these headings
const DUTIES = '[주요 업무]'
const REQUIREMENTS = '[자격 요건 및 우대 사항]'

/** The job form as typed: numbers stay text until sent, '' = not given. */
export interface JobForm {
  title: string
  location: string
  employmentType: EmploymentType
  minExperience: string
  headcount: string
  deadline: string
  category: JobCategory | ''
  salaryNote: string
  duties: string
  requirements: string
}

export const emptyJobForm: JobForm = {
  title: '', location: '', employmentType: 'full_time', minExperience: '', headcount: '', deadline: '', category: '',
  salaryNote: '', duties: '', requirements: '',
}

/** The two text areas as one JD; an empty one is left out. */
export function joinDescription(duties: string, requirements: string): string {
  const parts = [[DUTIES, duties.trim()], [REQUIREMENTS, requirements.trim()]].filter(([, text]) => text)
  return parts.map(([heading, text]) => `${heading}\n${text}`).join('\n\n')
}

/** A JD written by this form back into its two parts; any other text goes to 주요 업무 (duties) as it is. */
export function splitDescription(description: string): { duties: string, requirements: string } {
  const text = description.trim()
  const r = text.indexOf(REQUIREMENTS)
  if (text.startsWith(DUTIES) || r === 0) {
    const duties = r === -1 ? text.slice(DUTIES.length) : r === 0 ? '' : text.slice(DUTIES.length, r)
    return { duties: duties.trim(), requirements: r === -1 ? '' : text.slice(r + REQUIREMENTS.length).trim() }
  }
  return { duties: text, requirements: '' }
}

const optionalNumber = (text: string) => text.trim() === '' ? null : Number(text)

export function toJobCreate(form: JobForm): JobCreate {
  return {
    title: form.title.trim(),
    description: joinDescription(form.duties, form.requirements),
    employment_type: form.employmentType,
    min_experience_years: optionalNumber(form.minExperience),
    location: form.location.trim(),
    salary_note: form.salaryNote.trim(),
    deadline: form.deadline || null,
    category: form.category || null,
    headcount: optionalNumber(form.headcount),
  }
}

export function toJobForm(job: JobOut): JobForm {
  return {
    title: job.title,
    location: job.location,
    employmentType: job.employment_type,
    minExperience: job.min_experience_years === null ? '' : String(job.min_experience_years),
    headcount: job.headcount === null ? '' : String(job.headcount),
    deadline: job.deadline ?? '',
    category: job.category ?? '',
    salaryNote: job.salary_note,
    ...splitDescription(job.description),
  }
}

/** A problem the form can show before sending, or null. */
export function jobFormProblem(form: JobForm): string | null {
  if (!form.title.trim())
    return '채용 직무명을 입력해 주세요.'
  const headcount = optionalNumber(form.headcount)
  if (headcount !== null && !(Number.isInteger(headcount) && headcount >= HEADCOUNT_MIN && headcount <= HEADCOUNT_MAX))
    return `모집 인원은 ${HEADCOUNT_MIN}~${HEADCOUNT_MAX}명 사이의 정수로 입력해 주세요.`
  return null
}

/** 작성 중 / 게시 중 / 기간 만료 / 마감 (draft / published / deadline passed / closed). */
export function jobStatusLabel(job: Pick<JobListItem, 'status' | 'expired'>): string {
  if (job.status === 'draft')
    return '작성 중'
  if (job.status === 'closed')
    return '마감'
  return job.expired ? '기간 만료' : '게시 중'
}

// ── Criteria ──

/** One editable row; `weight` stays text until sent. `key` is stable while editing. */
export interface CriterionRow {
  key: string
  id: number | null
  name: string
  description: string
  category: Category
  weight: string
}

export const toCriterionRows = (set: CriteriaSetOut | null): CriterionRow[] =>
  (set?.items ?? []).map(c => ({ key: `c${c.id}`, id: c.id, name: c.name, description: c.description, category: c.category, weight: String(c.weight) }))

export const toCriteriaIn = (rows: CriterionRow[]): CriterionIn[] =>
  rows.map(r => ({ id: r.id, name: r.name.trim(), description: r.description.trim(), category: r.category, weight: Number(r.weight) }))

export const weightTotal = (rows: CriterionRow[]) => rows.reduce((sum, r) => sum + (Number(r.weight) || 0), 0)

/** Problems in the set: `form` for the whole set, `rows` by row index. Mirrors criteria_service._validate_shape. */
export interface CriteriaProblems {
  form: string[]
  rows: Record<number, string>
}

export function criteriaProblems(rows: CriterionRow[]): CriteriaProblems {
  const form: string[] = []
  const byRow: Record<number, string> = {}
  if (rows.length < 1 || rows.length > CRITERIA_MAX_ITEMS)
    form.push(`평가 기준은 1개 이상 ${CRITERIA_MAX_ITEMS}개 이하로 설정해야 합니다.`)
  const seen = new Map<string, number>()
  rows.forEach((r, i) => {
    const name = r.name.trim()
    const weight = Number(r.weight)
    if (!name)
      byRow[i] = '항목 이름을 입력해 주세요.'
    else if (name.length > CRITERION_NAME_MAX)
      byRow[i] = `항목 이름은 ${CRITERION_NAME_MAX}자 이하여야 합니다.`
    else if (seen.has(name.toLowerCase()))
      byRow[i] = '같은 이름의 항목이 이미 있습니다.'
    else if (!(Number.isInteger(weight) && weight >= 1 && weight <= 100))
      byRow[i] = '가중치는 1~100 사이의 정수로 입력해 주세요.'
    seen.set(name.toLowerCase(), i)
  })
  const total = weightTotal(rows)
  if (rows.length > 0 && total !== CRITERIA_WEIGHT_TOTAL)
    form.push(`가중치 합계는 ${CRITERIA_WEIGHT_TOTAL}이어야 합니다. (현재 ${total})`)
  return { form, rows: byRow }
}

/** A guardrail hit as one Korean line: what matched, why, and the law. */
export const hitText = (hit: Pick<GuardrailHit, 'matched' | 'reason' | 'law_ref'>) => `‘${hit.matched}’ — ${hit.reason} (${hit.law_ref})`

/** A refused PUT /api/jobs/{id}/criteria: the server's sentence, plus the rows it names. */
export function criteriaIssue(error: unknown): CriteriaProblems {
  const rows: Record<number, string> = {}
  if (error instanceof ApiError) {
    const items = (error.body?.items ?? []) as { index: number | null, matched?: string, reason?: string, law_ref?: string }[]
    if (error.code === 'CRITERIA_BLOCKED')
      for (const hit of items)
        if (hit.index !== null && hit.reason)
          rows[hit.index] ??= hitText({ matched: hit.matched ?? '', reason: hit.reason, law_ref: hit.law_ref ?? '' })
    if (error.code === 'CRITERIA_MAJOR_REQUIRED')
      for (const item of items)
        if (item.index !== null)
          rows[item.index] = '평가할 전공을 적어 주세요. 예: 컴퓨터공학 전공, 이공계 전공'
    if (error.code === 'VALIDATION') {
      const issue = error.fields.items
      const index = issue?.loc[2]
      if (typeof index === 'number') {
        rows[index] = issueText(issue)
        return { form: ['입력한 평가 기준을 확인해 주세요.'], rows }
      }
    }
  }
  return { form: [errorText(error)], rows }
}

/** Where a refused publish is fixed: the job form, the criteria editor, or nowhere in particular. */
export interface PublishIssue {
  message: string
  fix: 'edit' | 'criteria' | null
}

const CRITERIA_CODES = ['CRITERIA_COUNT_INVALID', 'WEIGHT_SUM_INVALID', 'CRITERIA_DUPLICATE_NAME', 'CRITERIA_MAJOR_REQUIRED', 'CRITERIA_BLOCKED']

export function publishIssue(error: unknown): PublishIssue {
  if (!(error instanceof ApiError))
    return { message: errorText(error), fix: null }
  const fields = (error.body?.fields ?? []) as string[]
  if (error.code === 'FIELD_REQUIRED' && fields.includes('category'))
    return { message: '직무 분야를 선택해야 게시할 수 있어요. 공고 수정에서 직무 분야를 골라 주세요.', fix: 'edit' }
  if (error.code === 'JOB_INCOMPLETE')
    return { message: '주요 업무(공고 내용)를 입력해야 게시할 수 있어요.', fix: 'edit' }
  if (error.code === 'DEADLINE_IN_PAST')
    return { message: '마감일이 지났어요. 공고 수정에서 마감일을 오늘 이후로 바꾸거나 비워 주세요.', fix: 'edit' }
  if (error.code === 'CRITERIA_COUNT_INVALID' && error.body?.count === 0)
    return { message: '평가 기준을 먼저 설정해야 게시할 수 있어요.', fix: 'criteria' }
  if (CRITERIA_CODES.includes(error.code))
    return { message: `평가 기준을 고쳐야 게시할 수 있어요. ${error.message || errorText(error)}`, fix: 'criteria' }
  return { message: errorText(error), fix: null }
}
