import { useCareer } from '../context/CareerContext'
import { JobCard } from '../components/JobCard'
import { title } from '../components/formHelpers'
import type { Page } from '../types'
// The seeker dashboard; the company one is CompanyDashboardPage.
export function DashboardPage() {
  const { user, saved, setOnlySaved, applied, cv, recommendations, recommendationIssue, go, jobs } = useCareer()
  // Recommended jobs with a score now; jobs still being scored are counted on the tile's second line (D16, D43)
  const recoCount = recommendations ? String(recommendations.items.length) : recommendationIssue ? '—' : '…'
  const recoNote = recommendations && recommendations.pending_count > 0 ? `분석 중 ${recommendations.pending_count}건` : recommendationIssue ? '추천을 받으려면 확인이 필요해요' : '새로운 가능성이 기다려요'
  return (<>{title(`안녕하세요, ${user?.display_name ?? ''}님 👋`, '오늘도 당신의 가능성에 한 걸음 더 가까이.')}<div className="stats">{[['이력서 상태', cv ? (cv.confirmed ? '확인 완료' : '확인 필요') : '미등록'], ['추천 채용공고', recoCount], ['지원 현황', String(applied.length)], ['저장한 공고', String(saved.length)]].map(([l, v], i) => <button className="stat panel" key={l} onClick={() => { if (i === 3) setOnlySaved(true); go((['resume', 'matches', 'applications', 'jobs'] as Page[])[i]) }}>
    <span>{l} ↗</span>
    <b>{v}</b>
    <small>{i === 1 ? recoNote : '자세히 확인하기'}</small>
  </button>)}</div>
    <div className="dashboard-banner">
      <span>✳</span>
      <div>
        <h2>당신의 경험 속에 숨은 강점을 발견하세요.</h2>
        <p>AI와 함께 더 선명한 다음 단계를 그려보세요.</p>
      </div>
      <button className="btn" onClick={() => go('resume')}>이력서 분석하기 ↗</button>
    </div>
    <div className="section-heading">
      <h2>당신을 위한 추천 기회</h2>
      <button className="text-link" onClick={() => go('matches')}>전체 보기 →</button>
    </div>
    <div className="job-grid">{jobs.slice(0, 3).map(j => <JobCard key={j.id} job={j} />)}</div></>)
}
