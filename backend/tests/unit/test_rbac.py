"""RBAC matrix sanity tests — no DB, no async."""
from __future__ import annotations

import pytest

from app.modules.auth.rbac import Permission, has_permission
from app.shared.constants import UserRole


class TestRbacMatrix:
    def test_referrer_can_submit(self) -> None:
        assert has_permission(UserRole.REFERRER, Permission.SUBMIT_REFERRAL)

    def test_referrer_cannot_approve(self) -> None:
        assert not has_permission(
            UserRole.REFERRER, Permission.APPROVE_REJECT_REFERRAL
        )

    def test_only_program_owner_can_override_cooling(self) -> None:
        for role in UserRole:
            should = role is UserRole.PROGRAM_OWNER
            assert (
                has_permission(role, Permission.OVERRIDE_COOLING_PERIOD) is should
            ), f"{role} cooling-override permission incorrect"

    def test_system_role_has_no_permissions(self) -> None:
        # The reserved AI sentinel must NEVER hold human permissions
        # (decision A2). If this ever fails, audit assumptions break.
        for permission in Permission:
            assert not has_permission(UserRole.SYSTEM, permission), (
                f"SYSTEM role unexpectedly granted {permission}"
            )

    def test_three_actors_can_terminate(self) -> None:
        # Decision A20: candidate, HR, mentor can each initiate termination.
        for role in (UserRole.CANDIDATE, UserRole.HR, UserRole.MENTOR):
            assert has_permission(role, Permission.INITIATE_TERMINATION), (
                f"{role} should be able to initiate termination"
            )

    @pytest.mark.parametrize(
        "role",
        [UserRole.IT_AD, UserRole.ADMIN, UserRole.PROGRAM_OWNER],
    )
    def test_only_specific_roles_provision_or_admin(self, role: UserRole) -> None:
        # Cross-check that role-specific powers didn't leak.
        if role is UserRole.IT_AD:
            assert has_permission(role, Permission.PROVISION_AD_ACCOUNT)
            assert not has_permission(role, Permission.MANAGE_BADGE_ACCESS)
        elif role is UserRole.ADMIN:
            assert has_permission(role, Permission.MANAGE_BADGE_ACCESS)
            assert not has_permission(role, Permission.PROVISION_AD_ACCOUNT)
        else:
            assert has_permission(role, Permission.SYSTEM_CONFIGURATION)
