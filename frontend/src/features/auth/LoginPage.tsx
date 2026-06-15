import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { Card, CardInner, ErrorBanner } from "../../components/ui";
import { useAuth } from "../../lib/auth";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/dashboard" replace />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <Card className="login-card">
        <CardInner>
          <div className="brand" style={{ padding: "0 0 18px" }}>
            <div className="logo">D</div>
            <div>
              <strong>Anmelden</strong>
              <span>Dokumentenverwaltung</span>
            </div>
          </div>
          <ErrorBanner error={error} />
          <form onSubmit={onSubmit}>
            <label>
              <span>E-Mail</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label>
              <span>Passwort</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button className="btn primary" type="submit" disabled={busy} style={{ width: "100%" }}>
              {busy ? "Anmelden …" : "Anmelden"}
            </button>
          </form>
        </CardInner>
      </Card>
    </div>
  );
}
