// Abhaengigkeitsfreie Glyph-Icons (Unicode), gekapselt fuer einheitliche Nutzung.
export const ICONS = {
  dashboard: "▣", // ▣
  projects: "▦", // ▦
  audit: "◉", // ◉
  compliance: "☷", // ☷
  users: "\u{1F465}", // 👥
  account: "⚙", // ⚙
  upload: "⇧", // ⇧
  download: "↧", // ↧
  reprocess: "↻", // ↻
  open: "↗", // ↗
  add: "＋", // ＋
  menu: "☰", // ☰
  logout: "↪", // ↪
  lock: "\u{1F512}", // 🔒
} as const;

export function Glyph({ name }: { name: keyof typeof ICONS }) {
  return <span aria-hidden="true">{ICONS[name]}</span>;
}
