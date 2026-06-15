import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, uploadWithProgress } from "../../lib/apiClient";
import { toast } from "../../lib/toast";
import type { DocumentDetailOut, VersionOut } from "../../types/api";

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentDetailOut>(`/documents/${documentId}`),
  });
}

export function useVersions(documentId: string) {
  return useQuery({
    queryKey: ["versions", documentId],
    queryFn: () => api.get<VersionOut[]>(`/documents/${documentId}/versions`),
    refetchInterval: (query) => {
      const data = query.state.data as VersionOut[] | undefined;
      const pending = data?.some(
        (v) => v.processing_status === "uploaded" || v.processing_status === "processing",
      );
      return pending ? 2000 : false;
    },
  });
}

function invalidate(qc: ReturnType<typeof useQueryClient>, documentId: string) {
  qc.invalidateQueries({ queryKey: ["document", documentId] });
  qc.invalidateQueries({ queryKey: ["versions", documentId] });
  qc.invalidateQueries({ queryKey: ["documents"] });
}

export function useUploadVersion(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { form: FormData; onProgress?: (p: number) => void }) =>
      uploadWithProgress<VersionOut>(
        `/documents/${documentId}/versions`,
        vars.form,
        vars.onProgress,
      ),
    onSuccess: () => {
      toast.success("Neue Version hochgeladen.");
      invalidate(qc, documentId);
    },
  });
}

export function usePatchDocument(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Pick<DocumentDetailOut, "title" | "description" | "category" | "status">>) =>
      api.patch<DocumentDetailOut>(`/documents/${documentId}`, body),
    onSuccess: () => {
      toast.success("Gespeichert.");
      invalidate(qc, documentId);
    },
  });
}

export function useDeleteDocument(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.del<void>(`/documents/${documentId}`),
    onSuccess: () => {
      toast.success("Dokument in den Papierkorb verschoben.");
      invalidate(qc, documentId);
    },
  });
}

export function useReprocessVersion(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: string) =>
      api.post<VersionOut>(`/versions/${versionId}/reprocess`),
    onSuccess: () => {
      toast.success("Verarbeitung neu gestartet.");
      invalidate(qc, documentId);
    },
  });
}

export function useRestoreDocument(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<DocumentDetailOut>(`/documents/${documentId}/restore`),
    onSuccess: () => {
      toast.success("Dokument wiederhergestellt.");
      invalidate(qc, documentId);
    },
  });
}
