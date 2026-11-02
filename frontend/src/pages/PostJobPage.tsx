import { useState } from 'react'
import { useCareer } from '../context/CareerContext'
import { title } from '../components/formHelpers'
import { categories, regions } from '../data/categories'
import { employmentTypeOptions, HEADCOUNT_MAX, HEADCOUNT_MIN, JOB_DESCRIPTION_MAX, JOB_TEXT_MAX, JOB_TITLE_MAX, MIN_EXPERIENCE_MAX } from '../data/formFields'
import { emptyJobForm, jobFormProblem, joinDescription, toJobForm, type JobForm } from '../services/jobForm'
import type { JobCategory } from '../types/job'
// #post: POST /api/jobs creates a DRAFT. #post/12: PATCH /api/jobs/12 while it is a draft. The two text areas become
// one JD with headings (F13). Category and 주요 업무 (duties) are needed to publish, not to save a draft.

const todayIso = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function JobFormPanel({ initial, jobId, busy, onSubmit, onCancel }: { initial: JobForm, jobId: number | null, busy: boolean, onSubmit: (form: JobForm) => void, onCancel: () => void }) {
  const [form, setForm] = useState<JobForm>(initial)
  const [problem, setProblem] = useState('')
  const set = (patch: Partial<JobForm>) => setForm(f => ({ ...f, ...patch }))
  const tooLong = joinDescription(form.duties, form.requirements).length > JOB_DESCRIPTION_MAX
  return <form className="panel profile-form" onSubmit={(e) => {
    e.preventDefault()
    const found = jobFormProblem(form) ?? (tooLong ? `공고 내용은 모두 합쳐 ${JOB_DESCRIPTION_MAX.toLocaleString()}자 이하여야 합니다.` : null)
    setProblem(found ?? '')
    if (!found)
      onSubmit(form)
  }}>
    <div className="form-grid">
      <label>채용 직무명<input value={form.title} required maxLength={JOB_TITLE_MAX} placeholder="예: 백엔드 개발자 (Java/Spring)" onChange={e => set({ title: e.target.value })} /></label>
      <label>직무 분야<select value={form.category} onChange={e => set({ category: e.target.value as JobCategory | '' })}>
        <option value="">선택 안 함</option>
        {categories.filter(c => c.code).map(c => <option key={c.code} value={c.code ?? ''}>{c.label}</option>)}
      </select>
        <small className="field-hint">게시하려면 꼭 골라야 해요. 공고 목록의 분야 필터에 쓰여요.</small>
      </label>
      <label>근무 지역<input value={form.location} maxLength={JOB_TEXT_MAX} list="job-regions" placeholder="예: 서울 강남구" onChange={e => set({ location: e.target.value })} />
        <datalist id="job-regions">{regions.map(r => <option key={r} value={r} />)}</datalist>
      </label>
      <label>고용 형태<select value={form.employmentType} onChange={e => set({ employmentType: e.target.value as JobForm['employmentType'] })}>
        {employmentTypeOptions.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
      </select>
      </label>
      <label>경력 요건 (년 이상)<input type="number" min={0} max={MIN_EXPERIENCE_MAX} step={1} value={form.minExperience} placeholder="비우면 신입 가능" onChange={e => set({ minExperience: e.target.value })} /></label>
      <label>모집 인원<input type="number" min={HEADCOUNT_MIN} max={HEADCOUNT_MAX} step={1} value={form.headcount} placeholder="비우면 표시하지 않아요" onChange={e => set({ headcount: e.target.value })} /></label>
      <label>마감일<input type="date" min={todayIso()} value={form.deadline} onChange={e => set({ deadline: e.target.value })} />
        <small className="field-hint">비우면 상시 채용이에요.</small>
      </label>
      <label>급여 안내<input value={form.salaryNote} maxLength={JOB_TEXT_MAX} placeholder="예: 회사 내규에 따름" onChange={e => set({ salaryNote: e.target.value })} /></label>
    </div>
    <label>주요 업무<textarea value={form.duties} rows={6} placeholder="함께 하게 될 업무를 소개해주세요" onChange={e => set({ duties: e.target.value })} />
      <small className="field-hint">게시하려면 꼭 적어야 해요.</small>
    </label>
    <label>자격 요건 및 우대 사항<textarea value={form.requirements} rows={6} placeholder="필수 역량과 우대 역량을 구분해주세요" onChange={e => set({ requirements: e.target.value })} />
      <small className="field-hint">두 칸은 제목을 붙여 하나의 공고 내용으로 저장돼요. 적힌 기술은 평가 기준과 함께 공고 태그가 됩니다.</small>
    </label>
    {problem && <div className="info-box form-problem" role="alert">{problem}</div>}
    <div className="form-actions">
      <button className="btn" disabled={busy}>{jobId === null ? '임시 저장하고 평가 기준 설정 ↗' : '변경 사항 저장'}</button>
      <button type="button" className="btn secondary" onClick={onCancel}>취소</button>
    </div>
    <p className="demo-note">저장한 공고는 ‘작성 중’ 상태예요. 평가 기준을 정한 뒤 대시보드에서 게시하면 구직자에게 보입니다.</p>
  </form>
}

export function PostJobPage() {
  const { busy, editedJob, submitJob, go, routeJobId: jobId } = useCareer()
  const editing = editedJob
  const heading = title('우리 팀의 다음 동료를 만나세요.', '구체적인 채용 정보로 좋은 연결을 시작하세요.')
  if (jobId !== null) {
    if (!editing)
      return <>{heading}<div className="empty-state">공고를 불러오는 중…</div></>
    if (!editing.job)
      return <>{heading}<div className="empty-state">{editing.error}</div></>
    if (editing.job.status !== 'draft')
      return <>{heading}<div className="panel"><div className="empty-state">
        <p>게시했거나 마감한 공고는 여기서 수정할 수 없어요. 지원자 점수가 공고 내용으로 계산되기 때문이에요.</p>
        <button className="btn" onClick={() => go('company')}>대시보드로 돌아가기</button>
      </div></div></>
  }
  const initial = jobId !== null && editing?.job ? toJobForm(editing.job) : emptyJobForm
  return (<>{heading}
    {/* Rebuilt when another job is opened, so the form starts from that job */}
    <JobFormPanel key={jobId ?? 'new'} initial={initial} jobId={jobId} busy={busy} onSubmit={form => void submitJob(form, jobId)} onCancel={() => go('company')} />
  </>)
}
