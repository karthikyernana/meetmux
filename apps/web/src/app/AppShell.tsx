import { Outlet, NavLink, useParams } from "react-router-dom";
import {
  LayoutDashboard,
  Database,
  Activity,
  Sparkles,
  Table2,
  History,
  Settings,
} from "lucide-react";

function ShieldIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M8 1L2 3.5V8c0 3.31 2.5 5.79 6 7 3.5-1.21 6-3.69 6-7V3.5L8 1z" fill="currentColor" opacity="0.9"/>
    </svg>
  );
}

function WorkspaceNav() {
  const { workspaceId } = useParams();
  if (!workspaceId) return null;

  const base = `/workspaces/${workspaceId}`;
  const items = [
    { to: base, label: "Overview", icon: LayoutDashboard, end: true },
    { to: `${base}/workload`, label: "Workload", icon: Activity },
    { to: `${base}/recommendations`, label: "Recommendations", icon: Sparkles },
    { to: `${base}/indexes`, label: "Indexes", icon: Table2 },
    { to: `${base}/history`, label: "History", icon: History },
    { to: `${base}/settings`, label: "Settings", icon: Settings },
  ];

  return (
    <div className="sidebar-section">
      <p className="sidebar-label">Workspace</p>
      <nav style={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <Icon size={14} />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function GlobalNav() {
  return (
    <div className="sidebar-section">
      <p className="sidebar-label">Navigation</p>
      <nav>
        <NavLink
          to="/workspaces"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
        >
          <Database size={14} />
          Workspaces
        </NavLink>
      </nav>
    </div>
  );
}

export function AppShell() {
  return (
    <div className="shell">
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">
            <ShieldIcon />
          </div>
          <div>
            <div className="sidebar-logo-text">PlanGuard</div>
            <div className="sidebar-logo-sub">v0.1.0</div>
          </div>
        </div>

        {/* Nav */}
        <GlobalNav />
        <WorkspaceNav />

        <div className="sidebar-footer">PostgreSQL Optimizer</div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
