import { useState } from "react";

import { Pagination } from "../../components/Pagination";
import {
  Badge,
  Card,
  CardInner,
  Empty,
  ErrorBanner,
  Loading,
  PageHead,
  SectionHead,
} from "../../components/ui";
import { confirmDialog } from "../../lib/confirm";
import { triggerDownload } from "../../lib/download";
import { formatDate } from "../../lib/format";
import {
  PAGE_SIZE,
  useAdminUsers,
  useAnonymizeUser,
  useCreateExport,
  useCreateUser,
  useExports,
} from "./hooks";

export function UsersPage() {
  const [offset, setOffset] = useState(0);
  const users = useAdminUsers(PAGE_SIZE, offset);
  const anonymize = useAnonymizeUser();
  const createExport = useCreateExport();

  return (
    <div>
      <PageHead
        eyebrow="Admin / Benutzer"
        title="Benutzer"
        note="Benutzerkonten verwalten, Daten exportieren (Art. 15) und Konten anonymisieren (Art. 17)."
      />
      <CreateUserForm />
      <ErrorBanner error={users.error || anonymize.error || createExport.error} />
      <Card>
        {users.isPending ? (
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
                  <td>
                    {u.is_superadmin ? <Badge variant="primary">superadmin</Badge> : "—"}
                  </td>
                  <td>
                    {u.is_anonymized ? (
                      <Badge variant="danger" dot>
                        anonymisiert
                      </Badge>
                    ) : u.is_active ? (
                      <Badge variant="success" dot>
                        aktiv
                      </Badge>
                    ) : (
                      <Badge variant="neutral" dot>
                        inaktiv
                      </Badge>
                    )}
                    <div className="muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>
                      {formatDate(u.created_at)}
                    </div>
                  </td>
                  <td>
                    <div className="row end wrap">
                      <button
                        className="btn small"
                        onClick={() => createExport.mutate(u.id)}
                        disabled={createExport.isPending}
                      >
                        Daten exportieren
                      </button>
                      {!u.is_anonymized && (
                        <button
                          className="btn small danger"
                          onClick={async () => {
                            const ok = await confirmDialog({
                              title: "Benutzer anonymisieren",
                              message:
                                "Benutzer anonymisieren (Art. 17)? Konto wird deaktiviert, PII entfernt. Nicht umkehrbar.",
                              confirmLabel: "Anonymisieren",
                              danger: true,
                            });
                            if (ok) anonymize.mutate(u.id);
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
          <CardInner>
            <Pagination
              total={users.data.total}
              limit={users.data.limit}
              offset={users.data.offset}
              onChange={setOffset}
            />
          </CardInner>
        )}
      </Card>
      <ExportsList />
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
    try {
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
    } catch {
      /* Fehler via create.error im ErrorBanner */
    }
  }

  return (
    <Card>
      <CardInner>
        <SectionHead
          title="Benutzer anlegen"
          hint="Neues Konto mit Passwort erstellen, optional als Superadmin."
          actions={
            <button className="btn primary" onClick={() => setOpen((v) => !v)}>
              {open ? "Abbrechen" : "Neuer Benutzer"}
            </button>
          }
        />
        {open && (
          <form onSubmit={onSubmit}>
            <ErrorBanner error={create.error} />
            <label>
              <span>E-Mail</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
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
            <button className="btn primary" type="submit" disabled={create.isPending}>
              {create.isPending ? "Wird angelegt …" : "Anlegen"}
            </button>
          </form>
        )}
      </CardInner>
    </Card>
  );
}

function ExportsList() {
  const [offset, setOffset] = useState(0);
  const { data, isPending, error } = useExports(PAGE_SIZE, offset);

  return (
    <Card>
      <CardInner>
        <SectionHead
          title="Datenexporte"
          hint="DSGVO-Auskunft (Art. 15). Pending/Processing wird automatisch aktualisiert."
        />
        <ErrorBanner error={error} />
      </CardInner>
      {isPending ? (
        <Loading />
      ) : !data?.items.length ? (
        <Empty>Noch keine Exporte. Über „Daten exportieren" oben anfordern.</Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Betroffener</th>
              <th>Status</th>
              <th>Läuft ab</th>
              <th>Erstellt</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((e) => (
              <tr key={e.id}>
                <td className="mono">{e.subject_user_id.slice(0, 8)}</td>
                <td>
                  {e.status === "ready" ? (
                    <Badge variant="success" dot>
                      {e.status}
                    </Badge>
                  ) : e.status === "failed" ? (
                    <Badge variant="danger" dot>
                      {e.status}
                    </Badge>
                  ) : (
                    <Badge variant="warning" dot>
                      {e.status}
                    </Badge>
                  )}
                </td>
                <td className="muted">{formatDate(e.expires_at)}</td>
                <td className="muted">{formatDate(e.created_at)}</td>
                <td>
                  <div className="row end">
                    {e.status === "ready" && (
                      <button
                        className="btn small"
                        onClick={() => triggerDownload(`/admin/exports/${e.id}/download`)}
                      >
                        Herunterladen
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && (
        <CardInner>
          <Pagination
            total={data.total}
            limit={data.limit}
            offset={data.offset}
            onChange={setOffset}
          />
        </CardInner>
      )}
    </Card>
  );
}
