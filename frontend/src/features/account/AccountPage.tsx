import { useState } from "react";

import { Card, CardInner, ErrorBanner, PageHead, SectionHead, SuccessBanner } from "../../components/ui";
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
      <PageHead
        eyebrow="Konto / Einstellungen"
        title="Konto"
        note={`Angemeldet als ${user?.full_name || user?.email} (${user?.email}).`}
      />
      <Card className="login-card">
        <CardInner>
          <SectionHead title="Passwort ändern" hint="Nach der Änderung werden andere Sitzungen abgemeldet." />
          <ErrorBanner error={change.error} />
          {mismatch && (
            <div className="banner error">Die neuen Passwörter stimmen nicht überein.</div>
          )}
          {done && (
            <SuccessBanner>Passwort geändert. Andere Sitzungen wurden abgemeldet.</SuccessBanner>
          )}
          <form onSubmit={onSubmit}>
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
            <button className="btn primary" type="submit" disabled={change.isPending}>
              {change.isPending ? "Wird geändert …" : "Passwort ändern"}
            </button>
          </form>
        </CardInner>
      </Card>
    </div>
  );
}
