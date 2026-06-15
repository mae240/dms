import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function AppLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">DMS</div>
        <nav>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/projects">Projekte</NavLink>
        </nav>
        {user?.is_superadmin && (
          <>
            <div className="section">Compliance</div>
            <nav>
              <NavLink to="/admin/users">Benutzer</NavLink>
              <NavLink to="/admin/audit-logs">Audit-Log</NavLink>
              <NavLink to="/admin/compliance">Compliance</NavLink>
            </nav>
          </>
        )}
        <div className="section">Konto</div>
        <nav>
          <NavLink to="/account">Konto / Passwort</NavLink>
        </nav>
        <div className="muted" style={{ padding: "0.25rem 0.7rem", fontSize: "0.85rem" }}>
          {user?.full_name || user?.email}
        </div>
        <button className="small" style={{ marginTop: "0.5rem" }} onClick={() => logout()}>
          Abmelden
        </button>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
