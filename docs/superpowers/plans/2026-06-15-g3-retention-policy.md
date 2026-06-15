# G-3: Retention-Policy & Auto-Purge (mit Kategorie-Regeln) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dokumente bekommen eine angewandte Aufbewahrungs-Policy: eine Default-**Mindest**-Aufbewahrung beim Upload und eine pro Projekt **und pro Kategorie** konfigurierbare **Maximal**-Aufbewahrung, nach der nicht mehr benötigte Dokumente automatisch entfernt werden (DSGVO Art. 5(1e)). Inklusive sauberem **Aus-Schalter**.

**Architecture:** Zwei getrennte Konzepte. (1) `retention_until` = rechtliche **Mindest**-Aufbewahrung (blockt Löschung), beim Upload mit `default_retention_days` vorbelegt, pro Dokument überschreibbar. (2) Eine neue Tabelle `retention_rules(project_id, category, max_days)` definiert die **Maximal**-Aufbewahrung. Auflösung pro Dokument: **spezifischste Regel gewinnt** — Regel für (Projekt+Kategorie) schlägt Projekt-Default (Kategorie = NULL); existiert keine Regel → kein Auto-Purge (default aus). `max_days = NULL` in einer Regel = **„nie löschen" (exempt)**. Der **Aus-Schalter** ist das Löschen der Regel; das **Kategorie-Exempt** ist eine Regel mit `max_days = NULL`. Ein Beat-Task soft-deletet abgelaufene Dokumente; die bestehende Purge-Logik räumt nach der Grace-Period ab. Alles respektiert `legal_hold` und die Mindest-Aufbewahrung.

**Tech Stack:** FastAPI, sync SQLModel/SQLAlchemy 2.0 (`case`, `aliased`, `make_interval`), Alembic, Celery-Beat, **PostgreSQL 15+** (`NULLS NOT DISTINCT` für die Projekt-Default-Regel), pytest mit DB-Fixture.

**Invarianten:** Response-Shapes nur additiv; `purge_deleted_documents` bleibt die einzige hart-löschende Stelle; Auto-Soft-Delete fasst nur `status=active` an; Default-Auto-Purge = aus.

---

## File Structure

- **Modify** `packages/dms_core/dms_core/enums.py` — `AuditAction.document_auto_expired` (action ist plain `String`, keine CHECK-Migration nötig).
- **Modify** `packages/dms_core/dms_core/models/project.py` — neues Modell `RetentionRule`.
- **Create** Alembic-Migration — Tabelle `retention_rules` + Backfill `documents.retention_until`.
- **Modify** `backend/app/services/document_service.py` — Default-Mindest-Retention beim Upload.
- **Modify** `packages/dms_core/dms_core/maintenance.py` — `auto_soft_delete_expired(...)` mit Regel-Auflösung.
- **Modify** `packages/dms_core/dms_core/celery_app.py` + `worker/worker/tasks/maintenance.py` — Beat-Task.
- **Create** `backend/app/schemas/retention.py`; **Modify** `backend/app/services/project_service.py`, `backend/app/api/routes_projects.py` — Retention-Rules-CRUD (setzen / **löschen=aus** / listen).
- **Modify** `frontend/src/types/api.ts`, `frontend/src/features/projects/*`, `frontend/src/features/admin/AuditLogsPage.tsx` — Regel-Verwaltung + neue Audit-Aktion (optional).

---

### Task 1: Audit-Aktion `document.auto_expired`

**Files:** Modify `packages/dms_core/dms_core/enums.py`

- [ ] **Step 1:** In `AuditAction` nach `document_purged` einfügen: `document_auto_expired = "document.auto_expired"`
- [ ] **Step 2:** Run: `docker compose run --rm --no-deps backend python -c "from dms_core.enums import AuditAction; print(AuditAction.document_auto_expired.value)"` → Expected: `document.auto_expired`
- [ ] **Step 3:** Commit: `git add packages/dms_core/dms_core/enums.py && git commit -m "G-3: Audit-Aktion document.auto_expired"`

---

### Task 2: `RetentionRule`-Modell + Migration

**Files:** Modify `packages/dms_core/dms_core/models/project.py`; Create Migration

Semantik der Tabelle:
- `(project_id, category=NULL, max_days=N)` → Projekt-Default: alle Kategorien ohne eigene Regel werden nach N Tagen gelöscht.
- `(project_id, category="Rechnung", max_days=NULL)` → „Rechnung" ist **exempt** (nie auto-löschen), auch wenn der Projekt-Default existiert.
- `(project_id, category="Entwurf", max_days=30)` → „Entwurf" nach 30 Tagen.
- Keine Regel für ein Dokument → kein Auto-Purge.

- [ ] **Step 1: Modell** in `project.py` ergänzen (`Integer` zum sqlalchemy-Import hinzufügen):

```python
class RetentionRule(SQLModel, table=True):
    """Maximal-Aufbewahrung pro Projekt (+ optional Kategorie). Art. 5(1e).

    category = NULL  -> Projekt-Default (gilt fuer alle Kategorien ohne eigene Regel)
    max_days = NULL  -> exempt (nie automatisch loeschen)
    Aufloesung: spezifischste Regel (Projekt+Kategorie) schlaegt Projekt-Default.
    """

    __tablename__ = "retention_rules"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "category", name="retention_rule_scope", postgresql_nulls_not_distinct=True
        ),
    )

    id: uuid.UUID = pk_field()
    project_id: uuid.UUID = fk_uuid("projects.id", nullable=False, ondelete="CASCADE", index=True)
    category: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    max_days: int | None = Field(default=None, sa_column=Column(Integer(), nullable=True))
    created_at: datetime = created_at_field()
```

(`Integer` zum `from sqlalchemy import ...`-Block ergänzen.)

- [ ] **Step 2: Migration erzeugen:** `docker compose run --rm --user "$(id -u):$(id -g)" backend alembic revision --autogenerate -m "retention rules"` → erzeugt `create_table("retention_rules", ...)`.

- [ ] **Step 3: NULLS-NOT-DISTINCT + Backfill prüfen/ergänzen.** Autogenerate setzt `postgresql_nulls_not_distinct` evtl. nicht in den `UniqueConstraint` — sicherstellen, dass die Constraint in der Migration `postgresql_nulls_not_distinct=True` hat (sonst sind mehrere Projekt-Default-Zeilen pro Projekt möglich). Am Ende von `upgrade()` den Mindest-Retention-Backfill ergänzen:

```python
    from dms_core.config import settings

    days = settings.default_retention_days
    if days > 0:
        op.execute(
            sa.text(
                "UPDATE documents SET retention_until = "
                "(created_at AT TIME ZONE 'UTC')::date + (:days || ' days')::interval "
                "WHERE retention_until IS NULL"
            ).bindparams(days=days)
        )
```

- [ ] **Step 4:** Run: `make migrate && make check-migrations` → Expected: Upgrade ok; „No new upgrade operations detected." Falls Drift wegen `nulls_not_distinct`: Constraint in Modell `__table_args__` und Migration identisch halten.
- [ ] **Step 5:** Commit: `git add packages/dms_core/dms_core/models/project.py alembic/versions/ && git commit -m "G-3: retention_rules-Tabelle + retention_until-Backfill"`

---

### Task 3: Default-Mindest-Retention beim Upload

**Files:** Modify `backend/app/services/document_service.py`; Test `backend/tests/test_documents.py`

- [ ] **Step 1: Failing test** in `test_documents.py`:

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

- [ ] **Step 2:** Run: `... pytest tests/test_documents.py::test_upload_sets_default_retention -q` → Expected: FAIL.

- [ ] **Step 3:** In `document_service.py` `from datetime import date, timedelta` ergänzen; in `create_document_with_version` beim `Document(...)` setzen:

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

- [ ] **Step 4:** Run: `... pytest tests/test_documents.py -q` → Expected: PASS.
- [ ] **Step 5:** Commit: `git add backend/app/services/document_service.py backend/tests/test_documents.py && git commit -m "G-3: Default-Mindest-Retention beim Upload"`

---

### Task 4: Auto-Soft-Delete mit Regel-Auflösung (Maintenance-Kern)

**Files:** Modify `packages/dms_core/dms_core/maintenance.py`; Test `backend/tests/test_compliance.py`

Effektive Maximal-Frist pro Dokument (SQL): `CASE WHEN <Kategorie-Regel existiert> THEN <ihre max_days> ELSE <Projekt-Default max_days> END`. Eine Kategorie-Regel überschreibt den Default **auch wenn ihr `max_days = NULL`** (exempt). Eligible = effektive Frist ist nicht NULL **und** Alter überschritten **und** legal_hold falsch **und** Mindest-Aufbewahrung abgelaufen/leer.

- [ ] **Step 1: Failing tests** in `test_compliance.py` (Helfer `_project_with_document` aus Task-4-Step-1, der Projekt+Dokument mit Alter anlegt; Factories der Datei wiederverwenden):

```python
def _rule(session, project, category, max_days):  # noqa: ANN001
    from dms_core.models.project import RetentionRule
    r = RetentionRule(project_id=project.id, category=category, max_days=max_days)
    session.add(r)
    session.flush()
    return r


def test_auto_expire_off_when_no_rule(db_session):  # noqa: ANN001
    from dms_core import maintenance
    _, doc = _project_with_document(db_session, age_days=10_000)
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    db_session.refresh(doc)
    assert doc.status == "active"


def test_auto_expire_project_default(db_session):  # noqa: ANN001
    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=400)
    doc.retention_until = None
    db_session.add(doc)
    _rule(db_session, project, None, 365)  # Projekt-Default
    assert maintenance.auto_soft_delete_expired(db_session) == 1
    db_session.refresh(doc)
    assert doc.status == "deleted" and doc.purge_after is not None


def test_category_rule_overrides_default(db_session):  # noqa: ANN001
    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=400, category="Rechnung")
    doc.retention_until = None
    db_session.add(doc)
    _rule(db_session, project, None, 365)          # Default: loeschen nach 365
    _rule(db_session, project, "Rechnung", None)   # aber Rechnung = exempt
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    db_session.refresh(doc)
    assert doc.status == "active"


def test_category_rule_shorter_than_default(db_session):  # noqa: ANN001
    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=40, category="Entwurf")
    doc.retention_until = None
    db_session.add(doc)
    _rule(db_session, project, "Entwurf", 30)  # Entwurf schon nach 30 Tagen weg
    assert maintenance.auto_soft_delete_expired(db_session) == 1


def test_auto_expire_respects_legal_hold_and_min_retention(db_session):  # noqa: ANN001
    from datetime import date, timedelta

    from dms_core import maintenance
    project, doc = _project_with_document(db_session, age_days=400)
    _rule(db_session, project, None, 365)
    doc.legal_hold = True
    db_session.add(doc)
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    doc.legal_hold = False
    doc.retention_until = date.today() + timedelta(days=30)  # Mindest-Aufbewahrung laeuft noch
    db_session.add(doc)
    assert maintenance.auto_soft_delete_expired(db_session) == 0
```

- [ ] **Step 2:** Run: `... pytest tests/test_compliance.py -q -k "auto_expire or category"` → Expected: FAIL.

- [ ] **Step 3: Funktion** in `maintenance.py` (Imports ergänzen: `from sqlalchemy import case`, `from sqlalchemy.orm import aliased`, `from dms_core.models.project import Project, RetentionRule`; `func`/`or_`/`and_` ggf. ergänzen):

```python
def auto_soft_delete_expired(session: Session, *, now: datetime | None = None) -> int:
    """Soft-deletet aktive Dokumente gemaess Retention-Regeln (Maximal-Aufbewahrung).

    Aufloesung: Kategorie-Regel schlaegt Projekt-Default (category=NULL). Eine
    Kategorie-Regel mit max_days=NULL ist 'exempt'. Respektiert legal_hold und
    die Mindest-Aufbewahrung (retention_until). Gechunked via PURGE_BATCH.
    """
    now = now or datetime.now(UTC)
    today = now.date()
    rc = aliased(RetentionRule)  # Kategorie-spezifisch
    rp = aliased(RetentionRule)  # Projekt-Default (category IS NULL)
    effective = case((rc.id.is_not(None), rc.max_days), else_=rp.max_days)

    candidates = session.exec(
        select(Document)
        .join(Project, Project.id == Document.project_id)
        .outerjoin(
            rc, and_(rc.project_id == Document.project_id, rc.category == Document.category)
        )
        .outerjoin(rp, and_(rp.project_id == Document.project_id, rp.category.is_(None)))
        .where(
            Document.status == DocumentStatus.active,
            Document.legal_hold.is_(False),
            effective.is_not(None),
            Document.created_at < now - func.make_interval(0, 0, 0, effective),
            or_(Document.retention_until.is_(None), Document.retention_until <= today),
        )
        .limit(PURGE_BATCH)
    ).all()

    purge_after = now + timedelta(days=settings.purge_grace_days)
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
            metadata={"reason": "retention_max"},
        )
    session.flush()
    return len(candidates)
```

- [ ] **Step 4:** Run: `... pytest tests/test_compliance.py -q` → Expected: PASS (alle neuen + bestehende).
- [ ] **Step 5:** Commit: `git add packages/dms_core/dms_core/maintenance.py backend/tests/test_compliance.py backend/tests/factories.py && git commit -m "G-3: auto_soft_delete_expired mit Kategorie-Regel-Aufloesung"`

---

### Task 5: Worker-Task + Beat-Schedule

**Files:** Modify `packages/dms_core/dms_core/celery_app.py`, `worker/worker/tasks/maintenance.py`

- [ ] **Step 1:** In `celery_app.py`: `TASK_AUTO_EXPIRE = "tasks.auto_soft_delete_expired"`; in `task_routes`: `TASK_AUTO_EXPIRE: {"queue": "maintenance"},`; in `beat_schedule`:

```python
        "auto-expire-documents": {
            "task": TASK_AUTO_EXPIRE,
            "schedule": crontab(minute=30, hour=2),  # taeglich 02:30 UTC, vor dem Purge
        },
```

- [ ] **Step 2:** In `worker/worker/tasks/maintenance.py` (Import `TASK_AUTO_EXPIRE` ergänzen):

```python
@celery_app.task(name=TASK_AUTO_EXPIRE)
def auto_soft_delete_expired() -> int:
    with session_scope() as session:
        return maintenance.auto_soft_delete_expired(session)
```

- [ ] **Step 3:** Run: `make test-worker` → Expected: PASS (kein Bruch durch neuen Task).
- [ ] **Step 4:** Commit: `git add packages/dms_core/dms_core/celery_app.py worker/worker/tasks/maintenance.py && git commit -m "G-3: Beat-Task auto_soft_delete_expired (02:30 UTC)"`

---

### Task 6: Retention-Rules-API — setzen / **löschen (=aus)** / listen

**Files:** Create `backend/app/schemas/retention.py`; Modify `backend/app/services/project_service.py`, `backend/app/api/routes_projects.py`; Test `backend/tests/test_projects.py`

**Aus-Schalter:** Auto-Purge für ein Projekt abschalten = die Projekt-Default-Regel (category=NULL) **löschen**. Eine Kategorie schützen = Regel mit `max_days=NULL` setzen. Beides explizit, keine 100-Jahre-Krücke.

Berechtigung: `require_project_role(admin)` (Owner/Admin) — Muster der bestehenden Projekt-Endpoints.

- [ ] **Step 1: Failing tests** in `test_projects.py`:

```python
def test_set_list_and_delete_retention_rule(client, owner_headers, project_id):  # noqa: ANN001
    # setzen (Projekt-Default)
    res = client.put(
        f"/api/projects/{project_id}/retention-rules",
        json={"category": None, "max_days": 365},
        headers=owner_headers,
    )
    assert res.status_code == 200, res.text
    # Kategorie-Exempt
    client.put(
        f"/api/projects/{project_id}/retention-rules",
        json={"category": "Rechnung", "max_days": None},
        headers=owner_headers,
    )
    # listen
    rules = client.get(
        f"/api/projects/{project_id}/retention-rules", headers=owner_headers
    ).json()
    assert {r["category"] for r in rules} == {None, "Rechnung"}
    # AUS-Schalter: Projekt-Default loeschen
    res = client.request(
        "DELETE",
        f"/api/projects/{project_id}/retention-rules",
        json={"category": None},
        headers=owner_headers,
    )
    assert res.status_code == 204
    rules = client.get(
        f"/api/projects/{project_id}/retention-rules", headers=owner_headers
    ).json()
    assert {r["category"] for r in rules} == {"Rechnung"}


def test_retention_rule_requires_admin(client, viewer_headers, project_id):  # noqa: ANN001
    res = client.put(
        f"/api/projects/{project_id}/retention-rules",
        json={"category": None, "max_days": 365},
        headers=viewer_headers,
    )
    assert res.status_code == 403
```

- [ ] **Step 2:** Run: `... pytest tests/test_projects.py -q -k retention` → Expected: FAIL.

- [ ] **Step 3: Schemas** `backend/app/schemas/retention.py`:

```python
"""DTOs fuer Retention-Regeln (Maximal-Aufbewahrung pro Projekt/Kategorie)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RetentionRuleIn(BaseModel):
    category: str | None = Field(default=None, max_length=100)
    max_days: int | None = Field(default=None, ge=1, le=36500)  # None = exempt (nie loeschen)


class RetentionRuleDelete(BaseModel):
    category: str | None = None


class RetentionRuleOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category: str | None
    max_days: int | None
    created_at: datetime
```

- [ ] **Step 4: Service** in `project_service.py` (Upsert/List/Delete; Audit über `project_updated` o.ä.):

```python
def upsert_retention_rule(
    session: Session, *, project: Project, category: str | None, max_days: int | None,
    actor: User, ip: str | None,
) -> RetentionRule:
    rule = session.exec(
        select(RetentionRule).where(
            RetentionRule.project_id == project.id,
            RetentionRule.category.is_(None) if category is None else RetentionRule.category == category,
        )
    ).first()
    if rule is None:
        rule = RetentionRule(project_id=project.id, category=category, max_days=max_days)
        session.add(rule)
    else:
        rule.max_days = max_days
        session.add(rule)
    write_audit_log(
        session, action=AuditAction.project_updated, entity_type="project",
        actor_user_id=actor.id, entity_id=project.id, project_id=project.id, ip_address=ip,
        metadata={"retention_rule": category or "<default>"},
    )
    session.flush()
    return rule


def list_retention_rules(session: Session, *, project: Project) -> list[RetentionRule]:
    return list(
        session.exec(select(RetentionRule).where(RetentionRule.project_id == project.id)).all()
    )


def delete_retention_rule(
    session: Session, *, project: Project, category: str | None, actor: User, ip: str | None
) -> None:
    rule = session.exec(
        select(RetentionRule).where(
            RetentionRule.project_id == project.id,
            RetentionRule.category.is_(None) if category is None else RetentionRule.category == category,
        )
    ).first()
    if rule is not None:
        session.delete(rule)
        write_audit_log(
            session, action=AuditAction.project_updated, entity_type="project",
            actor_user_id=actor.id, entity_id=project.id, project_id=project.id, ip_address=ip,
            metadata={"retention_rule_removed": category or "<default>"},
        )
        session.flush()
```

(Imports `RetentionRule` ergänzen.)

- [ ] **Step 5: Routes** in `routes_projects.py` (3 Endpoints, `ProjAdmin`-Dependency analog vorhandener Projekt-Rollen-Annotationen):

```python
@router.put("/projects/{project_id}/retention-rules", response_model=RetentionRuleOut)
def put_retention_rule(
    body: RetentionRuleIn, ctx: ProjAdmin, session: SessionDep, request: Request
) -> RetentionRuleOut:
    rule = project_service.upsert_retention_rule(
        session, project=ctx.project, category=body.category, max_days=body.max_days,
        actor=ctx.user, ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(rule)
    return RetentionRuleOut.model_validate(rule)


@router.get("/projects/{project_id}/retention-rules", response_model=list[RetentionRuleOut])
def get_retention_rules(ctx: ProjAdmin, session: SessionDep) -> list[RetentionRuleOut]:
    return [RetentionRuleOut.model_validate(r) for r in project_service.list_retention_rules(session, project=ctx.project)]


@router.delete("/projects/{project_id}/retention-rules", status_code=status.HTTP_204_NO_CONTENT)
def delete_retention_rule(
    body: RetentionRuleDelete, ctx: ProjAdmin, session: SessionDep, request: Request
) -> Response:
    project_service.delete_retention_rule(
        session, project=ctx.project, category=body.category, actor=ctx.user, ip=get_client_ip(request)
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

(Imports + `ProjAdmin = Annotated[ProjectContext, Depends(require_project_role(ProjectRole.admin))]` analog zu den bestehenden Annotationen in der Datei.)

- [ ] **Step 6:** Run: `... pytest tests/test_projects.py -q && make test` → Expected: PASS.
- [ ] **Step 7:** Commit: `git add backend/app/schemas/retention.py backend/app/services/project_service.py backend/app/api/routes_projects.py backend/tests/test_projects.py && git commit -m "G-3: Retention-Rules-API (setzen/loeschen=aus/listen, Kategorie-Exempt)"`

---

### Task 7 (optional): Frontend — Regel-Verwaltung + Audit-Aktion

**Files:** `frontend/src/types/api.ts`, `frontend/src/features/projects/ProjectDetailPage.tsx` + `hooks.ts`, `frontend/src/features/admin/AuditLogsPage.tsx`

- [ ] **Step 1:** Typen: `RetentionRuleOut`/`RetentionRuleIn`; `AUDIT_ACTIONS` um `"document.auto_expired"` erweitern.
- [ ] **Step 2:** In der „Projekt verwalten"-Karte eine kleine Regel-Tabelle: Zeilen mit (Kategorie | Max-Tage | „nie" | Entfernen). „+ Regel" öffnet ein Mini-Formular (Kategorie leer = Projekt-Default; Max-Tage leer = exempt/„nie"). Hooks: `useRetentionRules(projectId)`, `useUpsertRetentionRule`, `useDeleteRetentionRule` (Muster der bestehenden Mutations + `confirmDialog` beim Entfernen). Deutsche Labels, `keepPreviousData` nicht nötig.
- [ ] **Step 3:** Run: `docker compose run --rm --no-deps --entrypoint sh frontend -c "npm ci && npx tsc --noEmit && npm run test"` → Expected: tsc sauber, vitest grün.
- [ ] **Step 4:** Commit: `git add frontend/src && git commit -m "G-3: Frontend — Retention-Regel-Verwaltung pro Projekt/Kategorie"`

---

### Task 8: Doku — CLAUDE.md

**Files:** Modify `CLAUDE.md`

- [ ] **Step 1:** Retention-Konventionen festhalten: `retention_until` = Mindest-Aufbewahrung (Default beim Upload, pro Dokument überschreibbar, blockt Löschung). `retention_rules` = Maximal-Aufbewahrung pro Projekt/Kategorie; **Auflösung spezifischste-Regel-gewinnt**, `max_days=NULL` = exempt; **Aus-Schalter = Regel löschen**. Auto-Soft-Delete via Beat `auto_soft_delete_expired` (02:30), Hard-Purge danach über Grace. Alles respektiert `legal_hold` + Mindest-Aufbewahrung.
- [ ] **Step 2:** Commit: `git add CLAUDE.md && git commit -m "G-3: CLAUDE.md — Retention-Regeln + Aus-Schalter"`

---

## Self-Review

- **Spec-Abdeckung:** Min-Retention-Default (Task 3), Max-Retention **pro Projekt UND Kategorie** (Task 2/4/6), Auto-Purge default-aus (keine Regel → `effective` NULL → nichts), **Kategorie-Exempt** (`max_days=NULL`), **sauberer Aus-Schalter** (DELETE der Regel, Task 6), Bestands-Backfill (Task 2), respektiert legal_hold + min-retention (Task 4 Tests). ✓
- **Type-Konsistenz:** `RetentionRule(project_id, category, max_days)` durchgängig in Modell/Auflösung/API; `auto_soft_delete_expired(session, *, now=None)` in Kern (Task 4) und Wrapper (Task 5). ✓
- **DB-Voraussetzung:** `NULLS NOT DISTINCT` braucht PostgreSQL 15+ (Compose nutzt PG 16 ✓). Modell- und Migrations-Constraint müssen identisch sein, sonst `alembic check`-Drift.
- **Edge:** Dokumente ohne Kategorie (`category IS NULL`) matchen keine Kategorie-Regel (NULL=NULL ist im JOIN nicht wahr) → fallen korrekt auf den Projekt-Default. Gewollt.

---

## Execution Handoff

1. **Subagent-Driven (empfohlen)** — pro Task ein frischer Subagent, Review dazwischen.
2. **Inline** — Tasks in dieser Session mit Checkpoints.
