# G-3: Retention-Policy & Auto-Purge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dokumente bekommen eine angewandte Aufbewahrungs-Policy: eine Default-**Mindest**-Aufbewahrung beim Upload und eine optionale, pro Projekt konfigurierbare **Maximal**-Aufbewahrung, nach der nicht mehr benötigte Dokumente automatisch entfernt werden (DSGVO Art. 5(1e) Speicherbegrenzung).

**Architecture:** Zwei klar getrennte Konzepte. (1) `retention_until` bleibt die rechtliche **Mindest**-Aufbewahrung (blockt Löschung) — wird beim Upload mit `default_retention_days` vorbelegt. (2) Neues `Project.retention_max_days` (nullable, `None` = aus) ist die **Maximal**-Frist; ein Beat-gesteuerter Maintenance-Task soft-deletet abgelaufene Dokumente, die bestehende Purge-Logik räumt sie nach der Grace-Period endgültig ab. Beide respektieren `legal_hold` und die Mindest-Aufbewahrung.

**Tech Stack:** FastAPI, sync SQLModel/SQLAlchemy 2.0, Alembic, Celery-Beat, PostgreSQL (`make_interval`), pytest (`backend/tests` mit DB-Fixture).

**Invarianten:** Response-Shapes nur additiv erweitern; `purge_deleted_documents` (bestehend) bleibt die einzige Stelle, die Blobs/Zeilen hart löscht; Auto-Soft-Delete fasst nur `status=active`-Dokumente an.

---

## File Structure

- **Modify** `packages/dms_core/dms_core/enums.py` — neue `AuditAction.document_auto_expired` (action ist plain `String`, **keine** CHECK-Migration nötig).
- **Modify** `packages/dms_core/dms_core/models/project.py` — Spalte `retention_max_days: int | None`.
- **Create** Alembic-Migration — Spalte `projects.retention_max_days` + Backfill `documents.retention_until`.
- **Modify** `backend/app/services/document_service.py` — Default-Mindest-Retention beim Upload.
- **Modify** `packages/dms_core/dms_core/maintenance.py` — `auto_soft_delete_expired(...)`.
- **Modify** `packages/dms_core/dms_core/celery_app.py` + `worker/worker/tasks/maintenance.py` — Task + Beat-Schedule.
- **Modify** `backend/app/schemas/project.py`, `backend/app/services/project_service.py`, `backend/app/api/routes_projects.py` — `retention_max_days` über die Projekt-API setzbar.
- **Modify** `frontend/src/types/api.ts`, `frontend/src/features/projects/*`, `frontend/src/features/admin/AuditLogsPage.tsx` — UI-Feld + neue Audit-Aktion (optional, Task 7).

---

### Task 1: Audit-Aktion `document.auto_expired`

**Files:**
- Modify: `packages/dms_core/dms_core/enums.py:77` (nach `document_purged`)

- [ ] **Step 1: Enum-Wert ergänzen**

In `AuditAction` nach `document_purged = "document.purged"` einfügen:

```python
    document_auto_expired = "document.auto_expired"
```

- [ ] **Step 2: Import-Smoke**

Run: `docker compose run --rm --no-deps backend python -c "from dms_core.enums import AuditAction; print(AuditAction.document_auto_expired.value)"`
Expected: `document.auto_expired`

- [ ] **Step 3: Commit**

```bash
git add packages/dms_core/dms_core/enums.py
git commit -m "G-3: Audit-Aktion document.auto_expired"
```

---

### Task 2: `Project.retention_max_days` Modell + Migration

**Files:**
- Modify: `packages/dms_core/dms_core/models/project.py:39` (nach `updated_at`)
- Create: `alembic/versions/<rev>_retention_policy.py`

- [ ] **Step 1: Modell-Spalte ergänzen**

In `Project` nach `updated_at` einfügen:

```python
    # Maximal-Aufbewahrung (Art. 5(1e)). None = Auto-Purge fuer dieses Projekt AUS.
    retention_max_days: int | None = Field(
        default=None, sa_column=Column(Integer(), nullable=True)
    )
```

`Integer` zum bestehenden `from sqlalchemy import ...`-Block in `project.py` hinzufügen.

- [ ] **Step 2: Migration erzeugen (als Host-User)**

Run: `docker compose run --rm --user "$(id -u):$(id -g)" backend alembic revision --autogenerate -m "retention policy"`
Expected: neue Datei in `alembic/versions/` mit `op.add_column("projects", sa.Column("retention_max_days", sa.Integer(), nullable=True))`.

- [ ] **Step 3: Backfill in die Migration eintragen**

In der erzeugten Migration **am Ende von `upgrade()`** ergänzen (Default-Mindest-Retention für Bestand, abgeleitet aus `created_at`):

```python
    from dms_core.config import settings

    days = settings.default_retention_days
    if days > 0:
        op.execute(
            sa.text(
                "UPDATE documents "
                "SET retention_until = (created_at AT TIME ZONE 'UTC')::date "
                "    + (:days || ' days')::interval "
                "WHERE retention_until IS NULL"
            ).bindparams(days=days)
        )
```

`downgrade()` muss `retention_max_days` wieder droppen (autogenerate erzeugt das). Der Backfill ist Daten-only und braucht kein Downgrade.

- [ ] **Step 4: Migration anwenden + Drift-Check**

Run: `make migrate && make check-migrations`
Expected: Upgrade läuft; `check-migrations` → „No new upgrade operations detected." (Modell ↔ Migration synchron.)

- [ ] **Step 5: Commit**

```bash
git add packages/dms_core/dms_core/models/project.py alembic/versions/
git commit -m "G-3: projects.retention_max_days + Backfill documents.retention_until"
```

---

### Task 3: Default-Mindest-Retention beim Upload

**Files:**
- Modify: `backend/app/services/document_service.py` (Imports + `create_document_with_version`)
- Test: `backend/tests/test_documents.py`

- [ ] **Step 1: Failing test schreiben**

In `backend/tests/test_documents.py` ergänzen (nutzt die vorhandenen Fixtures/Helfer der Datei — Upload als Editor, dann Detail prüfen):

```python
def test_upload_sets_default_retention(client, editor_headers, project_id):  # noqa: ANN001
    from datetime import date, timedelta

    from dms_core.config import settings

    res = client.post(
        f"/api/projects/{project_id}/documents",
        data={"title": "Vertrag"},
        files={"file": ("v.txt", b"inhalt", "text/plain")},
        headers=editor_headers,
    )
    assert res.status_code == 201, res.text
    expected = (date.today() + timedelta(days=settings.default_retention_days)).isoformat()
    assert res.json()["retention_until"] == expected
```

(Falls die Fixture-Namen in der Datei abweichen, die dort etablierten verwenden — Muster aus den bestehenden Upload-Tests übernehmen.)

- [ ] **Step 2: Test laufen lassen (muss fehlschlagen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_documents.py::test_upload_sets_default_retention -q`
Expected: FAIL (`retention_until` ist `None`).

- [ ] **Step 3: Default setzen**

In `document_service.py` Imports ergänzen:

```python
from datetime import date, timedelta
```

In `create_document_with_version` beim Anlegen des `Document` `retention_until` setzen:

```python
    retention_until = (
        date.today() + timedelta(days=settings.default_retention_days)
        if settings.default_retention_days > 0
        else None
    )
    document = Document(
        id=uuid.uuid4(),
        project_id=project_id,
        title=title,
        description=description,
        category=category,
        status=DocumentStatus.active,
        created_by=actor.id,
        retention_until=retention_until,
    )
```

- [ ] **Step 4: Test laufen lassen (muss bestehen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_documents.py -q`
Expected: PASS (neuer Test + bestehende Upload-Tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_service.py backend/tests/test_documents.py
git commit -m "G-3: Default-Mindest-Retention beim Upload"
```

---

### Task 4: Auto-Soft-Delete-Logik (Maintenance-Kern)

**Files:**
- Modify: `packages/dms_core/dms_core/maintenance.py` (Import `Project`; neue Funktion)
- Test: `backend/tests/test_compliance.py`

- [ ] **Step 1: Failing tests schreiben**

In `backend/tests/test_compliance.py` ergänzen (nutzt `db_session` + die vorhandenen Factories für User/Projekt/Dokument; Muster aus bestehenden Compliance-Tests übernehmen):

```python
def test_auto_expire_off_by_default(db_session):  # noqa: ANN001
    from dms_core import maintenance
    # Projekt ohne retention_max_days + altes Dokument -> nichts passiert.
    project, doc = _project_with_document(db_session, age_days=10_000)
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    db_session.refresh(doc)
    assert doc.status == "active"


def test_auto_expire_soft_deletes_old_document(db_session):  # noqa: ANN001
    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=400)
    project.retention_max_days = 365
    doc.retention_until = None  # keine Mindest-Aufbewahrung im Weg
    db_session.add_all([project, doc])
    db_session.flush()
    assert maintenance.auto_soft_delete_expired(db_session) == 1
    db_session.refresh(doc)
    assert doc.status == "deleted"
    assert doc.purge_after is not None


def test_auto_expire_respects_legal_hold(db_session):  # noqa: ANN001
    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=400)
    project.retention_max_days = 365
    doc.legal_hold = True
    db_session.add_all([project, doc])
    db_session.flush()
    assert maintenance.auto_soft_delete_expired(db_session) == 0


def test_auto_expire_respects_min_retention(db_session):  # noqa: ANN001
    from datetime import date, timedelta

    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=400)
    project.retention_max_days = 365
    doc.retention_until = date.today() + timedelta(days=30)  # Mindest-Aufbewahrung laeuft noch
    db_session.add_all([project, doc])
    db_session.flush()
    assert maintenance.auto_soft_delete_expired(db_session) == 0
```

Dazu einen kleinen Helfer am Anfang der Testdatei (oder in `factories.py`), der ein Projekt + ein Dokument mit gegebenem Alter anlegt:

```python
def _project_with_document(session, *, age_days: int):  # noqa: ANN001
    from datetime import UTC, datetime, timedelta

    from tests.factories import make_document, make_project, make_user  # vorhandene Factories
    user = make_user(session)
    project = make_project(session, owner=user)
    doc = make_document(session, project=project, author=user)
    doc.created_at = datetime.now(UTC) - timedelta(days=age_days)
    session.add(doc)
    session.flush()
    return project, doc
```

(Falls `factories.py` keine passenden Helfer hat: die in den bestehenden Compliance-Tests genutzte Anlage-Routine wiederverwenden.)

- [ ] **Step 2: Tests laufen lassen (müssen fehlschlagen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_compliance.py -q -k auto_expire`
Expected: FAIL (`AttributeError: module ... has no attribute 'auto_soft_delete_expired'`).

- [ ] **Step 3: Funktion implementieren**

In `maintenance.py` `Project` importieren (zum bestehenden Models-Import-Block) und ergänzen:

```python
def auto_soft_delete_expired(session: Session, *, now: datetime | None = None) -> int:
    """Soft-deletet aktive Dokumente, deren Projekt eine Maximal-Aufbewahrung
    (Project.retention_max_days) hat und deren Alter sie ueberschreitet.

    Respektiert legal_hold und die Mindest-Aufbewahrung (retention_until). Der
    endgueltige Purge laeuft danach ueber purge_deleted_documents (Grace-Period).
    Gechunked via PURGE_BATCH.
    """
    now = now or datetime.now(UTC)
    today = now.date()
    candidates = session.exec(
        select(Document)
        .join(Project, Project.id == Document.project_id)
        .where(
            Document.status == DocumentStatus.active,
            Document.legal_hold.is_(False),
            Project.retention_max_days.is_not(None),
            Document.created_at
            < now - func.make_interval(0, 0, 0, Project.retention_max_days),
            or_(
                Document.retention_until.is_(None),
                Document.retention_until <= today,
            ),
        )
        .limit(PURGE_BATCH)
    ).all()

    purge_after = now + timedelta(days=settings.purge_grace_days)
    count = 0
    for doc in candidates:
        doc.status = DocumentStatus.deleted
        doc.deleted_at = now
        doc.purge_after = purge_after
        session.add(doc)
        write_audit_log(
            session,
            action=AuditAction.document_auto_expired,
            entity_type="document",
            actor_user_id=None,
            entity_id=doc.id,
            project_id=doc.project_id,
            metadata={"retention_max_days": doc.project_id and None},
        )
        count += 1
    session.flush()
    return count
```

Hinweis: `func` ist in `maintenance.py` bereits importiert? Falls nicht: `from sqlalchemy import func` ergänzen (neben `or_, update`). `settings` ist importiert. Das `metadata`-Feld bewusst minimal halten (keine PII).

- [ ] **Step 4: Tests laufen lassen (müssen bestehen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_compliance.py -q`
Expected: PASS (4 neue + bestehende).

- [ ] **Step 5: Commit**

```bash
git add packages/dms_core/dms_core/maintenance.py backend/tests/test_compliance.py backend/tests/factories.py
git commit -m "G-3: auto_soft_delete_expired (Maximal-Retention, respektiert hold/min-retention)"
```

---

### Task 5: Worker-Task + Beat-Schedule

**Files:**
- Modify: `packages/dms_core/dms_core/celery_app.py` (Task-Name, Route, Beat)
- Modify: `worker/worker/tasks/maintenance.py` (Task-Wrapper)
- Test: `worker/tests/test_processing.py` oder neuer `worker/tests/test_maintenance.py` (Wrapper ruft Kernlogik)

- [ ] **Step 1: Task-Name + Route + Beat eintragen**

In `celery_app.py` Task-Namen ergänzen:

```python
TASK_AUTO_EXPIRE = "tasks.auto_soft_delete_expired"
```

In `task_routes` ergänzen:

```python
        TASK_AUTO_EXPIRE: {"queue": "maintenance"},
```

In `beat_schedule` ergänzen (täglich 02:30 UTC — vor dem Purge um 03:00, damit frisch Soft-Deletes erst nach Ablauf der Grace-Period gepurged werden):

```python
        "auto-expire-documents": {
            "task": TASK_AUTO_EXPIRE,
            "schedule": crontab(minute=30, hour=2),
        },
```

- [ ] **Step 2: Worker-Wrapper ergänzen**

In `worker/worker/tasks/maintenance.py` Import um `TASK_AUTO_EXPIRE` erweitern und Task ergänzen:

```python
@celery_app.task(name=TASK_AUTO_EXPIRE)
def auto_soft_delete_expired() -> int:
    with session_scope() as session:
        return maintenance.auto_soft_delete_expired(session)
```

- [ ] **Step 3: Verifizieren (Task registriert, Kernlogik aufrufbar)**

Run: `make test-worker`
Expected: PASS (bestehende Worker-Tests bleiben grün; kein Bruch durch den neuen Task).

- [ ] **Step 4: Commit**

```bash
git add packages/dms_core/dms_core/celery_app.py worker/worker/tasks/maintenance.py worker/tests/
git commit -m "G-3: Beat-Task auto_soft_delete_expired (taeglich 02:30 UTC)"
```

---

### Task 6: `retention_max_days` über die Projekt-API setzbar

**Files:**
- Modify: `backend/app/schemas/project.py:19-22` (`ProjectUpdate`), `:25-32` (`ProjectOut`)
- Modify: `backend/app/services/project_service.py` (`update_project`)
- Modify: `backend/app/api/routes_projects.py` (PATCH-Handler — `retention_max_days` durchreichen)
- Test: `backend/tests/test_projects.py`

- [ ] **Step 1: Failing test schreiben**

In `backend/tests/test_projects.py` ergänzen:

```python
def test_owner_can_set_retention_max_days(client, owner_headers, project_id):  # noqa: ANN001
    res = client.patch(
        f"/api/projects/{project_id}",
        json={"retention_max_days": 730},
        headers=owner_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["retention_max_days"] == 730
```

- [ ] **Step 2: Test laufen lassen (muss fehlschlagen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_projects.py::test_owner_can_set_retention_max_days -q`
Expected: FAIL (Feld unbekannt / nicht im Response).

- [ ] **Step 3: Schema + Service + Route erweitern**

`ProjectUpdate` ergänzen:

```python
    retention_max_days: int | None = Field(default=None, ge=0, le=36500)
```

`ProjectOut` ergänzen:

```python
    retention_max_days: int | None = None
```

`update_project`-Signatur um `retention_max_days: int | None` erweitern und im Body behandeln (Sentinel-Problem beachten: `None` heißt „nicht ändern" — wer Auto-Purge **abschalten** will, ist hier nicht abbildbar; für MVP genügt „setzen". Falls explizites Abschalten gewünscht: separates Flag/`-1`-Konvention dokumentieren):

```python
    if retention_max_days is not None:
        project.retention_max_days = retention_max_days
        changed["retention_max_days"] = retention_max_days
```

Im PATCH-Handler in `routes_projects.py` den Aufruf um `retention_max_days=body.retention_max_days` ergänzen (analog zu `name`/`description`/`status`).

- [ ] **Step 4: Test laufen lassen (muss bestehen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_projects.py -q && make test`
Expected: PASS (gesamte Backend-Suite).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/project.py backend/app/services/project_service.py backend/app/api/routes_projects.py backend/tests/test_projects.py
git commit -m "G-3: retention_max_days ueber Projekt-API setzbar"
```

---

### Task 7 (optional): Frontend — UI-Feld + Audit-Aktion

**Files:**
- Modify: `frontend/src/types/api.ts` — `ProjectOut.retention_max_days?: number | null`; `AUDIT_ACTIONS` um `"document.auto_expired"` erweitern.
- Modify: `frontend/src/features/projects/ProjectDetailPage.tsx` + `hooks.ts` — Eingabefeld „Maximal-Aufbewahrung (Tage)" in der „Projekt verwalten"-Karte; `useUpdateProject` um `retention_max_days` erweitern.
- Modify: `frontend/src/features/admin/AuditLogsPage.tsx` — Filter zeigt die neue Aktion (kommt automatisch über `AUDIT_ACTIONS`).

- [ ] **Step 1: Typen + Hook + UI ergänzen** (Muster der bestehenden Felder/Mutationen übernehmen, deutsche Labels).

- [ ] **Step 2: Typecheck + Tests**

Run: `docker compose run --rm --no-deps --entrypoint sh frontend -c "npm ci && npx tsc --noEmit && npm run test"`
Expected: tsc sauber, vitest grün.

- [ ] **Step 3: Commit**

```bash
git add frontend/src
git commit -m "G-3: Frontend — Maximal-Aufbewahrung pro Projekt + Audit-Aktion"
```

---

### Task 8: Doku — CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Retention-Konvention dokumentieren**

Unter „Worker / Skalierung" bzw. einem neuen „Compliance/Retention"-Punkt festhalten: `retention_until` = Mindest-Aufbewahrung (blockt Löschung, Default aus `default_retention_days` beim Upload); `Project.retention_max_days` = Maximal-Aufbewahrung (None = aus), Auto-Soft-Delete via Beat-Task `auto_soft_delete_expired` (täglich 02:30), endgültiger Purge danach über die Grace-Period. Beide respektieren `legal_hold` und die Mindest-Aufbewahrung.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "G-3: CLAUDE.md — Retention-/Auto-Purge-Konventionen"
```

---

## Self-Review

- **Spec-Abdeckung:** Min-Retention-Default (Task 3), Max-Retention pro Projekt (Task 2/6), Auto-Purge off-by-default (Task 4, `retention_max_days IS NOT NULL`), Bestands-Backfill via Migration (Task 2), respektiert legal_hold + min-retention (Task 4 Tests). ✓
- **Type-Konsistenz:** `auto_soft_delete_expired(session, *, now=None)` einheitlich in Kern (Task 4) und Wrapper (Task 5); `retention_max_days` als `int | None` durchgängig in Modell/Schema/Service. ✓
- **Bekannte Grenze (dokumentieren):** „pro Kategorie" ist hier nicht umgesetzt — die Policy hängt am Projekt (pragmatischer 80-%-Fall). Kategorie-Policy ⇒ späterer Task mit Policy-Tabelle. Außerdem: „retention_max_days wieder abschalten" über die PATCH-API ist mit der `None=nicht ändern`-Semantik nicht abbildbar (Task 6 Hinweis) — bei Bedarf eigene Konvention.
- **Reihenfolge-Abhängigkeit:** Task 2 (Migration/Spalte) muss vor Task 4/6 laufen. Task 1 vor Task 4 (Audit-Aktion).

---

## Execution Handoff

Zwei Ausführungsoptionen:
1. **Subagent-Driven (empfohlen)** — pro Task ein frischer Subagent, Review dazwischen.
2. **Inline** — Tasks in dieser Session mit Checkpoints.
