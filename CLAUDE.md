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

### Sicherheit (Default-sicher)
- Secrets nur via Env/`.env` (ist in `.gitignore`, NIE committen — nur `.env.example`). Keine Credentials/Keys im Code.
- In `production` erzwingt `config._enforce_prod_secrets` echte Secrets (kein `change-me`-Default für `jwt_secret`/`database_url`) UND `refresh_cookie_secure=True` (HTTPS-Pflicht — langlebiges Refresh-Cookie nie über HTTP).
- Dokumentinhalte werden minimiert: `extracted_text` wird NICHT unverschlüsselt in der DB persistiert (die Extraktion validiert nur die Lesbarkeit). Reaktivierung nur mit Volltextsuche, dann als `tsvector` (Tokens statt Klartext).
- Rate-Limiting auf allen Auth-/CPU-teuren Endpunkten (`enforce_rate_limit`). Fehlende Client-IP = fail-closed (429), nur Redis-Ausfall ist fail-open.
- `X-Forwarded-For` nur auswerten wenn `settings.trust_proxy_headers` (hinter vertrauenswürdigem Proxy) — sonst IP-Spoofing/Rate-Limit-Bypass. Proxy zusätzlich via uvicorn `--proxy-headers --forwarded-allow-ips` absichern.
- Eingaben an Systemgrenzen validieren (Pydantic-Längen, MIME via python-magic NICHT via Extension, Storage-Keys opak/nicht erratbar, Dateinamen sanitizen).
- Fehlertexte an den Client sind generisch — keine internen Pfade/Stacktraces (auch nicht in `processing_error` o.ä.). Technische Details server-seitig loggen.
- DSGVO-Datenminimierung im Audit-Log: keine Klartext-PII in `metadata` (E-Mails hashen, Beschreibungen nicht im Klartext loggen). `entity_id` reicht zur Zuordnung.

### Worker / Skalierung
- Große Dateien (bis 50 MB) NICHT komplett in den RAM. Streamen: SHA chunked, MIME nur `HEAD_BYTES`, Extraktion über seekbares Tempfile.
- Wartungs-Kernlogik gehört in `dms_core/maintenance.py` (Session+Storage als Param → testbar); Worker-Tasks sind dünne Wrapper. Tasks idempotent (`acks_late` + Status-Check), Enqueue strikt NACH Commit.
- Bulk-Wartung (purge/cleanup) in Batches (`PURGE_BATCH`), keine unbounded `UPDATE`/Iterationen (Lock-/Timeout-Risiko).
- DB-Pool (`db.py`) auf FastAPI-Threadpool-Größe abstimmen (`db_pool_size`/`db_max_overflow` in config).

### Frontend (React + TanStack Query)
- KEIN `window.confirm`/`alert`. Für destruktive Aktionen `confirmDialog({...})` aus `lib/confirm` (imperativ, `Promise<boolean>`, barrierefrei). Toaster: `lib/toast`.
- Geteilte Helfer wiederverwenden statt duplizieren: `lib/download.triggerDownload`, `lib/format` (downloadAuthed/formatBytes/formatDate), `components/ui` (StatusBadge/ErrorBanner/Loading/Empty).
- Async-Aktionen: Loading-/Disabled-States, Double-Submit-Guards (`isPending`), klare deutsche Fehlermeldungen.
- TanStack Query v5: `isPending` (nicht `isLoading`) für „noch keine Daten"; paginierte Queries mit `placeholderData: keepPreviousData` (kein Flackern beim Blättern); Mutationen invalidieren betroffene Query-Keys in `onSuccess`/`onSettled`.
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
- **Review-/Fix-Pass 2026-06-15** (Branch `fix/review-findings-2026-06-15`): Multi-Agent-Repo-Review (Security/Quality/Architektur/Modernization), anschließend 2 Critical + 9 High + 13 Medium + 7 Low gefixt. Schwerpunkte: Proxy-Trust/Rate-Limit-Härtung (IP-Spoofing, fail-closed, register-Limit, atomarer Redis-Zähler), Seed-/Prod-Secret-Schutz, CSP/HSTS-Header, DB-Connection-Pool, Worker-Streaming statt RAM-Vollladung, `add_version`-Race-Lock, N+1/Version-Lade-Fixes via `DISTINCT ON`, Such-/Audit-Indizes (`pg_trgm` GIN + `actor_user_id` + Composite), DSGVO-Audit-PII-Minimierung, generischer `paginate`-Helfer; Frontend: `confirmDialog` statt `window.confirm`, `lib/download`-Dedup, `keepPreviousData`/`isPending`, Upload-Abort, `ProjectStatus`-Typ, vollständige `AUDIT_ACTIONS`. **Deferred** (eigene Tasks, zu groß/API-brechend): Keyset-Pagination für Audit-`COUNT(*)`, `tsvector`-Volltextsuche auf `extracted_text`, Multi-Tenancy, Audit-Trigger-`created_at`-Guard (App-Check existiert), SFTP-Storage-Backend.
