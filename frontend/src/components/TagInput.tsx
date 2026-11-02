import { useId, useState } from 'react'

// A list of short texts: Enter or a comma adds what was typed, × removes one. `suggestions` fill a datalist.
export function TagInput({ label, values, onChange, max, minLength = 1, suggestions, placeholder, hint }: {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  max: number
  minLength?: number
  suggestions?: string[]
  placeholder?: string
  hint?: string
}) {
  const [text, setText] = useState('')
  const [problem, setProblem] = useState('')
  const id = useId()
  const listId = suggestions ? id : undefined
  const add = (typed: string) => {
    const value = typed.trim().replace(/,$/, '').trim()
    if (!value)
      return
    if (value.length < minLength || value.length > 100)
      setProblem(`${minLength}~100자로 입력해 주세요.`)
    else if (values.some(v => v.toLowerCase() === value.toLowerCase()))
      setProblem('이미 추가한 항목이에요.')
    else if (values.length >= max)
      setProblem(`최대 ${max}개까지 추가할 수 있어요.`)
    else {
      onChange([...values, value])
      setProblem('')
    }
    setText('')
  }
  return <div className="tag-input">
    <label>{label}
      <input list={listId} value={text} placeholder={placeholder} onChange={e => { if (e.target.value.endsWith(',')) add(e.target.value); else setText(e.target.value) }}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(text) } }} onBlur={() => add(text)} />
    </label>
    {suggestions && <datalist id={listId}>{suggestions.map(s => <option key={s} value={s} />)}</datalist>}
    <div className="tags">{values.map(v => <span key={v}>{v} <button type="button" className="tag-remove" aria-label={`${v} 삭제`} onClick={() => onChange(values.filter(x => x !== v))}>×</button></span>)}</div>
    <small className="field-hint">{problem || hint || `${values.length}/${max}`}</small>
  </div>
}
