import { useState } from "react";
import { Link } from "react-router-dom";

import { Pagination } from "../../components/Pagination";
import { Empty, ErrorBanner, Loading, StatusBadge } from "../../components/ui";
import { formatDate } from "../../lib/format";
import type { DocumentStatus } from "../../types/api";
import { PAGE_SIZE, useCreateProject, useProjects, useRestoreProject } from "./hooks";

const VIEWS: { key: DocumentStatus; label: string }[] = [
  { key: "active", label: "Aktiv" },
  { key: "archived", label: "Archiviert" },
  { key: "deleted", label: "Papierkorb" },
];

export function ProjectsPage() {
  const [view, setView] = useState<DocumentStatus>("active");
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error } = useProjects(view, PAGE_SIZE, offset);
  const restore = useRestoreProject();
  const create = useCreateProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [open, setOpen] = useState(false);
  const isTrash = view === "deleted";

  function switchView(v: DocumentStatus) {
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
      <div className="row between">
        <h1>Projekte</h1>
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
          {view === "active" && (
            <button className="primary" onClick={() => setOpen((o) => !o)}>
              {open ? "Abbrechen" : "Neues Projekt"}
            </button>
          )}
        </div>
      </div>

      {open && view === "active" && (
        <form className="card" onSubmit={onCreate}>
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
      )}

      <ErrorBanner error={error || restore.error} />
      <div className="card">
        {isLoading ? (
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
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Deine Rolle</th>
                <th>Erstellt</th>
                {isTrash && <th></th>}
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id}>
                  <td>
                    {isTrash ? p.name : <Link to={`/projects/${p.id}`}>{p.name}</Link>}
                  </td>
                  <td>
                    <StatusBadge status={p.status} />
                  </td>
                  <td>
                    <span className="badge">{p.my_role}</span>
                  </td>
                  <td className="muted">{formatDate(p.created_at)}</td>
                  {isTrash && (
                    <td>
                      {p.my_role === "owner" && (
                        <button
                          className="small"
                          disabled={restore.isPending}
                          onClick={() => restore.mutate(p.id)}
                        >
                          Wiederherstellen
                        </button>
                      )}
                    </td>
                  )}
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
    </div>
  );
}
