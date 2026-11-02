import type { Job } from '../types'
import { Icon } from './Icon'
import { useCareer } from '../context/CareerContext'
export function JobCard({ job: j }: {
  job: Job
}) {
  const { saved, toggleSave, user, openJob } = useCareer()
  const isSaved = saved.includes(j.id)
  return <article className="job-card">
    <div className="job-top">
      <span className={`company-logo ${j.color}`}>{j.logo}</span>
      {/* Saved jobs are for seekers (D45); a guest's click goes to login, companies do not see the button */}
      {user?.role !== 'company' && <button className={`icon-button ${isSaved ? 'is-saved' : ''}`} aria-pressed={isSaved} onClick={() => void toggleSave(j)} aria-label={`${j.company} ${j.title} 공고 ${isSaved ? '저장 취소' : '저장'}`}>
        <Icon name="bookmark" />
      </button>}
    </div>
    <div className="company-name">{j.company}</div>
    <button className="job-title" onClick={() => openJob(j.id)}>{j.title}<span>↗</span>
    </button>
    <p className="job-meta">{j.location && <>{j.location} <i /> </>}{j.experience} <i /> {j.employment}</p>
    {j.tags.length > 0 && <div className="tags">{j.tags.map(t => <span key={t}>{t}</span>)}</div>}
    <div className="job-bottom">
      <span>새로운 커리어의 시작</span>
      <b>{j.dDay}</b>
    </div>
  </article>
}
