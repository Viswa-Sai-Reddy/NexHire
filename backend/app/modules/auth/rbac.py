"""Role-based access control — permission matrix from Blueprint §2.2.

Why a code-resident matrix (and not DB-stored) for v1:
  * The matrix is small (8 roles × ~30 permissions).
  * It changes rarely; when it does, change is policy and deserves a
    code review + ADR.
  * No need for runtime configuration UI — Program Owner role-mgmt
    panel (S25) only flips role assignments, not the matrix itself.

When DB-stored becomes worthwhile (multi-tenant, custom roles per org),
we replace this module — the public API is just `has_permission(...)`.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends

from app.middleware.auth import CurrentUser, Principal
from app.shared.constants import UserRole
from app.shared.exceptions import InsufficientPermissionsError


class Permission(StrEnum):
    # Referral
    SUBMIT_REFERRAL = "SUBMIT_REFERRAL"
    SELECT_OR_CHANGE_MENTOR = "SELECT_OR_CHANGE_MENTOR"
    APPROVE_REJECT_REFERRAL = "APPROVE_REJECT_REFERRAL"
    OVERRIDE_AI_DECISION = "OVERRIDE_AI_DECISION"
    VIEW_OWN_REFERRALS = "VIEW_OWN_REFERRALS"
    VIEW_ALL_REFERRALS = "VIEW_ALL_REFERRALS"
    # Mentor
    ACCEPT_REJECT_MENTORING = "ACCEPT_REJECT_MENTORING"
    REASSIGN_MENTOR = "REASSIGN_MENTOR"            # decision A14, HR-only
    # Candidate / onboarding
    COMPLETE_JOINING_FORM = "COMPLETE_JOINING_FORM"
    LOCK_JOINING_FORM = "LOCK_JOINING_FORM"
    ISSUE_NON_WORKER_ID = "ISSUE_NON_WORKER_ID"
    # Provisioning
    PROVISION_AD_ACCOUNT = "PROVISION_AD_ACCOUNT"
    MANAGE_BADGE_ACCESS = "MANAGE_BADGE_ACCESS"
    # Closure
    GENERATE_CERTIFICATE = "GENERATE_CERTIFICATE"
    INITIATE_TERMINATION = "INITIATE_TERMINATION"  # decision A20, multi-actor
    # Admin / governance
    VIEW_SLA_DASHBOARD = "VIEW_SLA_DASHBOARD"
    VIEW_AUDIT_TRAIL = "VIEW_AUDIT_TRAIL"
    SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION"
    QUERY_AI_CHATBOT = "QUERY_AI_CHATBOT"
    OVERRIDE_COOLING_PERIOD = "OVERRIDE_COOLING_PERIOD"  # PO only (RULE-CP7)
    # PII
    REVEAL_PAN = "REVEAL_PAN"                            # decision E19
    # Recall
    RECALL_AI_AUTO_ACTION = "RECALL_AI_AUTO_ACTION"


# ────────────────────────────────────────────────────────────────────
# The matrix. Each role's set is the closure of its permissions.
# Mirrors Blueprint §2.2 + the decision-log additions (A14, A20, E19).
# ────────────────────────────────────────────────────────────────────
_ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.REFERRER: frozenset(
        {
            Permission.SUBMIT_REFERRAL,
            Permission.SELECT_OR_CHANGE_MENTOR,
            Permission.VIEW_OWN_REFERRALS,
            Permission.INITIATE_TERMINATION,  # A20
        }
    ),
    UserRole.MENTOR: frozenset(
        {
            Permission.ACCEPT_REJECT_MENTORING,
            Permission.VIEW_OWN_REFERRALS,
            Permission.INITIATE_TERMINATION,  # A20
        }
    ),
    UserRole.HR: frozenset(
        {
            Permission.SUBMIT_REFERRAL,
            Permission.SELECT_OR_CHANGE_MENTOR,
            Permission.APPROVE_REJECT_REFERRAL,
            Permission.OVERRIDE_AI_DECISION,
            Permission.VIEW_ALL_REFERRALS,
            Permission.LOCK_JOINING_FORM,
            Permission.ISSUE_NON_WORKER_ID,
            Permission.GENERATE_CERTIFICATE,
            Permission.VIEW_SLA_DASHBOARD,
            Permission.VIEW_AUDIT_TRAIL,
            Permission.QUERY_AI_CHATBOT,
            Permission.REVEAL_PAN,            # E19
            Permission.RECALL_AI_AUTO_ACTION, # A21
            Permission.REASSIGN_MENTOR,       # A14
            Permission.INITIATE_TERMINATION,  # A20
        }
    ),
    UserRole.IT_AD: frozenset(
        {
            Permission.PROVISION_AD_ACCOUNT,
        }
    ),
    UserRole.ADMIN: frozenset(
        {
            Permission.MANAGE_BADGE_ACCESS,
        }
    ),
    UserRole.PROGRAM_OWNER: frozenset(
        {
            Permission.SUBMIT_REFERRAL,
            Permission.SELECT_OR_CHANGE_MENTOR,
            Permission.APPROVE_REJECT_REFERRAL,
            Permission.OVERRIDE_AI_DECISION,
            Permission.VIEW_ALL_REFERRALS,
            Permission.VIEW_SLA_DASHBOARD,
            Permission.VIEW_AUDIT_TRAIL,
            Permission.SYSTEM_CONFIGURATION,
            Permission.QUERY_AI_CHATBOT,
            Permission.OVERRIDE_COOLING_PERIOD,  # RULE-CP7
            Permission.REVEAL_PAN,
        }
    ),
    UserRole.CANDIDATE: frozenset(
        {
            Permission.COMPLETE_JOINING_FORM,
            Permission.INITIATE_TERMINATION,  # A20
        }
    ),
    # SYSTEM has no human RBAC permissions; it's the AI sentinel actor.
    UserRole.SYSTEM: frozenset(),
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in _ROLE_PERMISSIONS.get(role, frozenset())


def assert_permission(principal: Principal, *required: Permission) -> None:
    """Raise `InsufficientPermissionsError` unless principal holds ALL
    required permissions.

    Multiple permissions = "AND" (caller must have every one). For "OR"
    semantics use multiple route-level guards or compose at call-site.
    """
    role_perms = _ROLE_PERMISSIONS.get(principal.role, frozenset())
    missing = [p for p in required if p not in role_perms]
    if missing:
        raise InsufficientPermissionsError(
            details={"missing_permissions": [p.value for p in missing]}
        )


# ────────────────────────────────────────────────────────────────────
# FastAPI dependency factory.
# Usage:
#     @router.post("/referrals", dependencies=[Depends(require(Permission.SUBMIT_REFERRAL))])
#     async def submit(...): ...
# ────────────────────────────────────────────────────────────────────
def require(*permissions: Permission):  # type: ignore[no-untyped-def]
    async def dependency(principal: CurrentUser) -> Principal:
        assert_permission(principal, *permissions)
        return principal

    return dependency


def permissions_for(role: UserRole) -> Iterable[Permission]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


__all__ = [
    "Permission",
    "assert_permission",
    "has_permission",
    "permissions_for",
    "require",
]


# Suppress unused-import warning when the file is loaded standalone.
_ = Annotated, Depends
