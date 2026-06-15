import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { toast } from "../../lib/toast";
import type {
  AdminUserOut,
  AuditLogOut,
  DocumentDetailOut,
  ExportOut,
  Page,
} from "../../types/api";

export const PAGE_SIZE = 25;

export function useAdminUsers(limit = PAGE_SIZE, offset = 0) {
  return useQuery({
    queryKey: ["admin", "users", limit, offset],
    queryFn: () => api.get<Page<AdminUserOut>>(`/admin/users?limit=${limit}&offset=${offset}`),
    placeholderData: keepPreviousData,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      email: string;
      password: string;
      full_name: string;
      is_superadmin: boolean;
    }) => api.post<AdminUserOut>("/admin/users", body),
    onSuccess: () => {
      toast.success("Benutzer angelegt.");
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useAnonymizeUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.del<AdminUserOut>(`/admin/users/${userId}`),
    onSuccess: () => {
      toast.success("Benutzer anonymisiert.");
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useCreateExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.post<ExportOut>(`/admin/users/${userId}/export`),
    onSuccess: () => {
      toast.success("Export angefordert.");
      qc.invalidateQueries({ queryKey: ["admin", "exports"] });
    },
  });
}

export function useExports(limit = PAGE_SIZE, offset = 0) {
  return useQuery({
    queryKey: ["admin", "exports", limit, offset],
    queryFn: () => api.get<Page<ExportOut>>(`/admin/exports?limit=${limit}&offset=${offset}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const data = query.state.data as Page<ExportOut> | undefined;
      const pending = data?.items.some(
        (e) => e.status === "pending" || e.status === "processing",
      );
      return pending ? 2000 : false;
    },
  });
}

export interface AuditFilters {
  action?: string;
  projectId?: string;
  actorUserId?: string;
}

export function useAuditLogs(filters: AuditFilters, limit = PAGE_SIZE, offset = 0) {
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (filters.action) q.set("action", filters.action);
  if (filters.projectId) q.set("project_id", filters.projectId);
  if (filters.actorUserId) q.set("actor_user_id", filters.actorUserId);
  return useQuery({
    queryKey: ["admin", "audit", filters, limit, offset],
    queryFn: () => api.get<Page<AuditLogOut>>(`/admin/audit-logs?${q}`),
    placeholderData: keepPreviousData,
  });
}

export function useSetRetention() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentId,
      retention_until,
    }: {
      documentId: string;
      retention_until: string | null;
    }) =>
      api.post<DocumentDetailOut>(`/admin/documents/${documentId}/set-retention`, {
        retention_until,
      }),
    onSuccess: (_data, vars) => {
      toast.success("Aufbewahrung gesetzt.");
      qc.invalidateQueries({ queryKey: ["document", vars.documentId] });
    },
  });
}

export function useRewrapStorage() {
  return useMutation({
    mutationFn: () => api.post<void>("/admin/storage/rewrap"),
    onSuccess: () => {
      toast.success("Schluessel-Rotation gestartet. Sie laeuft im Hintergrund.");
    },
  });
}

export function useSetLegalHold() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, legal_hold }: { documentId: string; legal_hold: boolean }) =>
      api.post<DocumentDetailOut>(`/admin/documents/${documentId}/legal-hold`, { legal_hold }),
    onSuccess: (_data, vars) => {
      toast.success(vars.legal_hold ? "Legal Hold aktiviert." : "Legal Hold aufgehoben.");
      qc.invalidateQueries({ queryKey: ["document", vars.documentId] });
    },
  });
}
