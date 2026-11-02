import { useCareer } from '../context/CareerContext'
import { title } from '../components/formHelpers'
import { applicationStatusLabel } from '../data/labels'
// GET /api/applications/mine. The status is set only by the company (AI rule 5); applied jobs show no score (Q-D).
export function ApplicationsPage() {
  const { openJob, applications, go } = useCareer()
  const count = (statuses: string[]) => applications.filter(a => statuses.includes(a.status)).length
  return (<>{title('한 걸음씩, 다음 커리어로.', '지원한 공고와 진행 상태를 한눈에 확인하세요.')}<div className="stats">
    <div className="panel stat">
      <span>전체 지원</span>
      <b>{applications.length}</b>
    </div>
    <div className="panel stat">
      <span>검토 중</span>
      <b>{count(['submitted', 'reviewing'])}</b>
    </div>
    <div className="panel stat">
      <span>면접 예정</span>
      <b>{count(['interview'])}</b>
    </div>
  </div>
    <div className="panel">
      <h2>나의 지원 내역</h2>{applications.map(a => <button className="list-row" key={a.id} onClick={() => openJob(a.job_id)}>
        <span className="avatar">{a.company_name.slice(0, 1)}</span>
        <b>{a.company_name} · {a.job_title}</b>
        <span>{a.created_at.slice(0, 10)} 지원</span>
        <span className="status">{applicationStatusLabel[a.status]}</span>
        <span>↗</span>
      </button>)}{!applications.length && <div className="empty-state">
        <p>아직 지원한 공고가 없어요.<br />마음에 드는 기회에 첫 발을 내디뎌보세요.</p>
        <button className="btn" onClick={() => go('jobs')}>채용공고 둘러보기 →</button>
      </div>}
      <p className="demo-note">진행 상태는 기업 담당자가 바꿉니다. AI 분석은 참고용이며 합격 여부를 정하지 않습니다.</p>
    </div>
  </>)
}
