# DMS — DSGVO-orientiertes Dokumentenmanagementsystem (MVP)

![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Ein schlankes, praktisches DMS für ein kleines IT-Startup: Verwaltung interner
Verträge, Kundenverträge und mit Kunden geteilter Projekt-Dokumente. Zugriff ist
strikt **projektgebunden** (Privacy by Default, Art. 25) — Kunden werden gezielt als
Projekt-Mitglieder (viewer/editor) zu genau den Dokumenten eingeladen, die geteilt
werden sollen.

## Tech-Stack

- **Frontend:** React + TypeScript + Vite, TanStack Query, zentraler `apiClient`
- **Backend:** Python + FastAPI (REST JSON), SQLModel/SQLAlchemy 2.x (sync)
- **Worker:** Celery (Redis-Broker) — Dateiverarbeitung, Retention, Export, Cleanups
- **DB:** PostgreSQL · **Migrationen:** Alembic · **Queue/Cache:** Redis
- **Auth:** JWT Access (in-memory) + Refresh (httpOnly-Cookie), Argon2id
- **Storage:** providerneutrale Abstraktion — lokal im MVP, später Hetzner Storage Box
- **Container:** Docker Compose

## Architektur

uv-Workspace-Monorepo mit gemeinsamem Paket `dms_core` (Models, DB, Settings,
Storage, Security, Audit, Celery, Compliance-Logik) — **eine** Schema-/Migrations-
Quelle, geteilt von Backend und Worker (verhindert Schema-Drift).

```
packages/dms_core/   gemeinsamer Kern (Modelle, DB, Security, Storage, Audit, maintenance)
backend/             FastAPI (api/, services/, schemas/, core/)
worker/              Celery-Tasks (processing, maintenance)
alembic/             Migrationen
frontend/            React + TS + Vite
docker-compose.yml   Dev-Stack (5 Services)
docker-compose.prod.yml  Produktions-Override (nginx single-origin, migrate-Step)
```

## Quickstart (Entwicklung)

Voraussetzungen: Docker + Docker Compose.

```bash
cp .env.example .env          # Werte für lokale Entwicklung sind voreingestellt
make up                       # baut & startet postgres, redis, backend, worker, frontend
make migrate                  # Datenbankschema anlegen (alembic upgrade head)
make seed                     # Demo-Daten + Login-Accounts
```

- Frontend: http://localhost:5173
- API-Health: http://localhost:5173/api/health (über Vite-Proxy) bzw. http://localhost:8000/api/health
- API-Docs (OpenAPI): http://localhost:8000/docs

**Seed-Logins:**

| Rolle  | E-Mail                | Passwort      |
|--------|-----------------------|---------------|
| Admin  | admin@dms.local       | adminpass123  |
| Editor | editor@demo.local     | demopass123   |
| Viewer | viewer@demo.local     | demopass123   |

Nützliche Make-Targets: `make logs`, `make ps`, `make test`, `make test-worker`,
`make revision m="..."`, `make check-migrations`, `make down`.

## Acceptance-Kriterien — manueller Durchlauf

1. **Erst-Admin:** `POST /api/auth/register-first-admin` (nur möglich, solange kein User existiert) → Login.
2. **Projekt anlegen** (`/projects`) — Ersteller wird Owner.
3. **Mitglied hinzufügen** per E-Mail mit Rolle (owner/admin → editor/viewer).
4. **Editor lädt Dokument hoch** → Version 1; der Worker verarbeitet (sha256, MIME, Textextraktion) → Status `ready`.
5. **Zweiter Upload** → Version 2; Versionshistorie zeigt beide, alte Datei bleibt erhalten.
6. **Viewer** kann herunterladen, aber nicht hochladen/bearbeiten (403).
7. **Nutzer außerhalb des Projekts** erhält 404 (Existenz wird nicht verraten).
8. **Löschen** = nur Soft-Delete (Status `deleted`, wiederherstellbar); Restore setzt `purge_after` zurück.
9. **Legal Hold** (Admin/Compliance) blockiert den Purge bedingungslos.
10. **Audit-Log** zeichnet sensible Aktionen auf (append-only).
11. **Admin** erstellt einen User-Datenexport (JSON, asynchron, ablaufend).
12. **Purge-Job** löscht nur Dokumente mit erreichter Grace-Period und **ohne** Legal Hold/laufende Retention.

## DSGVO-Bezug (technische Umsetzung)

- **Art. 5 / 25 – Datenminimierung, Privacy by Default:** projektgebundener Zugriff, schlanke List-DTOs (kein Volltext in Listen), Default = kein Zugriff.
- **Art. 5 – Speicherbegrenzung:** `retention_until`, Soft-Delete + `purge_after`-Grace-Period, Worker-Purge; Audit-IP-Schwärzung nach 90 Tagen.
- **Art. 5(2) – Rechenschaftspflicht:** Audit-Log ist **append-only** (DB-Trigger blockiert UPDATE/DELETE; nur IP-Schwärzung erlaubt).
- **Art. 15/20 – Auskunft/Übertragbarkeit:** Admin-Export aller personenbezogenen Daten als JSON (kurzlebig, abgesichert, auditiert).
- **Art. 17 – Löschung:** User-Anonymisierung (Konto deaktiviert, PII entfernt, Tokens widerrufen, Mitgliedschaften entfernt); Dokument-Purge löscht alle Blobs.
- **Art. 30 – VVT:** Tabelle `processing_activities` (Seed).
- **Art. 32 – Sicherheit:** Argon2id, JWT mit Rotation, httpOnly-Cookie, server-seitige Download-Autorisierung (keine offenen Datei-URLs), Magic-Byte-Validierung, Upload-Limits, Rate-Limiting, Security-Header.

### Technisch-organisatorische Maßnahmen (Betreiber-Pflichten)

Zwei Punkte werden bewusst auf Infrastrukturebene gelöst und **müssen beim Deployment dokumentiert/aktiviert** werden:

- **Verschlüsselung at-rest:** Volume-/Disk-Verschlüsselung (z. B. LUKS oder providerseitig) für DB- und Storage-Volumes ist Voraussetzung — im MVP keine App-seitige Blob-Verschlüsselung.
- **Backups & Wiederherstellbarkeit (Art. 32):** regelmäßige DB-Backups einrichten. Aufbewahrungs-Statement festhalten, z. B. „Löschungen wirken auf Backups nach max. N Tagen Rotation" — wichtig für die Konsistenz mit Art. 17.

## Storage & Hetzner Storage Box

Die `StorageBackend`-Abstraktion (`packages/dms_core/dms_core/storage/`) ist
**providerneutral und S3-frei**: nur `save/open/delete` mit opaken Keys, keine
presigned-URL-Annahme. Downloads laufen **immer** server-seitig durch FastAPI.

- **MVP:** `LocalFilesystemBackend` (Docker-Volume, geteilt Backend ↔ Worker).
- **Produktion:** Hetzner Storage Box als gemounteter Pfad (`STORAGE_ROOT` auf den
  CIFS/SFTP-Mount setzen) — kein Codeänderung nötig. Optional ist ein direktes
  SFTP-Backend (paramiko) additiv nachrüstbar; S3/MinIO bleibt ebenfalls möglich.
- **S3 ist nicht nötig** — die Storage Box reicht für ein Single-Server-DMS.

## Migrationen

```bash
make revision m="beschreibung"   # autogenerate (läuft als Host-User, schreibt nach alembic/versions)
make migrate                     # anwenden
make check-migrations            # prüft, ob Modelle und Migrationen synchron sind (alembic check)
```

## Tests

```bash
make test          # Backend (pytest, separate Postgres-Test-DB, transaktionales Rollback)
make test-worker   # Worker (Verarbeitungs-Pipeline)
cd frontend && npm test   # Frontend-Smoke (vitest)
```

Abgedeckt u. a.: Auth + Token-Rotation, Projekt-Zugriffskontrolle, Upload/Versionierung,
Download-Autorisierung, Audit-Logging, **legal_hold blockt Purge**, Retention/Grace-Period,
User-Export, Anonymisierung, Audit-IP-Schwärzung.

## Produktion

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --build postgres redis migrate backend worker web
```

- `web` (nginx) liefert das gebaute Frontend **single-origin** aus und proxyt `/api` → Backend.
- Migrationen laufen als separater `migrate`-Schritt (Backend startet mit `RUN_MIGRATIONS=false`).
- In `.env` für Produktion zwingend `ENVIRONMENT=production` und ein starkes `JWT_SECRET` setzen
  (die App verweigert sonst den Start), sowie `REFRESH_COOKIE_SECURE=true` hinter TLS.
- Den Dev-`frontend`-Service in Produktion nicht starten.
