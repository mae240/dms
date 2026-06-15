import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Card, CardInner, ErrorBanner } from "../../components/ui";
import { ApiError } from "../../lib/apiClient";
import { useAuth } from "../../lib/auth";
import { toast } from "../../lib/toast";

export function SetupPage() {
  const { registerFirstAdmin } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await registerFirstAdmin(email, password, fullName);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "already_initialized") {
        toast.error("System ist bereits eingerichtet. Bitte anmelden.");
        setPending(false);
        navigate("/login", { replace: true });
        return;
      }
      setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="login-wrap">
      <Card className="login-card">
        <CardInner>
          <div className="brand" style={{ padding: "0 0 18px" }}>
            <div className="logo">D</div>
            <div>
              <strong>DMS einrichten</strong>
              <span>Erst-Administrator anlegen</span>
            </div>
          </div>
          <ErrorBanner error={error} />
          <form onSubmit={onSubmit}>
            <label>
              <span>Voller Name</span>
              <input
                aria-label="Voller Name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
              />
            </label>
            <label>
              <span>E-Mail</span>
              <input
                aria-label="E-Mail"
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
                aria-label="Passwort"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={8}
              />
            </label>
            <button className="btn primary" type="submit" disabled={pending} style={{ width: "100%" }}>
              {pending ? "Wird eingerichtet …" : "Administrator anlegen"}
            </button>
          </form>
        </CardInner>
      </Card>
    </div>
  );
}
