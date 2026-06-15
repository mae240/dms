import { useState } from "react";
import { Link } from "react-router-dom";

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
  StatusBadge,
  Tabs,
} from "../../components/ui";
import { formatDate } from "../../lib/format";
import type { ProjectStatus } from "../../types/api";
import { PAGE_SIZE, useCreateProject, useProjects, useRestoreProject } from "./hooks";

const VIEWS: { id: ProjectStatus; label: string }[] = [
  { id: "active", label: "Aktiv" },
  { id: "archived", label: "Archiviert" },
  { id: "deleted", label: "Papierkorb" },
];

export function ProjectsPage() {
  const [view, setView] = useState<ProjectStatus>("active");
  const [offset, setOffset] = useState(0);
  const { data, isPending, error } = useProjects(view, PAGE_SIZE, offset);
  const restore = useRestoreProject();
  const create = useCreateProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [open, setOpen] = useState(false);
  const isTrash = view === "deleted";

  function switchView(v: ProjectStatus) {
    setView(v);
    setOffset(0);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    await create.mutateAsync({ name, description: description || undefined });
    setName("");
    setDescription("");
    setOpen(false);
  }

  return (
    <div>
      <PageHead
        eyebrow="Projekte / Uebersicht"
        title="Projekte"
        actions={
          view === "active" && (
            <button className="primary" onClick={() => setOpen((o) => !o)}>
              {open ? "Abbrechen" : "Neues Projekt"}
            </button>
          )
        }
      />

      {open && view === "active" && (
        <Card>
          <CardInner>
            <SectionHead title="Neues Projekt" hint="Lege ein Projekt fuer ein Kundenengagement oder einen internen Bereich an." />
            <form onSubmit={onCreate}>
              <ErrorBanner error={create.error} />
              <label>
                <span>Name</span>
                <input value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
              <label>
                <span>Beschreibung (optional)</span>
                <input value={description} onChange={(e) => setDescription(e.target.value)} />
              </label>
              <button className="primary" type="submit" disabled={create.isPending}>
                Anlegen
              </button>
            </form>
          </CardInner>
        </Card>
      )}

      <Card>
        <Tabs tabs={VIEWS} value={view} onChange={switchView} />
        <CardInner>
          <ErrorBanner error={error || restore.error} />
          {isPending ? (
            <Loading />
          ) : !data?.items.length ? (
            <Empty>
              {isTrash
                ? "Der Papierkorb ist leer."
                : view === "archived"
                  ? "Keine archivierten Projekte."
                  : "Noch keine Projekte. Lege dein erstes Projekt an."}
            </Empty>
          ) : (
            <div className="card-grid">
              {data.items.map((p) => (
                <div key={p.id} className="tile">
                  <div className="row between">
                    {isTrash ? (
                      <strong>{p.name}</strong>
                    ) : (
                      <Link to={`/projects/${p.id}`}>
                        <strong>{p.name}</strong>
                      </Link>
                    )}
                    <StatusBadge status={p.status} />
                  </div>
                  {p.description && (
                    <p className="muted" style={{ margin: "10px 0 0" }}>
                      {p.description}
                    </p>
                  )}
                  <div className="row between" style={{ marginTop: 12 }}>
                    {p.my_role && <Badge variant="primary">{p.my_role}</Badge>}
                    <span className="muted" style={{ fontSize: "0.8rem" }}>
                      {formatDate(p.created_at)}
                    </span>
                  </div>
                  {isTrash && p.my_role === "owner" && (
                    <div style={{ marginTop: 12 }}>
                      <button
                        className="small"
                        disabled={restore.isPending}
                        onClick={() => restore.mutate(p.id)}
                      >
                        Wiederherstellen
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
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
    </div>
  );
}
