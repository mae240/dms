// Manuelle API-Typen (MVP). Optional automatisch generierbar via `npm run gen:api`.

// Spiegel von dms_core.enums.AuditAction (fuer das Filter-Dropdown).
export const AUDIT_ACTIONS = [
  "user.login",
  "user.login_failed",
  "user.logout",
  "user.created",
  "user.anonymized",
  "document.uploaded",
  "document.version_created",
  "document.downloaded",
  "document.deleted",
  "document.restored",
  "document.metadata_updated",
  "document.purged",
  "project.created",
  "project.member_added",
  "project.member_removed",
  "project.member_role_changed",
  "compliance.user_export_created",
  "compliance.user_export_downloaded",
  "compliance.retention_set",
  "compliance.legal_hold_set",
  "compliance.document_purged",
] as const;

export type ProjectRole = "owner" | "admin" | "editor" | "viewer";
export type DocumentStatus = "active" | "archived" | "deleted";
export type ProcessingStatus =
  | "uploaded"
  | "processing"
  | "ready"
  | "failed"
  | "quarantined";

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superadmin: boolean;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProjectOut {
  id: string;
  name: string;
  description: string | null;
  owner_id: string;
  status: DocumentStatus; // active | archived | deleted
  created_at: string;
  my_role: ProjectRole | null;
}

export interface RecentDocument {
  id: string;
  title: string;
  project_id: string;
  project_name: string;
  status: DocumentStatus;
  latest_processing_status: ProcessingStatus | null;
  updated_at: string;
}

export interface MemberOut {
  user_id: string;
  email: string;
  full_name: string;
  role: ProjectRole;
  created_at: string;
}

export interface ProjectDetailOut extends ProjectOut {
  members: MemberOut[];
}

export interface VersionOut {
  id: string;
  version_number: number;
  file_name: string;
  file_hash: string;
  mime_type: string;
  size_bytes: number;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface DocumentListItem {
  id: string;
  title: string;
  category: string | null;
  status: DocumentStatus;
  latest_version_number: number | null;
  latest_processing_status: ProcessingStatus | null;
  version_count: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  purge_after: string | null;
  legal_hold: boolean;
  retention_until: string | null;
}

export interface DocumentDetailOut {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  category: string | null;
  status: DocumentStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  retention_until: string | null;
  legal_hold: boolean;
  purge_after: string | null;
  current_version: VersionOut | null;
}

export interface AdminUserOut extends UserOut {
  is_anonymized: boolean;
}

export interface AuditLogOut {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  project_id: string | null;
  ip_address: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface ExportOut {
  id: string;
  subject_user_id: string;
  requested_by: string;
  status: string;
  expires_at: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}
