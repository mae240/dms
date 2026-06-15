import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Empty, ErrorBanner, Loading, StatusBadge } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { roleAtLeast } from "../../lib/can";
import { confirmDialog } from "../../lib/confirm";
import { triggerDownload } from "../../lib/download";
import { formatBytes, formatDate } from "../../lib/format";
import type { DocumentDetailOut, DocumentStatus } from "../../types/api";
import { useSetLegalHold, useSetRetention } from "../admin/hooks";
import { useProject } from "../projects/hooks";
import {
  useDeleteDocument,
  useDocument,
  usePatchDocument,
  useReprocessVersion,
  useRestoreDocument,
  useUploadVersion,
  useVersions,
} from "./hooks";

export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const { user } = useAuth();
  const doc = useDocument(documentId);
  const versions = useVersions(documentId);
  const reprocess = useReprocessVersion(documentId);
  const project = useProject(doc.data?.project_id ?? "");

  if (doc.isLoading) return <Loading />;
  if (doc.error) return <ErrorBanner error={doc.error} />;
  if (!doc.data) return <Empty>Dokument nicht gefunden.</Empty>;

  const d = doc.data;
  const myRole = project.data?.my_role;
  const canEdit = roleAtLeast(myRole, "editor");
  const canManage = roleAtLeast(myRole, "admin");
  const isSuperadmin = !!user?.is_superadmin;

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/projects">Projekte</Link>
        {" / "}
        <Link to={`/projects/${d.project_id}`}>
          {project.data?.name ?? "Projekt"}
        </Link>
        {" / "}
        {d.title}
      </div>
      <div className="row between">
        <h1 style={{ margin: 0 }}>{d.title}</h1>
        <div className="row">
          <StatusBadge status={d.status} />
          {d.legal_hold && <span className="badge failed">Legal Hold</span>}
        </div>
      </div>

      <div className="card">
        <div className="row wrap" style={{ gap: "2rem" }}>
          <Field label="Kategorie" value={d.category || "—"} />
          <Field label="Erstellt" value={formatDate(d.created_at)} />
          <Field label="Aufbewahrung bis" value={d.retention_until || "—"} />
          {d.status === "deleted" && (
            <Field label="Endgueltige Loeschung am" value={formatDate(d.purge_after)} />
          )}
        </div>
        {d.description && <p>{d.description}</p>}
        <div className="row">
          <button
            onClick={() => triggerDownload(`/documents/${d.id}/download`)}
            disabled={!d.current_version || d.current_version.processing_status === "quarantined"}
          >
            Aktuelle Version herunterladen
          </button>
          {canManage && d.status !== "deleted" && <DeleteButton documentId={d.id} />}
          {canManage && d.status === "deleted" && <RestoreButton documentId={d.id} />}
        </div>
      </div>

      {isSuperadmin && <ComplianceControls doc={d} />}

      {canEdit && d.status !== "deleted" && (
        <>
          <MetadataEditor key={d.id + d.updated_at} doc={d} />
          <NewVersion documentId={d.id} />
        </>
      )}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Versionshistorie</h2>
        <ErrorBanner error={versions.error} />
        {versions.isLoading ? (
          <Loading />
        ) : !versions.data?.length ? (
          <Empty>Keine Versionen.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Version</th>
                <th>Datei</th>
                <th>Groesse</th>
                <th>Verarbeitung</th>
                <th>Erstellt</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {versions.data.map((v) => (
                <tr key={v.id}>
                  <td>v{v.version_number}</td>
                  <td className="mono">{v.file_name}</td>
                  <td>{formatBytes(v.size_bytes)}</td>
                  <td>
                    <StatusBadge status={v.processing_status} />
                    {v.processing_error && (
                      <div className="muted" style={{ fontSize: "0.75rem" }}>
                        {v.processing_error}
                      </div>
                    )}
                  </td>
                  <td className="muted">{formatDate(v.created_at)}</td>
                  <td>
                    <div className="row">
                      <button
                        className="small"
                        disabled={v.processing_status === "quarantined"}
                        onClick={() => triggerDownload(`/versions/${v.id}/download`)}
                      >
                        Download
                      </button>
                      {canEdit && d.status !== "deleted" && (
                        <button
                          className="small"
                          disabled={reprocess.isPending || v.processing_status === "processing"}
                          onClick={() => reprocess.mutate(v.id)}
                          title="Verarbeitung neu starten"
                        >
                          Neu verarbeiten
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="muted" style={{ fontSize: "0.75rem" }}>
        {label}
      </div>
      <div>{value}</div>
    </div>
  );
}

function DeleteButton({ documentId }: { documentId: string }) {
  const del = useDeleteDocument(documentId);
  return (
    <button
      className="danger"
      onClick={async () => {
        if (
          await confirmDialog({
            title: "Dokument loeschen",
            message: "Soft-Delete, wiederherstellbar. Fortfahren?",
            confirmLabel: "Loeschen",
            danger: true,
          })
        )
          del.mutate();
      }}
      disabled={del.isPending}
    >
      Loeschen
    </button>
  );
}

function RestoreButton({ documentId }: { documentId: string }) {
  const restore = useRestoreDocument(documentId);
  return (
    <button onClick={() => restore.mutate()} disabled={restore.isPending}>
      Wiederherstellen
    </button>
  );
}

function ComplianceControls({ doc }: { doc: DocumentDetailOut }) {
  const setRetention = useSetRetention();
  const setLegalHold = useSetLegalHold();
  const [retention, setRetentionDate] = useState(doc.retention_until ?? "");

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Compliance (Superadmin)</h2>
      <ErrorBanner error={setRetention.error || setLegalHold.error} />
      <div className="row wrap" style={{ alignItems: "flex-end", gap: "1rem" }}>
        <label style={{ marginBottom: 0 }}>
          <span>Aufbewahrung bis</span>
          <input
            type="date"
            value={retention}
            onChange={(e) => setRetentionDate(e.target.value)}
          />
        </label>
        <button
          disabled={setRetention.isPending}
          onClick={() =>
            setRetention.mutate({ documentId: doc.id, retention_until: retention || null })
          }
        >
          Aufbewahrung setzen
        </button>
        {doc.legal_hold ? (
          <button
            disabled={setLegalHold.isPending}
            onClick={async () => {
              if (
                await confirmDialog({
                  title: "Legal Hold aufheben",
                  message: "Legal Hold fuer dieses Dokument aufheben?",
                  confirmLabel: "Aufheben",
                })
              )
                setLegalHold.mutate({ documentId: doc.id, legal_hold: false });
            }}
          >
            Legal Hold aufheben
          </button>
        ) : (
          <button
            className="danger"
            disabled={setLegalHold.isPending}
            onClick={async () => {
              if (
                await confirmDialog({
                  title: "Legal Hold aktivieren",
                  message:
                    "Das Dokument kann dann nicht geloescht oder gepurged werden. Fortfahren?",
                  confirmLabel: "Aktivieren",
                  danger: true,
                })
              )
                setLegalHold.mutate({ documentId: doc.id, legal_hold: true });
            }}
          >
            Legal Hold aktivieren
          </button>
        )}
      </div>
    </div>
  );
}

function MetadataEditor({
  doc,
}: {
  doc: {
    id: string;
    title: string;
    description: string | null;
    category: string | null;
    status: DocumentStatus;
  };
}) {
  const patch = usePatchDocument(doc.id);
  const [title, setTitle] = useState(doc.title);
  const [description, setDescription] = useState(doc.description ?? "");
  const [category, setCategory] = useState(doc.category ?? "");
  const [status, setStatus] = useState<DocumentStatus>(doc.status);
  const [saved, setSaved] = useState(false);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    await patch.mutateAsync({ title, description, category, status });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <form className="card" onSubmit={onSave}>
      <h2 style={{ marginTop: 0 }}>Metadaten bearbeiten</h2>
      <ErrorBanner error={patch.error} />
      <label>
        <span>Titel</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        <span>Kategorie</span>
        <input value={category} onChange={(e) => setCategory(e.target.value)} />
      </label>
      <label>
        <span>Status</span>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as DocumentStatus)}
        >
          <option value="active">aktiv</option>
          <option value="archived">archiviert</option>
        </select>
      </label>
      <label>
        <span>Beschreibung</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
      </label>
      <button className="primary" type="submit" disabled={patch.isPending}>
        Speichern
      </button>
      {saved && <span className="muted" style={{ marginLeft: "0.75rem" }}>Gespeichert ✓</span>}
    </form>
  );
}

function NewVersion({ documentId }: { documentId: string }) {
  const upload = useUploadVersion(documentId);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setProgress(0);
    try {
      await upload.mutateAsync({ form, onProgress: setProgress });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } finally {
      setProgress(null);
    }
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h2 style={{ marginTop: 0 }}>Neue Version hochladen</h2>
      <ErrorBanner error={upload.error} />
      <input ref={inputRef} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      {progress !== null && (
        <div className="progress">
          <div style={{ width: `${progress}%` }} />
        </div>
      )}
      <p className="muted" style={{ fontSize: "0.8rem" }}>
        Die vorherige Version bleibt erhalten.
      </p>
      <button className="primary" type="submit" disabled={!file || upload.isPending}>
        {upload.isPending ? `Lade hoch … ${progress ?? 0}%` : "Version hinzufuegen"}
      </button>
    </form>
  );
}
