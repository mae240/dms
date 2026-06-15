import { Link } from "react-router-dom";

import { Empty, ErrorBanner, Loading, StatusBadge } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { formatDate } from "../../lib/format";
import { useProjects, useRecentDocuments } from "../projects/hooks";

export function DashboardPage() {
  const { user } = useAuth();
  const projects = useProjects();
  const recent = useRecentDocuments();

  return (
    <div>
      <h1>Dashboard</h1>
      <p className="muted">
        Willkommen, {user?.full_name || user?.email}
        {user?.is_superadmin ? " (Superadmin)" : ""}.
      </p>

      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Deine Projekte</h2>
          <Link to="/projects">Alle ansehen →</Link>
        </div>
        <ErrorBanner error={projects.error} />
        {projects.isPending ? (
          <Loading />
        ) : (
          <p style={{ fontSize: "2rem", margin: "0.5rem 0" }}>{projects.data?.total ?? 0}</p>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Zuletzt bearbeitet</h2>
        <ErrorBanner error={recent.error} />
        {recent.isLoading ? (
          <Loading />
        ) : !recent.data?.length ? (
          <Empty>Noch keine Dokumente.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Titel</th>
                <th>Projekt</th>
                <th>Verarbeitung</th>
                <th>Aktualisiert</th>
              </tr>
            </thead>
            <tbody>
              {recent.data.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link to={`/documents/${d.id}`}>{d.title}</Link>
                  </td>
                  <td>
                    <Link to={`/projects/${d.project_id}`} className="muted">
                      {d.project_name}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={d.latest_processing_status} />
                  </td>
                  <td className="muted">{formatDate(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
