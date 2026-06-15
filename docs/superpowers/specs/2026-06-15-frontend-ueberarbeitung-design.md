# Frontend-Ueberarbeitung DMS — Design-Spec

**Datum:** 2026-06-15
**Branch:** `frontend/ueberarbeitung`
**Scope:** Nur Frontend. Backend bleibt unveraendert, API-Response-Shapes werden nicht gebrochen.

---

## 1. Ziel

Komplett neues, modernes UI im Dark-SaaS-Look (feste Sidebar mit Sektionen
Workspace/Compliance/Admin, Gradient-Akzente, Glassmorphism-Cards, Status-Badges
mit farbcodierten Dots, KPI-Karten, Tabs, Drag&Drop-Upload-Zonen, runde Radien,
weiche Schatten). Nordstern sind zwei Prototypen
(`docs/superpowers/prototypes/dashboard.html`, `document-detail.html`) — visuelle
Inspiration, KEINE 1:1-Vorlage. Bestehender Funktionsumfang bleibt vollstaendig
erhalten. Zusaetzlich drei bisher nicht im Frontend nutzbare Backend-Features
("A-Luecken") integrieren.

## 2. Leitentscheidungen (vom User bestaetigt)

1. **Unbacked Prototyp-Elemente weglassen.** Keine globale Suche, keine globale
   Dokumentenliste, keine Favoriten, keine Speicher-Quota, keine "Risiken"-Aggregate
   — diese haben kein Backend. Sidebar/Widgets werden strikt auf vorhandene
   Endpoints gemappt. Keine toten Links, keine Fake-Zahlen.
2. **Styling: globales CSS erneuern + Komponentenklassen.** `index.css` mit neuem
   Dark-SaaS-Token-Set ueberarbeiten, dazu wiederverwendbare Komponentenklassen.
   Keine neue Build-Dependency (kein Tailwind/CSS-in-JS). Konsistent mit Bestand.
3. **Sidebar-Mapping:** Workspace (Dashboard, Projekte) | Compliance (superadmin:
   Audit-Log, Compliance-Center) | Admin (superadmin: Benutzer) | Konto unten
   (Name/E-Mail, Konto/Passwort, Abmelden). Bestehende Routen 1:1, kein Routen-Umbau.
4. **Erst-Admin-Setup:** nur ueber `/setup`-Route erreichbar, KEIN Link auf der
   Login-Seite. `register-first-admin`: 201 -> eingeloggt; 409 `already_initialized`
   -> Toast + Redirect zu Login.
5. **Schlankes echtes Dashboard:** KPIs aus billigen Daten (aktive/archivierte
   Projekte via `Page.total`), Projekt-Grid ohne Mini-Zaehler, "Zuletzt bearbeitet"
   (`recent-documents`), Quick-Upload, Aktivitaets-Feed NUR fuer Superadmin (Audit).
   Keine N+1-Requests, keine Fake-Zahlen.
6. **Dokumentdetail-Tabs:** nur Versionen + Metadaten (beides voll gebackt).
   Keine Vorschau (kein Preview/OCR im MVP), kein Audit-Tab (nicht entity-genau
   filterbar), keine Berechtigungen am Dokument (Mitglieder gehoeren auf die
   Projektseite). Hero-Card + Compliance-Card (Aufbewahrung/Legal-Hold/Restlaufzeit)
   bleiben wie im Prototyp.

## 3. Backend-Bestand (Grundlage, unveraendert)

Vorhandene Endpoints (relevant fuers Frontend):

- Auth: `register-first-admin` (201 / 409 `already_initialized`), `login`, `refresh`,
  `change-password`, `logout`.
- Me: `GET /me`, `GET /me/recent-documents`.
- Projekte: list (`Page[ProjectOut]`), create, get detail (`ProjectDetailOut` inkl.
  members), patch, delete (soft), restore; Mitglieder add/patch/delete;
  Retention-Rules put/get/delete.
- Dokumente: list pro Projekt (`Page[DocumentListItem]`), upload, get detail, patch,
  delete (soft), restore, versions list, add version, download (doc + version),
  reprocess version.
- Admin (superadmin): users list/create/delete(anonymize), audit-logs list
  (Filter: action/project_id/actor_user_id), exports list/download,
  `POST /storage/rewrap` (202), set-retention, legal-hold.

**Nicht vorhanden** (daher nicht im UI): globale Suche, globale Dokumentenliste,
Aggregat-Statistiken, Dokument-/Versionszaehler in der Projektliste, per-Dokument-
Audit-Filter, Datei-Vorschau.

`AuditLogOut.metadata` ist bereits Teil der API-Response (gemappt aus `metadata_`)
und im Frontend-Typ vorhanden — wird heute nur nicht gerendert (A3).

## 4. Architektur der Aenderung

Rein im Frontend, in drei Bereichen:

- `frontend/src/index.css` — neues Token-Set + Komponentenklassen + Shell-Layout.
- `frontend/src/components/` — `AppLayout` (Shell) + `ui.tsx` (Design-System).
- `frontend/src/features/*/Page.tsx` — Seiten neu aufgebaut; `hooks.ts` werden
  wiederverwendet, nur um wenige neue Hooks ergaenzt.

**Unveraendert:** `lib/apiClient`, `lib/auth`, `lib/can`, `lib/download`,
`lib/format`, `lib/confirm` (API), `lib/toast` (API), alle Query-Keys und
Response-Shapes, `App.tsx`-Routenstruktur (plus neue `/setup`-Route).

### 4.1 Token-Set (`index.css`)

Aus beiden Prototypen vereinheitlicht:

- Hintergrund `#080d19` mit zwei radialen Gradient-Glows (primary + success).
- Surfaces als Glass-Gradient `linear-gradient(180deg, rgba(255,255,255,.06),
  rgba(255,255,255,.03))`, Border `rgba(255,255,255,.09)`, Border-strong
  `rgba(255,255,255,.16)`.
- Farben: primary `#6d7cff` (Verlauf nach `#8b5cff`), success `#35d07f`,
  warning `#ffbd4a`, danger `#ff6174`, je mit `-soft`-Variante (Badge-Hintergruende).
- Text `#eef4ff`, muted `#99a8c0`, muted-2 `#687891`.
- Radien `--radius-xl:22px / lg:18px / md:14px / sm:10px`, Schatten
  `0 26px 90px rgba(0,0,0,.42)`, Font `Inter, ui-sans-serif, system-ui, ...`
  (kein externer Font-Load, System-Fallback).

### 4.2 Shell (`AppLayout`)

Sticky Glass-Sidebar: Brand mit Gradient-Logo, Nav-Sektionen (Workspace /
Compliance / Admin via `NavLink`, aktiver Zustand), Account-Card unten mit
Avatar-Initialen + Abmelden. Superadmin-Sektionen nur bei `user.is_superadmin`.
Mobil (`max-width: 1180px`): Sidebar als Off-Canvas-Drawer mit Burger-Button in
einer schlanken Topbar; Schliessen via Overlay/ESC.

### 4.3 Design-System (`components/ui.tsx`)

Bestehende Exports (`StatusBadge`, `ErrorBanner`, `SuccessBanner`, `Empty`,
`Loading`) bleiben kompatibel, werden optisch erneuert. Neu:

- `Card` / `CardInner`, `SectionHead` (Titel + Hint + Slot), `PageHead`
  (Eyebrow / Titel / Actions).
- `KpiCard` (Icon, Wert, Label, optional Trend-Badge).
- `Badge` mit farbcodiertem Dot; Varianten success/warning/danger/primary/neutral.
  `StatusBadge` mappt Status -> Variante: ready/active -> success;
  processing/uploaded -> warning; failed/quarantined/deleted -> danger;
  archived -> neutral.
- `Tabs` (controlled, `value`/`onChange`).
- Button-Varianten via Klassen (`.btn .primary/.ghost/.danger`, `.icon-btn`).
- `UploadZone` (Drag&Drop, kapselt vorhandene Upload-Logik + Progress, Abort).
- `ProgressBar` (Restlaufzeit + Upload).

Globale Form-Elemente (`input/select/textarea`) zentral neu gestylt; `confirm`/
`toast`/`modal` an Glass-Look angepasst (API unveraendert).

## 5. Seiten

| Route | Inhalt |
|-------|--------|
| `/login` | Zentrierte Glass-Card, Gradient-Brand. |
| `/setup` | Oeffentlich, kein Login-Link. Formular email/password/full_name -> `register-first-admin`. 201 -> Token setzen + Redirect Dashboard; 409 -> Toast + Redirect Login. |
| `/dashboard` | PageHead; KPI-Grid (aktive/archivierte Projekte via `Page.total`); Projekt-Grid (ohne Mini-Zaehler); "Zuletzt bearbeitet" (`recent-documents`); Quick-Upload-Card (Projekt-Select + Datei); Aktivitaets-Feed nur Superadmin (Audit-Logs). |
| `/projects` | PageHead + Anlegen; Projekt-Karten-Grid; Status-Filter; Pagination. |
| `/projects/:id` | Header mit Status-Badge + Aktionen (archivieren/loeschen/restore); Mitglieder-Verwaltung (Rollen); Retention-Regeln-Verwaltung; Dokumentenliste mit Upload (Progress). |
| `/documents/:id` | Hero-Card (Datei-Icon, Kategorie/Erstellt/Datei/Groesse) + Compliance-Card (Aufbewahrung-Datum, Restlaufzeit-Progress, Legal-Hold-Toggle [superadmin]); Tabs Versionen (Liste mit Download/Reprocess + Neue-Version-Upload) und Metadaten (Titel/Kategorie/Beschreibung/Status, Soft-Delete/Restore). |
| `/account` | Passwort-aendern-Card. |
| `/admin/users` | Tabelle; Benutzer anlegen; anonymisieren; Export anfordern/herunterladen. |
| `/admin/audit-logs` | Filter (action/Projekt/Actor) + Tabelle; jede Zeile aufklappbar -> `metadata` als formatiertes JSON (A3). |
| `/admin/compliance` | Legal-Hold/Retention/Exporte/Anonymisierung + neue Card "Speicher-Verschluesselung" mit Key-Rotation-Button (A1). |

## 6. A-Features

- **A1 Key-Rotation:** neuer Hook `useRewrapStorage` -> `confirmDialog` ->
  `POST /api/admin/storage/rewrap` -> Toast "Schluessel-Rotation gestartet"
  (202, asynchron). Card auf der Compliance-Seite.
- **A2 First-Admin:** neuer Hook `useRegisterFirstAdmin`, `/setup`-Route,
  409-`already_initialized`-Handling (Toast + Redirect Login).
- **A3 Audit-Metadaten:** Audit-Zeile expandierbar; `metadata` als eingeruecktes
  JSON (mono). Bei `null` Hinweis "keine Details".

## 7. Build-Reihenfolge (subagent-driven, Review zwischen Tasks)

1. Tokens/`index.css` + Shell (`AppLayout`) + Shared Components (`ui.tsx`).
2. Login + `/setup` (A2).
3. Dashboard.
4. Projekte + Projektdetail.
5. Dokumentdetail.
6. Account + Admin/Benutzer.
7. Audit-Log + Metadaten (A3).
8. Compliance + Key-Rotation (A1).

## 8. Testing & Verifikation

- TDD/vitest wo sinnvoll: Badge-Status-Mapping, Restlaufzeit-Berechnung
  (retention_until -> Prozent), Setup-409-Handling, `metadata`-Render bei null.
- Bestehende Tests (`lib/can.test.ts`) gruen halten.
- Pro Task gruen, sonst kein Commit:
  `docker compose run --rm --no-deps --entrypoint sh frontend -c "npm ci && npx tsc --noEmit && npm run test"`
- Niemals `--no-verify`, keine Tests skippen.

## 9. Nicht im Scope

Globale Suche, globale Dokumentenliste, Favoriten, Speicher-Quota, Aggregat-
Statistiken, Datei-Vorschau/OCR, per-Dokument-Audit, Multi-Tenancy, jegliche
Backend-Aenderung.
