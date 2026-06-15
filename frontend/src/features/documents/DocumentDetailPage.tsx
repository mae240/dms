import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  Badge,
  Card,
  CardInner,
  Empty,
  ErrorBanner,
  Loading,
  PageHead,
  ProgressBar,
  SectionHead,
  StatusBadge,
  Tabs,
  UploadZone,
} from "../../components/ui";
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
import { retentionProgress } from "./retention";

type DetailTab = "versionen" | "metadaten";

// Datei-Glyph aus MIME-Typ bzw. Dateiendung ableiten (rein praesentativ).
function fileGlyph(mime: string | null | undefined, fileName: string | null | undefined): string {
  const m = (mime ?? "").toLowerCase();
  const name = (fileName ?? "").toLowerCase();
  if (m.includes("pdf") || name.endsWith(".pdf")) return "PDF";
  if (m.includes("word") || m.includes("officedocument.wordprocessing") || /\.docx?$/.test(name))
    return "DOC";
  if (
    m.includes("spreadsheet") ||
    m.includes("excel") ||
    m.includes("officedocument.spreadsheet") ||
    /\.xlsx?$/.test(name)
  )
    return "XLS";
  if (m.startsWith("image/")) return "IMG";
  if (m.startsWith("text/") || /\.(txt|md|csv)$/.test(name)) return "TXT";
  return "DAT";
}

export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const { user } = useAuth();
  const doc = useDocument(documentId);
  const versions = useVersions(documentId);
  const project = useProject(doc.data?.project_id ?? "");
  const [tab, setTab] = useState<DetailTab>("versionen");
  const uploadRef = useRef<HTMLDivElement>(null);

  if (doc.isPending) return <Loading />;
  if (doc.error) return <ErrorBanner error={doc.error} />;
  if (!doc.data) return <Empty>Dokument nicht gefunden.</Empty>;

  const d = doc.data;
  const myRole = project.data?.my_role;
  const canEdit = roleAtLeast(myRole, "editor");
  const canManage = roleAtLeast(myRole, "admin");
  const isSuperadmin = !!user?.is_superadmin;
  const cur = d.current_version;
  const versionCount = versions.data?.length ?? 0;
  const downloadDisabled = !cur || cur.processing_status === "quarantined";

  function focusUpload() {
    setTab("versionen");
    // Nach Tab-Wechsel zur Upload-Karte scrollen.
    requestAnimationFrame(() => {
      uploadRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/projects">Projekte</Link>
        {" / "}
        <Link to={`/projects/${d.project_id}`}>{project.data?.name ?? "Projekt"}</Link>
        {" / "}
        {d.title}
      </div>

      <PageHead
        eyebrow="Dokument"
        title={d.title}
        actions={
          <>
            <StatusBadge status={d.status} />
            <Badge variant="primary">
              {versionCount} {versionCount === 1 ? "Version" : "Versionen"}
            </Badge>
            {d.legal_hold && <Badge variant="danger">Legal Hold</Badge>}
            <button
              className="btn"
              disabled={downloadDisabled}
              onClick={() => triggerDownload(`/documents/${d.id}/download`)}
            >
              Aktuelle Version laden
            </button>
            {canEdit && d.status !== "deleted" && (
              <button className="btn primary" onClick={focusUpload}>
                Neue Version
              </button>
            )}
            {isSuperadmin && <LegalHoldButton doc={d} />}
          </>
        }
      />

      <div
        className="row wrap"
        style={{ alignItems: "stretch", gap: 18, marginBottom: 18 }}
      >
        <HeroCard doc={d} />
        <ComplianceCard doc={d} isSuperadmin={isSuperadmin} />
      </div>

      <Card>
        <Tabs
          tabs={[
            { id: "versionen", label: "Versionen" },
            { id: "metadaten", label: "Metadaten" },
          ]}
          value={tab}
          onChange={setTab}
        />
        <CardInner>
          {tab === "versionen" ? (
            <div role="tabpanel">
              <VersionsPanel
                doc={d}
                canEdit={canEdit}
                versions={versions}
                uploadRef={uploadRef}
              />
            </div>
          ) : (
            <div role="tabpanel">
              <MetadataPanel doc={d} canEdit={canEdit} canManage={canManage} />
            </div>
          )}
        </CardInner>
      </Card>
    </div>
  );
}

function HeroCard({ doc }: { doc: DocumentDetailOut }) {
  const cur = doc.current_version;
  const glyph = fileGlyph(cur?.mime_type, cur?.file_name);
  return (
    <Card>
      <CardInner>
        <div className="row" style={{ alignItems: "flex-start", gap: 16 }}>
          <div className="kpi-icon" aria-hidden="true" style={{ fontSize: 13, fontWeight: 900 }}>
            {glyph}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2 style={{ marginBottom: 4 }}>{doc.title}</h2>
            {doc.description && (
              <p className="muted" style={{ marginTop: 0 }}>
                {doc.description}
              </p>
            )}
            <div className="row wrap" style={{ gap: "1.5rem", marginTop: 12 }}>
              <Field label="Kategorie" value={doc.category || "—"} />
              <Field label="Erstellt" value={formatDate(doc.created_at)} />
              <Field label="Aktuelle Datei" value={cur?.file_name ?? "—"} mono />
              <Field label="Groesse" value={cur ? formatBytes(cur.size_bytes) : "—"} />
            </div>
          </div>
        </div>
      </CardInner>
    </Card>
  );
}

function ComplianceCard({
  doc,
  isSuperadmin,
}: {
  doc: DocumentDetailOut;
  isSuperadmin: boolean;
}) {
  const setRetention = useSetRetention();
  const setLegalHold = useSetLegalHold();
  const [retention, setRetentionDate] = useState(doc.retention_until ?? "");
  const progress = retentionProgress(doc.created_at, doc.retention_until);

  return (
    <Card>
      <CardInner>
        <SectionHead title="Aufbewahrung & Compliance" />
        {isSuperadmin && <ErrorBanner error={setRetention.error || setLegalHold.error} />}

        {isSuperadmin ? (
          <label style={{ marginBottom: "0.85rem" }}>
            <span>Aufbewahrung bis</span>
            <div className="row" style={{ gap: 8 }}>
              <input
                type="date"
                value={retention}
                onChange={(e) => setRetentionDate(e.target.value)}
                style={{ flex: 1 }}
              />
              <button
                className="btn"
                disabled={setRetention.isPending}
                onClick={() =>
                  setRetention.mutate({ documentId: doc.id, retention_until: retention || null })
                }
              >
                Setzen
              </button>
            </div>
          </label>
        ) : (
          <Field label="Aufbewahrung bis" value={doc.retention_until || "—"} />
        )}

        {progress && (
          <div style={{ marginTop: 12 }}>
            <div className="row between" style={{ marginBottom: 4 }}>
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                Restlaufzeit
              </span>
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                {progress.daysLeft} Tage
              </span>
            </div>
            <ProgressBar percent={progress.percent} />
          </div>
        )}

        <div className="row wrap" style={{ marginTop: 16, gap: 10 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="muted" style={{ fontSize: "0.75rem" }}>
              Legal Hold
            </div>
            <div>
              {doc.legal_hold ? (
                <Badge variant="danger">aktiv</Badge>
              ) : (
                <Badge variant="neutral">inaktiv</Badge>
              )}
            </div>
          </div>
          {isSuperadmin && <LegalHoldButton doc={doc} small />}
        </div>

        {doc.status === "deleted" && (
          <div style={{ marginTop: 12 }}>
            <Field label="Endgueltige Loeschung am" value={formatDate(doc.purge_after)} />
          </div>
        )}
      </CardInner>
    </Card>
  );
}

function LegalHoldButton({ doc, small = false }: { doc: DocumentDetailOut; small?: boolean }) {
  const setLegalHold = useSetLegalHold();
  const cls = small ? "btn small" : "btn";

  if (doc.legal_hold) {
    return (
      <button
        className={cls}
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
    );
  }
  return (
    <button
      className={`${cls} danger`}
      disabled={setLegalHold.isPending}
      onClick={async () => {
        if (
          await confirmDialog({
            title: "Legal Hold aktivieren",
            message: "Das Dokument kann dann nicht geloescht oder gepurged werden. Fortfahren?",
            confirmLabel: "Aktivieren",
            danger: true,
          })
        )
          setLegalHold.mutate({ documentId: doc.id, legal_hold: true });
      }}
    >
      Legal Hold aktivieren
    </button>
  );
}

function VersionsPanel({
  doc,
  canEdit,
  versions,
  uploadRef,
}: {
  doc: DocumentDetailOut;
  canEdit: boolean;
  versions: ReturnType<typeof useVersions>;
  uploadRef: React.RefObject<HTMLDivElement>;
}) {
  const reprocess = useReprocessVersion(doc.id);
  const currentVersionId = doc.current_version?.id;

  return (
    <>
      <SectionHead title="Versionshistorie" />
      <ErrorBanner error={versions.error || reprocess.error} />
      {versions.isPending ? (
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
                <td>
                  v{v.version_number}{" "}
                  {v.id === currentVersionId && <Badge variant="primary">aktuell</Badge>}
                </td>
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
                    {canEdit && doc.status !== "deleted" && (
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

      {canEdit && doc.status !== "deleted" && (
        <div ref={uploadRef} style={{ marginTop: 20 }}>
          <NewVersion documentId={doc.id} />
        </div>
      )}
    </>
  );
}

function NewVersion({ documentId }: { documentId: string }) {
  const upload = useUploadVersion(documentId);
  const [progress, setProgress] = useState<number | null>(null);

  async function onFile(file: File) {
    const form = new FormData();
    form.append("file", file);
    // Vorherigen Upload-Fehler verwerfen, damit der ErrorBanner beim erneuten Versuch verschwindet.
    upload.reset();
    setProgress(0);
    try {
      await upload.mutateAsync({ form, onProgress: setProgress });
    } finally {
      setProgress(null);
    }
  }

  return (
    <>
      <SectionHead
        title="Neue Version hochladen"
        hint="Die vorherige Version bleibt erhalten."
      />
      <ErrorBanner error={upload.error} />
      <UploadZone onFile={onFile} disabled={upload.isPending} />
      {progress !== null && <ProgressBar percent={progress} />}
    </>
  );
}

function MetadataPanel({
  doc,
  canEdit,
  canManage,
}: {
  doc: DocumentDetailOut;
  canEdit: boolean;
  canManage: boolean;
}) {
  return (
    <>
      {canEdit && doc.status !== "deleted" ? (
        <MetadataEditor key={doc.id + doc.updated_at} doc={doc} />
      ) : (
        <>
          <SectionHead title="Metadaten" />
          <div className="row wrap" style={{ gap: "1.5rem", marginBottom: 16 }}>
            <Field label="Titel" value={doc.title} />
            <Field label="Kategorie" value={doc.category || "—"} />
            <Field label="Status" value={doc.status} />
          </div>
          {doc.description && <p className="muted">{doc.description}</p>}
        </>
      )}

      {canManage && (
        <div className="row" style={{ marginTop: 16 }}>
          {doc.status === "deleted" ? (
            <RestoreButton documentId={doc.id} />
          ) : (
            <DeleteButton documentId={doc.id} />
          )}
        </div>
      )}
    </>
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

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    await patch.mutateAsync({ title, description, category, status });
  }

  return (
    <form onSubmit={onSave}>
      <SectionHead title="Metadaten bearbeiten" />
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
        <select value={status} onChange={(e) => setStatus(e.target.value as DocumentStatus)}>
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
    </form>
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

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div className="muted" style={{ fontSize: "0.75rem" }}>
        {label}
      </div>
      <div className={mono ? "mono" : undefined}>{value}</div>
    </div>
  );
}
