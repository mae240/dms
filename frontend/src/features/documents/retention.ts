// Restlaufzeit der Aufbewahrung als Prozent (0..100) und Resttage.
// Annahme: Aufbewahrung laeuft ab created_at bis retention_until.
export function retentionProgress(
  createdAt: string,
  retentionUntil: string | null,
  now: Date = new Date(),
): { percent: number; daysLeft: number } | null {
  if (!retentionUntil) return null;
  const start = new Date(createdAt).getTime();
  const end = new Date(retentionUntil).getTime();
  const cur = now.getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  const elapsed = cur - start;
  const total = end - start;
  const percent = Math.max(0, Math.min(100, (elapsed / total) * 100));
  const daysLeft = Math.max(0, Math.ceil((end - cur) / 86_400_000));
  return { percent, daysLeft };
}
