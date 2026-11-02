import { useState } from 'react'
import { useCareer } from '../context/CareerContext'
import { Icon } from '../components/Icon'
import { TagInput } from '../components/TagInput'
import { title } from '../components/formHelpers'
import { regions } from '../data/categories'
import { employmentTypeOptions, experienceLevelOptions, PREFERENCE_MAX_ITEMS, PROFILE_MAX_SKILLS } from '../data/formFields'
import { toPreferenceForm, type PreferenceForm } from '../services/preferenceView'
import type { PreferenceOut } from '../types/preference'

// Account: PATCH /api/users/me (name only; the email is the login and read-only, D36). A seeker's name is locked
// once a CV was uploaded (D46), because the CV was masked with it (D39).
// Preferences: PUT /api/preferences/me. Job keywords, regions and employment types feed Pref (맞춤 추천, D15);
// experience level and skills are display only (D46) and the form says so.

function PreferencesForm({ prefs, busy, onSave }: { prefs: PreferenceOut | null, busy: boolean, onSave: (form: PreferenceForm) => void }) {
  const [form, setForm] = useState<PreferenceForm>(() => toPreferenceForm(prefs))
  const set = (patch: Partial<PreferenceForm>) => setForm(f => ({ ...f, ...patch }))
  return <form className="panel profile-form" onSubmit={e => { e.preventDefault(); onSave(form) }}>
    <h2>희망 조건</h2>
    <p className="muted">아래 세 가지는 맞춤 공고 추천에 반영돼요.</p>
    <TagInput label="희망 직무 키워드" values={form.jobKeywords} onChange={jobKeywords => set({ jobKeywords })} max={PREFERENCE_MAX_ITEMS} minLength={2} placeholder="예: 백엔드, Java (Enter로 추가)" />
    <TagInput label="희망 근무 지역" values={form.locations} onChange={locations => set({ locations })} max={PREFERENCE_MAX_ITEMS} minLength={2} suggestions={regions} placeholder="예: 서울 (Enter로 추가)" />
    <fieldset className="choice-group">
      <legend>희망 근무 형태</legend>
      {employmentTypeOptions.map(o => <label key={o.code} className="checkbox-label">
        <input type="checkbox" checked={form.employmentTypes.includes(o.code)} onChange={e => set({ employmentTypes: e.target.checked ? [...form.employmentTypes, o.code] : form.employmentTypes.filter(t => t !== o.code) })} />{o.label}</label>)}
    </fieldset>
    <h3>나를 소개하는 정보 <span className="status">표시 전용</span></h3>
    <p className="muted">경력 수준과 보유 기술은 프로필에 보여 주기 위한 정보예요. 추천과 지원 평가에는 쓰이지 않고, 평가는 이력서 내용만 봅니다.</p>
    <label>경력 수준<select value={form.experienceLevel} onChange={e => set({ experienceLevel: e.target.value as PreferenceForm['experienceLevel'] })}>
      <option value="">선택 안 함</option>
      {experienceLevelOptions.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
    </select>
    </label>
    <TagInput label="보유 기술 스택" values={form.skills} onChange={skills => set({ skills })} max={PROFILE_MAX_SKILLS} placeholder="예: React, TypeScript (Enter로 추가)" hint={`최대 ${PROFILE_MAX_SKILLS}개 · 저장하면 표준 이름으로 정리돼요 (예: 리액트 → React)`} />
    <button className="btn" disabled={busy}>변경 사항 저장 <Icon name="check" /></button>
  </form>
}

export function ProfilePage() {
  const { busy, user, cvLoaded, nameLocked, renameMe, preferences, savePreferences } = useCareer()
  const [name, setName] = useState(user?.display_name ?? '')
  if (!user)
    return null
  const locked = nameLocked || !cvLoaded // until the CV state is known, do not offer a rename
  return (<>{title('나를 더 잘 알릴 수 있도록.', '기본 정보와 희망 조건을 관리하세요.')}
    <form className="panel profile-form" onSubmit={e => { e.preventDefault(); if (name.trim() && name.trim() !== user.display_name) void renameMe(name.trim()) }}>
      <h2>기본 정보</h2>
      <div className="form-grid">
        <label>이름<input value={name} maxLength={50} required disabled={locked} onChange={e => setName(e.target.value)} />
          <small className="field-hint">{nameLocked ? '이력서를 올린 뒤에는 이름을 바꿀 수 없어요. 이력서의 개인정보를 가릴 때 이 이름을 사용했기 때문이에요.' : cvLoaded ? '이력서를 올리기 전에만 바꿀 수 있어요. 지원한 기업과 제안을 수락한 기업에만 공개돼요.' : '확인하는 중…'}</small>
        </label>
        <label>이메일<input value={user.email} readOnly disabled />
          <small className="field-hint">로그인에 쓰는 이메일은 바꿀 수 없어요.</small>
        </label>
      </div>
      {!locked && <button className="btn" disabled={busy || !name.trim() || name.trim() === user.display_name}>이름 저장 <Icon name="check" /></button>}
    </form>
    {/* Rebuilt when the stored preferences arrive or change, so the form starts from them */}
    <PreferencesForm key={JSON.stringify(preferences)} prefs={preferences} busy={busy} onSave={form => void savePreferences(form)} />
  </>)
}
