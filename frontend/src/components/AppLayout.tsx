import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../lib/auth";
import { Glyph } from "./icons";

export function AppLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const raw = user?.full_name?.trim() || user?.email?.trim() || "?";
  const initials =
    raw.split(/\s+/).filter(Boolean).map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "?";

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div className="layout">
      <div className="mobile-topbar">
        <button
          className="icon-btn"
          onClick={() => setOpen(true)}
          aria-label="Menue oeffnen"
          aria-expanded={open}
          aria-controls="app-sidebar"
        >
          <Glyph name="menu" />
        </button>
        <strong>DMS</strong>
      </div>
      {open && <div className="drawer-overlay" onClick={close} />}
      <aside id="app-sidebar" className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <div className="logo">D</div>
          <div>
            <strong>DMS</strong>
            <span>Dokumentenverwaltung</span>
          </div>
        </div>

        <div className="nav-label">Workspace</div>
        <nav>
          <NavLink to="/dashboard" onClick={close}>
            <span className="nav-icon"><Glyph name="dashboard" /></span> Dashboard
          </NavLink>
          <NavLink to="/projects" onClick={close}>
            <span className="nav-icon"><Glyph name="projects" /></span> Projekte
          </NavLink>
        </nav>

        {user?.is_superadmin && (
          <>
            <div className="nav-label">Compliance</div>
            <nav>
              <NavLink to="/admin/audit-logs" onClick={close}>
                <span className="nav-icon"><Glyph name="audit" /></span> Audit-Log
              </NavLink>
              <NavLink to="/admin/compliance" onClick={close}>
                <span className="nav-icon"><Glyph name="compliance" /></span> Compliance-Center
              </NavLink>
            </nav>
            <div className="nav-label">Admin</div>
            <nav>
              <NavLink to="/admin/users" onClick={close}>
                <span className="nav-icon"><Glyph name="users" /></span> Benutzer
              </NavLink>
            </nav>
          </>
        )}

        <div className="account-card">
          <div className="account-row">
            <div className="avatar">{initials}</div>
            <div style={{ minWidth: 0 }}>
              <div className="account-name">{user?.full_name || "—"}</div>
              <div className="account-mail">{user?.email}</div>
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <NavLink to="/account" className="btn small ghost" onClick={close} style={{ flex: 1 }}>
              Konto
            </NavLink>
            <button className="btn small" onClick={() => logout()} style={{ flex: 1 }}>
              Abmelden
            </button>
          </div>
        </div>
      </aside>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
