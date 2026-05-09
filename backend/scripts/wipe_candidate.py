"""Dev-only utility: wipe everything tied to a single candidate email.

Used to recycle a test email through the end-to-end onboarding flow
without colliding with half-broken legacy rows from earlier test runs.
NOT exposed via HTTP — intentionally CLI-only so it can't be hit from
a deployed app.

Usage:
    cd backend
    uv run python scripts/wipe_candidate.py <email>
    uv run python scripts/wipe_candidate.py <email> --yes   # skip prompt

Deletes (in dependency-safe order, single transaction):
    action_tokens, notifications, referral_stage_history,
    ai_auto_actions, ai_parse_results, risk_profiles,
    duplicate_check_results, joining_forms, nda_records,
    mentor_assignments, cooling_period_overrides, tasks, documents
    (resume + certificate), interns, referrals, the candidate's user.

Leaves alone:
    audit_events (kept for history), outbox_events (harmless),
    other users (referrer, mentors), other candidates' rows.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

# Make `app.*` imports work regardless of how the script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import ColumnElement, delete, or_, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.infrastructure.database import (  # noqa: E402
    dispose_engine,
    get_sessionmaker,
)
from app.modules.auth.models import ActionToken, User  # noqa: E402
from app.modules.nda.models import NdaRecord  # noqa: E402
from app.modules.onboarding.models import Intern, JoiningForm  # noqa: E402
from app.modules.referral.models import (  # noqa: E402
    AiAutoAction,
    AiParseResult,
    CoolingPeriodOverride,
    Document,
    DuplicateCheckResult,
    MentorAssignment,
    Notification,
    Referral,
    ReferralStageHistory,
    RiskProfile,
    Task,
)
from app.shared.constants import UserRole  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("wipe_candidate")


async def _wipe(email: str, *, skip_prompt: bool) -> int:
    email = email.strip().lower()
    factory = get_sessionmaker()

    async with factory() as session:
        # ── Lookup phase ─────────────────────────────────────────
        async with session.begin():
            user = (
                await session.execute(
                    select(User).where(
                        User.email == email,
                        User.role == UserRole.CANDIDATE.value,
                    )
                )
            ).scalar_one_or_none()
            referrals = list(
                (
                    await session.execute(
                        select(Referral).where(Referral.candidate_email == email)
                    )
                ).scalars()
            )
            intern_query = select(Intern).where(
                Intern.referral_id.in_([r.id for r in referrals])
            ) if referrals else None
            interns_by_referral: list[Intern] = (
                list((await session.execute(intern_query)).scalars())
                if intern_query is not None
                else []
            )
            interns_by_user: list[Intern] = (
                list(
                    (
                        await session.execute(
                            select(Intern).where(Intern.user_id == user.id)
                        )
                    ).scalars()
                )
                if user is not None
                else []
            )
            # Dedupe.
            interns: list[Intern] = list(
                {i.id: i for i in interns_by_referral + interns_by_user}.values()
            )

        if user is None and not referrals and not interns:
            logger.info("Nothing to wipe — no rows match email %r.", email)
            return 0

        logger.info("Will wipe for email %r:", email)
        logger.info("  user           : %s", user.id if user else "(none)")
        logger.info("  referrals      : %d", len(referrals))
        for r in referrals:
            logger.info("    - %s  status=%s", r.id, r.status)
        logger.info("  interns        : %d", len(interns))
        for i in interns:
            logger.info(
                "    - %s  status=%s  nw_id=%s",
                i.id,
                i.status,
                i.non_worker_id,
            )

        if not skip_prompt:
            answer = input("\nType 'YES' to permanently delete all of the above: ")
            if answer.strip() != "YES":
                logger.info("Aborted — no changes made.")
                return 1

        intern_ids: list[UUID] = [i.id for i in interns]
        referral_ids: list[UUID] = [r.id for r in referrals]
        resume_doc_ids: list[UUID] = [
            r.resume_document_id for r in referrals
            if r.resume_document_id is not None
        ]
        cert_blob_keys: list[str] = [
            f"certificates/{iid}.pdf" for iid in intern_ids
        ]

        # ── Delete phase ─────────────────────────────────────────
        async with session.begin():
            counts: dict[str, int] = {}

            def any_clauses(*clauses: ColumnElement[bool] | None) -> ColumnElement[bool] | None:
                non_null = [c for c in clauses if c is not None]
                if not non_null:
                    return None
                if len(non_null) == 1:
                    return non_null[0]
                return or_(*non_null)

            counts["action_tokens"] = await _delete_where(
                session, ActionToken,
                any_clauses(
                    _in(ActionToken.intern_id, intern_ids),
                    _in(ActionToken.referral_id, referral_ids),
                    (ActionToken.actor_user_id == user.id) if user else None,
                ),
            )
            counts["notifications"] = await _delete_where(
                session, Notification,
                _in(Notification.referral_id, referral_ids),
            )
            counts["referral_stage_history"] = await _delete_where(
                session, ReferralStageHistory,
                _in(ReferralStageHistory.referral_id, referral_ids),
            )
            counts["ai_auto_actions"] = await _delete_where(
                session, AiAutoAction,
                any_clauses(
                    _in(AiAutoAction.referral_id, referral_ids),
                    _in(AiAutoAction.intern_id, intern_ids),
                ),
            )
            counts["ai_parse_results"] = await _delete_where(
                session, AiParseResult,
                _in(AiParseResult.referral_id, referral_ids),
            )
            counts["risk_profiles"] = await _delete_where(
                session, RiskProfile,
                _in(RiskProfile.referral_id, referral_ids),
            )
            counts["duplicate_check_results"] = await _delete_where(
                session, DuplicateCheckResult,
                _in(DuplicateCheckResult.referral_id, referral_ids),
            )
            counts["joining_forms"] = await _delete_where(
                session, JoiningForm,
                _in(JoiningForm.intern_id, intern_ids),
            )
            counts["nda_records"] = await _delete_where(
                session, NdaRecord,
                _in(NdaRecord.intern_id, intern_ids),
            )
            counts["mentor_assignments"] = await _delete_where(
                session, MentorAssignment,
                _in(MentorAssignment.referral_id, referral_ids),
            )
            counts["cooling_period_overrides"] = await _delete_where(
                session, CoolingPeriodOverride,
                _in(CoolingPeriodOverride.referral_id, referral_ids),
            )
            counts["tasks"] = await _delete_where(
                session, Task,
                any_clauses(
                    _in(Task.referral_id, referral_ids),
                    _in(Task.intern_id, intern_ids),
                ),
            )
            counts["documents"] = await _delete_where(
                session, Document,
                any_clauses(
                    _in(Document.id, resume_doc_ids),
                    _in(Document.azure_blob_key, cert_blob_keys),
                ),
            )
            # Now the parents.
            counts["interns"] = await _delete_where(
                session, Intern, _in(Intern.id, intern_ids),
            )
            counts["referrals"] = await _delete_where(
                session, Referral, _in(Referral.id, referral_ids),
            )
            counts["users"] = await _delete_where(
                session, User,
                (User.id == user.id) if user else None,
            )

    logger.info("\nDeleted (transaction committed):")
    for table, n in counts.items():
        logger.info("  %-26s %d", table, n)
    return 0


def _in(column, values: Iterable | None) -> ColumnElement[bool] | None:
    """Build a `column IN (...)` clause, returning None when the
    value list is empty (so callers can skip the delete entirely)."""
    if not values:
        return None
    materialised = list(values)
    if not materialised:
        return None
    return column.in_(materialised)


async def _delete_where(
    session: AsyncSession, model, where_clause: ColumnElement[bool] | None
) -> int:
    if where_clause is None:
        return 0
    result = await session.execute(delete(model).where(where_clause))
    return result.rowcount or 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Hard-delete every row tied to a candidate email."
    )
    p.add_argument("email", help="Candidate email to wipe (case-insensitive).")
    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt (for scripted runs).",
    )
    return p.parse_args()


async def _main() -> int:
    args = _parse_args()
    try:
        return await _wipe(args.email, skip_prompt=args.yes)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
