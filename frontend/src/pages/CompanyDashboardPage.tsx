import { useCareer } from '../context/CareerContext'
import { title } from '../components/formHelpers'
import { categories } from '../data/categories'
import { jobStatusLabel } from '../services/jobForm'
import { dDayLabel } from '../services/jobView'
import type { JobListItem } from '../types/job'
// The company's own jobs from GET /api/jobs/mine with what can be done in each status. The dashboard counts (D45)
// come with the stats endpoint in a later step; until then no numbers are shown. Who saved a job is never shown (D45).

const categoryLabel = (code: JobListItem['category']) => categories.find(c => c.code === code)?.label ?? '분야 미지정'

function JobRow({ job }: { job: JobListItem }) {
  const { busy, go, publishJob, publishProblem, closeJob, deleteJob } = useCareer()
  const issue = publishProblem?.jobId === job.id ? publishProblem : null
  const draft = job.status === 'draft'
  const published = job.status === 'published'
  const deadline = job.deadline ? `마감일 ${job.deadline} (${dDayLabel(job.deadline, job.status === 'closed' || job.expired)})` : '상시 채용'
  return <div className="company-job">
    <div className="company-job-main">
      <div>
        <b>{job.title}</b> <span className={`status job-status-${job.status}${job.expired && published ? ' expired' : ''}`}>{jobStatusLabel(job)}</span>
        <p className="muted">{[categoryLabel(job.category), job.location || '근무지 미정', deadline, `평가 기준 ${job.criteria_count}개`].join(' · ')}</p>
      </div>
      <div className="company-job-actions">
        {draft && <button className="text-link" onClick={() => go('post', job.id)}>수정</button>}
        <button className="text-link" onClick={() => go('criteria', job.id)}>{draft ? '평가 기준 설정' : '평가 기준'}</button>
        {!draft && <button className="text-link" onClick={() => go('detail', job.id)}>공고 보기</button>}
        {draft && <button className="btn small" disabled={busy} onClick={() => void publishJob(job.id)}>게시하기</button>}
        {published && <button className="btn small secondary" disabled={busy} onClick={() => {
          if (window.confirm(`‘${job.title}’ 공고를 마감할까요?\n마감하면 다시 게시할 수 없고, 공고 목록과 추천에서 빠집니다. 지원자는 그대로 볼 수 있어요.`))
            void closeJob(job.id)
        }}>마감하기</button>}
        {draft && <button className="text-link danger" disabled={busy} onClick={() => {
          if (window.confirm(`작성 중인 ‘${job.title}’ 공고를 삭제할까요? 되돌릴 수 없어요.`))
            void deleteJob(job.id)
        }}>삭제</button>}
      </div>
    </div>
    {issue && <div className="info-box apply-issue" role="alert">
      {issue.message}
      {issue.fix && <p><button className="text-link" onClick={() => go(issue.fix === 'edit' ? 'post' : 'criteria', job.id)}>{issue.fix === 'edit' ? '공고 수정하러 가기 →' : '평가 기준 설정하러 가기 →'}</button></p>}
    </div>}
  </div>
}

export function CompanyDashboardPage() {
  const { go, myJobs } = useCareer()
  return (<>{title('좋은 팀의 시작, 여기서.', '우리 팀에 꼭 맞는 동료를 만나보세요.')}
    <div className="dashboard-banner">
      <span>✳</span>
      <div>
        <h2>함께 성장할 동료를 찾고 있나요?</h2>
        <p>공고를 임시 저장하고 평가 기준을 정한 뒤 게시하세요.</p>
      </div>
      <button className="btn" onClick={() => go('post')}>공고 등록하기 ↗</button>
    </div>
    <div className="section-heading">
      <h2>우리 회사 공고 {myJobs && <span className="muted">{myJobs.length}</span>}</h2>
    </div>
    <div className="panel">
      {myJobs === null
        ? <div className="empty-state">공고를 불러오는 중…</div>
        : myJobs.length === 0
          ? <div className="empty-state"><p>아직 등록한 공고가 없어요.</p><button className="btn" onClick={() => go('post')}>첫 공고 등록하기 →</button></div>
          : myJobs.map(job => <JobRow key={job.id} job={job} />)}
    </div>
  </>)
}
