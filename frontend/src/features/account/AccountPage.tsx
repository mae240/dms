import { useState } from "react";

import { ErrorBanner, SuccessBanner } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { useChangePassword } from "./hooks";

export function AccountPage() {
  const { user } = useAuth();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setDone(false);
    if (next !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    await change.mutateAsync({ current_password: current, new_password: next });
    setCurrent("");
    setNext("");
    setConfirm("");
    setDone(true);
  }

  return (
    <div>
      <h1>Konto</h1>
      <p className="muted">
        Angemeldet als {user?.full_name || user?.email} ({user?.email}).
      </p>
      <form className="card" style={{ maxWidth: 480 }} onSubmit={onSubmit}>
        <h2 style={{ marginTop: 0 }}>Passwort ändern</h2>
        <ErrorBanner error={change.error} />
        {mismatch && <div className="banner error">Die neuen Passwörter stimmen nicht überein.</div>}
        {done && <SuccessBanner>Passwort geändert. Andere Sitzungen wurden abgemeldet.</SuccessBanner>}
        <label>
          <span>Aktuelles Passwort</span>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label>
          <span>Neues Passwort (min. 8 Zeichen)</span>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <label>
          <span>Neues Passwort bestätigen</span>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <button className="primary" type="submit" disabled={change.isPending}>
          Passwort ändern
        </button>
      </form>
    </div>
  );
}
