import { useState } from "react";
import { Link } from "react-router-dom";

import { Glyph } from "../../components/icons";
import {
  Badge,
  Card,
  CardInner,
  Empty,
  ErrorBanner,
  KpiCard,
  Loading,
  PageHead,
  ProgressBar,
  SectionHead,
  StatusBadge,
  UploadZone,
} from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { formatDate } from "../../lib/format";
import { useAuditLogs } from "../admin/hooks";
import { useProjects, useRecentDocuments, useUploadDocument } from "../projects/hooks";

export function DashboardPage() {
  const { user } = useAuth();
  // Grid + Schnell-Upload-Select zeigen bis zu 100 aktive Projekte; vollstaendige
  // Verwaltung laeuft ueber die Projekte-Seite. Die KPI nutzt weiter .total (echte Anzahl).
  const activeProjects = useProjects("active", 100);
  // Nur fuer die KPI ".total" genutzt → Default-Limit reicht.
  const archivedProjects = useProjects("archived");
  const recent = useRecentDocuments();

  return (
    <div>
      <PageHead
        eyebrow="Dashboard / Uebersicht"
        title="Willkommen zurueck"
        note={`Angemeldet als ${user?.full_name || user?.email}${
          user?.is_superadmin ? " (Superadmin)" : ""
        }.`}
        actions={<Link to="/projects">Alle Projekte ansehen</Link>}
      />

      <section className="kpi-grid">
        <KpiCard
          icon={<Glyph name="projects" />}
          value={activeProjects.isPending ? "…" : (activeProjects.data?.total ?? 0)}
          label="Aktive Projekte"
        />
        <KpiCard
          icon={<Glyph name="projects" />}
          value={archivedProjects.isPending ? "…" : (archivedProjects.data?.total ?? 0)}
          label="Archivierte Projekte"
        />
        <KpiCard
          icon={<Glyph name="dashboard" />}
          value={recent.isPending ? "…" : (recent.data?.length ?? 0)}
          label="Zuletzt bearbeitet"
        />
      </section>

      <Card>
        <CardInner>
          <SectionHead
            title="Zuletzt bearbeitet"
            hint="Direkter Zugriff auf die zuletzt geaenderten Dokumente."
            actions={<Link to="/projects">Alle Projekte</Link>}
          />
          <ErrorBanner error={recent.error} />
          {recent.isPending ? (
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
        </CardInner>
      </Card>

      <Card>
        <CardInner>
          <SectionHead
            title="Aktive Projekte"
            hint="Schneller Sprung in deine laufenden Projekte."
          />
          <ErrorBanner error={activeProjects.error} />
          {activeProjects.isPending ? (
            <Loading />
          ) : !activeProjects.data?.items.length ? (
            <Empty>Noch keine aktiven Projekte.</Empty>
          ) : (
            <div className="card-grid">
              {activeProjects.data.items.map((p) => (
                <Link key={p.id} to={`/projects/${p.id}`} className="tile">
                  <div className="row between">
                    <strong>{p.name}</strong>
                    <StatusBadge status={p.status} />
                  </div>
                  {p.my_role && (
                    <div style={{ marginTop: 10 }}>
                      <Badge variant="primary">{p.my_role}</Badge>
                    </div>
                  )}
                </Link>
              ))}
            </div>
          )}
        </CardInner>
      </Card>

      <QuickUpload
        projects={activeProjects.data?.items ?? []}
        loading={activeProjects.isPending}
      />

      {user?.is_superadmin && <ActivityFeed />}
    </div>
  );
}

function QuickUpload({
  projects,
  loading,
}: {
  projects: { id: string; name: string }[];
  loading: boolean;
}) {
  const [projectId, setProjectId] = useState("");

  return (
    <Card>
      <CardInner>
        <SectionHead
          title="Schnell-Upload"
          hint="Datei hochladen und direkt einem Projekt zuweisen."
        />
        <label>
          <span>Projekt</span>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={loading || !projects.length}
          >
            <option value="">Projekt auswaehlen …</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {/* Hook ist an die projectId gebunden → bei Wechsel via key remounten. */}
        <UploadField key={projectId} projectId={projectId} />
      </CardInner>
    </Card>
  );
}

function UploadField({ projectId }: { projectId: string }) {
  const upload = useUploadDocument(projectId);
  const [progress, setProgress] = useState<number | null>(null);
  const disabled = !projectId || upload.isPending;

  async function onFile(file: File) {
    if (!projectId) return;
    // Vorherigen Upload-Fehler verwerfen, damit der ErrorBanner beim erneuten Versuch verschwindet.
    upload.reset();
    const form = new FormData();
    form.append("file", file);
    form.append("title", file.name);
    setProgress(0);
    try {
      await upload.mutateAsync({ form, onProgress: setProgress });
    } finally {
      setProgress(null);
    }
  }

  return (
    <>
      <ErrorBanner error={upload.error} />
      <UploadZone
        onFile={onFile}
        disabled={disabled}
        hint={
          projectId
            ? "Datei hier ablegen oder klicken zum Auswaehlen"
            : "Zuerst ein Projekt auswaehlen"
        }
      />
      {progress !== null && <ProgressBar percent={progress} />}
    </>
  );
}

function ActivityFeed() {
  const logs = useAuditLogs({}, 6, 0);

  return (
    <Card>
      <CardInner>
        <SectionHead title="Aktivitaet" hint="Die letzten Aktionen im Workspace." />
        <ErrorBanner error={logs.error} />
        {logs.isPending ? (
          <Loading />
        ) : !logs.data?.items.length ? (
          <Empty>Noch keine Aktivitaet.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Aktion</th>
                <th>Zeitpunkt</th>
              </tr>
            </thead>
            <tbody>
              {logs.data.items.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.action}</td>
                  <td className="muted">{formatDate(entry.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardInner>
    </Card>
  );
}
