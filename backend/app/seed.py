"""Idempotentes Seed-Script fuer lokale Entwicklung.

Aufruf:  docker compose run --rm backend python -m app.seed

Legt an (nur falls noch nicht vorhanden):
- Superadmin
- ein normaler Test-User
"""

from __future__ import annotations

import os

from sqlmodel import Session, select

from dms_core.config import settings
from dms_core.db import engine
from dms_core.models.user import User
from dms_core.security import hash_password

ADMIN_EMAIL = "admin@dms.local"
TEST_EMAIL = "test@dms.local"


def _seed_password(env_var: str, dev_default: str) -> str:
    """Seed-Passwort aus der Umgebung lesen.

    In production MUSS die Env-Variable gesetzt sein (sonst RuntimeError) — der
    Dev-Default verhindert versehentlich schwache Passwoerter in Prod.
    """
    value = os.environ.get(env_var)
    if value:
        return value
    if settings.environment == "production":
        raise RuntimeError(f"{env_var} muss in production gesetzt sein")
    return dev_default


ADMIN_PASSWORD = _seed_password("SEED_ADMIN_PASSWORD", "adminpass123")
TEST_PASSWORD = _seed_password("SEED_TEST_PASSWORD", "testpass123")


def _get_or_create_user(
    session: Session, email: str, *, full_name: str, password: str, superadmin: bool = False
) -> User:
    user = session.exec(select(User).where(User.email == email)).first()
    if user:
        return user
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_superadmin=superadmin,
    )
    session.add(user)
    session.flush()
    print(f"  + User {email}")
    return user


def main() -> None:
    print("Seeding …")
    with Session(engine) as session:
        _get_or_create_user(
            session, ADMIN_EMAIL, full_name="Admin", password=ADMIN_PASSWORD, superadmin=True
        )
        _get_or_create_user(session, TEST_EMAIL, full_name="Test User", password=TEST_PASSWORD)
        session.commit()

    # Passwoerter NICHT im Klartext ausgeben (Schulter-Surfing / Logs).
    print("\nFertig. Login (Passwoerter siehe SEED_*_PASSWORD bzw. Dev-Default):")
    print(f"  Admin : {ADMIN_EMAIL} / *****")
    print(f"  Test  : {TEST_EMAIL} / *****")


if __name__ == "__main__":
    main()
