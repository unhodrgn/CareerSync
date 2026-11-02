import { useCareer } from '../context/CareerContext'
import { Icon } from '../components/Icon'
import { consentDraftNote, consentItems } from '../data/consentText'
import { roleLabel } from '../hooks/useCareerStore'
import type { Role } from '../types/common'

// Same rule as RegisterIn in backend/app/schemas/auth.py: 8–128 characters with a letter and a digit
const passwordProblem = (password: string) => password.length < 8 ? '비밀번호는 8자 이상이어야 합니다.' : !(/[A-Za-z]/.test(password) && /\d/.test(password)) ? '비밀번호는 영문과 숫자를 모두 포함해야 합니다.' : ''

export function AuthPage() {
  const { busy, page, registerRole, setRegisterRole, go, notify, login, register } = useCareer()
  const company = registerRole === 'company'
  return (<div className="auth-layout">
    <div className="auth-intro">
      <span className="eyebrow">YOUR FUTURE STARTS HERE</span>
      <h1>가능성의 시작,<br />
        <span className="blue-text">함께 연결해요.</span>
      </h1>
      <div className="auth-art">✳</div>
      <p>나를 알아보는 기회, CareerSync.</p>
    </div>
    <div className="panel auth-panel">{page === 'signup' ? <>
      <span className="eyebrow">LET’S GET STARTED</span>
      <h2>어떤 여정을 시작할까요?</h2>
      <p className="muted">이용 목적에 맞는 계정을 선택해주세요.</p>{(['seeker', 'company'] as Role[]).map(r => <button key={r} className="role-card" onClick={() => { setRegisterRole(r); go('register') }}>
        <span>{r === 'company' ? '▦' : '✦'}</span>
        <div>
          <h3>{roleLabel(r)}로 시작하기</h3>
          <p>{r === 'company' ? '우리 팀의 다음 동료를 만나세요.' : '나에게 맞는 다음 기회를 발견하세요.'}</p>
        </div>↗</button>)}<button className="text-link" onClick={() => go('login')}>이미 계정이 있나요? 로그인 →</button>
    </> : <form onSubmit={e => {
      e.preventDefault()
      const data = new FormData(e.currentTarget)
      const text = (name: string) => String(data.get(name) ?? '').trim()
      if (page === 'login') {
        void login(text('email'), String(data.get('password') ?? ''))
        return
      }
      const password = String(data.get('password') ?? '')
      const problem = passwordProblem(password) || (password !== data.get('confirm') ? '비밀번호가 일치하지 않습니다.' : '')
      if (problem) {
        notify(problem)
        return
      }
      void register({
        role: registerRole,
        displayName: text('display_name'),
        companyName: text('company_name'),
        email: text('email'),
        password,
        consentPrivacy: data.get('consent_privacy') === 'on',
        consentAi: data.get('consent_ai') === 'on',
      })
    }}>
      <span className="eyebrow">WELCOME TO CAREERSYNC</span>
      <h2>{page === 'login' ? '다시 만나 반가워요.' : `${roleLabel(registerRole)} 회원가입`}</h2>
      <p className="muted">당신의 다음 챕터를 시작하세요.</p>
      {page === 'register' && company && <label>회사명<input name="company_name" required maxLength={100} placeholder="회사명 입력" />
        <small className="field-hint">계정 하나에 기업 하나가 등록됩니다.</small>
      </label>}
      {page === 'register' && <label>{company ? '담당자 표시 이름' : '이름'}<input name="display_name" required maxLength={50} placeholder={company ? '예: 넥스트코드 인사팀' : '이름 입력'} />
        <small className="field-hint">{company ? '이 계정에 표시되는 이름입니다.' : '지원한 기업, 그리고 제안을 수락한 기업에만 공개됩니다.'}</small>
      </label>}
      <label>이메일<input name="email" type="email" required maxLength={255} autoComplete="email" placeholder="hello@example.com" />
      </label>
      <label>비밀번호<input name="password" type="password" minLength={page === 'register' ? 8 : undefined} maxLength={128} required autoComplete={page === 'login' ? 'current-password' : 'new-password'} placeholder={page === 'login' ? '비밀번호 입력' : '8자 이상, 영문과 숫자를 모두 포함'} />
      </label>{page === 'register' && <>
        <label>비밀번호 확인<input name="confirm" type="password" required autoComplete="new-password" placeholder="비밀번호를 다시 입력해주세요" />
        </label>
        {consentItems.map(item => <div className="consent-item" key={item.name}>
          <label className="checkbox-label">
            <input type="checkbox" name={item.name} required />[필수] {item.title}</label>
          <details>
            <summary>내용 보기</summary>
            <p>{item.body}</p>
          </details>
        </div>)}
        <p className="demo-note">{consentDraftNote}</p>
      </>}<button className="btn full" disabled={busy}>{page === 'login' ? '로그인' : '가입하기'} <Icon name="arrow" />
      </button>
      <button type="button" className="text-link" onClick={() => go(page === 'login' ? 'signup' : 'login')}>{page === 'login' ? '처음이신가요? 회원가입 →' : '이미 계정이 있나요? 로그인 →'}</button>
    </form>}</div>
  </div>)
}
