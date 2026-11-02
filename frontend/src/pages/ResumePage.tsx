import { useState } from 'react'
import { useCareer } from '../context/CareerContext'
import { Icon } from '../components/Icon'
import { CvEditor } from '../components/CvEditor'
import { title } from '../components/formHelpers'
import { maskedKindLabel } from '../data/labels'
import type { CvReviewItem } from '../types/cv'

// Same limits as the backend (ai/parsing/pdf.py): a text PDF of at most 5 MB and 5 pages. The page count is only
// known after reading the file, so the server checks it (422 CV_TOO_MANY_PAGES).
const MAX_BYTES = 5 * 1024 * 1024

// The page shows only what the API returns: the analysis of the PII-masked text (D39). Nothing is logged.
function ReviewList({ heading, items }: { heading: string, items: CvReviewItem[] }) {
  return <>
    <h3>{heading}</h3>
    {items.length === 0 && <p className="muted">해당 항목이 없어요.</p>}
    {items.map((item, i) => <div className="review-item" key={i}>
      <b>{item.title}{item.affects_scoring && <span className="status">평가에 영향</span>}</b>
      <p>{item.detail}</p>
      {item.cv_quote && <blockquote>{item.cv_quote}</blockquote>}
    </div>)}
  </>
}

export function ResumePage() {
  const { busy, cv, cvLoaded, cvReview, uploadCv, confirmCv, reviewCv, go, notify } = useCareer()
  const [file, setFile] = useState<File | null>(null)
  const pick = (f: File | undefined) => {
    if (!f)
      return
    if (f.type !== 'application/pdf')
      notify('PDF 파일만 올릴 수 있습니다.')
    else if (f.size > MAX_BYTES)
      notify('이력서 파일은 5MB 이하여야 합니다.')
    else
      setFile(f)
  }
  const years = cv ? Math.floor(cv.total_experience_months / 12) : 0
  const months = cv ? cv.total_experience_months % 12 : 0
  return (<>{title('경험을 넘어, 가능성을 발견해요.', '이력서를 올리고 나의 강점과 다음 단계를 확인하세요.')}<div className="two-columns">
    <div className="panel">
      <h2>{cv ? '내 이력서' : '이력서 업로드'}</h2>
      {cv && <div className="info-box">
        <b className="cv-file">{cv.file_name}</b>
        <p>{cv.pages}쪽 · 버전 {cv.version} · 경력 {years}년 {months}개월</p>
        <p>{cv.confirmed ? '✓ 확인 완료 — 이 내용으로 지원합니다.' : '확인이 필요해요. 아래 내용을 확인하고 저장해야 지원할 수 있어요.'}</p>
        <p>{cv.masked_kinds.length ? `분석 전에 가린 개인정보: ${cv.masked_kinds.map(k => maskedKindLabel[k] ?? k).join(', ')}` : '분석 전에 가린 개인정보가 없어요.'}</p>
      </div>}
      <label className="upload-zone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); pick(e.dataTransfer.files[0]) }}>
        <Icon name="upload" size={34} />
        <b>{file ? file.name : cv ? '새 이력서를 여기에 놓아주세요' : '이력서를 여기에 놓아주세요'}</b>
        <span>또는 클릭하여 파일 선택 · 텍스트 PDF, 최대 5MB · 5쪽</span>
        <input type="file" accept="application/pdf" onChange={e => pick(e.target.files?.[0])} />
      </label>
      <p className="muted small-copy">이름·연락처 등 개인정보는 서버에서 가린 뒤 분석합니다. 결과는 확인하고 저장해야 지원에 쓰입니다.</p>
      <button className="btn full" disabled={!file || busy} onClick={() => { if (file) void uploadCv(file).then(ok => { if (ok) setFile(null) }) }}>✦ {cv ? '새 이력서로 다시 분석' : '이력서 분석 시작'}</button>
      {cv && <div className="info-box ai-notice">{cv.notice}</div>}
    </div>
    <div className="panel">
      <span className="eyebrow">YOUR CAREER INSIGHTS</span>
      <h2>{cvReview ? '가능성이 더 선명해졌어요.' : '당신의 강점, 곧 만나보세요.'}</h2>
      {!cvLoaded ? <div className="empty-state">불러오는 중…</div> : !cv ? <div className="empty-state">
        <span>✳</span>
        <p>이력서를 올리면<br />강점과 보완할 점을 AI가 점검해드려요.</p>
      </div> : cvReview ? <>
        {cvReview.limited && <p className="muted">오늘 AI 점검 횟수를 모두 써서 규칙 기반 점검 결과를 보여드려요.</p>}
        <ReviewList heading="✦ 잘하고 있어요" items={cvReview.strengths} />
        <ReviewList heading="↗ 이렇게 더해보세요" items={cvReview.improvements} />
        <div className="info-box ai-notice">{cvReview.notice}</div>
        <button className="btn secondary" onClick={() => go('jobs')}>채용공고 둘러보기 →</button>
      </> : <>
        <p className="muted">현재 버전의 이력서를 기준으로 강점과 보완할 점을 알려드려요. 점수는 매기지 않아요.</p>
        <button className="btn" disabled={busy} onClick={() => void reviewCv()}>✦ AI 이력서 점검 받기</button>
      </>}
    </div>
  </div>
    {cv && <div className="panel cv-panel">
      <h2>분석 결과 확인</h2>
      <p className="muted">AI가 읽은 내용이에요. 틀린 부분을 고치고 저장하면 새 버전으로 저장되고, 그 버전으로 지원합니다.</p>
      {/* A new version (upload or save) resets the form to what the server returned */}
      <CvEditor key={cv.id} profile={cv.profile} busy={busy} confirmed={cv.confirmed} onConfirm={profile => void confirmCv(profile)} />
    </div>}
  </>)
}
