import { Fragment, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Pagination } from "../../components/Pagination";
import { Empty, ErrorBanner, Loading, StatusBadge } from "../../components/ui";
import { getAccessToken } from "../../lib/apiClient";
import { roleAtLeast } from "../../lib/can";
import { downloadAuthed, formatBytes, formatDate } from "../../lib/format";
import { toast } from "../../lib/toast";
import type { DocumentStatus, MemberOut, ProjectDetailOut, ProjectRole } from "../../types/api";
import { useVersions } from "../documents/hooks";
import {
  PAGE_SIZE,
  useAddMember,
  useChangeMemberRole,
  useDeleteProject,
  useDocuments,
  useProject,
  useRemoveMember,
  useRestoreDocumentInProject,
  useUpdateProject,
  useUploadDocument,
} from "./hooks";

async function triggerDownload(path: string): Promise<void> {
  try {
    await downloadAuthed(path, getAccessToken());
  } catch {
    toast.error("Download fehlgeschlagen.");
  }
}

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);

  if (project.isLoading) return <Loading />;
  if (project.error) return <ErrorBanner error={project.error} />;
  if (!project.data) return <Empty>Projekt nicht gefunden.</Empty>;

  const p = project.data;
  const canManage = roleAtLeast(p.my_role, "admin");
  const canUpload = roleAtLeast(p.my_role, "editor");

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/projects">Projekte</Link> / {p.name}
      </div>
      <div className="row between">
        <h1 style={{ margin: 0 }}>{p.name}</h1>
        <span className="badge">{p.my_role}</span>
      </div>
      {p.description && <p className="muted">{p.description}</p>}

      {canManage && <ProjectSettings project={p} />}
      <Members projectId={projectId} members={p.members} canManage={canManage} />
      {canUpload && <UploadCard projectId={projectId} />}
      <DocumentsCard projectId={projectId} />
    </div>
  );
}

function ProjectSettings({ project }: { project: ProjectDetailOut }) {
  const update = useUpdateProject(project.id);
  const del = useDeleteProject();
  const navigate = useNavigate();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const isOwner = project.my_role === "owner";
  const isArchived = project.status === "archived";

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    await update.mutateAsync({ name, description });
  }

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Projekt verwalten</h2>
      <ErrorBanner error={update.error || del.error} />
      <form onSubmit={onSave}>
        <label>
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          <span>Beschreibung</span>
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="row">
          <button className="primary" type="submit" disabled={update.isPending}>
            Speichern
          </button>
          <button
            type="button"
            disabled={update.isPending}
            onClick={() => update.mutate({ status: isArchived ? "active" : "archived" })}
          >
            {isArchived ? "Reaktivieren" : "Archivieren"}
          </button>
          {isOwner && (
            <button
              type="button"
              className="danger"
              disabled={del.isPending}
              onClick={async () => {
                if (confirm("Projekt loeschen? (Papierkorb, wiederherstellbar)")) {
                  await del.mutateAsync(project.id);
                  navigate("/projects");
                }
              }}
            >
              Loeschen
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function Members({
  projectId,
  members,
  canManage,
}: {
  projectId: string;
  members: MemberOut[];
  canManage: boolean;
}) {
  const add = useAddMember(projectId);
  const remove = useRemoveMember(projectId);
  const changeRole = useChangeMemberRole(projectId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<ProjectRole>("viewer");

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    await add.mutateAsync({ email, role });
    setEmail("");
  }

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Mitglieder</h2>
      <ErrorBanner error={add.error || remove.error || changeRole.error} />
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>E-Mail</th>
            <th>Rolle</th>
            {canManage && <th></th>}
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.user_id}>
              <td>{m.full_name || "—"}</td>
              <td className="mono">{m.email}</td>
              <td>
                {canManage && m.role !== "owner" ? (
                  <select
                    value={m.role}
                    onChange={(e) =>
                      changeRole.mutate({ userId: m.user_id, role: e.target.value as ProjectRole })
                    }
                    style={{ width: "auto" }}
                  >
                    <option value="viewer">viewer</option>
                    <option value="editor">editor</option>
                    <option value="admin">admin</option>
                  </select>
                ) : (
                  <span className="badge">{m.role}</span>
                )}
              </td>
              {canManage && (
                <td>
                  {m.role !== "owner" && (
                    <button className="small danger" onClick={() => remove.mutate(m.user_id)}>
                      Entfernen
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {canManage && (
        <form className="row wrap" style={{ marginTop: "1rem" }} onSubmit={onAdd}>
          <input
            style={{ flex: 2, minWidth: 220 }}
            type="email"
            placeholder="E-Mail des Mitglieds"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <select
            style={{ flex: 1, minWidth: 120 }}
            value={role}
            onChange={(e) => setRole(e.target.value as ProjectRole)}
          >
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="admin">admin</option>
          </select>
          <button className="primary" type="submit" disabled={add.isPending}>
            Hinzufuegen
          </button>
        </form>
      )}
    </div>
  );
}

function UploadCard({ projectId }: { projectId: string }) {
  const upload = useUploadDocument(projectId);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("title", title || file.name);
    setProgress(0);
    try {
      await upload.mutateAsync({ form, onProgress: setProgress });
      setTitle("");
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } finally {
      setProgress(null);
    }
  }

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Dokument hochladen</h2>
      <ErrorBanner error={upload.error} />
      <form onSubmit={onSubmit}>
        <label>
          <span>Titel (optional, sonst Dateiname)</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div
          className={`dropzone ${drag ? "drag" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
          }}
        >
          {file ? <strong>{file.name}</strong> : "Datei hierher ziehen oder klicken"}
          <input
            ref={inputRef}
            type="file"
            hidden
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        {progress !== null && (
          <div className="progress">
            <div style={{ width: `${progress}%` }} />
          </div>
        )}
        <p className="muted" style={{ fontSize: "0.8rem" }}>
          Neuer Upload erzeugt Version 1 — vorhandene Versionen bleiben erhalten.
        </p>
        <button className="primary" type="submit" disabled={!file || upload.isPending}>
          {upload.isPending ? `Lade hoch … ${progress ?? 0}%` : "Hochladen"}
        </button>
      </form>
    </div>
  );
}

const VIEWS: { key: DocumentStatus; label: string }[] = [
  { key: "active", label: "Aktiv" },
  { key: "archived", label: "Archiviert" },
  { key: "deleted", label: "Papierkorb" },
];

function DocumentsCard({ projectId }: { projectId: string }) {
  const [view, setView] = useState<DocumentStatus>("active");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error } = useDocuments(projectId, view, search, PAGE_SIZE, offset);
  const restore = useRestoreDocumentInProject(projectId);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const isTrash = view === "deleted";

  function switchView(v: DocumentStatus) {
    setView(v);
    setOffset(0);
    setExpanded(new Set());
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="card">
      <div className="row between">
        <h2 style={{ marginTop: 0 }}>Dokumente</h2>
        <div className="row">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              className={`small ${view === v.key ? "primary" : ""}`}
              onClick={() => switchView(v.key)}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <div className="toolbar">
        <input
          placeholder="Titel durchsuchen …"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
          style={{ minWidth: 240 }}
        />
      </div>
      <ErrorBanner error={error || restore.error} />
      {isLoading ? (
        <Loading />
      ) : !data?.items.length ? (
        <Empty>
          {search
            ? "Keine Treffer."
            : isTrash
              ? "Der Papierkorb ist leer."
              : view === "archived"
                ? "Keine archivierten Dokumente."
                : "Noch keine aktiven Dokumente in diesem Projekt."}
        </Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th style={{ width: "1.5rem" }}></th>
              <th>Titel</th>
              <th>Status</th>
              <th>Verarbeitung</th>
              <th>Versionen</th>
              <th>{isTrash ? "Endgueltige Loeschung" : "Aktualisiert"}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((d) => {
              const isOpen = expanded.has(d.id);
              return (
                <Fragment key={d.id}>
                  <tr>
                    <td>
                      <button
                        className="small"
                        aria-label={isOpen ? "Einklappen" : "Versionen anzeigen"}
                        onClick={() => toggle(d.id)}
                        style={{ padding: "0.1rem 0.45rem" }}
                      >
                        {isOpen ? "▾" : "▸"}
                      </button>
                    </td>
                    <td>
                      <Link to={`/documents/${d.id}`}>{d.title}</Link>{" "}
                      {d.legal_hold && <span className="badge failed">Hold</span>}{" "}
                      {d.retention_until && (
                        <span className="badge" title="Aufbewahrung bis">
                          ⏲ {d.retention_until}
                        </span>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={d.status} />
                    </td>
                    <td>
                      <StatusBadge status={d.latest_processing_status} />
                    </td>
                    <td>{d.version_count}</td>
                    <td className="muted">
                      {isTrash ? formatDate(d.purge_after) : formatDate(d.updated_at)}
                    </td>
                    <td>
                      {isTrash ? (
                        <button
                          className="small"
                          disabled={restore.isPending}
                          onClick={() => restore.mutate(d.id)}
                        >
                          Wiederherstellen
                        </button>
                      ) : (
                        <button
                          className="small"
                          disabled={d.latest_processing_status === "quarantined"}
                          onClick={() => triggerDownload(`/documents/${d.id}/download`)}
                        >
                          Neueste laden
                        </button>
                      )}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={7} style={{ background: "var(--surface-2)" }}>
                        <VersionList documentId={d.id} downloadDisabled={isTrash} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
      {data && (
        <Pagination total={data.total} limit={data.limit} offset={data.offset} onChange={setOffset} />
      )}
    </div>
  );
}

function VersionList({
  documentId,
  downloadDisabled = false,
}: {
  documentId: string;
  downloadDisabled?: boolean;
}) {
  const { data, isLoading, error } = useVersions(documentId);
  if (isLoading) return <div className="muted">Lade Versionen …</div>;
  if (error) return <ErrorBanner error={error} />;
  if (!data?.length) return <div className="muted">Keine Versionen.</div>;
  return (
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
        {data.map((v) => (
          <tr key={v.id}>
            <td>v{v.version_number}</td>
            <td className="mono">{v.file_name}</td>
            <td>{formatBytes(v.size_bytes)}</td>
            <td>
              <StatusBadge status={v.processing_status} />
            </td>
            <td className="muted">{formatDate(v.created_at)}</td>
            <td>
              <button
                className="small"
                disabled={downloadDisabled || v.processing_status === "quarantined"}
                onClick={() => triggerDownload(`/versions/${v.id}/download`)}
              >
                Download
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
