import { useEffect, useState } from 'react'
import { useCareer } from '../context/CareerContext'
import { title } from '../components/formHelpers'
import { CRITERIA_MAX_ITEMS, CRITERIA_WEIGHT_TOTAL, CRITERION_DESCRIPTION_MAX, CRITERION_NAME_MAX, criterionCategoryOptions } from '../data/formFields'
import { criteriaProblems, hitText, toCriteriaIn, toCriterionRows, weightTotal, type CriterionRow } from '../services/jobForm'
import type { CheckResult } from '../types/criteria'
// #criteria/12: the owner's criteria editor (GET/PUT /api/jobs/12/criteria). Weights are shown here only: this page is
// for the owning company, and seekers only ever get importance labels (D30). Drafts: add, remove and edit rows.
// Published jobs: weights and order only (the rest is locked so stored scores stay valid). Closed jobs: read only.
// Every name and rubric is checked live against the legal guardrail (POST /api/criteria/check) while typing.

let nextKey = 0
const newRow = (): CriterionRow => ({ key: `n${nextKey++}`, id: null, name: '', description: '', category: 'skill', weight: '' })

/** Live guardrail check of one row, half a second after the last keystroke. */
function useLiveCheck(name: string, description: string, check: (n: string, d: string) => Promise<CheckResult | null>) {
  const [result, setResult] = useState<{ for: string, value: CheckResult | null } | null>(null)
  const wanted = `${name.trim()}\n${description.trim()}`
  useEffect(() => {
    if (!name.trim())
      return
    let active = true
    const timer = window.setTimeout(() => {
      void check(name.trim(), description.trim()).then((value) => {
        if (active)
          setResult({ for: wanted, value })
      })
    }, 500)
    return () => { active = false; window.clearTimeout(timer) }
  }, [name, description, wanted, check])
  return name.trim() && result?.for === wanted ? result.value : null
}

function CriterionEditor({ row, index, locked, weightOnly, problem, canRemove, onChange, onRemove, check }: {
  row: CriterionRow, index: number, locked: boolean, weightOnly: boolean, problem: string | undefined, canRemove: boolean,
  onChange: (patch: Partial<CriterionRow>) => void, onRemove: () => void, check: (n: string, d: string) => Promise<CheckResult | null>
}) {
  const live = useLiveCheck(locked || weightOnly ? '' : row.name, row.description, check)
  const textLocked = locked || weightOnly
  const hint = criterionCategoryOptions.find(o => o.code === row.category)?.hint
  return <div className={`criterion-row ${problem || live?.allowed === false ? 'has-problem' : ''}`}>
    <span className="criterion-index">{index + 1}</span>
    <div className="criterion-fields">
      <div className="criterion-line">
        <label>항목 이름<input value={row.name} maxLength={CRITERION_NAME_MAX} disabled={textLocked} placeholder="예: Java 활용 능력" onChange={e => onChange({ name: e.target.value })} /></label>
        <label>분류<select value={row.category} disabled={textLocked} onChange={e => onChange({ category: e.target.value as CriterionRow['category'] })}>
          {criterionCategoryOptions.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
        </select></label>
        <label className="criterion-weight">가중치<input type="number" min={1} max={100} step={1} value={row.weight} disabled={locked} onChange={e => onChange({ weight: e.target.value })} /></label>
      </div>
      <label>평가 방법 (선택)<textarea rows={2} value={row.description} maxLength={CRITERION_DESCRIPTION_MAX} disabled={textLocked} placeholder="무엇을 보면 충족인지 적어 주세요. 예: Java 17, 동시성 이해" onChange={e => onChange({ description: e.target.value })} />
        {!textLocked && hint && <small className="field-hint">{hint}</small>}
      </label>
      {live && !live.allowed && <ul className="criterion-hits" role="alert">{live.hits.map(h => <li key={`${h.rule_id}-${h.field}`}>사용할 수 없는 기준: {hitText(h)}</li>)}</ul>}
      {problem && <p className="criterion-problem" role="alert">{problem}</p>}
    </div>
    {canRemove && <button type="button" className="text-link" onClick={onRemove} aria-label={`${index + 1}번 항목 삭제`}>삭제</button>}
  </div>
}

function CriteriaForm({ initial, status, busy, onSave, check, serverProblem }: {
  initial: CriterionRow[], status: string, busy: boolean, onSave: (rows: CriterionRow[]) => void,
  check: (n: string, d: string) => Promise<CheckResult | null>, serverProblem: { form: string[], rows: Record<number, string> } | null
}) {
  const [rows, setRows] = useState<CriterionRow[]>(() => initial.length ? initial : [newRow()])
  const [shown, setShown] = useState<{ form: string[], rows: Record<number, string> } | null>(null)
  const draft = status === 'draft'
  const locked = status === 'closed'
  const total = weightTotal(rows)
  const problems = shown ?? serverProblem
  const change = (key: string, patch: Partial<CriterionRow>) => setRows(rs => rs.map(r => r.key === key ? { ...r, ...patch } : r))
  return <form className="panel criteria-form" onSubmit={(e) => {
    e.preventDefault()
    const found = criteriaProblems(rows)
    const blocked = found.form.length > 0 || Object.keys(found.rows).length > 0
    setShown(blocked ? found : null)
    if (!blocked)
      onSave(rows)
  }}>
    <div className="criteria-head">
      <h2>평가 기준 <span className="muted">{rows.length} / {CRITERIA_MAX_ITEMS}</span></h2>
      <span className={`weight-total ${total === CRITERIA_WEIGHT_TOTAL ? 'ok' : ''}`}>가중치 합계 {total} / {CRITERIA_WEIGHT_TOTAL}</span>
    </div>
    <p className="muted">{draft
      ? '지원자는 이 기준으로 평가되고, 같은 기준으로 이 공고가 구직자에게 추천돼요. 가중치는 우리 회사에만 보이고, 구직자에게는 중요도(핵심 · 중요 · 일반)만 보여요.'
      : locked ? '마감한 공고의 평가 기준은 볼 수만 있어요.' : '게시한 공고는 가중치만 바꿀 수 있어요. 항목을 바꾸면 이미 계산된 지원자 점수가 맞지 않게 되기 때문이에요. 가중치를 바꾸면 순위가 바로 다시 계산돼요.'}</p>
    {rows.map((row, i) => <CriterionEditor key={row.key} row={row} index={i} locked={locked} weightOnly={!draft} problem={problems?.rows[i]} canRemove={draft && rows.length > 1}
      onChange={patch => change(row.key, patch)} onRemove={() => setRows(rs => rs.filter(r => r.key !== row.key))} check={check} />)}
    {draft && rows.length < CRITERIA_MAX_ITEMS && <button type="button" className="btn secondary" onClick={() => setRows(rs => [...rs, newRow()])}>＋ 평가 항목 추가</button>}
    {problems && problems.form.length > 0 && <div className="info-box form-problem" role="alert">{problems.form.map(m => <p key={m}>{m}</p>)}</div>}
    {!locked && <div className="form-actions"><button className="btn" disabled={busy}>평가 기준 저장</button></div>}
  </form>
}

export function CriteriaPage() {
  const { busy, editedJob, saveCriteria, criteriaProblem, checkCriterion, go } = useCareer()
  const heading = title('무엇을 보고 함께할지 정하세요.', '평가 기준은 지원자 평가와 공고 추천에 똑같이 쓰여요.')
  const back = <button className="text-link" onClick={() => go('company')}>← 대시보드로 돌아가기</button>
  if (!editedJob)
    return <>{back}{heading}<div className="empty-state">평가 기준을 불러오는 중…</div></>
  const { job, criteria } = editedJob
  if (!job)
    return <>{back}{heading}<div className="empty-state">{editedJob.error}</div></>
  return (<>{back}{heading}
    <div className="panel criteria-job"><b>{job.title}</b> <span className="status">{job.status === 'draft' ? '작성 중' : job.status === 'closed' ? '마감' : '게시 중'}</span></div>
    {/* Rebuilt when the saved set comes back, so ids of new rows are those the server gave */}
    <CriteriaForm key={JSON.stringify(criteria?.items.map(c => [c.id, c.weight, c.position]))} initial={toCriterionRows(criteria)} status={job.status} busy={busy}
      serverProblem={criteriaProblem} check={checkCriterion}
      onSave={rows => void saveCriteria(job.id, toCriteriaIn(rows)).then(saved => { if (saved && job.status === 'draft') go('company') })} />
  </>)
}
