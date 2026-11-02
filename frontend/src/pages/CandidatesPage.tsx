import { useCareer } from '../context/CareerContext'
import { title } from '../components/formHelpers'
export function CandidatesPage() {
  const { candidate, setCandidate, invited, inviteCandidate } = useCareer()
  return (<>{title('가능성을 가진 다음 동료.', '지원자의 경험과 역량을 함께 살펴보세요.')}<div className="two-columns">
    <div className="panel">
      <h2>지원자 목록 <span className="muted">4</span>
      </h2>{['김지원', '박민서', '이서준', '최하린'].map((n, i) => <button key={n} className={`candidate-row ${candidate === i ? 'selected' : ''}`} onClick={() => setCandidate(i)}>
        <span className="avatar">{n[0]}</span>
        <div>
          <b>{n}</b>
          <p>React · TypeScript</p>
        </div>
        <b className="blue-text">{96 - i * 5}%</b>
        <span className="status">{invited.includes(i) ? '면접 예정' : '서류 검토'}</span>
      </button>)}</div>
    <div className="panel">
      <span className="eyebrow">CANDIDATE INSIGHTS</span>
      <h2>{['김지원', '박민서', '이서준', '최하린'][candidate]}</h2>
      <div className="match-score">
        <b>{96 - candidate * 5}%</b>
        <span>예시 AI 적합도</span>
      </div>
      <h3>추천 근거</h3>
      <p>React 및 TypeScript 프로젝트 경험이 직무 요구 사항과 연결됩니다.</p>
      <h3>추가 검토 사항</h3>
      <p>테스트 자동화와 서비스 운영 경험을 면접에서 확인해보세요.</p>
      <button className="btn full" disabled={invited.includes(candidate)} onClick={() => void inviteCandidate(candidate)}>{invited.includes(candidate) ? '면접 대상 선정 완료 ✓' : '면접 대상 선정 →'}</button>
      <p className="demo-note">모든 지원자 정보는 가상 데이터입니다.</p>
    </div>
  </div>
  </>)
}
