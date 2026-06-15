import { Fragment, useState } from "react";

import { Pagination } from "../../components/Pagination";
import { Badge, Card, CardInner, Empty, ErrorBanner, Loading, PageHead } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { AUDIT_ACTIONS } from "../../types/api";
import { PAGE_SIZE, useAuditLogs, type AuditFilters } from "./hooks";

export function AuditLogsPage() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { data, isPending, error } = useAuditLogs(filters, PAGE_SIZE, offset);

  function update(patch: Partial<AuditFilters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setOffset(0);
  }

  return (
    <div>
      <PageHead
        eyebrow="Admin / Audit"
        title="Audit-Log"
        note="Eintraege sind unveraenderlich (append-only). IPs werden nach Ablauf geschwaerzt."
      />
      <Card>
        <CardInner>
          <div className="toolbar">
            <select
              value={filters.action ?? ""}
              onChange={(e) => update({ action: e.target.value || undefined })}
            >
              <option value="">Alle Aktionen</option>
              {AUDIT_ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <input
              placeholder="Projekt-ID (optional)"
              value={filters.projectId ?? ""}
              onChange={(e) => update({ projectId: e.target.value.trim() || undefined })}
              style={{ minWidth: 220 }}
            />
            <input
              placeholder="Akteur-ID (optional)"
              value={filters.actorUserId ?? ""}
              onChange={(e) => update({ actorUserId: e.target.value.trim() || undefined })}
              style={{ minWidth: 220 }}
            />
          </div>
          <ErrorBanner error={error} />
        </CardInner>
        {isPending ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty>Keine Eintraege.</Empty>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Zeit</th>
                <th>Aktion</th>
                <th>Objekt</th>
                <th>Akteur</th>
                <th>IP</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => {
                const expanded = expandedId === a.id;
                return (
                  <Fragment key={a.id}>
                    <tr>
                      <td className="muted">{formatDate(a.created_at)}</td>
                      <td>
                        <Badge>{a.action}</Badge>
                      </td>
                      <td className="mono">
                        {a.entity_type}
                        {a.entity_id ? `:${a.entity_id.slice(0, 8)}` : ""}
                      </td>
                      <td className="mono">
                        {a.actor_user_id ? a.actor_user_id.slice(0, 8) : "system"}
                      </td>
                      <td className="mono">{a.ip_address ?? "—"}</td>
                      <td>
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={expanded ? "Details ausblenden" : "Details anzeigen"}
                          aria-expanded={expanded}
                          onClick={() => setExpandedId(expanded ? null : a.id)}
                        >
                          {expanded ? "▾" : "▸"}
                        </button>
                      </td>
                    </tr>
                    {expanded && (
                      <tr>
                        <td colSpan={6}>
                          {a.metadata && Object.keys(a.metadata).length > 0 ? (
                            <pre className="audit-meta-pre mono">
                              {JSON.stringify(a.metadata, null, 2)}
                            </pre>
                          ) : (
                            <span className="muted">Keine Details</span>
                          )}
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
          <CardInner>
            <Pagination
              total={data.total}
              limit={data.limit}
              offset={data.offset}
              onChange={setOffset}
            />
          </CardInner>
        )}
      </Card>
    </div>
  );
}
