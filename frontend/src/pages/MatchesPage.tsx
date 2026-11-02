import { useCareer } from '../context/CareerContext'
import { title } from '../components/formHelpers'
import { MatchScore } from '../components/MatchScore'
import { dDayLabel, EMPLOYMENT_LABEL } from '../services/jobView'
import { RECOMMENDATION_NEXT } from '../services/matchView'
// GET /api/recommendations/jobs (D16, D42, D43): jobs ranked by the match score, each with its band, the skills
// the CV text shows (strengths) and lacks (gaps). Jobs still being scored are only counted (pending_count).
export function MatchesPage() {
  const { busy, go, openJob, recommendations, recommendationIssue, recommendationsLoaded, refreshRecommendations } = useCareer()
  const heading = title('당신과 연결되는 기회.', '추천 이유와 성장 방향까지, 함께 확인해보세요.')
  if (!recommendationsLoaded)
    return <>{heading}<div className="empty-state">추천 공고를 불러오는 중…</div></>
  if (!recommendations) {
    const next = recommendationIssue?.code ? RECOMMENDATION_NEXT[recommendationIssue.code] : undefined
    return (<>{heading}<div className="panel">
      <div className="empty-state" role="alert">
        <p>{recommendationIssue?.message}</p>
        {next ? <button className="btn" onClick={() => go(next.page)}>{next.label}</button> : <button className="btn" onClick={refreshRecommendations}>다시 시도</button>}
      </div>
    </div></>)
  }
  const { items, pending_count: pending, notice } = recommendations
  return (<>{heading}
    {pending > 0 && <div className="info-box reco-pending">
      분석 중인 공고가 {pending}건 있어요. 잠시 후 새로고침하면 결과가 보여요.
      <p><button className="text-link" disabled={busy} onClick={refreshRecommendations}>새로고침 ↻</button></p>
    </div>}
    {items.length === 0
      ? <div className="panel"><div className="empty-state">
          <span>✳</span>
          <p>{pending > 0 ? '분석이 끝나면 추천 공고가 여기에 보여요.' : '아직 추천할 공고가 없어요.'}<br />희망 조건을 바꾸거나 채용공고에서 새로운 기회를 찾아보세요.</p>
          <button className="btn secondary" onClick={() => go('profile')}>희망 조건 바꾸기</button> <button className="btn" onClick={() => go('jobs')}>채용공고 둘러보기 →</button>
        </div></div>
      : <div className="reco-list">{items.map(item => <article className="panel reco-card" key={item.job_id}>
          <div>
            <p className="muted">{item.company_name}</p>
            <button className="job-title" onClick={() => openJob(item.job_id)}>{item.title}<span>↗</span></button>
            <p className="muted">{[item.location, EMPLOYMENT_LABEL[item.employment_type], item.deadline ? `마감일 ${item.deadline} (${dDayLabel(item.deadline, false)})` : dDayLabel(null, false)].join(' · ')}</p>
            {item.strengths.length > 0 && <div className="reco-skills"><b>이력서에서 확인된 기술</b><div className="tags">{item.strengths.map(s => <span key={s}>{s}</span>)}</div></div>}
            {item.gaps.length > 0 && <div className="reco-skills"><b>이력서에서 찾지 못한 기술</b><div className="tags gap-tags">{item.gaps.map(s => <span key={s}>{s}</span>)}</div></div>}
          </div>
          <MatchScore score={item.match_score} level={item.match_level} notice={notice} />
        </article>)}</div>}
  </>)
}
