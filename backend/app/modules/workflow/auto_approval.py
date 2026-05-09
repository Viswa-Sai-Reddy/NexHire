"""F-35 Auto-Approval Engine.

Trigger: `MentorAccepted` event (mentor clicked Accept).

Mentor acceptance is the sole gate: every accepted referral is
auto-approved and the candidate receives the joining-form magic link
immediately. The six AI checks still run for audit and to seed the
2-hour recall window so HR can intervene if a flagged case needs to be
revisited.

Checks recorded on the `ai_auto_actions` row:
  1. PAN duplicate match.
  2. Fuzzy duplicate score >= 0.6.
  3. Risk score > 25.
  4. AI parse confidence < 0.82 (per field).
  5. Missing mandatory fields.
  6. Resume red flags.

Outcome:
  * Always → status = APPROVED, approved_by_label = AI_AUTO_APPROVAL.
             Publishes ReferralAutoApproved (recall window) and
             ReferralApproved (onboarding provisions the candidate).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.referral.models import (
    AiAutoAction,
    AiParseResult,
    DuplicateCheckResult,
    Referral,
    ReferralStageHistory,
    RiskProfile,
)
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    ReferralStatus,
)
from app.shared.domain_events import (
    ReferralApproved,
    ReferralAutoApproved,
)
from app.shared.value_objects import ReferralId, UserId

logger = logging.getLogger("nexhire.workflow.auto_approval")

# Thresholds — Blueprint §18.3.
MAX_RISK_SCORE = 25
MIN_AI_PARSE_CONFIDENCE = 0.82
MAX_FUZZY_DUPLICATE_SCORE = 0.59  # < 0.6 = below WARN

# Recall window — decision §17.13 + spec §18.6.
AUTO_APPROVE_RECALL_HOURS = 2


HrRecommendation = Literal[
    "LIKELY_APPROVE",
    "LIKELY_REJECT",
    "REVIEW_CAREFULLY",
    "REQUIRES_REVIEW",
]


@dataclass(frozen=True, slots=True)
class AutoApprovalResult:
    decision: Literal["AUTO_APPROVED"]
    flags: tuple[str, ...] = ()
    hr_recommendation: HrRecommendation | None = None
    conditions_met: tuple[str, ...] = ()
    auto_action_id: UUID | None = None
    recall_until: datetime | None = None


@dataclass(slots=True)
class _Inputs:
    referral: Referral
    risk: RiskProfile | None
    duplicate: DuplicateCheckResult | None
    resume_parse: AiParseResult | None


# ────────────────────────────────────────────────────────────────────
# Public entry.
# ────────────────────────────────────────────────────────────────────
async def evaluate_and_route(
    session: AsyncSession,
    *,
    referral_id: UUID,
) -> AutoApprovalResult:
    inputs = await _load_inputs(session, referral_id)
    if inputs is None:
        raise RuntimeError(f"Referral {referral_id} missing in auto-approval.")

    flags: list[str] = []
    conditions: list[str] = []

    # CHECK 1: PAN duplicate.
    if (
        inputs.duplicate is not None
        and inputs.duplicate.match_type == "PAN_EXACT"
    ):
        flags.append("PAN duplicate detected — definite re-submission.")
    else:
        conditions.append("No PAN duplicate.")

    # CHECK 2: Fuzzy duplicate score.
    if inputs.duplicate is not None and inputs.duplicate.similarity_score > MAX_FUZZY_DUPLICATE_SCORE:
        flags.append(
            f"Possible fuzzy duplicate "
            f"({int(inputs.duplicate.similarity_score * 100)}% match)."
        )
    else:
        conditions.append("No fuzzy-duplicate flag.")

    # CHECK 3: Risk score.
    if inputs.risk is not None and inputs.risk.risk_score > MAX_RISK_SCORE:
        flags.append(
            f"Risk score {inputs.risk.risk_score} exceeds "
            f"threshold ({MAX_RISK_SCORE})."
        )
    else:
        conditions.append("Risk score within threshold.")

    # CHECK 4: AI parse confidence.
    low_confidence_fields = _low_confidence_fields(inputs.resume_parse)
    if low_confidence_fields:
        flags.append(
            "Low confidence on: " + ", ".join(low_confidence_fields)
        )
    else:
        conditions.append("All AI-parsed fields above confidence threshold.")

    # CHECK 5: Mandatory fields complete.
    missing = _missing_mandatory_fields(inputs.referral)
    if missing:
        flags.append("Missing fields: " + ", ".join(missing))
    else:
        conditions.append("All mandatory fields present.")

    # CHECK 6: Resume red flags.
    red_flags = _resume_red_flags(inputs.resume_parse)
    if red_flags:
        flags.extend(red_flags)
    else:
        conditions.append("No resume red flags.")

    return await _auto_approve(
        session,
        referral=inputs.referral,
        conditions=conditions,
        flags=flags,
    )


# ────────────────────────────────────────────────────────────────────
# Decision branches.
# ────────────────────────────────────────────────────────────────────
async def _auto_approve(
    session: AsyncSession,
    *,
    referral: Referral,
    conditions: list[str],
    flags: list[str],
) -> AutoApprovalResult:
    now = datetime.now(UTC)
    recall_until = now + timedelta(hours=AUTO_APPROVE_RECALL_HOURS)

    # FSM: MENTOR_ACCEPTED → APPROVED. Mentor acceptance is the sole
    # gate; flags are recorded for audit and recall, not for routing.
    referral.status = ReferralStatus.APPROVED.value
    referral.current_stage = ReferralStatus.APPROVED.value
    referral.stage_entered_at = now
    referral.approved_at = now
    referral.approved_by = AI_SYSTEM_USER_ID
    referral.approved_by_label = "AI_AUTO_APPROVAL"
    referral.updated_at = now

    auto_action = AiAutoAction(
        action_type="AUTO_APPROVE",
        decision="EXECUTED",
        referral_id=referral.id,
        conditions_met=conditions,
        flags=flags or None,
    )
    session.add(auto_action)
    history_reason = (
        "AI auto-approved with flags — see ai_auto_actions for detail."
        if flags
        else "Clean case — AI auto-approved."
    )
    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.MENTOR_ACCEPTED.value,
            to_status=ReferralStatus.APPROVED.value,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason=history_reason,
            payload={"flags": flags} if flags else None,
        )
    )
    await session.flush()

    await audit.publish(
        event_type="REFERRAL_AUTO_APPROVED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "auto_action_id": str(auto_action.id),
            "conditions_met": conditions,
            "flags": flags,
            "recall_until": recall_until.isoformat(),
        },
        session=session,
    )

    bus = get_bus()
    await bus.publish(
        ReferralAutoApproved(
            referral_id=ReferralId(referral.id),
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
            recall_until=recall_until,
        )
    )
    # ReferralApproved is the canonical "approval happened" event;
    # onboarding subscribes to it to provision the candidate user +
    # first magic link.
    await bus.publish(
        ReferralApproved(
            referral_id=ReferralId(referral.id),
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
            approved_by_user_id=UserId(AI_SYSTEM_USER_ID),
            approved_by_label="AI_AUTO_APPROVAL",
        )
    )

    return AutoApprovalResult(
        decision="AUTO_APPROVED",
        flags=tuple(flags),
        conditions_met=tuple(conditions),
        auto_action_id=auto_action.id,
        recall_until=recall_until,
    )


# ────────────────────────────────────────────────────────────────────
# Inputs loader.
# ────────────────────────────────────────────────────────────────────
async def _load_inputs(
    session: AsyncSession, referral_id: UUID
) -> _Inputs | None:
    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        return None

    risk = (
        await session.execute(
            select(RiskProfile).where(RiskProfile.referral_id == referral.id)
        )
    ).scalar_one_or_none()
    duplicate = (
        await session.execute(
            select(DuplicateCheckResult)
            .where(DuplicateCheckResult.referral_id == referral.id)
            .order_by(DuplicateCheckResult.checked_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    parse = (
        await session.execute(
            select(AiParseResult)
            .where(
                AiParseResult.referral_id == referral.id,
                AiParseResult.ai_touchpoint == "RESUME_PARSE",
            )
            .order_by(AiParseResult.parsed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return _Inputs(
        referral=referral,
        risk=risk,
        duplicate=duplicate,
        resume_parse=parse,
    )


# ────────────────────────────────────────────────────────────────────
# Per-check helpers.
# ────────────────────────────────────────────────────────────────────
def _low_confidence_fields(parse: AiParseResult | None) -> list[str]:
    """Return field names whose AI confidence is below the threshold.

    A missing parse row (no resume uploaded) does NOT flag — we only
    surface a confidence concern when AI-1 actually ran.
    """
    if parse is None or not parse.confidence_scores:
        return []
    low: list[str] = []
    for field_name, value in parse.confidence_scores.items():
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if score < MIN_AI_PARSE_CONFIDENCE:
            low.append(field_name)
    return sorted(low)


def _missing_mandatory_fields(referral: Referral) -> list[str]:
    missing: list[str] = []
    if not referral.candidate_name:
        missing.append("candidate_name")
    if not referral.candidate_email:
        missing.append("candidate_email")
    if not referral.candidate_phone:
        missing.append("candidate_phone")
    if not referral.project_title:
        missing.append("project_title")
    if not referral.joining_location:
        missing.append("joining_location")
    if not referral.internship_start_date or not referral.internship_end_date:
        missing.append("internship_dates")
    return missing


def _resume_red_flags(parse: AiParseResult | None) -> list[str]:
    if parse is None or not parse.raw_output:
        return []
    raw = parse.raw_output.get("red_flags") if isinstance(parse.raw_output, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


__all__ = [
    "AUTO_APPROVE_RECALL_HOURS",
    "AutoApprovalResult",
    "HrRecommendation",
    "evaluate_and_route",
]


# Suppress unused-import warning when the file is loaded standalone.
_ = field
