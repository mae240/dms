import { useState } from "react";

import { Pagination } from "../../components/Pagination";
import { Empty, ErrorBanner, Loading } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { AUDIT_ACTIONS } from "../../types/api";
import { PAGE_SIZE, useAuditLogs, type AuditFilters } from "./hooks";

export function AuditLogsPage() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const [offset, setOffset] = useState(0);
  const { data, isPending, error } = useAuditLogs(filters, PAGE_SIZE, offset);

  function update(patch: Partial<AuditFilters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setOffset(0);
  }

  return (
    <div>
      <h1>Audit-Log</h1>
      <div className="card">
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
        {isPending ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty>Keine Eintraege.</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Zeit</th>
                <th>Aktion</th>
                <th>Objekt</th>
                <th>Akteur</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id}>
                  <td className="muted">{formatDate(a.created_at)}</td>
                  <td>
                    <span className="badge">{a.action}</span>
                  </td>
                  <td className="mono">
                    {a.entity_type}
                    {a.entity_id ? `:${a.entity_id.slice(0, 8)}` : ""}
                  </td>
                  <td className="mono">{a.actor_user_id ? a.actor_user_id.slice(0, 8) : "system"}</td>
                  <td className="mono">{a.ip_address ?? "—"}</td>
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
      <p className="muted">
        Eintraege sind unveraenderlich (append-only). IPs werden nach Ablauf geschwaerzt.
      </p>
    </div>
  );
}
