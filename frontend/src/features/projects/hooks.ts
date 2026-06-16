import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, uploadWithProgress } from "../../lib/apiClient";
import { PAGE_SIZE } from "../../lib/constants";
import { toast } from "../../lib/toast";
import type {
  DocumentDetailOut,
  DocumentListItem,
  DocumentStatus,
  MemberOut,
  Page,
  ProjectDetailOut,
  ProjectOut,
  ProjectRole,
  ProjectStatus,
  RecentDocument,
  RetentionRuleIn,
  RetentionRuleOut,
} from "../../types/api";

// PAGE_SIZE liegt zentral in lib/constants; hier re-exportiert, damit bestehende
// Importe aus diesem Modul (ProjectsPage/ProjectDetailPage) unveraendert bleiben.
export { PAGE_SIZE };

export function useProjects(status?: ProjectStatus, limit = PAGE_SIZE, offset = 0) {
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) q.set("status", status);
  return useQuery({
    queryKey: ["projects", status ?? "default", limit, offset],
    queryFn: () => api.get<Page<ProjectOut>>(`/projects?${q}`),
    placeholderData: keepPreviousData,
  });
}

export function useUpdateProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string; status?: ProjectStatus }) =>
      api.patch<ProjectOut>(`/projects/${projectId}`, body),
    onSuccess: () => {
      toast.success("Projekt aktualisiert.");
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => api.del<void>(`/projects/${projectId}`),
    onSuccess: (_d, projectId) => {
      toast.success("Projekt in den Papierkorb verschoben.");
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useRestoreProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => api.post<ProjectOut>(`/projects/${projectId}/restore`),
    onSuccess: (_d, projectId) => {
      toast.success("Projekt wiederhergestellt.");
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useRecentDocuments() {
  return useQuery({
    queryKey: ["recent-documents"],
    queryFn: () => api.get<RecentDocument[]>("/me/recent-documents"),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      api.post<ProjectOut>("/projects", body),
    onSuccess: () => {
      toast.success("Projekt angelegt.");
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.get<ProjectDetailOut>(`/projects/${projectId}`),
    enabled: !!projectId, // nicht mit leerer ID feuern (vermeidet /projects/-Redirect)
  });
}

export function useAddMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; role: ProjectRole }) =>
      api.post<MemberOut>(`/projects/${projectId}/members`, body),
    onSuccess: () => {
      toast.success("Mitglied hinzugefuegt.");
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useRemoveMember(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.del<void>(`/projects/${projectId}/members/${userId}`),
    onSuccess: () => {
      toast.success("Mitglied entfernt.");
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useChangeMemberRole(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: ProjectRole }) =>
      api.patch<MemberOut>(`/projects/${projectId}/members/${userId}`, { role }),
    onSuccess: () => {
      toast.success("Rolle aktualisiert.");
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useDocuments(
  projectId: string,
  status: DocumentStatus = "active",
  search = "",
  limit = PAGE_SIZE,
  offset = 0,
) {
  const q = new URLSearchParams({ status, limit: String(limit), offset: String(offset) });
  if (search.trim()) q.set("search", search.trim());
  return useQuery({
    queryKey: ["documents", projectId, status, search.trim(), limit, offset],
    queryFn: () => api.get<Page<DocumentListItem>>(`/projects/${projectId}/documents?${q}`),
    placeholderData: keepPreviousData,
    // Solange Versionen verarbeitet werden, regelmaessig aktualisieren.
    refetchInterval: (query) => {
      const data = query.state.data as Page<DocumentListItem> | undefined;
      const pending = data?.items.some(
        (d) =>
          d.latest_processing_status === "uploaded" ||
          d.latest_processing_status === "processing",
      );
      return pending ? 2000 : false;
    },
  });
}

export function useUploadDocument(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { form: FormData; onProgress?: (p: number) => void }) =>
      uploadWithProgress<DocumentDetailOut>(
        `/projects/${projectId}/documents`,
        vars.form,
        vars.onProgress,
      ),
    onSuccess: () => {
      toast.success("Dokument hochgeladen.");
      qc.invalidateQueries({ queryKey: ["documents", projectId] });
    },
  });
}

export function useRetentionRules(projectId: string) {
  return useQuery({
    queryKey: ["retention-rules", projectId],
    queryFn: () => api.get<RetentionRuleOut[]>(`/projects/${projectId}/retention-rules`),
    enabled: !!projectId,
  });
}

export function useUpsertRetentionRule(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RetentionRuleIn) =>
      api.put<RetentionRuleOut>(`/projects/${projectId}/retention-rules`, body),
    onSuccess: () => {
      toast.success("Aufbewahrungsregel gespeichert.");
      qc.invalidateQueries({ queryKey: ["retention-rules", projectId] });
    },
  });
}

export function useDeleteRetentionRule(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (category: string | null) =>
      api.del<void>(`/projects/${projectId}/retention-rules`, { category }),
    onSuccess: () => {
      toast.success("Aufbewahrungsregel entfernt.");
      qc.invalidateQueries({ queryKey: ["retention-rules", projectId] });
    },
  });
}

export function useRestoreDocumentInProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      api.post<DocumentDetailOut>(`/documents/${documentId}/restore`),
    onSuccess: (_data, documentId) => {
      toast.success("Dokument wiederhergestellt.");
      qc.invalidateQueries({ queryKey: ["documents", projectId] });
      qc.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}
