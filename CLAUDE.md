# CLAUDE.md — DSGVO-Dokumentenmanagementsystem (DMS)

Projekt-Leitfaden für Claude. Diese Datei hat Vorrang vor Default-Verhalten. **Globale
User-Regeln** (`~/.claude/CLAUDE.md`) gelten zusätzlich: Antworten auf Deutsch, keine
Emojis, kurz und direkt, keine abschließenden Zusammenfassungen, keine Co-Authored-By-Zeilen.

---

## 1. Was ist das?

DSGVO-orientiertes Dokumentenmanagementsystem (MVP) für ein kleines IT-Startup:
verwaltet interne Verträge, Kundenverträge und mit Kunden geteilte Projekt-Dokumente.

**Zugriffsmodell: Single-Tenant.** Eine Organisation betreibt die Instanz. Jedes Projekt =
Kundenengagement/interner Bereich. Kunden werden als Projekt-Mitglieder (`viewer`/`editor`)
eingeladen. Multi-Tenancy (mehrere Mandanten-Orgs) ist **bewusst nicht** im MVP.

---

## 2. Architektur & Stack

**uv-Workspace-Monorepo.** Eine Schema-Quelle, von Backend und Worker geteilt.

```
packages/dms_core/   # EINE Quelle für Models/DB/Settings/Storage/Security/Audit/Celery
  dms_core/
    models/          # SQLModel-Tabellen (user, project, document, audit, compliance, export)
    security/        # passwords (argon2id), tokens (JWT + Refresh-Hash)
    storage/         # StorageBackend-Protocol + LocalFilesystemBackend
    config.py        # Pydantic-Settings (EINE Konfig-Quelle, env-basiert)
    db.py            # Engine + get_session (FastAPI-Dependency)
    audit.py         # write_audit_log (append-only)
    maintenance.py   # Wartungs-Kernlogik (Session+Storage als Param → testbar)
    enums.py         # VARCHAR+CHECK-Enums (AuditAction, DocumentStatus, ...)
    celery_app.py    # Celery-Konfiguration

backend/             # FastAPI (REST JSON), sync SQLModel/SQLAlchemy 2.x
  app/
    api/routes_*.py  # Controller — dünn, kein Business-Code
    services/*.py    # Business-Logik
    schemas/*.py     # Pydantic-DTOs (Request/Response)
    core/            # deps (Auth/DI), errors, ratelimit, cookies, tasks, project_access

worker/              # Celery + Redis (Textextraktion, Wartung); dünne Wrapper um dms_core
  worker/tasks/      # processing.py, maintenance.py

frontend/            # React 18 + TS + Vite + TanStack Query 5 + react-router-dom 6
  src/
    features/<domain>/{Page.tsx, hooks.ts}   # Feature-Slices
    components/      # ui.tsx, AppLayout, Pagination, RequireAuth
    lib/             # auth, apiClient, can, format, toast, confirm, download

alembic/             # Migrationen (PostgreSQL)
```

**Versionen:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0/SQLModel, Pydantic v2,
Celery 5, Redis · React 18.3, react-router-dom 6.28, @tanstack/react-query 5.62,
Vite 6, TypeScript 5.7, Vitest 2 · PostgreSQL 16. Deployment: Docker Compose (5 Services).

**Schlüsselentscheidungen (vom User bestätigt — nicht ohne Rückfrage ändern):**
- Auth: Access-Token in-memory (Frontend) + Refresh als httpOnly+Secure+SameSite=Strict-Cookie, Single-Origin.
- User-Löschung (Art. 17): deaktivieren + PII anonymisieren, KEIN Hard-Delete (User-FKs RESTRICT/SET NULL).
- Verarbeitung: nur Textextraktion (pypdf/python-docx), keine Bild-Preview/OCR im MVP.
- Storage: providerneutrales `StorageBackend`-Protocol (save/open/delete, opake Keys, KEINE presigned-URL/S3-Annahme). MVP=LocalFilesystemBackend; Prod=Hetzner Storage Box. KEIN S3.
- Argon2id (argon2-cffi), PyJWT, python-magic, VARCHAR+CHECK statt native Enums, UUIDv4-PKs.
- Audit-Log append-only via DB-Trigger (UPDATE/DELETE/TRUNCATE blockiert, nur ip_address→NULL erlaubt).
- Celery: visibility_timeout > längster Task, task_ignore_result, Status nur in DB.

---

## 3. Befehle (alle via `make`, laufen in Docker Compose)

| Befehl | Zweck |
|--------|-------|
| `make up` / `make down` | Stack starten/stoppen |
| `make migrate` | `alembic upgrade head` |
| `make revision m="..."` | Autogenerate-Migration (als Host-User, s.u.) |
| `make check-migrations` | `alembic check` — Models ↔ Migrationen synchron? (braucht DB auf head) |
| `make seed` | Demo-Daten |
| `make test` | Backend-Tests (`-w /app/backend pytest`, separate DB `dms_test`) |
| `make test-worker` | Worker-Tests |
| `make lint` / `make fmt` | Ruff Lint/Format |

**Frontend-Verifikation** (node_modules liegt im Container-Volume, lokal leer):
`docker compose run --rm --no-deps --entrypoint sh frontend -c "npx tsc --noEmit && npm run test"`

**Vor jedem Commit gilt als grün:** Backend-Tests, Worker-Tests, `alembic check`
(nach `make migrate`), Frontend `tsc --noEmit` + vitest. Niemals „fertig" melden, solange
eines rot ist. Niemals `--no-verify`, niemals Tests skippen um grün zu faken.

**Betriebshinweise:**
- `make revision` muss als Host-User laufen (`--user "$(id -u):$(id -g)"`), sonst PermissionError auf gemountetem `alembic/versions`.
- `check-migrations` braucht die DB zuerst auf head → erst `make migrate`, dann `make check-migrations`.
- Test-DB `dms_test`: Schema via `SQLModel.metadata.create_all` (NICHT Migrationen). Wer eine
  DB-Extension/Trigger in einer Migration einführt, muss sie auch im `conftest.py`-Engine-Fixture
  bereitstellen (z.B. `CREATE EXTENSION IF NOT EXISTS pg_trgm`), sonst scheitert `create_all`.
- Seed-Logins (dev): admin@dms.local / `adminpass123`, editor@demo.local & viewer@demo.local / `demopass123`.
  Passwörter überschreibbar via `SEED_ADMIN_PASSWORD`/`SEED_DEMO_PASSWORD`; in `production` sind sie Pflicht.

---

## 4. Konventionen (verbindlich)

### Schichtentrennung (Backend) — gerichtet, nicht durchbrechen
```
routes_*.py (Controller)  →  services/*.py (Business)  →  dms_core/models (ORM)
```
- **Controller bleiben dünn**: Auth/DI via Dependency, Validierung via Schema, dann Service-Call. KEINE Business-Logik in Routes.
- **Services kennen kein FastAPI**: keine `Request`/`Response`-Objekte in Services. Cross-Cutting-Werte (z.B. Client-IP) werden als `str | None`-Parameter durchgereicht, extrahiert in `core/deps.get_client_ip`.
- **`dms_core` ist Single Source of Truth** und importiert NIE von `backend`/`worker` (keine Kreis-Abhängigkeit).
- **Commit liegt in der Route**, nicht im Service. Services nutzen `session.flush()`, nicht `session.commit()`.
- **Default = kein Zugriff** (Art. 25): Endpunkte fordern explizit eine Auth-Dependency an (`CurrentUser`, `SuperadminDep`, `require_project_role`).
- **User-IDs immer aus Session/JWT** (`CurrentUser`), nie aus Request-Body/Parametern.

### Datenbank / SQLAlchemy
- 2.0-Style: `session.exec(select(...))` + `.scalars()/.all()/.first()/.one()`. KEIN Legacy `session.query()`, kein `Query.get()` (stattdessen `session.get()`).
- N+1 vermeiden: Aggregate (`func.count()`, `GROUP BY`) oder `DISTINCT ON`/`selectinload` statt Schleifen-Queries.
- Listen-Endpunkte IMMER paginiert mit Limit-Cap. Gemeinsamer Helfer: `schemas/common.paginate(session, stmt, *, limit, offset)`.
- Migrationen: eine Migration pro logischer Änderung, `down_revision` = aktueller head, Stil bestehender Migrationen 1:1 kopieren. Jeder per Migration erzeugte Index MUSS im Model (`__table_args__`/`Field(index=True)`) gespiegelt sein, sonst meldet `alembic check` Drift.
- Audit-Log ist append-only (DB-Trigger). Nur `ip_address`→NULL ist erlaubt (IP-Retention). Audit-Mutationen niemals umgehen.
- Audit-Reihenfolge: ein Audit-Event erst schreiben/committen, NACHDEM der zugehörige Seiteneffekt garantiert erfolgreich ist. Z.B. beim Download den Blob-Stream (`open_stream`) öffnen, BEVOR `document.downloaded` + `commit` laufen — sonst steht ein „erledigt"-Eintrag im append-only Log, obwohl die Aktion (StorageError/Quarantäne) fehlschlug.

### Sicherheit (Default-sicher)
- Secrets nur via Env/`.env` (ist in `.gitignore`, NIE committen — nur `.env.example`). Keine Credentials/Keys im Code.
- In `production` erzwingt `config._enforce_prod_secrets` echte Secrets (kein `change-me`-Default für `jwt_secret`/`database_url`) UND `refresh_cookie_secure=True` (HTTPS-Pflicht — langlebiges Refresh-Cookie nie über HTTP).
- Dokumentinhalte werden minimiert: `extracted_text` wird NICHT unverschlüsselt in der DB persistiert (die Extraktion validiert nur die Lesbarkeit). Reaktivierung nur mit Volltextsuche, dann als `tsvector` (Tokens statt Klartext).
- Rate-Limiting auf allen Auth-/CPU-teuren Endpunkten (`enforce_rate_limit`). Fehlende Client-IP = fail-closed (429), nur Redis-Ausfall ist fail-open.
- `X-Forwarded-For` nur auswerten wenn `settings.trust_proxy_headers` (hinter vertrauenswürdigem Proxy) — sonst IP-Spoofing/Rate-Limit-Bypass. Proxy zusätzlich via uvicorn `--proxy-headers --forwarded-allow-ips` absichern.
- Eingaben an Systemgrenzen validieren (Pydantic-Längen, MIME via python-magic NICHT via Extension, Storage-Keys opak/nicht erratbar, Dateinamen sanitizen).
- Fehlertexte an den Client sind generisch — keine internen Pfade/Stacktraces (auch nicht in `processing_error` o.ä.). Technische Details server-seitig loggen.
- DSGVO-Datenminimierung im Audit-Log: keine Klartext-PII in `metadata` (E-Mails hashen, Beschreibungen sowie Dokument-`title` nicht im Klartext loggen — Titel kann personenbezogen sein). `entity_id` reicht zur Zuordnung; im `metadata_updated`-Stil nur die geänderten Feld-Namen (`changed.keys()`) statt der Werte loggen.
- **At-rest-Verschluesselung der Blobs (G-1):** Bei gesetztem Keyring (`STORAGE_ENCRYPTION_KEYS` + `STORAGE_ACTIVE_KEY_ID`) wraps `EncryptedStorageBackend` das `LocalFilesystemBackend` transparent. Algorithmus: AES-256-GCM in 64-KB-Frames mit Envelope-Encryption (pro-Blob-DEK, Header traegt Key-Version-ID). `file_hash` bleibt SHA-256 ueber den Klartext. In `production` sind beide Variablen Pflicht (`_enforce_prod_secrets`); leerer Keyring = Verschluesselung aus (nur Dev). Bestehende unverschluesselte Blobs einmalig mit `scripts/reencrypt_blobs.py` migrieren (idempotent). **Rotations-Runbook:** (1) `make gen-storage-key` — neue Version mit hoeherer ID in `STORAGE_ENCRYPTION_KEYS` ergaenzen, `STORAGE_ACTIVE_KEY_ID` hochsetzen, Dienste neu starten; (2) Superadmin `POST /api/admin/storage/rewrap` ausloesen (re-wraps nur den kleinen DEK pro Blob — kein Re-Encrypt der Datei); (3) nach Abschluss alte Key-Version aus dem Ring entfernen. DB-at-rest separat ueber verschluesseltes Volume (LUKS/Hetzner-Volume) fuer Postgres-Datenverzeichnis + Storage-Mount absichern.

### Retention-Policy (G-3)
- `documents.retention_until` = gesetzliche **Mindest-Aufbewahrung** (Date). Wird beim Upload aus `settings.default_retention_days` (Default: 365) befüllt, pro Dokument ueberschreibbar. Solange `retention_until` in der Zukunft liegt, sind weder manuelles Loeschen noch Auto-Expire erlaubt — auch `legal_hold` nicht umgehbar.
- `retention_rules(project_id, category, max_days)` = **Maximal-Aufbewahrung** pro Projekt/Kategorie. `category=NULL` = Projekt-Default (gilt fuer alle Kategorien ohne eigene Regel). Kategorie-Regel gewinnt immer — auch wenn `max_days=NULL` (= Exempt: kein Auto-Delete fuer diese Kategorie). Kein Treffer → kein Auto-Expire (Default: aus). Unique-Constraint `(project_id, category)` NULLS NOT DISTINCT.
- **Aus-Schalter:** Projekt-Default-Regel loeschen (`DELETE` bei `category=NULL`) deaktiviert Auto-Expire projektweise. Kategorie schuetzen: Regel mit `max_days=NULL` setzen.
- Beat-Task `auto_soft_delete_expired` laeuft taeglich 02:30 UTC (vor dem 03:00-Hard-Purge): setzt abgelaufene aktive Dokumente auf `status=deleted` + `purge_after = now + purge_grace_days`. Hard-Purge danach durch bestehenden Wartungs-Task.
- API: `PUT/GET/DELETE /api/projects/{id}/retention-rules` (Projekt-Admin). Audit-Actions: `compliance.retention_set`, `compliance.retention_removed`, `document.auto_expired`.

### Worker / Skalierung
- Große Dateien (bis 50 MB) NICHT komplett in den RAM. Streamen: SHA chunked, MIME nur `HEAD_BYTES`, Extraktion über seekbares Tempfile.
- Wartungs-Kernlogik gehört in `dms_core/maintenance.py` (Session+Storage als Param → testbar); Worker-Tasks sind dünne Wrapper. Tasks idempotent (`acks_late` + Status-Check), Enqueue strikt NACH Commit.
- Bulk-Wartung (purge/cleanup) in Batches (`PURGE_BATCH`), keine unbounded `UPDATE`/Iterationen (Lock-/Timeout-Risiko).
- DB-Pool (`db.py`) auf FastAPI-Threadpool-Größe abstimmen (`db_pool_size`/`db_max_overflow` in config).

### Frontend (React + TanStack Query)
- KEIN `window.confirm`/`alert`. Für destruktive Aktionen `confirmDialog({...})` aus `lib/confirm` (imperativ, `Promise<boolean>`, barrierefrei). Toaster: `lib/toast`.
- Geteilte Helfer wiederverwenden statt duplizieren: `lib/download.triggerDownload`, `lib/format` (downloadAuthed/formatBytes/formatDate), `components/ui` (StatusBadge/ErrorBanner/Loading/Empty).
- Async-Aktionen: Loading-/Disabled-States, Double-Submit-Guards (`isPending`), klare deutsche Fehlermeldungen. `mutateAsync` IMMER in `try/catch` kapseln (sonst unhandled Promise rejection); Fehler werden via `ErrorBanner`/`mutation.error` angezeigt, Follow-up-State-Reset nur im Erfolgsfall.
- TanStack Query v5: `isPending` (nicht `isLoading`) für „noch keine Daten"; paginierte Queries mit `placeholderData: keepPreviousData` (kein Flackern beim Blättern); Mutationen invalidieren betroffene Query-Keys in `onSuccess`/`onSettled`. ID-abhängige Queries IMMER mit `enabled: !!id` (nicht mit leerer ID feuern — Route-Params können via `useParams`-Default `""` sein).
- Lokaler State aus Props, der nach Server-Update stale wird → via `key={…updated_at}` remounten statt manuell syncen.
- Geschützte Routen über `RequireAuth`/`RequireSuperadmin` (beachten `loading`-State, nicht vorschnell redirecten).
- Typen konsistent: `ProjectStatus` vs. `DocumentStatus` nicht vermischen. Backend-Enums (z.B. `AUDIT_ACTIONS`) im Frontend vollständig spiegeln.
- Sprache/Stil: deutsche UI-Texte/Kommentare im Stil der umgebenden Datei (teils oe/ae statt Umlaute — am Kontext orientieren).

### Code-Stil allgemein
- Ruff (E,F,I,UP,B,C4,SIM,TID), line-length 100, mypy. Imports am Dateianfang (isort-Reihenfolge), keine ungenutzten Imports.
- Keine unnötigen Refactorings, die nichts mit der Aufgabe zu tun haben. API-Response-Shapes nicht stillschweigend ändern (Frontend hängt dran).

---

## 5. Workflow

- Git-Operationen IMMER direkt mit `git` (keine Skills/Plugins für commit/push/PR). GitHub via `gh` CLI.
- Kein direkter Commit auf `main`/`dev` — Fix-/Feature-Branch nutzen. Commit nur auf explizite Aufforderung.
- Bei Library-/Framework-/API-Fragen zuerst `context7` MCP (Versions-Drift vermeiden), nicht aus dem Gedächtnis.
- Review/Fix-Workflow: `repo-review` (Multi-Agent-Audit) → `fix-findings` (parallelisierte Umsetzung + Verifikation).

---

## 6. Änderungshistorie (wesentliche Schritte)

- **MVP M0–M7:** Vollständiges DMS (Auth, Projekte, Dokumente+Versionen, Compliance/Audit, Export, Wartung).
- **Runde 2:** Frontend-Verbesserungen (Pagination, Suche, Upload-Progress, Toasts, Breadcrumbs) + Endpoints `POST /admin/users`, `PATCH /projects/{id}/members/{user_id}`.
- **Runde 3:** Projekt-Status-Verwaltung (active/archived/deleted + soft-delete/restore), Version-Reprocess, Passwort ändern, Dashboard „zuletzt bearbeitet".
- **G-1 At-rest-Verschluesselung 2026-06-15** (Branch `fix/g3-g1-umsetzung`): `EncryptedStorageBackend` (AES-256-GCM, 64-KB-Frames, Envelope-Encryption), Key-Rotation via `POST /api/admin/storage/rewrap` + Celery-Task `rewrap_blobs`, Migrations-Script `scripts/reencrypt_blobs.py`, Prod-Enforcement in `_enforce_prod_secrets`.
- **G-3 Retention-Policy 2026-06-15** (Branch `fix/g3-g1-umsetzung`): Mindest- (`retention_until`) + Maximal-Aufbewahrung (`retention_rules`), Beat-Task `auto_soft_delete_expired`, API `PUT/GET/DELETE /api/projects/{id}/retention-rules`, Audit-Actions.
- **Review-/Fix-Pass 2026-06-15** (Branch `fix/review-findings-2026-06-15`): Multi-Agent-Repo-Review (Security/Quality/Architektur/Modernization), anschließend 2 Critical + 9 High + 13 Medium + 7 Low gefixt. Schwerpunkte: Proxy-Trust/Rate-Limit-Härtung (IP-Spoofing, fail-closed, register-Limit, atomarer Redis-Zähler), Seed-/Prod-Secret-Schutz, CSP/HSTS-Header, DB-Connection-Pool, Worker-Streaming statt RAM-Vollladung, `add_version`-Race-Lock, N+1/Version-Lade-Fixes via `DISTINCT ON`, Such-/Audit-Indizes (`pg_trgm` GIN + `actor_user_id` + Composite), DSGVO-Audit-PII-Minimierung, generischer `paginate`-Helfer; Frontend: `confirmDialog` statt `window.confirm`, `lib/download`-Dedup, `keepPreviousData`/`isPending`, Upload-Abort, `ProjectStatus`-Typ, vollständige `AUDIT_ACTIONS`. **Deferred** (eigene Tasks, zu groß/API-brechend): Keyset-Pagination für Audit-`COUNT(*)`, `tsvector`-Volltextsuche auf `extracted_text`, Multi-Tenancy, Audit-Trigger-`created_at`-Guard (App-Check existiert), SFTP-Storage-Backend.
- **Review-/Fix-Pass 2026-06-16** (Branch `review/full-codebase-2026-06-16`): Multi-Agent-Repo-Review (Security/Quality/Modernization/Funktionalität via Playwright), anschließend Security+Quality-Findings gefixt (5 parallele Agents, disjunkte Scopes): 2 High-Sec + 5 Med-Sec + 2 Low-Sec sowie 1 (Quality-)High `session.commit()`-im-Service-Verstoß, weitere High/Med/Low Quality. Schwerpunkte Backend: `soft_delete_document` blockt jetzt bei aktiver `retention_until` (G-3-Durchsetzung), ILIKE-Suche escaped Metazeichen (`_escape_like` + `escape="\\"`), `require_document_role`/`require_version_access` prüfen Projekt-`status==deleted` (nicht nur `deleted_at`), `?status=deleted`-Listing nur für Projekt-Admin, `change-password` rate-limited, `export.error` generisch (kein Exception-Leak), `rewrap_blobs`/`build_export_payload`-Audit gebatcht statt RAM-Vollladung, `_normalize_email`→`schemas/common.normalize_email`, getypte Security-Header-Middleware, Seed-Passwort maskiert, `TRUST_PROXY_HEADERS` in `.env.example`+`docker-compose.prod.yml` (uvicorn `--proxy-headers --forwarded-allow-ips`). Frontend: `mutateAsync`-try/catch (DocumentDetail/ProjectDetail), Projekt-Löschung cancelt/removed `["project",id]`-Query (kein 404-Refetch), `Tabs` mit `type="button"` + a11y-Panel-Verknüpfung (`idBase`/`tabId`/`tabPanelId`), `PAGE_SIZE` zentral in `lib/constants.ts`, `LoginPage` wartet `loading` ab, Compliance-Erfolgsfeedback nur noch via Toast (kein doppelter SuccessBanner). Zusätzlich (Rest-Findings): **EmailStr-Validierung** an Eingabe-DTOs (`RegisterFirstAdminIn`/`AdminUserCreate`/`MemberAddIn` via `pydantic[email]`/`email-validator`; `normalize_email` als `mode="before"`-Vornormalisierung; `LoginIn` bewusst nur normalisiert für einheitliche 401) und **Autofill-Härtung** der Benutzer-Anlage (`autoComplete="off"`/`"new-password"`). Verifikation grün: Backend 66, Worker 6, Frontend tsc + 18 vitest, `alembic check` (keine Schema-Änderung), `ruff check`. **Ruff-Setup-Befund** (separat, nicht in diesem Pass): `ruff` weder im Container installiert noch mise-Version gepinnt → `make lint`/`make fmt` brechen aktuell; zusätzlich Format-Drift in 40 Dateien (`ruff format` nie konsistent gelaufen) — als eigener Commit offen. **Konventionen ergänzt:** ILIKE-/LIKE-Suchen IMMER mit escaptem User-Input (`escape="\\"`); Dokument/Version-Zugriff muss den Projekt-Status mitprüfen; geteilte Frontend-Konstanten in `lib/constants.ts`.
- **Review-/Fix-Pass 2026-06-20** (Branch `fix/review-findings-2026-06-20`): Technische Findings-Liste validiert (mehrere als ungültig/non-issue verworfen: `compliance.document_purged` war bereits im Frontend-`AUDIT_ACTIONS`; HSTS-Dev-Header betrifft nur das Prod-nginx-Image; `normalize_email` lässt `a@@b.de` durch, aber `EmailStr` validiert real), anschließend 8 Findings via 7 parallele Agents (disjunkte Datei-Scopes) gefixt. Backend: `build_export_payload` lädt jetzt auch `documents`/`versions` gebatcht (OFFSET-Schleife wie `audit_events`, vorher RAM-Vollladung); Download-Audit (`download_current`/`download_version`) baut die `StreamingResponse` VOR `write_audit_log`+`commit` auf → kein „downloaded"-Eintrag mehr bei `StorageError`/Quarantäne; `title`-Klartext-PII aus Purge- (`maintenance.py`) und Upload-Audit-`metadata` entfernt (`entity_id` reicht; `document_metadata_updated` loggt ohnehin nur `changed.keys()`); `update_metadata` erzwingt Status-Enum (`active`/`archived`, kein `deleted`) als Defense-in-Depth; `LoginIn` nutzt nicht-raisenden `_normalize_login_email` (nur strip/lower) → ungültige Login-Mail endet einheitlich als 401 statt 422 (`mode="before"` wäre kein Fix, `normalize_email` raised in jedem Modus). Frontend: `useDocument`/`useVersions` mit `enabled: !!documentId`-Guard (Muster wie `useProject`; `DocumentDetailPage` defaultet `documentId=""`), `RetentionRulesCard.onAdd`+`Members.onAdd` mit `mutateAsync`-try/catch (übersehen im 2026-06-16-Pass). Test: 3 neue PATCH-`/documents/{id}`-Status-Lifecycle-Tests. **Deferred** (Low/eigene Tasks): Orphan-Blob-Cleanup bei DB-Fehler nach Storage-Save, `change-password` zusätzlich user-basiert raten, `--forwarded-allow-ips` auf nginx-Subnetz einengen, SetupPage-`loading`-Guard. Verifikation grün: Backend 69, Worker 6, Frontend tsc + 18 vitest, `alembic check` (keine Schema-Änderung), `ruff check`/`ruff format --check`. **Ruff läuft jetzt** via `mise install` (Pin `ruff=0.8.4` in `.mise.toml`, einmalig `mise trust` + `mise install`) — der Ruff-Setup-Befund aus dem 2026-06-16-Pass ist mit Commit `d0f9213` erledigt.
- **Frontend-Ueberarbeitung 2026-06-15** (Branch `frontend/ueberarbeitung`, nur Frontend, Backend unverändert): Komplettes UI-Redesign im Dark-SaaS-Look. Neues Token-Set + Komponentenklassen in `index.css` (keine neue Dependency, kein Tailwind), ausgebautes Design-System in `components/ui.tsx` (Card/KpiCard/Badge+Dot/Tabs/PageHead/SectionHead/ProgressBar/UploadZone), Glass-Sidebar-Shell mit Sektionen Workspace/Compliance/Admin + mobilem Drawer (`AppLayout`), `components/icons.tsx`. Alle Seiten neu aufgebaut unter Erhalt aller Hooks/Permissions/API-Shapes. DOM-Test-Infra ergänzt (Vitest jsdom + Testing Library). Drei zuvor ungenutzte Backend-Features integriert ("A-Lücken"): **A1** Key-Rotation-Button auf der Compliance-Seite (`useRewrapStorage` → `POST /api/admin/storage/rewrap`, confirmDialog + Toast); **A2** Erst-Admin-Setup unter `/setup` (`register-first-admin`, 409-`already_initialized`-Handling, KEIN Login-Link); **A3** Audit-Log-Metadaten pro Eintrag aufklappbar als JSON. Bewusst weggelassen (kein Backend): globale Suche/Dokumentenliste, Favoriten, Speicher-Quota, Aggregat-KPIs, Dokument-Vorschau, per-Dokument-Audit. Spec/Plan unter `docs/superpowers/{specs,plans}/2026-06-15-frontend-ueberarbeitung*`.
