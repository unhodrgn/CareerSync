import { Navigate, Route, Routes } from "react-router-dom";
import type { Role } from "./api/types";
import { homeFor, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import Applicants from "./pages/company/Applicants";
import CompanyProfile from "./pages/company/CompanyProfile";
import JobEditor from "./pages/company/JobEditor";
import JobList from "./pages/company/JobList";
import Talent from "./pages/company/Talent";
import JobDetail from "./pages/seeker/JobDetail";
import MyPage from "./pages/seeker/MyPage";
import Prep from "./pages/seeker/Prep";
import Recommended from "./pages/seeker/Recommended";
import Resume from "./pages/seeker/Resume";
import Login from "./pages/Login";
import Register from "./pages/Register";

function Guard({ role, children }: { role: Role; children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted center-text">불러오는 중…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={homeFor(user)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted center-text">불러오는 중…</p>;
  return <Navigate to={user ? homeFor(user) : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<Layout />}>
        <Route path="/seeker" element={<Guard role="seeker"><Recommended /></Guard>} />
        <Route path="/seeker/jobs/:id" element={<Guard role="seeker"><JobDetail /></Guard>} />
        <Route path="/seeker/resume" element={<Guard role="seeker"><Resume /></Guard>} />
        <Route path="/seeker/prep" element={<Guard role="seeker"><Prep /></Guard>} />
        <Route path="/seeker/me" element={<Guard role="seeker"><MyPage /></Guard>} />

        <Route path="/company/jobs" element={<Guard role="company"><JobList /></Guard>} />
        <Route path="/company/jobs/new" element={<Guard role="company"><JobEditor /></Guard>} />
        <Route path="/company/jobs/:id/edit" element={<Guard role="company"><JobEditor /></Guard>} />
        <Route path="/company/applicants" element={<Guard role="company"><Applicants /></Guard>} />
        <Route path="/company/talent" element={<Guard role="company"><Talent /></Guard>} />
        <Route path="/company/profile" element={<Guard role="company"><CompanyProfile /></Guard>} />
      </Route>

      <Route path="*" element={<Home />} />
    </Routes>
  );
}
