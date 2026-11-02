import { useCareer } from '../context/CareerContext'
import { Icon } from '../components/Icon'
import { title } from '../components/formHelpers'
import { consentDraftNote, consentItems } from '../data/consentText'
import { homeFor } from '../hooks/useCareerStore'

// Re-consent (docs/DECISIONS.md D17): shown when GET /api/users/me says consent_required, i.e. the user agreed to
// an older text version or withdrew AI consent. The store only routes signed-in users here.
export function ConsentPage() {
  const { busy, user, go, logout, submitConsent } = useCareer()
  if (!user)
    return null
  // Same version but still required: AI consent was withdrawn; otherwise the text changed since the last consent
  const withdrawn = user.consent_version === user.current_consent_version
  return (<>{title('동의가 필요합니다', withdrawn ? 'AI 분석 동의가 철회된 상태입니다. 서비스를 계속 이용하려면 다시 동의해 주세요.' : '동의 문구가 바뀌었습니다. 바뀐 내용을 확인하고 다시 동의해 주세요.')}
    <form className="panel profile-form" onSubmit={e => { e.preventDefault(); void submitConsent() }}>
      <p className="muted">동의 문구 버전 <b>{user.current_consent_version}</b></p>
      {consentItems.map(item => <div className="consent-item" key={item.name}>
        <label className="checkbox-label">
          <input type="checkbox" name={item.name} required />[필수] {item.title}</label>
        <details>
          <summary>내용 보기</summary>
          <p>{item.body}</p>
        </details>
      </div>)}
      <p className="demo-note">{consentDraftNote}</p>
      <button className="btn" disabled={busy}>동의하고 계속하기 <Icon name="check" /></button>
      <div className="consent-actions">
        {/* A withdrawn seeker may keep using the features without AI (D17) */}
        {withdrawn && <button type="button" className="text-link" onClick={() => go(homeFor(user.role))}>나중에 하기</button>}
        <button type="button" className="text-link" onClick={() => { logout(); go('login') }}>다른 계정으로 로그인</button>
      </div>
    </form>
  </>)
}
