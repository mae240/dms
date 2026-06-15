// Imperativer Bestaetigungs-Dialog (Ersatz fuer window.confirm).
// Gleiches Modul-Store-Pattern wie lib/toast.tsx: ueber confirmDialog() von
// ueberall aufrufbar, gerendert von <ConfirmContainer/> (in main.tsx gemountet).
// Barrierefrei: role="alertdialog", Fokus auf Abbrechen, Esc=Abbrechen, Enter=Bestaetigen.

import { useEffect, useState } from "react";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

interface ConfirmRequest extends ConfirmOptions {
  id: number;
  resolve: (ok: boolean) => void;
}

let counter = 0;
let current: ConfirmRequest | null = null;
const listeners = new Set<(c: ConfirmRequest | null) => void>();

function notify() {
  listeners.forEach((l) => l(current));
}

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    // Falls noch ein Dialog offen ist, diesen abbrechen, bevor der neue kommt.
    if (current) current.resolve(false);
    current = { ...options, id: ++counter, resolve };
    notify();
  });
}

function settle(ok: boolean) {
  if (!current) return;
  current.resolve(ok);
  current = null;
  notify();
}

export function ConfirmContainer() {
  const [req, setReq] = useState<ConfirmRequest | null>(current);
  useEffect(() => {
    listeners.add(setReq);
    return () => {
      listeners.delete(setReq);
    };
  }, []);
  useEffect(() => {
    if (!req) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") settle(false);
      if (e.key === "Enter") settle(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [req]);

  if (!req) return null;
  return (
    <div className="modal-overlay" onClick={() => settle(false)} role="presentation">
      <div
        className="modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={req.title ? "confirm-title" : undefined}
        aria-describedby="confirm-message"
        onClick={(e) => e.stopPropagation()}
      >
        {req.title && (
          <h2 id="confirm-title" style={{ marginTop: 0 }}>
            {req.title}
          </h2>
        )}
        <p id="confirm-message">{req.message}</p>
        <div className="row end">
          <button type="button" onClick={() => settle(false)} autoFocus>
            {req.cancelLabel ?? "Abbrechen"}
          </button>
          <button
            type="button"
            className={req.danger ? "danger" : "primary"}
            onClick={() => settle(true)}
          >
            {req.confirmLabel ?? "Bestaetigen"}
          </button>
        </div>
      </div>
    </div>
  );
}
