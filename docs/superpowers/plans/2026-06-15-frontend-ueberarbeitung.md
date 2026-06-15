# Frontend-Ueberarbeitung DMS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Komplette visuelle Neuauflage des DMS-Frontends im Dark-SaaS-Look (Glass-Sidebar, Gradient-Akzente, KPI-Karten, Tabs, Drag&Drop-Upload), unter vollstaendigem Erhalt der bestehenden Funktionalitaet, plus drei neuer A-Features (Key-Rotation, Erst-Admin-Setup, Audit-Metadaten).

**Architecture:** Rein Frontend. Neues Token-Set + Komponentenklassen in `index.css`, ausgebautes Design-System in `components/ui.tsx`, neue Shell in `components/AppLayout.tsx`. Alle Seiten (`features/*/Page.tsx`) werden neu aufgebaut, wobei die bestehenden Hooks (`features/*/hooks.ts`), `lib/*` und alle API-Response-Shapes unveraendert wiederverwendet werden. Backend bleibt unangetastet.

**Tech Stack:** React 18.3, TypeScript 5.7, Vite 6, react-router-dom 6.28, @tanstack/react-query 5.62, Vitest 2. Styling: globales CSS mit CSS-Custom-Properties (keine neue Dependency).

**Spec:** `docs/superpowers/specs/2026-06-15-frontend-ueberarbeitung-design.md`

---

## Wichtige Regeln fuer jeden Task

- **Funktionalitaet erhalten:** Vor jedem Seiten-Umbau die bestehende `Page.tsx` lesen. Alle verwendeten Hooks, Mutationen, Query-Keys, `confirmDialog`/`toast`-Aufrufe, Permission-Checks (`useAuth`, `roleAtLeast`), Loading/Error/Empty-States und das Verhalten bleiben erhalten. Es aendert sich nur das Markup/Styling.
- **Keine API-Shape-Aenderungen.** Keine neuen Backend-Calls ausser den im Plan genannten (`register-first-admin`, `storage/rewrap`).
- **Keine `window.confirm`/`alert`.** Immer `confirmDialog` aus `lib/confirm`.
- **TanStack Query v5:** `isPending` statt `isLoading`; paginierte Queries mit `placeholderData: keepPreviousData`; Mutationen invalidieren in `onSuccess`/`onSettled` (bereits in den Hooks erledigt).
- **Deutsche UI-Texte**, Stil der Umgebung. Keine Emojis im Code. Ruff/ESLint-konform, Imports am Dateianfang.
- **Verifikation pro Task (muss gruen sein, sonst kein Commit):**
  ```bash
  docker compose run --rm --no-deps --entrypoint sh frontend -c "npm ci && npx tsc --noEmit && npm run test"
  ```
  Niemals `--no-verify`, keine Tests skippen.

---

## File Structure

**Neu:**
- `frontend/src/features/auth/SetupPage.tsx` — Erst-Admin-Setup (A2).
- `frontend/src/components/icons.tsx` — kleine Inline-SVG/Glyph-Icons fuer Nav/KPIs (kein externes Icon-Paket).

**Stark ueberarbeitet:**
- `frontend/src/index.css` — neues Token-Set, Komponentenklassen, Shell-Layout.
- `frontend/src/components/ui.tsx` — Design-System (Card, KpiCard, Badge, Tabs, PageHead, SectionHead, UploadZone, ProgressBar, restylte Bestands-Exports).
- `frontend/src/components/AppLayout.tsx` — Glass-Sidebar-Shell mit Sektionen + mobilem Drawer.
- Alle `frontend/src/features/*/Page.tsx`.

**Punktuell erweitert (additiv, keine Breaking Changes):**
- `frontend/src/lib/apiClient.ts` — `registerFirstAdminRequest`.
- `frontend/src/lib/auth.tsx` — `registerFirstAdmin` in `AuthState`.
- `frontend/src/features/admin/hooks.ts` — `useRewrapStorage` (A1).
- `frontend/src/App.tsx` — Route `/setup`.

**Unveraendert:** `lib/apiClient` (Kern), `lib/can`, `lib/format`, `lib/download`, `lib/confirm` (API), `lib/toast` (API), alle `features/*/hooks.ts` (ausser admin: +1 Hook), `types/api.ts`, `components/Pagination.tsx`, `components/RequireAuth.tsx`, `main.tsx`.

---

## Task 1: Design-System-Fundament (Tokens, Shared Components, Shell)

Dies ist die Basis fuer alle weiteren Tasks. Reine Praesentation, keine neue Logik.

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/ui.tsx`
- Create: `frontend/src/components/icons.tsx`
- Modify: `frontend/src/components/AppLayout.tsx`
- Test: `frontend/src/components/ui.test.tsx`

- [ ] **Step 1: Token-Set + Basis-Styles in `index.css` schreiben**

Ersetze den Inhalt von `index.css` vollstaendig durch das neue Token-Set. Behalte ALLE bestehenden Klassennamen bei, die Seiten/Komponenten heute nutzen (`.card`, `.badge`, `.banner`, `.empty`, `.row`, `.toolbar`, `.breadcrumb`, `.dropzone`, `.progress`, `.toast*`, `.modal*`, `.login-wrap`, `.login-card`, `.muted`, `.mono`, `.spacer`), aber im neuen Look. Ergaenze die neuen Klassen.

```css
:root {
  --bg: #080d19;
  --surface: #101827;
  --surface-2: #151f33;
  --surface-3: #1b2942;
  --border: rgba(255, 255, 255, 0.09);
  --border-strong: rgba(255, 255, 255, 0.16);
  --text: #eef4ff;
  --muted: #99a8c0;
  --muted-2: #687891;
  --primary: #6d7cff;
  --primary-2: #bfc8ff;
  --primary-soft: rgba(109, 124, 255, 0.15);
  --success: #35d07f;
  --success-soft: rgba(53, 208, 127, 0.13);
  --warning: #ffbd4a;
  --warning-soft: rgba(255, 189, 74, 0.14);
  --danger: #ff6174;
  --danger-soft: rgba(255, 97, 116, 0.13);
  --shadow: 0 26px 90px rgba(0, 0, 0, 0.42);
  --glass: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.03));
  --radius-xl: 22px;
  --radius-lg: 18px;
  --radius-md: 14px;
  --radius-sm: 10px;
  --radius: 14px; /* Alias fuer Bestands-Klassen */
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  background:
    radial-gradient(circle at top left, rgba(109, 124, 255, 0.22), transparent 34rem),
    radial-gradient(circle at 85% 12%, rgba(53, 208, 127, 0.1), transparent 30rem),
    var(--bg);
  color: var(--text);
  font-size: 14px;
}

a { color: var(--primary-2); text-decoration: none; }
a:hover { text-decoration: underline; }

h1 { font-size: clamp(26px, 3vw, 38px); line-height: 1.08; letter-spacing: -0.04em; margin: 0; }
h2 { font-size: 18px; margin: 0; letter-spacing: -0.02em; }

/* Buttons */
button { font: inherit; }
.btn,
button.btn {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  color: var(--text);
  background: rgba(255, 255, 255, 0.06);
  padding: 10px 14px;
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: 0.16s ease;
  white-space: nowrap;
}
.btn:hover:not(:disabled) { transform: translateY(-1px); background: rgba(255, 255, 255, 0.1); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary {
  border-color: transparent;
  background: linear-gradient(135deg, var(--primary), #8b5cff);
  box-shadow: 0 18px 44px rgba(109, 124, 255, 0.28);
  color: #fff;
}
.btn.ghost { border-color: transparent; background: transparent; }
.btn.danger { color: var(--danger); border-color: rgba(255, 97, 116, 0.28); background: rgba(255, 97, 116, 0.08); }
.btn.small { padding: 6px 10px; min-height: 34px; font-size: 0.85rem; }
.icon-btn {
  width: 38px; height: 38px; flex: 0 0 auto;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text); background: rgba(255, 255, 255, 0.055); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
}
.icon-btn:hover:not(:disabled) { background: rgba(255, 255, 255, 0.1); }
.icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Plain bestehende Buttons (ohne .btn) auf neuen Look heben */
button:not(.btn):not(.icon-btn):not(.tab) {
  font: inherit; cursor: pointer;
  border: 1px solid var(--border-strong);
  background: rgba(255, 255, 255, 0.06);
  color: var(--text);
  padding: 10px 14px;
  border-radius: var(--radius-md);
  transition: 0.16s ease;
}
button:not(.btn):not(.icon-btn):not(.tab):hover:not(:disabled) { background: rgba(255, 255, 255, 0.1); }
button:not(.btn):not(.icon-btn):not(.tab):disabled { opacity: 0.5; cursor: not-allowed; }
button.primary { border-color: transparent; background: linear-gradient(135deg, var(--primary), #8b5cff); color: #fff; }
button.danger { color: var(--danger); border-color: rgba(255, 97, 116, 0.28); background: rgba(255, 97, 116, 0.08); }
button.small { padding: 6px 10px; font-size: 0.85rem; }

/* Form-Elemente */
input, select, textarea {
  font: inherit;
  width: 100%;
  color: var(--text);
  background: rgba(5, 9, 18, 0.72);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 11px 12px;
  outline: none;
}
input:focus, select:focus, textarea:focus {
  border-color: rgba(109, 124, 255, 0.55);
  box-shadow: 0 0 0 3px rgba(109, 124, 255, 0.22);
}
textarea { min-height: 92px; resize: vertical; line-height: 1.5; }
label { display: block; margin-bottom: 0.85rem; }
label span { display: block; margin-bottom: 0.35rem; color: var(--muted); font-size: 0.8rem; }

/* Tabellen */
table, .table { width: 100%; border-collapse: collapse; }
th, td, .table th, .table td {
  text-align: left; padding: 13px 10px;
  border-bottom: 1px solid var(--border); font-size: 13px;
}
th, .table th {
  color: var(--muted); font-weight: 800; font-size: 0.7rem;
  text-transform: uppercase; letter-spacing: 0.08em;
}
tr:hover td { background: rgba(255, 255, 255, 0.03); }

/* Cards */
.card {
  border: 1px solid var(--border);
  background: var(--glass);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow);
  margin-bottom: 18px;
  overflow: hidden;
}
.card-inner { padding: 22px; }
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 16px; }
.hint { color: var(--muted); font-size: 13px; margin-top: 4px; line-height: 1.5; }

.page-head { display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 22px; flex-wrap: wrap; }
.eyebrow { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
.page-note { color: var(--muted); margin-top: 10px; max-width: 680px; line-height: 1.55; }
.page-actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }

.row { display: flex; gap: 0.75rem; align-items: center; }
.row.between { justify-content: space-between; }
.row.wrap { flex-wrap: wrap; }
.row.end { justify-content: flex-end; }
.spacer { flex: 1; }
.muted { color: var(--muted); }
.mono { font-family: ui-monospace, "SFMono-Regular", Menlo, monospace; font-size: 0.82rem; }

/* Badges mit Dot */
.badge {
  display: inline-flex; align-items: center; gap: 7px;
  border-radius: 999px; border: 1px solid var(--border);
  padding: 5px 10px; font-size: 12px; font-weight: 800; white-space: nowrap;
}
.badge .dot { width: 7px; height: 7px; border-radius: 999px; background: currentColor; }
.badge.success { color: var(--success); background: var(--success-soft); border-color: rgba(53, 208, 127, 0.32); }
.badge.warning { color: var(--warning); background: var(--warning-soft); border-color: rgba(255, 189, 74, 0.34); }
.badge.danger { color: var(--danger); background: var(--danger-soft); border-color: rgba(255, 97, 116, 0.34); }
.badge.primary { color: var(--primary-2); background: var(--primary-soft); border-color: rgba(109, 124, 255, 0.32); }
.badge.neutral, .badge.muted { color: var(--muted); }
/* Status-Aliase (Bestand) */
.badge.ready, .badge.active { color: var(--success); background: var(--success-soft); border-color: rgba(53, 208, 127, 0.32); }
.badge.processing, .badge.uploaded { color: var(--warning); background: var(--warning-soft); border-color: rgba(255, 189, 74, 0.34); }
.badge.failed, .badge.quarantined, .badge.deleted { color: var(--danger); background: var(--danger-soft); border-color: rgba(255, 97, 116, 0.34); }
.badge.archived { color: var(--muted); }

/* Banner */
.banner { padding: 0.85rem 1rem; border-radius: var(--radius-md); margin-bottom: 1rem; }
.banner.error { background: var(--danger-soft); border: 1px solid rgba(255, 97, 116, 0.34); color: #ffc2c8; }
.banner.success { background: var(--success-soft); border: 1px solid rgba(53, 208, 127, 0.34); color: #b6f0d2; }

.empty { text-align: center; color: var(--muted); padding: 2.5rem; }

/* KPI */
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.kpi { position: relative; overflow: hidden; padding: 20px; border-radius: var(--radius-xl); border: 1px solid var(--border); background: var(--glass); box-shadow: var(--shadow); }
.kpi::after { content: ""; position: absolute; right: -36px; top: -36px; width: 128px; height: 128px; border-radius: 999px; background: rgba(109, 124, 255, 0.14); }
.kpi-top { position: relative; z-index: 1; display: flex; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.kpi-icon { width: 44px; height: 44px; display: grid; place-items: center; border-radius: var(--radius-md); background: var(--primary-soft); color: var(--primary-2); font-size: 20px; }
.kpi-value { position: relative; z-index: 1; font-size: 34px; line-height: 1; font-weight: 900; letter-spacing: -0.05em; }
.kpi-label { position: relative; z-index: 1; color: var(--muted); font-size: 13px; margin-top: 6px; }

/* Tabs */
.tabs { display: flex; gap: 8px; padding: 10px; border-bottom: 1px solid var(--border); background: rgba(255, 255, 255, 0.035); overflow-x: auto; }
.tab { border: 0; border-radius: 999px; padding: 9px 13px; color: var(--muted); background: transparent; cursor: pointer; white-space: nowrap; }
.tab.active { color: var(--text); background: var(--primary-soft); box-shadow: inset 0 0 0 1px rgba(109, 124, 255, 0.28); }

/* Grids fuer Karten */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.tile {
  padding: 17px; border-radius: var(--radius-lg); border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.045); transition: 0.16s ease;
}
.tile:hover { transform: translateY(-1px); background: rgba(255, 255, 255, 0.07); border-color: rgba(109, 124, 255, 0.34); }

/* Upload-Zone */
.upload-zone {
  display: grid; place-items: center; text-align: center; min-height: 156px;
  border: 1px dashed rgba(139, 160, 255, 0.45); border-radius: var(--radius-lg);
  background: rgba(109, 124, 255, 0.08); padding: 20px; cursor: pointer;
}
.upload-zone.drag { border-color: var(--primary); background: rgba(109, 124, 255, 0.16); }
.upload-icon { width: 52px; height: 52px; display: grid; place-items: center; margin: 0 auto 12px; border-radius: var(--radius-md); background: var(--primary-soft); color: var(--primary-2); font-size: 24px; }
/* Bestands-Alias */
.dropzone { border: 1px dashed rgba(139, 160, 255, 0.45); border-radius: var(--radius-lg); padding: 1.5rem; text-align: center; color: var(--muted); cursor: pointer; background: rgba(109, 124, 255, 0.08); }
.dropzone.drag { border-color: var(--primary); color: var(--text); }

/* Progress */
.progress { height: 9px; background: rgba(255, 255, 255, 0.08); border-radius: 999px; overflow: hidden; margin: 0.5rem 0; }
.progress > div, .progress > span { display: block; height: 100%; background: linear-gradient(90deg, var(--primary), var(--success)); border-radius: inherit; transition: width 0.15s ease; }

/* Shell-Layout */
.layout { display: grid; grid-template-columns: 264px minmax(0, 1fr); min-height: 100vh; }
.sidebar {
  position: sticky; top: 0; height: 100vh; padding: 24px 16px;
  background: rgba(7, 12, 24, 0.78); border-right: 1px solid var(--border);
  backdrop-filter: blur(18px); display: flex; flex-direction: column;
}
.brand { display: flex; align-items: center; gap: 12px; padding: 0 8px 22px; }
.brand .logo { width: 44px; height: 44px; display: grid; place-items: center; border-radius: var(--radius-md); background: linear-gradient(135deg, #6d7cff, #9f6dff); box-shadow: 0 18px 48px rgba(109, 124, 255, 0.32); font-weight: 900; color: #fff; }
.brand strong { display: block; font-size: 20px; letter-spacing: -0.03em; }
.brand span { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
.sidebar nav { display: flex; flex-direction: column; }
.nav-label { margin: 18px 12px 8px; color: var(--muted-2); font-size: 11px; text-transform: uppercase; letter-spacing: 0.14em; }
.sidebar nav a, .nav-item {
  display: flex; align-items: center; gap: 11px; min-height: 43px; padding: 0 12px;
  border-radius: var(--radius-md); color: var(--muted); text-decoration: none; margin: 3px 0; transition: 0.16s ease;
}
.sidebar nav a:hover, .nav-item:hover { color: var(--text); background: rgba(255, 255, 255, 0.07); text-decoration: none; }
.sidebar nav a.active, .nav-item.active { color: var(--text); background: var(--primary-soft); box-shadow: inset 0 0 0 1px rgba(109, 124, 255, 0.25); }
.nav-icon { width: 22px; text-align: center; display: inline-flex; justify-content: center; }
.account-card { margin-top: auto; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--glass); }
.account-row { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.avatar { width: 38px; height: 38px; border-radius: var(--radius-md); display: grid; place-items: center; background: var(--primary-soft); color: var(--primary-2); font-weight: 900; flex: 0 0 auto; }
.account-name { font-weight: 800; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-mail { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.content { padding: 28px; max-width: 1480px; width: 100%; margin: 0 auto; }
.mobile-topbar { display: none; }

/* Breadcrumb / Toolbar (Bestand) */
.breadcrumb { font-size: 0.85rem; color: var(--muted); margin-bottom: 0.5rem; }
.breadcrumb a { color: var(--muted); }
.toolbar { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.85rem; }
.toolbar input, .toolbar select { width: auto; }

/* Login / Setup */
.login-wrap { display: flex; min-height: 100vh; align-items: center; justify-content: center; padding: 1rem; }
.login-card { width: 380px; max-width: 100%; }

/* Modal (lib/confirm) */
.modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); display: flex; align-items: center; justify-content: center; padding: 1rem; z-index: 1000; backdrop-filter: blur(4px); }
.modal { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.5rem; max-width: 28rem; width: 100%; box-shadow: var(--shadow); }

/* Toasts */
.toast-container { position: fixed; bottom: 1rem; right: 1rem; z-index: 1000; display: flex; flex-direction: column; gap: 0.5rem; max-width: 360px; }
.toast { padding: 0.8rem 1rem; border-radius: var(--radius-md); cursor: pointer; border: 1px solid var(--border); background: var(--surface-2); color: var(--text); box-shadow: var(--shadow); animation: toast-in 0.15s ease; }
.toast.success { border-color: rgba(53, 208, 127, 0.4); }
.toast.error { border-color: rgba(255, 97, 116, 0.4); }
@keyframes toast-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* Audit-Metadaten (A3) */
.audit-meta-pre { margin: 0; padding: 12px; background: rgba(5, 9, 18, 0.72); border: 1px solid var(--border); border-radius: var(--radius-sm); overflow-x: auto; white-space: pre-wrap; word-break: break-word; }

/* Responsiv: Drawer */
@media (max-width: 1180px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar {
    position: fixed; left: 0; top: 0; z-index: 1001; width: 282px;
    transform: translateX(-100%); transition: transform 0.2s ease;
  }
  .sidebar.open { transform: translateX(0); }
  .mobile-topbar { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border); background: rgba(7, 12, 24, 0.78); backdrop-filter: blur(18px); position: sticky; top: 0; z-index: 900; }
  .drawer-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); z-index: 1000; }
  .content { padding: 18px; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 720px) {
  .kpi-grid { grid-template-columns: 1fr; }
  .page-head { align-items: stretch; }
}
```

- [ ] **Step 2: `components/icons.tsx` anlegen**

Kleine, abhaengigkeitsfreie Glyph-Komponente fuer Nav/KPI-Icons. Verwendet Unicode-Glyphen (wie in den Prototypen), gekapselt fuer Konsistenz.

```tsx
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
```

- [ ] **Step 3: `components/ui.tsx` ausbauen**

Bestehende Exports beibehalten (`StatusBadge`, `ErrorBanner`, `SuccessBanner`, `Empty`, `Loading`), `StatusBadge` auf Variantenlogik umstellen, neue Komponenten ergaenzen.

```tsx
import type { ReactNode } from "react";

import { ApiError } from "../lib/apiClient";

type BadgeVariant = "success" | "warning" | "danger" | "primary" | "neutral";

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  ready: "success",
  active: "success",
  processing: "warning",
  uploaded: "warning",
  failed: "danger",
  quarantined: "danger",
  deleted: "danger",
  archived: "neutral",
};

export function Badge({
  variant = "neutral",
  dot = false,
  children,
}: {
  variant?: BadgeVariant;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`badge ${variant}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="badge neutral">—</span>;
  const variant = STATUS_VARIANT[status] ?? "neutral";
  return (
    <span className={`badge ${variant}`}>
      <span className="dot" />
      {status}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`card${className ? ` ${className}` : ""}`}>{children}</div>;
}

export function CardInner({ children }: { children: ReactNode }) {
  return <div className="card-inner">{children}</div>;
}

export function SectionHead({
  title,
  hint,
  actions,
}: {
  title: string;
  hint?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {hint && <div className="hint">{hint}</div>}
      </div>
      {actions}
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  note,
  actions,
}: {
  eyebrow?: string;
  title: string;
  note?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {note && <div className="page-note">{note}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function KpiCard({
  icon,
  value,
  label,
  badge,
}: {
  icon: ReactNode;
  value: ReactNode;
  label: string;
  badge?: ReactNode;
}) {
  return (
    <article className="kpi">
      <div className="kpi-top">
        <div className="kpi-icon">{icon}</div>
        {badge}
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </article>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === value}
          className={`tab${t.id === value ? " active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function ProgressBar({ percent }: { percent: number }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="progress">
      <div style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Unbekannter Fehler";
  return <div className="banner error">{message}</div>;
}

export function SuccessBanner({ children }: { children: ReactNode }) {
  return <div className="banner success">{children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Loading() {
  return <div className="empty">Lade …</div>;
}
```

- [ ] **Step 4: `UploadZone` ergaenzen (in `ui.tsx`)**

Wiederverwendbare Drag&Drop-Zone. Gibt ausgewaehlte Datei(en) per Callback zurueck; kapselt KEINE Upload-Logik (die bleibt in den Seiten via vorhandene Hooks), nur Datei-Auswahl + Drag-State.

```tsx
import { useRef, useState } from "react";

export function UploadZone({
  onFile,
  accept,
  hint = "Datei hier ablegen oder klicken zum Auswaehlen",
  disabled = false,
}: {
  onFile: (file: File) => void;
  accept?: string;
  hint?: string;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  return (
    <div
      className={`upload-zone${drag ? " drag" : ""}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (disabled) return;
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <div>
        <div className="upload-icon" aria-hidden="true">
          {"⇧"}
        </div>
        <strong>Dateien hochladen</strong>
        <div className="hint">{hint}</div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
```

> Hinweis: `useRef`/`useState`-Import oben in der Datei zusammenfuehren (ein Import-Statement aus `react`).

- [ ] **Step 5: `components/AppLayout.tsx` als Glass-Shell neu schreiben**

```tsx
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../lib/auth";
import { Glyph } from "./icons";

export function AppLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const initials = (user?.full_name || user?.email || "?")
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="layout">
      <div className="mobile-topbar">
        <button className="icon-btn" onClick={() => setOpen(true)} aria-label="Menue oeffnen">
          <Glyph name="menu" />
        </button>
        <strong>DMS</strong>
      </div>
      {open && <div className="drawer-overlay" onClick={close} />}
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <div className="logo">D</div>
          <div>
            <strong>DMS</strong>
            <span>Dokumentenverwaltung</span>
          </div>
        </div>

        <div className="nav-label">Workspace</div>
        <nav>
          <NavLink to="/dashboard" onClick={close}>
            <span className="nav-icon"><Glyph name="dashboard" /></span> Dashboard
          </NavLink>
          <NavLink to="/projects" onClick={close}>
            <span className="nav-icon"><Glyph name="projects" /></span> Projekte
          </NavLink>
        </nav>

        {user?.is_superadmin && (
          <>
            <div className="nav-label">Compliance</div>
            <nav>
              <NavLink to="/admin/audit-logs" onClick={close}>
                <span className="nav-icon"><Glyph name="audit" /></span> Audit-Log
              </NavLink>
              <NavLink to="/admin/compliance" onClick={close}>
                <span className="nav-icon"><Glyph name="compliance" /></span> Compliance-Center
              </NavLink>
            </nav>
            <div className="nav-label">Admin</div>
            <nav>
              <NavLink to="/admin/users" onClick={close}>
                <span className="nav-icon"><Glyph name="users" /></span> Benutzer
              </NavLink>
            </nav>
          </>
        )}

        <div className="account-card">
          <div className="account-row">
            <div className="avatar">{initials}</div>
            <div style={{ minWidth: 0 }}>
              <div className="account-name">{user?.full_name || "—"}</div>
              <div className="account-mail">{user?.email}</div>
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <NavLink to="/account" className="btn small ghost" onClick={close} style={{ flex: 1 }}>
              Konto
            </NavLink>
            <button className="btn small" onClick={() => logout()} style={{ flex: 1 }}>
              Abmelden
            </button>
          </div>
        </div>
      </aside>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 6: Komponenten-Test schreiben (`components/ui.test.tsx`)**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge, ProgressBar, StatusBadge } from "./ui";

describe("StatusBadge", () => {
  it("mappt ready auf success-Variante", () => {
    const { container } = render(<StatusBadge status="ready" />);
    expect(container.querySelector(".badge.success")).not.toBeNull();
  });
  it("mappt failed auf danger-Variante", () => {
    const { container } = render(<StatusBadge status="failed" />);
    expect(container.querySelector(".badge.danger")).not.toBeNull();
  });
  it("zeigt Platzhalter bei null", () => {
    render(<StatusBadge status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("rendert die gewuenschte Variante und Inhalt", () => {
    const { container } = render(<Badge variant="warning">Review</Badge>);
    expect(container.querySelector(".badge.warning")).not.toBeNull();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });
});

describe("ProgressBar", () => {
  it("begrenzt Prozent auf 0..100", () => {
    const { container } = render(<ProgressBar percent={150} />);
    const bar = container.querySelector(".progress > div") as HTMLElement;
    expect(bar.style.width).toBe("100%");
  });
});
```

> Falls `@testing-library/react`/`jest-dom` noch nicht eingerichtet sind: pruefen, ob `lib/can.test.ts` ein Setup nutzt. Wenn kein DOM-Test-Setup existiert, in diesem Step zusaetzlich `@testing-library/react`, `@testing-library/jest-dom` als devDependencies ergaenzen, `vite.config`/`vitest`-`environment: "jsdom"` und eine Setup-Datei mit `import "@testing-library/jest-dom"` einrichten. (Erst `frontend/package.json` + vorhandene Vitest-Config lesen.)

- [ ] **Step 7: Verifikation**

Run: `docker compose run --rm --no-deps --entrypoint sh frontend -c "npm ci && npx tsc --noEmit && npm run test"`
Expected: tsc ohne Fehler, alle Tests gruen (inkl. neuer `ui.test.tsx` und bestehender `can.test.ts`).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/index.css frontend/src/components/ frontend/package.json frontend/package-lock.json
git commit -m "Frontend: Design-System-Fundament (Tokens, UI-Komponenten, Glass-Shell)"
```

---

## Task 2: Login + Erst-Admin-Setup (A2)

**Files:**
- Modify: `frontend/src/lib/apiClient.ts`
- Modify: `frontend/src/lib/auth.tsx`
- Modify: `frontend/src/features/auth/LoginPage.tsx`
- Create: `frontend/src/features/auth/SetupPage.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/features/auth/SetupPage.test.tsx`

- [ ] **Step 1: `registerFirstAdminRequest` in `apiClient.ts` ergaenzen**

Direkt nach `loginRequest` einfuegen (mirror davon):

```ts
export async function registerFirstAdminRequest(
  email: string,
  password: string,
  full_name: string,
): Promise<string> {
  const res = await fetch(`${BASE}/auth/register-first-admin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name }),
  });
  if (!res.ok) throw await parseError(res);
  const data = (await res.json()) as { access_token: string };
  accessToken = data.access_token;
  return data.access_token;
}
```

- [ ] **Step 2: `registerFirstAdmin` in `auth.tsx` ergaenzen**

In `AuthState`-Interface ergaenzen:
```ts
  registerFirstAdmin: (email: string, password: string, fullName: string) => Promise<void>;
```
Import ergaenzen: `registerFirstAdminRequest` aus `./apiClient`.
Callback (analog `login`) im Provider:
```ts
  const registerFirstAdmin = useCallback(
    async (email: string, password: string, fullName: string) => {
      await registerFirstAdminRequest(email, password, fullName);
      await loadMe();
    },
    [loadMe],
  );
```
`useMemo`-Value erweitern: `{ user, loading, login, logout, registerFirstAdmin }` (und Dependency-Array ergaenzen).

- [ ] **Step 3: `SetupPage.tsx` schreiben**

`register-first-admin`: 201 -> eingeloggt -> Redirect `/dashboard`. 409 `already_initialized` -> Toast + Redirect `/login`. Bestehende Form-/Button-Patterns nutzen, Double-Submit-Guard.

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../lib/apiClient";
import { useAuth } from "../../lib/auth";
import { toast } from "../../lib/toast";
import { Card, CardInner, ErrorBanner } from "../../components/ui";

export function SetupPage() {
  const { registerFirstAdmin } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await registerFirstAdmin(email, password, fullName);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "already_initialized") {
        toast.error("System ist bereits eingerichtet. Bitte anmelden.");
        navigate("/login", { replace: true });
        return;
      }
      setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="login-wrap">
      <Card className="login-card">
        <CardInner>
          <div className="brand" style={{ padding: "0 0 18px" }}>
            <div className="logo">D</div>
            <div>
              <strong>DMS einrichten</strong>
              <span>Erst-Administrator anlegen</span>
            </div>
          </div>
          <ErrorBanner error={error} />
          <form onSubmit={onSubmit}>
            <label>
              <span>Voller Name</span>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            </label>
            <label>
              <span>E-Mail</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
            <label>
              <span>Passwort</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </label>
            <button className="btn primary" type="submit" disabled={pending} style={{ width: "100%" }}>
              {pending ? "Wird eingerichtet …" : "Administrator anlegen"}
            </button>
          </form>
        </CardInner>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: `LoginPage.tsx` neu stylen**

Bestehende Datei lesen, Logik (Felder, `login`, Error, Redirect, `pending`) erhalten. Markup auf `login-wrap` + `Card`/`CardInner` + Gradient-Brand umstellen (analog SetupPage, aber ohne Setup-Link — Spec-Entscheidung). Keine neuen Calls.

- [ ] **Step 5: Route `/setup` in `App.tsx` ergaenzen**

Import `SetupPage`. Neben `/login` (oeffentlich, ausserhalb `RequireAuth`):
```tsx
<Route path="/setup" element={<SetupPage />} />
```

- [ ] **Step 6: Test `SetupPage.test.tsx`**

Testet 409-Handling (Toast + Redirect Login) und Erfolg (Redirect Dashboard). `useAuth`/`toast`/`react-router` mocken.

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/apiClient";

const navigate = vi.fn();
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
const toastError = vi.fn();
vi.mock("../../lib/toast", () => ({ toast: { error: toastError, success: vi.fn() } }));
const registerFirstAdmin = vi.fn();
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ registerFirstAdmin }) }));

import { SetupPage } from "./SetupPage";

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText("Voller Name"), "Admin");
  await userEvent.type(screen.getByLabelText("E-Mail"), "a@b.de");
  await userEvent.type(screen.getByLabelText("Passwort"), "passwort1");
  await userEvent.click(screen.getByRole("button"));
}

describe("SetupPage", () => {
  it("leitet bei Erfolg aufs Dashboard", async () => {
    registerFirstAdmin.mockResolvedValueOnce(undefined);
    render(<SetupPage />);
    await fillAndSubmit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/dashboard", { replace: true }));
  });

  it("bei 409 Toast + Redirect Login", async () => {
    registerFirstAdmin.mockRejectedValueOnce(
      new ApiError(409, "already_initialized", "Es existiert bereits ein Benutzer."),
    );
    render(<SetupPage />);
    await fillAndSubmit();
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(navigate).toHaveBeenCalledWith("/login", { replace: true });
  });
});
```

> `label`-Zuordnung: Die Labels umschliessen die Inputs (implizite Zuordnung), daher findet `getByLabelText` sie ueber den `<span>`-Text. Falls nicht: `aria-label` an den Inputs ergaenzen.

- [ ] **Step 7: Verifikation** (Befehl wie Task 1, Step 7).

- [ ] **Step 8: Commit**
```bash
git add frontend/src/lib/apiClient.ts frontend/src/lib/auth.tsx frontend/src/features/auth/ frontend/src/App.tsx
git commit -m "Frontend: Login neu gestylt + Erst-Admin-Setup-Flow (/setup, A2)"
```

---

## Task 3: Dashboard

**Files:**
- Modify: `frontend/src/features/dashboard/DashboardPage.tsx`
- Test: `frontend/src/features/dashboard/retention.test.ts` (Restlaufzeit-Helfer, hier eingefuehrt — siehe Task 5; falls bereits in Task 5 erstellt, hier ueberspringen)

**Vorgehen:** Bestehende `DashboardPage.tsx` lesen, Datenquellen beibehalten. Verfuegbare Hooks: `useProjects(status)` (liefert `Page<ProjectOut>` mit `.total`), `useRecentDocuments()` (liefert `RecentDocument[]`). Fuer den Aktivitaets-Feed (nur Superadmin): `useAuditLogs({}, 6, 0)` aus `features/admin/hooks`.

- [ ] **Step 1: Layout aufbauen**
  - `PageHead` (eyebrow "Dashboard / Uebersicht", Titel, optional Aktion „Datei hochladen" -> Link/Scroll zu Quick-Upload oder zur Projektseite).
  - KPI-Grid mit `KpiCard`:
    - „Aktive Projekte" = `useProjects("active").data?.total ?? 0`.
    - „Archivierte Projekte" = `useProjects("archived").data?.total ?? 0`.
    - „Zuletzt bearbeitet" = `recentDocuments.length` (oder weglassen, wenn nur 2 KPIs gewuenscht — mind. 2 echte KPIs zeigen).
    - KEINE „Dokumente gesamt"/„Versionen gesamt"-KPIs (kein Endpoint).
  - „Zuletzt bearbeitet"-Liste aus `useRecentDocuments()` — pro Eintrag Titel (Link `/documents/:id`), Projektname, `StatusBadge` fuer `latest_processing_status`, `formatDate(updated_at)`.
  - Projekt-Grid (`card-grid` + `tile`): aktive Projekte als Karten (Name -> Link `/projects/:id`, `StatusBadge`, `my_role`), OHNE Dokument-/Versionszaehler.
  - Quick-Upload-Card: Projekt-Select (aus `useProjects("active")`) + `UploadZone`; nutzt `useUploadDocument(selectedProjectId)` aus `features/projects/hooks`. Upload nur aktiv wenn Projekt gewaehlt. Nach Erfolg Toast (Hook erledigt Invalidation).
  - Aktivitaets-Feed nur bei `user.is_superadmin`: `useAuditLogs({}, 6, 0)` -> Liste (action + `formatDate(created_at)`).

- [ ] **Step 2: Leere-/Lade-/Fehlerzustaende** via `Loading`/`Empty`/`ErrorBanner` abdecken (`isPending`).

- [ ] **Step 3: Verifikation** (Befehl wie Task 1).

- [ ] **Step 4: Commit**
```bash
git add frontend/src/features/dashboard/
git commit -m "Frontend: Dashboard im neuen Look (echte Daten, Quick-Upload, Superadmin-Feed)"
```

---

## Task 4: Projekte + Projektdetail

**Files:**
- Modify: `frontend/src/features/projects/ProjectsPage.tsx`
- Modify: `frontend/src/features/projects/ProjectDetailPage.tsx`

**Vorgehen:** Beide Seiten lesen, ALLE Hooks/Logik erhalten (`useProjects`, `useCreateProject`, `useUpdateProject`, `useDeleteProject`, `useRestoreProject`, `useProject`, `useAddMember`, `useRemoveMember`, `useChangeMemberRole`, `useDocuments`, `useUploadDocument`, `useRetentionRules`, `useUpsertRetentionRule`, `useDeleteRetentionRule`, `useRestoreDocumentInProject`). `confirmDialog` fuer destruktive Aktionen. Permissions via `roleAtLeast`/`useAuth` wie bisher.

- [ ] **Step 1: ProjectsPage** — `PageHead` + „Neues Projekt"-Aktion (oeffnet bestehende Anlegen-UI), Status-Filter (`toolbar`), Projekt-`card-grid` mit `tile` (Name->Link, `StatusBadge`, Beschreibung, `my_role`), `Pagination`. Anlegen-Form in einer `Card`.
- [ ] **Step 2: ProjectDetailPage** — Header via `PageHead` (Projektname, `StatusBadge`, Aktionen archivieren/loeschen/restore mit `confirmDialog`). Danach in `Card`s: Mitglieder-Verwaltung (Tabelle + Rolle aendern/entfernen + Mitglied hinzufuegen), Retention-Regeln-Verwaltung (Liste + put/delete), Dokumentenliste (`useDocuments`, paginiert, `placeholderData` ist in Hook) als Tabelle oder `doc-row`-Liste mit Status-Badge + Link, plus `UploadZone`/Upload-Card mit `useUploadDocument` (Progress via vorhandenem Mechanismus).
- [ ] **Step 3: Verifikation** (Befehl wie Task 1).
- [ ] **Step 4: Commit**
```bash
git add frontend/src/features/projects/
git commit -m "Frontend: Projekte + Projektdetail im neuen Look"
```

---

## Task 5: Dokumentdetail

**Files:**
- Modify: `frontend/src/features/documents/DocumentDetailPage.tsx`
- Create: `frontend/src/features/documents/retention.ts` (Restlaufzeit-Helfer)
- Test: `frontend/src/features/documents/retention.test.ts`

**Vorgehen:** Seite lesen. Hooks erhalten: `useDocument`, `useVersions`, `useUploadVersion`, `usePatchDocument`, `useDeleteDocument`, `useReprocessVersion`, `useRestoreDocument`; sowie `useSetRetention`, `useSetLegalHold` aus `features/admin/hooks` (Superadmin). Downloads via `downloadAuthed`/`triggerDownload`.

- [ ] **Step 1: Restlaufzeit-Helfer + Test (TDD)**

`retention.ts`:
```ts
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
```

`retention.test.ts`:
```ts
import { describe, expect, it } from "vitest";

import { retentionProgress } from "./retention";

describe("retentionProgress", () => {
  it("liefert null ohne retention_until", () => {
    expect(retentionProgress("2026-01-01", null)).toBeNull();
  });
  it("rechnet 50% in der Mitte", () => {
    const r = retentionProgress("2026-01-01T00:00:00Z", "2026-01-11T00:00:00Z", new Date("2026-01-06T00:00:00Z"));
    expect(r?.percent).toBeCloseTo(50, 0);
    expect(r?.daysLeft).toBe(5);
  });
  it("kappt bei abgelaufener Aufbewahrung auf 100% / 0 Tage", () => {
    const r = retentionProgress("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", new Date("2026-02-01T00:00:00Z"));
    expect(r?.percent).toBe(100);
    expect(r?.daysLeft).toBe(0);
  });
});
```
Run: `docker compose run --rm --no-deps --entrypoint sh frontend -c "npm run test -- retention"` — zuerst FAIL (Datei fehlt), dann nach Anlegen PASS.

- [ ] **Step 2: Layout** — Topbar/Breadcrumb + `PageHead` (Dokumenttitel, `StatusBadge`, Versionsanzahl-Badge, Aktionen: aktuelle Version herunterladen, neue Version (Fokus Upload-Card), Legal-Hold-Toggle [superadmin]). `overview-grid`: Hero-Card (Datei-Icon aus MIME/Endung, Kategorie/Erstellt/aktuelle Datei/Groesse via `formatBytes`) + Compliance-Card (Aufbewahrung-Datum-Input -> `useSetRetention`, `ProgressBar` aus `retentionProgress`, Legal-Hold-Button -> `useSetLegalHold`; beide nur Superadmin sichtbar/aktiv).
- [ ] **Step 3: Tabs** (`Tabs`-Komponente) mit `Versionen` und `Metadaten`:
  - Versionen: `useVersions` -> Versionsliste (`version-card`-Stil), pro Version Download (`downloadAuthed`/Version-Endpoint) + Reprocess (`useReprocessVersion`), aktuelle Version markiert.
  - Metadaten: Form (Titel/Kategorie/Beschreibung/Status) -> `usePatchDocument`; Soft-Delete/Restore -> `useDeleteDocument`/`useRestoreDocument` mit `confirmDialog`.
  - Neue-Version-Upload: `UploadZone` -> `useUploadVersion`.
- [ ] **Step 4: Verifikation** (Befehl wie Task 1).
- [ ] **Step 5: Commit**
```bash
git add frontend/src/features/documents/
git commit -m "Frontend: Dokumentdetail im neuen Look (Hero, Compliance-Card, Tabs)"
```

---

## Task 6: Account + Admin/Benutzer

**Files:**
- Modify: `frontend/src/features/account/AccountPage.tsx`
- Modify: `frontend/src/features/admin/UsersPage.tsx`

**Vorgehen:** Seiten lesen, Hooks erhalten (`useChangePassword`; `useAdminUsers`, `useCreateUser`, `useAnonymizeUser`, `useCreateExport`, `useExports`).

- [ ] **Step 1: AccountPage** — `PageHead` + Passwort-aendern-`Card` (Felder/Logik unveraendert, `pending`-Guard).
- [ ] **Step 2: UsersPage** — `PageHead` + „Benutzer anlegen"-`Card`, Benutzer-Tabelle (E-Mail, Name, Rolle/Status-Badges, anonymisiert-Flag), Aktionen anonymisieren (`confirmDialog`) + Export anfordern, Export-Liste (`useExports`, Auto-Refetch bleibt im Hook) mit Download, `Pagination`.
- [ ] **Step 3: Verifikation** (Befehl wie Task 1).
- [ ] **Step 4: Commit**
```bash
git add frontend/src/features/account/ frontend/src/features/admin/UsersPage.tsx
git commit -m "Frontend: Konto + Admin/Benutzer im neuen Look"
```

---

## Task 7: Audit-Log + Metadaten (A3)

**Files:**
- Modify: `frontend/src/features/admin/AuditLogsPage.tsx`

**Vorgehen:** Seite lesen. Hook `useAuditLogs(filters, limit, offset)` und `AUDIT_ACTIONS` (aus `types/api`) erhalten. `AuditLogOut.metadata` ist bereits im Typ vorhanden.

- [ ] **Step 1: Layout** — `PageHead`, Filter-`toolbar` (action-Select aus `AUDIT_ACTIONS`, Projekt-/Actor-Filter wie bisher), Tabelle (Zeit, Aktion, Entity, Actor, IP), `Pagination`.
- [ ] **Step 2: Metadaten ausklappbar (A3)** — pro Zeile ein Aufklapp-Button (`icon-btn`); im aufgeklappten Zustand zusaetzliche Zeile mit `metadata` als formatiertes JSON:
```tsx
{expandedId === log.id && (
  <tr>
    <td colSpan={COLSPAN}>
      {log.metadata && Object.keys(log.metadata).length > 0 ? (
        <pre className="audit-meta-pre mono">{JSON.stringify(log.metadata, null, 2)}</pre>
      ) : (
        <span className="muted">Keine Details</span>
      )}
    </td>
  </tr>
)}
```
`expandedId` als lokaler State (`useState<string | null>`), Toggle pro Zeile. `COLSPAN` = Anzahl Spalten.
- [ ] **Step 3: Verifikation** (Befehl wie Task 1).
- [ ] **Step 4: Commit**
```bash
git add frontend/src/features/admin/AuditLogsPage.tsx
git commit -m "Frontend: Audit-Log im neuen Look + aufklappbare Metadaten (A3)"
```

---

## Task 8: Compliance-Center + Key-Rotation (A1)

**Files:**
- Modify: `frontend/src/features/admin/hooks.ts`
- Modify: `frontend/src/features/admin/CompliancePage.tsx`

**Vorgehen:** Seite lesen. Bestehende Compliance-Funktionen (Legal-Hold/Retention/Exporte/Anonymisierung — soweit auf dieser Seite vorhanden) erhalten.

- [ ] **Step 1: Hook `useRewrapStorage` in `admin/hooks.ts`**
```ts
export function useRewrapStorage() {
  return useMutation({
    mutationFn: () => api.post<void>("/admin/storage/rewrap"),
    onSuccess: () => {
      toast.success("Schluessel-Rotation gestartet. Sie laeuft im Hintergrund.");
    },
  });
}
```
- [ ] **Step 2: Card „Speicher-Verschluesselung"** in `CompliancePage.tsx` ergaenzen:
```tsx
const rewrap = useRewrapStorage();

async function onRewrap() {
  const ok = await confirmDialog({
    title: "Schluessel-Rotation starten?",
    body: "Re-wrappt alle Blob-DEKs auf die aktive Schluessel-Version. Laeuft asynchron im Hintergrund.",
    confirmLabel: "Rotation starten",
  });
  if (ok) rewrap.mutate();
}
```
JSX (in einer `Card`/`CardInner` mit `SectionHead`):
```tsx
<Card>
  <CardInner>
    <SectionHead
      title="Speicher-Verschluesselung"
      hint="At-rest-Verschluesselung der Blobs (AES-256-GCM). Nach Schlusselwechsel die DEKs neu wrappen."
    />
    <button className="btn primary" onClick={onRewrap} disabled={rewrap.isPending}>
      {rewrap.isPending ? "Wird gestartet …" : "Schluessel-Rotation starten"}
    </button>
  </CardInner>
</Card>
```
> `confirmDialog`-Optionsfelder vor Nutzung an `ConfirmOptions` in `lib/confirm.tsx` abgleichen (exakte Property-Namen: ggf. `message` statt `body`, `confirmText` statt `confirmLabel`). Datei lesen und anpassen.
- [ ] **Step 3: Verifikation** (Befehl wie Task 1).
- [ ] **Step 4: Commit**
```bash
git add frontend/src/features/admin/hooks.ts frontend/src/features/admin/CompliancePage.tsx
git commit -m "Frontend: Compliance-Center im neuen Look + Key-Rotation-Button (A1)"
```

---

## Abschluss

- [ ] Gesamt-Verifikation: `docker compose run --rm --no-deps --entrypoint sh frontend -c "npm ci && npx tsc --noEmit && npm run test"` gruen.
- [ ] Manueller Smoke-Test (optional, Playwright/Browser): Login, Dashboard, Projekt anlegen, Dokument hochladen, Dokumentdetail-Tabs, Audit-Metadaten ausklappen, Key-Rotation (Superadmin), `/setup` (409-Pfad).
- [ ] CLAUDE.md Aenderungshistorie um die Frontend-Ueberarbeitung ergaenzen (eigener kleiner Commit).
- [ ] Branch-Abschluss via `superpowers:finishing-a-development-branch` (PR/Merge-Entscheidung).

## Self-Review-Notiz

- Spec-Abdeckung: Tokens/Shell/Komponenten (Task 1), Login+Setup/A2 (Task 2), Dashboard (Task 3), Projekte/Projektdetail inkl. Retention-Rules+Mitglieder (Task 4), Dokumentdetail inkl. Compliance-Card (Task 5), Account+Users (Task 6), Audit+Metadaten/A3 (Task 7), Compliance+Rewrap/A1 (Task 8). Alle Spec-Punkte abgedeckt.
- Offene Verifikationen, die der ausfuehrende Agent JEWEILS per Datei-Read bestaetigen muss: exakte `ConfirmOptions`-Feldnamen (`lib/confirm.tsx`), vorhandenes Vitest-DOM-Setup (`package.json`/vitest-config), exakte Upload-Progress-Nutzung in den Bestands-Hooks. Diese sind als Hinweise in den jeweiligen Steps vermerkt.
