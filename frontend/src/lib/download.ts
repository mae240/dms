// Geteilter Download-Helfer: authentifizierter Blob-Download mit Fehler-Toast.
// Vorher dupliziert in DocumentDetailPage und ProjectDetailPage.

import { getAccessToken } from "./apiClient";
import { downloadAuthed } from "./format";
import { toast } from "./toast";

export async function triggerDownload(path: string): Promise<void> {
  try {
    await downloadAuthed(path, getAccessToken());
  } catch {
    toast.error("Download fehlgeschlagen.");
  }
}
