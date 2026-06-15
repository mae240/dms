import { useState } from "react";

import { Pagination } from "../../components/Pagination";
import { Empty, ErrorBanner, Loading } from "../../components/ui";
import { formatDate } from "../../lib/format";
import {
  PAGE_SIZE,
  useAdminUsers,
  useAnonymizeUser,
  useCreateExport,
  useCreateUser,
} from "./hooks";

export function UsersPage() {
  const [offset, setOffset] = useState(0);
  const users = useAdminUsers(PAGE_SIZE, offset);
  const anonymize = useAnonymizeUser();
  const createExport = useCreateExport();

  return (
    <div>
      <div className="row between">
        <h1>Benutzer</h1>
      </div>
      <CreateUserForm />
      <ErrorBanner error={users.error || anonymize.error || createExport.error} />
      <div className="card">
        {users.isLoading ? (
          <Loading />
        ) : !users.data?.items.length ? (
          <Empty>Keine Benutzer.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>E-Mail</th>
                <th>Name</th>
                <th>Rolle</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.email}</td>
                  <td>{u.full_name || "—"}</td>
                  <td>{u.is_superadmin ? <span className="badge">superadmin</span> : "—"}</td>
                  <td>
                    {u.is_anonymized ? (
                      <span className="badge deleted">anonymisiert</span>
                    ) : u.is_active ? (
                      <span className="badge active">aktiv</span>
                    ) : (
                      <span className="badge">inaktiv</span>
                    )}
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      {formatDate(u.created_at)}
                    </div>
                  </td>
                  <td>
                    <div className="row">
                      <button
                        className="small"
                        onClick={() => createExport.mutate(u.id)}
                        disabled={createExport.isPending}
                      >
                        Daten exportieren
                      </button>
                      {!u.is_anonymized && (
                        <button
                          className="small danger"
                          onClick={() => {
                            if (
                              confirm(
                                "Benutzer anonymisieren (Art. 17)? Konto wird deaktiviert, PII entfernt.",
                              )
                            )
                              anonymize.mutate(u.id);
                          }}
                          disabled={anonymize.isPending}
                        >
                          Anonymisieren
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {users.data && (
          <Pagination
            total={users.data.total}
            limit={users.data.limit}
            offset={users.data.offset}
            onChange={setOffset}
          />
        )}
      </div>
      <p className="muted">
        Exporte erscheinen unter <a href="/admin/compliance">Compliance</a>.
      </p>
    </div>
  );
}

function CreateUserForm() {
  const create = useCreateUser();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [isSuperadmin, setIsSuperadmin] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    await create.mutateAsync({
      email,
      password,
      full_name: fullName,
      is_superadmin: isSuperadmin,
    });
    setEmail("");
    setFullName("");
    setPassword("");
    setIsSuperadmin(false);
    setOpen(false);
  }

  return (
    <div className="card">
      <div className="row between">
        <h2 style={{ margin: 0 }}>Benutzer anlegen</h2>
        <button className="primary" onClick={() => setOpen((v) => !v)}>
          {open ? "Abbrechen" : "Neuer Benutzer"}
        </button>
      </div>
      {open && (
        <form onSubmit={onSubmit} style={{ marginTop: "1rem" }}>
          <ErrorBanner error={create.error} />
          <label>
            <span>E-Mail</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            <span>Name</span>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label>
            <span>Passwort (min. 8 Zeichen)</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <label className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={isSuperadmin}
              onChange={(e) => setIsSuperadmin(e.target.checked)}
              style={{ width: "auto" }}
            />
            <span style={{ margin: 0 }}>Superadmin</span>
          </label>
          <button className="primary" type="submit" disabled={create.isPending}>
            Anlegen
          </button>
        </form>
      )}
    </div>
  );
}
