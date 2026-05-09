"""Seed 16 demo user rows for the hackathon demo.

Idempotent: re-running updates existing rows rather than inserting duplicates.
Run after `alembic upgrade head` and before the AAD users sign in for the
first time. The login backfill at `auth/service.py:154-159` populates
`azure_oid` automatically on first sign-in once a row with the matching
email already exists.

Usage:
    cd backend
    uv run python scripts/seed_demo_users.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend project root is on sys.path so `app.*` imports work
# regardless of how the script is invoked (`python scripts/seed_...py`
# adds the script's own dir to sys.path, not the project root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.infrastructure.database import dispose_engine, get_sessionmaker  # noqa: E402
from app.modules.auth.models import User  # noqa: E402
from app.shared.constants import UserRole  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_demo_users")

DOMAIN = "karthikirisoutlook.onmicrosoft.com"
DEMO_PASSWORD = "NexHireDemo2026!"

# Hash once at module load — bcrypt is intentionally slow per-call.
_DEMO_PASSWORD_HASH = bcrypt.hashpw(
    DEMO_PASSWORD.encode("utf-8"), bcrypt.gensalt()
).decode("ascii")


def _email(local: str) -> str:
    return f"{local}@{DOMAIN}".lower()


# (local-part, full_name, role, can_mentor, skills)
DEMO_ACCOUNTS: list[tuple[str, str, UserRole, bool, list[str]]] = [
    ("po",          "Demo Program Owner",  UserRole.PROGRAM_OWNER, False, []),
    ("hr",          "Demo HR",             UserRole.HR,            False, []),
    ("referrer",    "Demo Referrer",       UserRole.REFERRER,      False, []),
    ("admin",       "Demo Admin (Badge)",  UserRole.ADMIN,         False, []),
    ("itad",        "Demo IT/AD",          UserRole.IT_AD,         False, []),
    ("mentor.lead", "Demo Mentor Lead",    UserRole.MENTOR, True, ["python", "fastapi", "postgres", "azure"]),
    ("mentor1",     "Demo Mentor 1",       UserRole.MENTOR, True, ["python", "django", "ml"]),
    ("mentor2",     "Demo Mentor 2",       UserRole.MENTOR, True, ["react", "typescript", "tailwind"]),
    ("mentor3",     "Demo Mentor 3",       UserRole.MENTOR, True, ["nodejs", "express", "mongodb"]),
    ("mentor4",     "Demo Mentor 4",       UserRole.MENTOR, True, ["java", "spring", "kafka"]),
    ("mentor5",     "Demo Mentor 5",       UserRole.MENTOR, True, ["go", "grpc", "kubernetes"]),
    ("mentor6",     "Demo Mentor 6",       UserRole.MENTOR, True, ["aws", "terraform", "devops"]),
    ("mentor7",     "Demo Mentor 7",       UserRole.MENTOR, True, ["data-science", "pytorch", "pandas"]),
    ("mentor8",     "Demo Mentor 8",       UserRole.MENTOR, True, ["ios", "swift", "swiftui"]),
    ("mentor9",     "Demo Mentor 9",       UserRole.MENTOR, True, ["android", "kotlin", "compose"]),
    ("mentor10",    "Demo Mentor 10",      UserRole.MENTOR, True, ["security", "oauth", "penetration-testing"]),
]


async def seed() -> tuple[int, int]:
    factory = get_sessionmaker()
    inserted = 0
    updated = 0
    async with factory() as session, session.begin():
        for local, full_name, role, can_mentor, skills in DEMO_ACCOUNTS:
            email = _email(local)
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    User(
                        email=email,
                        full_name=full_name,
                        role=role.value,
                        password_hash=_DEMO_PASSWORD_HASH,
                        can_mentor=can_mentor,
                        skills=list(skills),
                    )
                )
                inserted += 1
                logger.info("INSERT  %-50s  %s", email, role.value)
            else:
                existing.full_name = full_name
                existing.role = role.value
                existing.password_hash = _DEMO_PASSWORD_HASH
                existing.can_mentor = can_mentor
                existing.skills = list(skills)
                updated += 1
                logger.info("UPDATE  %-50s  %s", email, role.value)
    return inserted, updated


async def main() -> None:
    try:
        inserted, updated = await seed()
        logger.info("")
        logger.info("Seed complete: %d inserted, %d updated, %d total", inserted, updated, len(DEMO_ACCOUNTS))
        logger.info("Demo password (shared across all 16 accounts): %s", DEMO_PASSWORD)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
