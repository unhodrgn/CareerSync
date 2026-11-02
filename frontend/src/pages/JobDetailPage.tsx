import { useCareer } from '../context/CareerContext'
import { MatchScore } from '../components/MatchScore'
import { applicationStatusLabel } from '../data/labels'
import { detailMatchState } from '../services/matchView'
import type { Page } from '../types'
// GET /api/jobs/{id} and its criteria. Match score (D44): GET /api/jobs/{id}/match for seekers, shown only when an
// evaluation is already done; it never starts one. Guests, companies and applied jobs see no score.
// Saving: seekers and guests (who go to login); companies do not see it (D45).
// Applying: POST /api/jobs/{id}/applications; the button follows the seeker's real application.

// What the seeker can do next after a refused apply (409); the message itself comes from services/errors.ts
const APPLY_NEXT: Record<string, { label: string, page: Page } | undefined> = {
  CV_NOT_CONFIRMED: { label: '내 이력서 확인하러 가기 →', page: 'resume' },
  AI_CONSENT_REQUIRED: { label: 'AI 분석 동의하러 가기 →', page: 'consent' },
}

export function JobDetailPage() {
  const { busy, jobDetail, user, applications, saved, toggleSave, go, apply, applyIssue, jobMatch } = useCareer()
  const back = <button className="text-link" onClick={() => go('jobs')}>← 채용공고로 돌아가기</button>
  if (!jobDetail)
    return <>{back}<div className="empty-state">공고를 불러오는 중…</div></>
  const job = jobDetail.job
  if (!job)
    return <>{back}<div className="empty-state">{jobDetail.error}</div></>
  const application = applications.find(a => a.job_id === job.id)
  const issue = applyIssue?.jobId === job.id ? applyIssue : null
  const next = issue ? APPLY_NEXT[issue.code] : undefined
  const matchState = detailMatchState(user?.role ?? null, !!application, jobMatch)
  return (<>
    {back}
    <div className="detail-layout">
      <article className="panel">
        <span className={`company-logo ${job.color}`}>{job.logo}</span>
        <p>{job.company}</p>
        <h1>{job.title}</h1>
        <p className="muted">{[job.location, job.employment, job.experience].filter(Boolean).join(' · ')}</p>
        <p className="muted">{job.deadline ? `마감일 ${job.deadline} (${job.dDay})` : job.dDay}</p>
        {job.tags.length > 0 && <div className="tags">{job.tags.map(t => <span key={t}>{t}</span>)}</div>}
        <section className="detail-section">
          <h2>공고 내용</h2>
          <p>{job.description || '공고 내용이 아직 없습니다.'}</p>
        </section>
        {job.salaryNote && <section className="detail-section">
          <h2>급여</h2>
          <p>{job.salaryNote}</p>
        </section>}
        {job.criteria.length > 0 && <section className="detail-section">
          <h2>평가 기준</h2>
          <p className="muted">이 공고는 아래 기준으로 지원자를 평가합니다.</p>
          <div className="tags">{job.criteria.map(c => <span key={c.name}>{c.name}{c.importance && ` · ${c.importance}`}</span>)}</div>
        </section>}
      </article>
      <aside className="panel apply-panel">
        <span className="eyebrow">YOUR NEXT OPPORTUNITY</span>
        <h2>새로운 시작을 함께해요.</h2>
        <p>이력서와 함께 당신의 가능성을 전하세요.</p>
        {matchState === 'done' && jobMatch?.match_score != null && jobMatch.match_level && <MatchScore score={jobMatch.match_score} level={jobMatch.match_level} notice={jobMatch.notice} />}
        {matchState === 'pending' && <div className="info-box">이 공고와의 매칭 점수를 계산하고 있어요. 잠시 후 다시 확인해 주세요.</div>}
        {matchState === 'none' && <div className="info-box">
          매칭 점수는 추천 공고에서 확인할 수 있어요.
          <p><button className="text-link" onClick={() => go('matches')}>추천 공고 보기 →</button></p>
        </div>}
        {/* Companies cannot apply; the backend answers 403 SEEKER_ONLY anyway */}
        {user?.role !== 'company' && <button className="btn" onClick={() => void apply(job.id)} disabled={busy || !!application || job.expired}>{application ? `지원 완료 ✓ · ${applicationStatusLabel[application.status]}` : job.expired ? '마감된 공고' : '지원하기 ↗'}</button>}
        {issue && <div className="info-box apply-issue" role="alert">
          {issue.message}
          {next && <p><button className="text-link" onClick={() => go(next.page)}>{next.label}</button></p>}
        </div>}
        {user?.role !== 'company' && <button className="btn secondary" aria-pressed={saved.includes(job.id)} onClick={() => void toggleSave(job)}>{saved.includes(job.id) ? '저장됨 ✓' : '공고 저장하기'}</button>}
      </aside>
    </div>
  </>)
}
