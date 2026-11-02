import { useCareer } from '../../context/CareerContext'
import { homeFor } from '../../hooks/useCareerStore'
export function Header() {
  const { page, user, setOnlySaved, go, logout } = useCareer()
  return (<header className="header">
    <button className="brand" onClick={() => go('home')}>
      <span className="brand-mark">✳</span>CareerSync<span className="brand-dot">.</span>
    </button>
    <nav>
      <button className={page === 'jobs' ? 'active' : ''} onClick={() => { setOnlySaved(false); go('jobs') }}>채용공고</button>
      <button onClick={() => go('matches')}>AI 커리어 매칭 <span className="new">NEW</span>
      </button>
      <button onClick={() => { go('home'); setTimeout(() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }), 50) }}>서비스 소개</button>
    </nav>
    <div className="header-actions">{user ? <>
      <button onClick={() => go(homeFor(user.role))}>내 대시보드</button>
      <button onClick={logout}>로그아웃</button>
      <button className="avatar" aria-label={`${user.display_name} 프로필`} title={user.display_name} onClick={() => go(user.role === 'company' ? 'company' : 'profile')}>{user.display_name.slice(0, 1)}</button>
    </> : <>
      <button onClick={() => go('login')}>로그인</button>
      <button className="btn small" onClick={() => go('signup')}>무료로 시작하기 <span>↗</span>
      </button>
    </>}</div>
  </header>)
}
