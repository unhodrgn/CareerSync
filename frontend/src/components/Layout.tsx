import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const SEEKER_NAV: NavItem[] = [
  { to: "/seeker", label: "추천 공고", end: true },
  { to: "/seeker/resume", label: "내 이력서" },
  { to: "/seeker/prep", label: "취업 준비" },
  { to: "/seeker/me", label: "마이페이지" },
];

const COMPANY_NAV: NavItem[] = [
  { to: "/company/jobs", label: "채용공고 관리" },
  { to: "/company/applicants", label: "지원자 관리" },
  { to: "/company/talent", label: "인재 추천" },
  { to: "/company/profile", label: "기업 프로필" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const nav = user?.role === "company" ? COMPANY_NAV : SEEKER_NAV;

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">CareerSync</span>
        <nav className="topnav">
          {nav.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-user">
          {user && (
            <>
              <span className="muted">{user.display_name}</span>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                로그아웃
              </button>
            </>
          )}
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
