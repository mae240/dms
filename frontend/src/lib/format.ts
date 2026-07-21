import { getAccessToken, refreshAccessToken } from "./apiClient";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function filenameFromDisposition(disposition: string): string {
  // RFC 5987: filename*=UTF-8''<percent-encoded>
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      return star[1].trim();
    }
  }
  // Fallback: filename="..."
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain ? plain[1].trim() : "download";
}

export async function downloadAuthed(path: string): Promise<void> {
  const authedFetch = () => {
    const token = getAccessToken();
    return fetch(`/api${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
  };
  let res = await authedFetch();
  // Abgelaufenes Access-Token einmal erneuern (gleiches Muster wie apiClient.request).
  if (res.status === 401 && (await refreshAccessToken())) {
    res = await authedFetch();
  }
  if (!res.ok) throw new Error("Download fehlgeschlagen");
  const blob = await res.blob();
  const filename = filenameFromDisposition(res.headers.get("content-disposition") ?? "");

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  // Anchor MUSS im DOM haengen, sonst ignoriert Chrome das download-Attribut
  // und benennt nach der Blob-URL (UUID).
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Blob-URL erst spaeter freigeben, sonst kann der Download abgebrochen werden.
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
