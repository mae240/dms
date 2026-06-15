import type { ReactNode } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="empty">Lade …</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function RequireSuperadmin() {
  const { user, loading } = useAuth();
  if (loading) return <div className="empty">Lade …</div>;
  if (!user?.is_superadmin) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
