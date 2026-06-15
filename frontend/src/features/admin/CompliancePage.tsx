import { useState } from "react";

import { Pagination } from "../../components/Pagination";
import { Empty, ErrorBanner, Loading, SuccessBanner } from "../../components/ui";
import { getAccessToken } from "../../lib/apiClient";
import { downloadAuthed, formatDate } from "../../lib/format";
import { PAGE_SIZE, useExports, useSetLegalHold, useSetRetention } from "./hooks";

export function CompliancePage() {
  return (
    <div>
      <h1>Compliance</h1>
      <RetentionTool />
      <ExportsList />
    </div>
  );
}

function RetentionTool() {
  const setRetention = useSetRetention();
  const setLegalHold = useSetLegalHold();
  const [documentId, setDocumentId] = useState("");
  const [retention, setRetention_] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Aufbewahrung &amp; Legal Hold</h2>
      <p className="muted">Per Dokument-ID (systemweit, unabhaengig von der Projekt-Mitgliedschaft).</p>
      <ErrorBanner error={setRetention.error || setLegalHold.error} />
      {msg && <SuccessBanner>{msg}</SuccessBanner>}
      <label>
        <span>Dokument-ID</span>
        <input className="mono" value={documentId} onChange={(e) => setDocumentId(e.target.value.trim())} />
      </label>
      <div className="row wrap" style={{ alignItems: "flex-end" }}>
        <label style={{ flex: 1, minWidth: 200, marginBottom: 0 }}>
          <span>Aufbewahrung bis</span>
          <input type="date" value={retention} onChange={(e) => setRetention_(e.target.value)} />
        </label>
        <button
          disabled={!documentId || setRetention.isPending}
          onClick={async () => {
            await setRetention.mutateAsync({
              documentId,
              retention_until: retention || null,
            });
            setMsg("Aufbewahrungsdatum gesetzt.");
          }}
        >
          Aufbewahrung setzen
        </button>
      </div>
      <div className="row" style={{ marginTop: "1rem" }}>
        <button
          disabled={!documentId || setLegalHold.isPending}
          onClick={async () => {
            await setLegalHold.mutateAsync({ documentId, legal_hold: true });
            setMsg("Legal Hold aktiviert.");
          }}
        >
          Legal Hold aktivieren
        </button>
        <button
          disabled={!documentId || setLegalHold.isPending}
          onClick={async () => {
            await setLegalHold.mutateAsync({ documentId, legal_hold: false });
            setMsg("Legal Hold aufgehoben.");
          }}
        >
          Legal Hold aufheben
        </button>
      </div>
    </div>
  );
}

function ExportsList() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error } = useExports(PAGE_SIZE, offset);
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Datenexporte</h2>
      <ErrorBanner error={error} />
      {isLoading ? (
        <Loading />
      ) : !data?.items.length ? (
        <Empty>Noch keine Exporte. Erstelle einen unter „Benutzer".</Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Betroffener</th>
              <th>Status</th>
              <th>Laeuft ab</th>
              <th>Erstellt</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((e) => (
              <tr key={e.id}>
                <td className="mono">{e.subject_user_id.slice(0, 8)}</td>
                <td>
                  <span className={`badge ${e.status === "ready" ? "ready" : ""}`}>{e.status}</span>
                </td>
                <td className="muted">{formatDate(e.expires_at)}</td>
                <td className="muted">{formatDate(e.created_at)}</td>
                <td>
                  {e.status === "ready" && (
                    <button
                      className="small"
                      onClick={() =>
                        downloadAuthed(`/admin/exports/${e.id}/download`, getAccessToken())
                      }
                    >
                      Herunterladen
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && (
        <Pagination
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          onChange={setOffset}
        />
      )}
    </div>
  );
}
