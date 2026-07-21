import { useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Pagination } from "../../components/Pagination";
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
  tabId,
  tabPanelId,
  UploadZone,
} from "../../components/ui";
import { roleAtLeast } from "../../lib/can";
import { confirmDialog } from "../../lib/confirm";
import { triggerDownload } from "../../lib/download";
import { formatBytes, formatDate } from "../../lib/format";
import type { DocumentStatus, MemberOut, ProjectDetailOut, ProjectRole } from "../../types/api";
import { useVersions } from "../documents/hooks";
import {
  PAGE_SIZE,
  useAddMember,
  useChangeMemberRole,
  useDeleteProject,
  useDeleteRetentionRule,
  useDocuments,
  useProject,
  useRemoveMember,
  useRestoreDocumentInProject,
  useRetentionRules,
  useUpdateProject,
  useUploadDocument,
  useUpsertRetentionRule,
} from "./hooks";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);

  if (project.isPending) return <Loading />;
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
      <PageHead
        eyebrow="Projekt"
        title={p.name}
        note={p.description || undefined}
        actions={
          <>
            <StatusBadge status={p.status} />
            {p.my_role && <Badge variant="primary">{p.my_role}</Badge>}
          </>
        }
      />

      {canManage && <ProjectSettings project={p} />}
      {canManage && <RetentionRulesCard projectId={projectId} />}
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
  const qc = useQueryClient();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const isOwner = project.my_role === "owner";
  const isArchived = project.status === "archived";

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    try {
      await update.mutateAsync({ name, description });
    } catch {
      // Fehler wird ueber update.error/ErrorBanner angezeigt.
    }
  }

  async function onDelete() {
    const ok = await confirmDialog({
      title: "Projekt loeschen",
      message: "Projekt in den Papierkorb verschieben? Es bleibt wiederherstellbar.",
      confirmLabel: "Loeschen",
      danger: true,
    });
    if (!ok) return;
    try {
      await del.mutateAsync(project.id);
      // Detail-Query stoppen/entfernen, damit kein 404-Refetch auf das geloeschte
      // Projekt laeuft, sobald wir wegnavigieren.
      await qc.cancelQueries({ queryKey: ["project", project.id] });
      qc.removeQueries({ queryKey: ["project", project.id] });
      navigate("/projects");
    } catch {
      // Fehler wird ueber del.error/ErrorBanner angezeigt.
    }
  }

  return (
    <Card>
      <CardInner>
        <SectionHead title="Projekt verwalten" />
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
          <div className="row wrap">
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
                onClick={onDelete}
              >
                Loeschen
              </button>
            )}
          </div>
        </form>
      </CardInner>
    </Card>
  );
}

function RetentionRulesCard({ projectId }: { projectId: string }) {
  const { data, isPending, error } = useRetentionRules(projectId);
  const upsert = useUpsertRetentionRule(projectId);
  const remove = useDeleteRetentionRule(projectId);
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState("");
  const [maxDays, setMaxDays] = useState("");

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    await upsert.mutateAsync({
      category: category.trim() || null,
      max_days: maxDays === "" ? null : Number(maxDays),
    });
    setCategory("");
    setMaxDays("");
    setShowForm(false);
  }

  async function onRemove(cat: string | null) {
    const ok = await confirmDialog({
      title: "Regel entfernen",
      message:
        cat === null
          ? "Projekt-Default entfernen? Damit wird die automatische Loeschung fuer dieses Projekt deaktiviert."
          : `Aufbewahrungsregel fuer Kategorie „${cat}" entfernen?`,
      confirmLabel: "Entfernen",
      danger: true,
    });
    if (ok) await remove.mutateAsync(cat);
  }

  return (
    <Card>
      <CardInner>
        <SectionHead
          title="Aufbewahrung"
          hint={'Regeln bestimmen, nach wie vielen Tagen Dokumente automatisch geloescht werden. Kategorie leer = Projekt-Default; Max-Tage „nie" = von der Loeschung ausgenommen.'}
          actions={
            !showForm && (
              <button className="small" onClick={() => setShowForm(true)}>
                + Regel
              </button>
            )
          }
        />
        <ErrorBanner error={error || upsert.error || remove.error} />
        {isPending ? (
          <Loading />
        ) : !data?.length ? (
          <Empty>Keine Aufbewahrungsregeln. Automatische Loeschung ist deaktiviert.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Kategorie</th>
                <th>Max-Tage</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>{r.category ?? "(Projekt-Default)"}</td>
                  <td>{r.max_days === null ? "nie" : r.max_days}</td>
                  <td>
                    <button
                      className="small danger"
                      disabled={remove.isPending}
                      onClick={() => onRemove(r.category)}
                    >
                      Entfernen
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {showForm && (
          <form className="row wrap" style={{ marginTop: "1rem" }} onSubmit={onAdd}>
            <input
              style={{ flex: 2, minWidth: 180 }}
              placeholder="Kategorie (leer = Projekt-Default)"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
            <input
              style={{ flex: 1, minWidth: 120 }}
              type="number"
              min={1}
              placeholder="Max-Tage (leer = nie)"
              value={maxDays}
              onChange={(e) => setMaxDays(e.target.value)}
            />
            <button className="primary" type="submit" disabled={upsert.isPending}>
              Speichern
            </button>
            <button
              type="button"
              disabled={upsert.isPending}
              onClick={() => {
                setShowForm(false);
                setCategory("");
                setMaxDays("");
              }}
            >
              Abbrechen
            </button>
          </form>
        )}
      </CardInner>
    </Card>
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
    <Card>
      <CardInner>
        <SectionHead title="Mitglieder" />
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
                        changeRole.mutate({
                          userId: m.user_id,
                          role: e.target.value as ProjectRole,
                        })
                      }
                      style={{ width: "auto" }}
                    >
                      <option value="viewer">viewer</option>
                      <option value="editor">editor</option>
                      <option value="admin">admin</option>
                    </select>
                  ) : (
                    <Badge variant="primary">{m.role}</Badge>
                  )}
                </td>
                {canManage && (
                  <td>
                    {m.role !== "owner" && (
                      <button
                        className="small danger"
                        onClick={async () => {
                          const ok = await confirmDialog({
                            title: "Mitglied entfernen?",
                            message: `Soll ${m.email} aus dem Projekt entfernt werden? Der Zugriff wird sofort entzogen.`,
                            confirmLabel: "Entfernen",
                            danger: true,
                          });
                          if (ok) remove.mutate(m.user_id);
                        }}
                      >
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
      </CardInner>
    </Card>
  );
}

function UploadCard({ projectId }: { projectId: string }) {
  const upload = useUploadDocument(projectId);
  const [title, setTitle] = useState("");
  const [progress, setProgress] = useState<number | null>(null);

  async function onFile(file: File) {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title || file.name);
    // Vorherigen Upload-Fehler verwerfen, damit der ErrorBanner beim erneuten Versuch verschwindet.
    upload.reset();
    setProgress(0);
    try {
      await upload.mutateAsync({ form, onProgress: setProgress });
      setTitle("");
    } finally {
      setProgress(null);
    }
  }

  return (
    <Card>
      <CardInner>
        <SectionHead
          title="Dokument hochladen"
          hint="Neuer Upload erzeugt Version 1 — vorhandene Versionen bleiben erhalten."
        />
        <ErrorBanner error={upload.error} />
        <label>
          <span>Titel (optional, sonst Dateiname)</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <UploadZone onFile={onFile} disabled={upload.isPending} />
        {progress !== null && <ProgressBar percent={progress} />}
      </CardInner>
    </Card>
  );
}

const VIEWS: { id: DocumentStatus; label: string }[] = [
  { id: "active", label: "Aktiv" },
  { id: "archived", label: "Archiviert" },
  { id: "deleted", label: "Papierkorb" },
];

function DocumentsCard({ projectId }: { projectId: string }) {
  const [view, setView] = useState<DocumentStatus>("active");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, isPending, error } = useDocuments(projectId, view, search, PAGE_SIZE, offset);
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
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  return (
    <Card>
      <Tabs idBase="project-docs" tabs={VIEWS} value={view} onChange={switchView} />
      <CardInner
        role="tabpanel"
        id={tabPanelId("project-docs", view)}
        aria-labelledby={tabId("project-docs", view)}
      >
        <SectionHead title="Dokumente" />
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
        {isPending ? (
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
                        {d.legal_hold && <Badge variant="danger">Hold</Badge>}{" "}
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
          <Pagination
            total={data.total}
            limit={data.limit}
            offset={data.offset}
            onChange={setOffset}
          />
        )}
      </CardInner>
    </Card>
  );
}

function VersionList({
  documentId,
  downloadDisabled = false,
}: {
  documentId: string;
  downloadDisabled?: boolean;
}) {
  const { data, isPending, error } = useVersions(documentId);
  if (isPending) return <div className="muted">Lade Versionen …</div>;
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
