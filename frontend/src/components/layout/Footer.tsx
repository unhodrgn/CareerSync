import { useCareer } from '../../context/CareerContext'
import { homeFor } from '../../hooks/useCareerStore'
export function Footer() {
  const { user, go, setRegisterRole } = useCareer()
  return (<footer>
    <button className="brand" onClick={() => go('home')}>
      <span className="brand-mark">✳</span>CareerSync.</button>
    <p>가능성을 연결하고, 내일을 바꾸다.</p>
    <span>© 2026 CareerSync · Team project</span>
    {/* Guests go to company sign-up; signed-in users to their own dashboard (no role switch) */}
    <button onClick={() => { if (!user) setRegisterRole('company'); go(user ? homeFor(user.role) : 'register') }}>기업 서비스 ↗</button>
  </footer>)
}
