import { useState } from "react";

import { Card, CardInner, ErrorBanner, PageHead, SectionHead, SuccessBanner } from "../../components/ui";
import { confirmDialog } from "../../lib/confirm";
import { useRewrapStorage, useSetLegalHold, useSetRetention } from "./hooks";

export function CompliancePage() {
  return (
    <div>
      <PageHead eyebrow="Compliance / Center" title="Compliance-Center" />
      <RetentionTool />
      <StorageEncryption />
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
    <Card>
      <CardInner>
        <SectionHead
          title="Aufbewahrung &amp; Legal Hold"
          hint="Per Dokument-ID (systemweit, unabhaengig von der Projekt-Mitgliedschaft)."
        />
        <ErrorBanner error={setRetention.error || setLegalHold.error} />
        {msg && <SuccessBanner>{msg}</SuccessBanner>}
        <label>
          <span>Dokument-ID</span>
          <input
            className="mono"
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value.trim())}
          />
        </label>
        <div className="row wrap" style={{ alignItems: "flex-end" }}>
          <label style={{ flex: 1, minWidth: 200, marginBottom: 0 }}>
            <span>Aufbewahrung bis</span>
            <input type="date" value={retention} onChange={(e) => setRetention_(e.target.value)} />
          </label>
          <button
            disabled={!documentId || setRetention.isPending}
            onClick={async () => {
              setMsg(null);
              try {
                await setRetention.mutateAsync({
                  documentId,
                  retention_until: retention || null,
                });
                setMsg("Aufbewahrungsdatum gesetzt.");
              } catch {
                /* Fehler via setRetention.error im ErrorBanner */
              }
            }}
          >
            Aufbewahrung setzen
          </button>
        </div>
        <div className="row" style={{ marginTop: "1rem" }}>
          <button
            disabled={!documentId || setLegalHold.isPending}
            onClick={async () => {
              setMsg(null);
              try {
                await setLegalHold.mutateAsync({ documentId, legal_hold: true });
                setMsg("Legal Hold aktiviert.");
              } catch {
                /* Fehler via setLegalHold.error im ErrorBanner */
              }
            }}
          >
            Legal Hold aktivieren
          </button>
          <button
            disabled={!documentId || setLegalHold.isPending}
            onClick={async () => {
              setMsg(null);
              try {
                await setLegalHold.mutateAsync({ documentId, legal_hold: false });
                setMsg("Legal Hold aufgehoben.");
              } catch {
                /* Fehler via setLegalHold.error im ErrorBanner */
              }
            }}
          >
            Legal Hold aufheben
          </button>
        </div>
      </CardInner>
    </Card>
  );
}

function StorageEncryption() {
  const rewrap = useRewrapStorage();
  async function onRewrap() {
    const ok = await confirmDialog({
      title: "Schluessel-Rotation starten?",
      message:
        "Re-wrappt alle Blob-DEKs auf die aktive Schluessel-Version. Laeuft asynchron im Hintergrund.",
      confirmLabel: "Rotation starten",
      danger: false,
    });
    if (ok) rewrap.mutate();
  }

  return (
    <Card>
      <CardInner>
        <SectionHead
          title="Speicher-Verschluesselung"
          hint="At-rest-Verschluesselung der Blobs (AES-256-GCM). Nach Schluesselwechsel die DEKs neu wrappen."
        />
        <ErrorBanner error={rewrap.error} />
        <button className="btn primary" onClick={onRewrap} disabled={rewrap.isPending}>
          {rewrap.isPending ? "Wird gestartet …" : "Schluessel-Rotation starten"}
        </button>
      </CardInner>
    </Card>
  );
}
