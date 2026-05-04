"""Public AiService façade.

Other modules import from here, never directly from `resume_parser` /
`risk_profiler` / `duplicate_detector`. This is the single boundary
that:
  * Persists every AI invocation to `ai_parse_results` (success + failure).
  * Tracks tokens + latency for cost monitoring.
  * Provides one place to plug in caching, kill-switches, A/B prompts.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai import (
    duplicate_detector,
    mentor_matcher,
    resume_parser,
    risk_profiler,
)
from app.modules.referral.models import (
    AiParseResult,
    DuplicateCheckResult,
    RiskProfile,
)

logger = logging.getLogger("nexhire.ai.service")

_RESUME_MODEL_VERSION = "gpt-4o:resume-parse:v1"
_RISK_MODEL_VERSION = "rules:risk:v1+gpt-4o:narrative:v1"
_DUP_MODEL_VERSION = "deterministic:fuzzy-jaro-winkler:v1"
_MATCHER_MODEL_VERSION = "rules:5-dim:v1+gpt-4o:reason:v1"


# ────────────────────────────────────────────────────────────────────
# Resume parsing.
# ────────────────────────────────────────────────────────────────────
async def parse_resume_and_persist(
    session: AsyncSession,
    *,
    referral_id: UUID | None,
    file_bytes: bytes,
    mime_type: str,
) -> resume_parser.ParseResult:
    result = await resume_parser.parse_resume(file_bytes=file_bytes, mime_type=mime_type)

    session.add(
        AiParseResult(
            ai_touchpoint=resume_parser.MODEL_TOUCHPOINT,
            model_version=_RESUME_MODEL_VERSION,
            raw_output=result.raw or {},
            referral_id=referral_id,
            azure_openai_request_id=result.azure_request_id,
            confidence_scores=result.confidence_scores or None,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
            succeeded=result.succeeded,
            degradation_reason=result.degradation_reason,
        )
    )
    return result


# ────────────────────────────────────────────────────────────────────
# Risk profile.
# ────────────────────────────────────────────────────────────────────
async def assess_risk_and_persist(
    session: AsyncSession,
    *,
    referral_id: UUID,
    form: risk_profiler.RiskInput,
) -> risk_profiler.RiskProfileResult:
    result = await risk_profiler.assess(form)

    session.add(
        RiskProfile(
            referral_id=referral_id,
            risk_score=result.risk_score,
            factors=result.factors_payload(),
            narrative=result.narrative or None,
        )
    )
    session.add(
        AiParseResult(
            ai_touchpoint=risk_profiler.MODEL_TOUCHPOINT,
            model_version=_RISK_MODEL_VERSION,
            raw_output={
                "risk_score": result.risk_score,
                "classification": result.classification,
                "factors": result.factors_payload(),
                "narrative": result.narrative,
            },
            referral_id=referral_id,
            succeeded=result.succeeded_ai,
            degradation_reason=None if result.succeeded_ai else "AI_NARRATIVE_UNAVAILABLE",
        )
    )
    return result


# ────────────────────────────────────────────────────────────────────
# Fuzzy dedup.
# ────────────────────────────────────────────────────────────────────
async def fuzzy_duplicate_check_and_persist(
    session: AsyncSession,
    *,
    referral_id: UUID | None,
    candidate_name: str,
    candidate_email: str,
    candidate_phone: str | None,
) -> duplicate_detector.FuzzyDuplicateResult:
    result = await duplicate_detector.fuzzy_match(
        session,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        candidate_phone=candidate_phone,
    )

    matched_id: UUID | None = None
    reasons: tuple[str, ...] = ()
    if result.matches:
        matched_id = result.matches[0].referral_id
        reasons = result.matches[0].match_reasons

    match_type = (
        "FUZZY_NAME_EMAIL_PHONE" if result.recommendation != "PASS" else "FUZZY_CLEAR"
    )
    session.add(
        DuplicateCheckResult(
            match_type=match_type,
            similarity_score=result.similarity_score,
            recommendation="CLEAR" if result.recommendation == "PASS" else result.recommendation,
            referral_id=referral_id,
            match_reasons=list(reasons),
            matched_referral_id=matched_id,
        )
    )
    session.add(
        AiParseResult(
            ai_touchpoint=duplicate_detector.MODEL_TOUCHPOINT,
            model_version=_DUP_MODEL_VERSION,
            raw_output=_serialize_dup_result(result),
            referral_id=referral_id,
            succeeded=True,
        )
    )
    return result


def _serialize_dup_result(
    result: duplicate_detector.FuzzyDuplicateResult,
) -> dict[str, Any]:
    return {
        "recommendation": result.recommendation,
        "similarity_score": result.similarity_score,
        "matches": [
            {
                "referral_id": str(m.referral_id),
                "similarity_score": m.similarity_score,
                "match_reasons": list(m.match_reasons),
                "matched_status": m.matched_status,
            }
            for m in result.matches
        ],
    }


# ────────────────────────────────────────────────────────────────────
# Mentor matcher.
# ────────────────────────────────────────────────────────────────────
async def suggest_mentors_and_persist(
    session: AsyncSession,
    *,
    referral_id: UUID | None,
    input_: mentor_matcher.MatchInput,
    top_n: int = 3,
) -> list[mentor_matcher.MentorRecommendation]:
    result = await mentor_matcher.suggest_mentors(
        session, input_=input_, top_n=top_n
    )
    session.add(
        AiParseResult(
            ai_touchpoint=mentor_matcher.MODEL_TOUCHPOINT,
            model_version=_MATCHER_MODEL_VERSION,
            raw_output={
                "candidate_skills": input_.candidate_skills,
                "college_id": str(input_.college_id),
                "excluded_mentor_ids": [str(u) for u in input_.excluded_mentor_ids],
                "recommendations": [
                    {
                        "user_id": str(r.user_id),
                        "match_score": r.match_score,
                        "radar": r.radar.to_dict(),
                        "ai_reason": r.ai_reason,
                    }
                    for r in result
                ],
            },
            referral_id=referral_id,
            succeeded=True,
        )
    )
    return result


__all__ = [
    "assess_risk_and_persist",
    "fuzzy_duplicate_check_and_persist",
    "parse_resume_and_persist",
    "suggest_mentors_and_persist",
]
