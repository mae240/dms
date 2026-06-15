import type { ReactNode } from "react";

import { ApiError } from "../lib/apiClient";

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="badge muted">—</span>;
  return <span className={`badge ${status}`}>{status}</span>;
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Unbekannter Fehler";
  return <div className="banner error">{message}</div>;
}

export function SuccessBanner({ children }: { children: ReactNode }) {
  return <div className="banner success">{children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Loading() {
  return <div className="empty">Lade …</div>;
}
