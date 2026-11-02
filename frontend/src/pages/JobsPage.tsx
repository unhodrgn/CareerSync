import { useCareer } from '../context/CareerContext'
import { Icon } from '../components/Icon'
import { JobCard } from '../components/JobCard'
import { title } from '../components/formHelpers'
import { categories, regions } from '../data/categories'
// Search and filters run on the server: GET /api/jobs?q=&category=&region= (D45). The 저장한 공고 tab (seekers)
// shows GET /api/saved-jobs/mine instead, closed and expired jobs included; the search and filters do not apply to it.
export function JobsPage() {
  const { busy, user, query, setQuery, category, setCategory, region, setRegion, jobs, jobsTotal, jobsLoading, loadMoreJobs, savedJobs, onlySaved, setOnlySaved } = useCareer()
  const showSaved = onlySaved && user?.role === 'seeker'
  const filtered = query !== '' || category !== null || region !== ''
  const list = showSaved ? savedJobs : jobs
  return (<>{title('새로운 가능성을 탐색하세요.', '당신의 다음 챕터가 될 기회를 찾아보세요.')}<form className="search-box wide-search" onSubmit={e => e.preventDefault()}>
    <Icon name="search" />
    <input aria-label="검색" value={query} onChange={e => { setQuery(e.target.value); setOnlySaved(false) }} maxLength={100} placeholder="직무, 기업, 기술 스택 검색" />
    <select aria-label="근무 지역" value={region} onChange={e => { setRegion(e.target.value); setOnlySaved(false) }}>
      <option value="">전체 지역</option>
      {regions.map(r => <option key={r} value={r}>{r}</option>)}
    </select>
  </form>
    <div className="category-tabs">{categories.map(c => <button key={c.label} className={!showSaved && category === c.code ? 'selected' : ''} aria-pressed={!showSaved && category === c.code} onClick={() => { setCategory(c.code); setOnlySaved(false) }}>{c.label}</button>)}
      {user?.role === 'seeker' && <button className={showSaved ? 'selected' : ''} aria-pressed={showSaved} onClick={() => setOnlySaved(!showSaved)}>저장한 공고 {savedJobs.length}</button>}
    </div>
    <div className="results-heading">
      <b>{showSaved ? `저장한 공고 ${savedJobs.length}개` : jobsLoading ? '불러오는 중…' : `${jobsTotal}개의 기회`}</b>
      {!showSaved && filtered && <button onClick={() => { setQuery(''); setCategory(null); setRegion('') }}>필터 초기화 ↻</button>}
    </div>
    <div className="job-grid">{list.map(j => <JobCard key={j.id} job={j} />)}</div>
    {showSaved && !savedJobs.length && <div className="empty-state">아직 저장한 공고가 없어요. 마음에 드는 공고의 북마크를 눌러보세요.</div>}
    {!showSaved && !jobsLoading && !jobs.length && <div className="empty-state">{filtered ? '검색 결과가 없어요. 다른 키워드나 조건으로 찾아보세요.' : '아직 게시된 채용공고가 없어요.'}</div>}
    {!showSaved && !jobsLoading && jobs.length < jobsTotal && <div className="load-more">
      <button className="btn secondary" disabled={busy} onClick={() => void loadMoreJobs()}>더 보기 ({jobs.length}/{jobsTotal})</button>
    </div>}
  </>)
}
