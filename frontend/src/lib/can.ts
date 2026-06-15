import type { ProjectRole } from "../types/api";

const ORDER: Record<ProjectRole, number> = {
  viewer: 0,
  editor: 1,
  admin: 2,
  owner: 3,
};

// Hinweis: Frontend-Gates sind reine UX. Die echte Autorisierung erfolgt IMMER
// serverseitig.
export function roleAtLeast(role: ProjectRole | null | undefined, min: ProjectRole): boolean {
  if (!role) return false;
  return ORDER[role] >= ORDER[min];
}
