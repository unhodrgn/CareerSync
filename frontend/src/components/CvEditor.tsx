import { useState, type ReactNode } from 'react'
import type { CvCertificate, CvEducation, CvExperience, CvProfile, CvProject } from '../types/cv'

// The seeker checks and corrects what the analysis read from the CV (cv_profile.v1), then confirms it.
// Edits only say what to look for: scoring still gives points only for what is in the masked CV text (AI rule 14).
// `source` (the CV line an item was read from) is kept as it came and never shown or edited here.

const emptyExperience: CvExperience = { org: '', role: '', start: null, end: null, description: '', source: '' }
const emptyProject: CvProject = { name: '', role: '', tech: [], description: '', source: '' }
const emptyEducation: CvEducation = { school: '', major: '', degree: '', source: '' }
const emptyCertificate: CvCertificate = { name: '', date: null, source: '' }
const DEGREES = ['', '고졸', '전문학사', '학사', '석사', '박사']

const splitList = (text: string) => text.split(',').map(s => s.trim()).filter(Boolean)
// While typing, empty parts stay so a trailing comma survives; they are dropped on save
const splitTyping = (text: string) => text.split(',').map(s => s.trimStart())
const monthOrNull = (value: string) => value || null

/** A list section with add and remove; `render` draws the fields of one item. */
function Section<T>({ title, items, empty, onChange, render }: {
  title: string
  items: T[]
  empty: T
  onChange: (items: T[]) => void
  render: (item: T, set: (patch: Partial<T>) => void) => ReactNode
}) {
  return <section className="cv-section">
    <h3>{title} <span className="muted">{items.length}</span></h3>
    {items.map((item, i) => <div className="cv-item" key={i}>
      <div className="form-grid">{render(item, patch => onChange(items.map((x, j) => j === i ? { ...x, ...patch } : x)))}</div>
      <button type="button" className="text-link" onClick={() => onChange(items.filter((_, j) => j !== i))}>삭제</button>
    </div>)}
    <button type="button" className="text-link" onClick={() => onChange([...items, { ...empty }])}>+ {title} 추가</button>
  </section>
}

export function CvEditor({ profile, busy, confirmed, onConfirm }: {
  profile: CvProfile
  busy: boolean
  confirmed: boolean
  onConfirm: (profile: CvProfile) => void
}) {
  const [draft, setDraft] = useState<CvProfile>(profile)
  // Skills and techs are edited as comma-separated text and split on save, so typing a comma works
  const [skillsText, setSkillsText] = useState(profile.skills.join(', '))
  const set = (patch: Partial<CvProfile>) => setDraft(d => ({ ...d, ...patch }))
  return <form className="profile-form cv-editor" onSubmit={(e) => { e.preventDefault(); onConfirm({ ...draft, skills: splitList(skillsText), projects: draft.projects.map(p => ({ ...p, tech: p.tech.map(t => t.trim()).filter(Boolean) })) }) }}>
    <label>요약<textarea rows={3} maxLength={500} value={draft.summary} onChange={e => set({ summary: e.target.value })} />
    </label>
    <label>보유 기술 (쉼표로 구분)<input value={skillsText} onChange={e => setSkillsText(e.target.value)} placeholder="예: Java, Spring, PostgreSQL" />
    </label>
    <Section title="경력" items={draft.experiences} empty={emptyExperience} onChange={experiences => set({ experiences })} render={(x, upd) => <>
      <label>회사·기관<input maxLength={100} value={x.org} onChange={e => upd({ org: e.target.value })} /></label>
      <label>직무<input maxLength={100} value={x.role} onChange={e => upd({ role: e.target.value })} /></label>
      <label>시작<input type="month" value={x.start ?? ''} onChange={e => upd({ start: monthOrNull(e.target.value) })} /></label>
      <label>종료 (재직 중이면 비움)<input type="month" value={x.end ?? ''} onChange={e => upd({ end: monthOrNull(e.target.value) })} /></label>
      <label className="span-2">설명<textarea rows={2} maxLength={2000} value={x.description} onChange={e => upd({ description: e.target.value })} /></label>
    </>} />
    <Section title="프로젝트" items={draft.projects} empty={emptyProject} onChange={projects => set({ projects })} render={(x, upd) => <>
      <label>프로젝트명<input maxLength={200} value={x.name} onChange={e => upd({ name: e.target.value })} /></label>
      <label>역할<input maxLength={100} value={x.role} onChange={e => upd({ role: e.target.value })} /></label>
      <label className="span-2">사용 기술 (쉼표로 구분)<input value={x.tech.join(',')} onChange={e => upd({ tech: splitTyping(e.target.value) })} placeholder="예: React, TypeScript" /></label>
      <label className="span-2">설명<textarea rows={2} maxLength={2000} value={x.description} onChange={e => upd({ description: e.target.value })} /></label>
    </>} />
    <Section title="학력" items={draft.education} empty={emptyEducation} onChange={education => set({ education })} render={(x, upd) => <>
      <label>학교<input maxLength={100} value={x.school} onChange={e => upd({ school: e.target.value })} /></label>
      <label>전공<input maxLength={100} value={x.major} onChange={e => upd({ major: e.target.value })} /></label>
      <label>학위<select value={x.degree} onChange={e => upd({ degree: e.target.value })}>{DEGREES.map(d => <option key={d} value={d}>{d || '선택 안 함'}</option>)}</select></label>
    </>} />
    <Section title="자격증" items={draft.certificates} empty={emptyCertificate} onChange={certificates => set({ certificates })} render={(x, upd) => <>
      <label>자격증명<input maxLength={100} value={x.name} onChange={e => upd({ name: e.target.value })} /></label>
      <label>취득 연월<input type="month" value={x.date ?? ''} onChange={e => upd({ date: monthOrNull(e.target.value) })} /></label>
    </>} />
    <p className="demo-note">수정한 내용은 무엇을 찾아볼지 알려줄 뿐이며, 평가는 원본 이력서(개인정보를 가린 텍스트)에 있는 내용만 반영합니다.</p>
    <button className="btn" disabled={busy}>{confirmed ? '수정 내용 저장' : '이대로 확인하고 저장'} ✓</button>
  </form>
}
