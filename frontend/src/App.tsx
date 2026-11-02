import { useScrollReveal } from './hooks/useScrollReveal'
import { CareerProvider, useCareer } from './context/CareerContext'
import { Header } from './components/layout/Header'
import { Footer } from './components/layout/Footer'
import { Sidebar } from './components/layout/Sidebar'
import { HomePage } from './pages/HomePage'
import { JobsPage } from './pages/JobsPage'
import { JobDetailPage } from './pages/JobDetailPage'
import { AuthPage } from './pages/AuthPage'
import { ConsentPage } from './pages/ConsentPage'
import { DashboardPage } from './pages/DashboardPage'
import { ResumePage } from './pages/ResumePage'
import { MatchesPage } from './pages/MatchesPage'
import { ProfilePage } from './pages/ProfilePage'
import { ApplicationsPage } from './pages/ApplicationsPage'
import { PostJobPage } from './pages/PostJobPage'
import { CompanyDashboardPage } from './pages/CompanyDashboardPage'
import { CriteriaPage } from './pages/CriteriaPage'
import { CandidatesPage } from './pages/CandidatesPage'
import './App.css'
import './motion.css'

// App only assembles the layout and the page. Data logic lives in hooks/ and services/.
function AppContent() {
  const { page, viewReady, toast, busy, error } = useCareer()
  const motionRoot = useScrollReveal(page, busy)
  const pages = {
    home: <HomePage />,
    jobs: <JobsPage />,
    detail: <JobDetailPage />,
    login: <AuthPage />,
    signup: <AuthPage />,
    register: <AuthPage />,
    consent: <ConsentPage />,
    dashboard: <DashboardPage />,
    company: <CompanyDashboardPage />,
    resume: <ResumePage />,
    matches: <MatchesPage />,
    profile: <ProfilePage />,
    applications: <ApplicationsPage />,
    post: <PostJobPage />,
    criteria: <CriteriaPage />,
    candidates: <CandidatesPage />,
  }

  return (
    <div className="app" ref={motionRoot}>
      <Header />
      {busy && <div className="request-status" role="status">처리 중…</div>}
      {error && <div className="request-error" role="alert">{error}</div>}
      {page === 'home' ? pages.home : (
        <main className="workspace">
          <Sidebar />
          {/* Until the stored token is checked, a signed-in page shows nothing rather than the login form */}
          <div className="page-content page-enter" key={page}>{viewReady && (pages[page] || pages.home)}</div>
        </main>
      )}
      <Footer />
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}

export default function App() {
  return (
    <CareerProvider>
      <AppContent />
    </CareerProvider>
  )
}
