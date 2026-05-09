"""AI-2 — Mentor Match Engine.

5-dimension scoring (Blueprint §7 AI-2), each scaled 0–20 → max 100:

  * skill_alignment       — Jaccard overlap of candidate.skills vs
                            mentor.skills, scaled.
  * availability          — (threshold - active_mentees) × (20/threshold).
  * reputation            — historical_completion_rate × 20.
  * college_familiarity   — same college → 20, same state → 10, else 5.
  * response_latency      — bucketed against avg_response_hours on
                            mentor_assignments.

Top-3 by total score are returned. GPT-4o produces a 1-sentence
recommendation reason per mentor; if AI is down we fall back to a
rule-templated reason ("Best skill overlap (60%)…").

Caching: Redis 1h TTL keyed on (referral_id?, sorted_skills,
college_id, excluded_ids) — stable across the same form's lifetime
without bloating the cache when minor edits happen.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure import azure_openai, redis_client
from app.modules.referral.models import College, MentorThresholdConfig
from app.shared.exceptions import (
    AzureOpenAiError,
    AzureOpenAiQuotaExceededError,
)

logger = logging.getLogger("nexhire.ai.mentor_matcher")

MODEL_TOUCHPOINT = "MENTOR_MATCH"
CACHE_TTL_SECONDS = 60 * 60  # 1h


# ────────────────────────────────────────────────────────────────────
# Output shapes.
# ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class RadarScores:
    skill: int
    availability: int
    reputation: int
    familiarity: int
    responsiveness: int

    @property
    def total(self) -> int:
        return (
            self.skill
            + self.availability
            + self.reputation
            + self.familiarity
            + self.responsiveness
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "skill": self.skill,
            "availability": self.availability,
            "reputation": self.reputation,
            "familiarity": self.familiarity,
            "responsiveness": self.responsiveness,
        }


@dataclass(frozen=True, slots=True)
class MentorRecommendation:
    user_id: UUID
    full_name: str
    email: str
    active_mentees: int
    threshold: int
    radar: RadarScores
    match_score: int  # alias of radar.total, for frontend convenience
    reason: str
    ai_reason: bool  # False when GPT-4o was unavailable + we fell back


@dataclass(frozen=True, slots=True)
class MatchInput:
    candidate_skills: list[str]
    college_id: UUID
    excluded_mentor_ids: list[UUID] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────
# Scoring helpers (pure).
# ────────────────────────────────────────────────────────────────────
def _normalize_skill(s: str) -> str:
    return s.strip().lower()


def _score_skill(candidate: list[str], mentor: list[str]) -> int:
    """Jaccard similarity → 0–20. Empty mentor skills returns 0."""
    cand = {_normalize_skill(s) for s in candidate if s.strip()}
    ment = {_normalize_skill(s) for s in mentor if s.strip()}
    if not cand or not ment:
        return 0
    intersection = len(cand & ment)
    union = len(cand | ment)
    if union == 0:
        return 0
    return round((intersection / union) * 20)


def _score_availability(active_mentees: int, threshold: int) -> int:
    if threshold <= 0:
        return 0
    return max(0, min(20, round((threshold - active_mentees) * (20 / threshold))))


def _score_reputation(completion_rate: float | None) -> int:
    """`completion_rate` is 0.0–1.0; None → neutral 12pts."""
    if completion_rate is None:
        return 12
    return max(0, min(20, round(completion_rate * 20)))


def _score_familiarity(
    *, mentor_states: list[str], candidate_state: str | None
) -> int:
    if candidate_state is None:
        return 5
    if candidate_state in mentor_states:
        return 20  # mentored from the same college's state historically
    return 5


def _score_response_speed(avg_hours: float | None) -> int:
    if avg_hours is None:
        return 12  # neutral until we have data
    if avg_hours < 2:
        return 20
    if avg_hours < 6:
        return 15
    if avg_hours < 12:
        return 10
    if avg_hours < 24:
        return 5
    return 0


# ────────────────────────────────────────────────────────────────────
# Cache key.
# ────────────────────────────────────────────────────────────────────
def _cache_key(input_: MatchInput) -> str:
    sorted_skills = sorted(_normalize_skill(s) for s in input_.candidate_skills)
    sorted_excluded = sorted(str(u) for u in input_.excluded_mentor_ids)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "skills": sorted_skills,
                "college": str(input_.college_id),
                "excluded": sorted_excluded,
            }
        ).encode("utf-8")
    ).hexdigest()[:16]
    return redis_client.k("ai", "mentor_match", fingerprint)


# ────────────────────────────────────────────────────────────────────
# Public entry — `suggest_mentors`.
# ────────────────────────────────────────────────────────────────────
async def suggest_mentors(
    session: AsyncSession,
    *,
    input_: MatchInput,
    top_n: int = 3,
) -> list[MentorRecommendation]:
    cache_key = _cache_key(input_)
    cached = await _get_cache(cache_key)
    if cached is not None:
        return cached

    college = (
        await session.execute(
            text(
                "SELECT canonical_name, location_state FROM colleges "
                "WHERE id = :id"
            ).bindparams(id=input_.college_id)
        )
    ).mappings().one_or_none()
    candidate_state = college["location_state"] if college else None

    threshold = (
        await session.execute(
            text(
                "SELECT max_mentees FROM mentor_threshold_config "
                "WHERE is_current = true"
            )
        )
    ).scalar_one()
    threshold = int(threshold)

    rows = (
        await session.execute(
            text(
                """
                SELECT u.id,
                       u.full_name,
                       u.email,
                       COALESCE(
                           (SELECT COUNT(*) FROM mentor_assignments ma
                              WHERE ma.mentor_id = u.id
                                AND ma.status = 'ACCEPTED'),
                           0
                       ) AS active_mentees,
                       (
                         SELECT AVG(
                             CASE WHEN ma.status = 'ACCEPTED' THEN 1.0 ELSE 0.0 END
                         )
                         FROM mentor_assignments ma
                         WHERE ma.mentor_id = u.id
                       ) AS completion_rate,
                       (
                         SELECT AVG(
                             EXTRACT(EPOCH FROM (ma.responded_at - ma.assigned_at)) / 3600.0
                         )
                         FROM mentor_assignments ma
                         WHERE ma.mentor_id = u.id
                           AND ma.responded_at IS NOT NULL
                       ) AS avg_response_hours,
                       COALESCE(
                           (SELECT array_agg(DISTINCT c.location_state)
                              FROM referrals r
                              JOIN colleges c ON c.id = r.college_id
                              WHERE r.mentor_id = u.id),
                           ARRAY[]::text[]
                       ) AS mentor_states,
                       u.skills AS skills
                FROM users u
                WHERE u.can_mentor = true
                  AND u.is_active = true
                  AND (u.out_of_office_until IS NULL OR u.out_of_office_until <= NOW())
                """
            )
        )
    ).mappings().all()

    excluded = {str(u) for u in input_.excluded_mentor_ids}
    candidates: list[MentorRecommendation] = []
    for row in rows:
        if str(row["id"]) in excluded:
            continue
        if int(row["active_mentees"]) >= threshold:
            continue  # full mentors not surfaced

        radar = RadarScores(
            skill=_score_skill(input_.candidate_skills, _mentor_skills(row)),
            availability=_score_availability(
                int(row["active_mentees"]), threshold
            ),
            reputation=_score_reputation(
                float(row["completion_rate"])
                if row["completion_rate"] is not None
                else None
            ),
            familiarity=_score_familiarity(
                mentor_states=list(row["mentor_states"] or []),
                candidate_state=candidate_state,
            ),
            responsiveness=_score_response_speed(
                float(row["avg_response_hours"])
                if row["avg_response_hours"] is not None
                else None
            ),
        )

        candidates.append(
            MentorRecommendation(
                user_id=row["id"],
                full_name=row["full_name"],
                email=row["email"],
                active_mentees=int(row["active_mentees"]),
                threshold=threshold,
                radar=radar,
                match_score=radar.total,
                reason=_rule_reason(radar),  # may be replaced by GPT-4o below
                ai_reason=False,
            )
        )

    candidates.sort(key=lambda r: r.match_score, reverse=True)
    top = candidates[:top_n]
    if not top:
        await _set_cache(cache_key, [])
        return []

    enriched = await _add_ai_reasons(top, candidate_skills=input_.candidate_skills)
    await _set_cache(cache_key, enriched)
    return enriched


def _mentor_skills(row: Any) -> list[str]:
    """Reads `users.skills` (JSONB list[str]).

    Mentors set their own skills via `PUT /auth/me/skills`; HR/PO can
    push bulk seeds for legacy users. Empty list is fine — `_score_skill`
    just returns 0 for that mentor and the other four radar axes drive
    the ranking.
    """
    raw = row.get("skills") if hasattr(row, "get") else row["skills"]
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(s).lower() for s in raw if s]
    return []


def _rule_reason(radar: RadarScores) -> str:
    """Used as fallback when AI is unavailable + as a fallback default
    before AI enrichment overrides it.
    """
    parts: list[str] = []
    if radar.availability >= 15:
        parts.append("plenty of capacity")
    if radar.reputation >= 16:
        parts.append("strong completion track record")
    if radar.familiarity >= 15:
        parts.append("has mentored from this college's state")
    if radar.responsiveness >= 15:
        parts.append("fast historical response")
    if not parts:
        return "Available; balanced score across criteria."
    return "Match reasons: " + ", ".join(parts) + "."


async def _add_ai_reasons(
    recommendations: list[MentorRecommendation],
    *,
    candidate_skills: list[str],
) -> list[MentorRecommendation]:
    cfg = get_settings()
    if not cfg.azure_openai_endpoint or not recommendations:
        return recommendations

    payload = {
        "candidate_skills": candidate_skills,
        "mentors": [
            {
                "name": r.full_name,
                "match_score": r.match_score,
                "active_mentees": r.active_mentees,
                "threshold": r.threshold,
                "radar": r.radar.to_dict(),
            }
            for r in recommendations
        ],
    }
    system = (
        "You write one-sentence mentor recommendation rationales for an "
        "internship referral form. For EACH mentor in the input, return a "
        "JSON array of objects {name, reason}. Reasons must be specific, "
        "neutral, and avoid fabrication. Do not infer attributes not in "
        "the input."
    )
    try:
        client = azure_openai.get_client()
        response = await azure_openai.call_with_retry(
            "mentor_match_reason",
            client.chat.completions.create,
            model=cfg.azure_openai_deployment_gpt4o,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=400,
            timeout=12.0,
        )
        text_response = (response.choices[0].message.content or "").strip()
        parsed = json.loads(text_response)
        reasons_by_name = {
            item.get("name"): item.get("reason", "")
            for item in (parsed.get("reasons", []) or parsed.get("data", []) or [])
        }
    except (AzureOpenAiError, AzureOpenAiQuotaExceededError, json.JSONDecodeError):
        logger.warning("nexhire.ai.mentor_matcher.reason_unavailable")
        return recommendations
    except Exception:
        logger.exception("nexhire.ai.mentor_matcher.reason_unexpected")
        return recommendations

    return [
        MentorRecommendation(
            user_id=r.user_id,
            full_name=r.full_name,
            email=r.email,
            active_mentees=r.active_mentees,
            threshold=r.threshold,
            radar=r.radar,
            match_score=r.match_score,
            reason=reasons_by_name.get(r.full_name, r.reason),
            ai_reason=r.full_name in reasons_by_name,
        )
        for r in recommendations
    ]


# ────────────────────────────────────────────────────────────────────
# Cache helpers.
# ────────────────────────────────────────────────────────────────────
async def _get_cache(key: str) -> list[MentorRecommendation] | None:
    try:
        client = await redis_client.get_client()
        raw = await client.get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        items = json.loads(raw)
        return [
            MentorRecommendation(
                user_id=UUID(item["user_id"]),
                full_name=item["full_name"],
                email=item["email"],
                active_mentees=item["active_mentees"],
                threshold=item["threshold"],
                radar=RadarScores(**item["radar"]),
                match_score=item["match_score"],
                reason=item["reason"],
                ai_reason=item["ai_reason"],
            )
            for item in items
        ]
    except (KeyError, ValueError, TypeError):
        return None


async def _set_cache(key: str, values: list[MentorRecommendation]) -> None:
    payload = json.dumps(
        [
            {
                "user_id": str(v.user_id),
                "full_name": v.full_name,
                "email": v.email,
                "active_mentees": v.active_mentees,
                "threshold": v.threshold,
                "radar": v.radar.to_dict(),
                "match_score": v.match_score,
                "reason": v.reason,
                "ai_reason": v.ai_reason,
            }
            for v in values
        ]
    )
    try:
        client = await redis_client.get_client()
        await client.set(key, payload, ex=CACHE_TTL_SECONDS)
    except Exception:
        return


__all__ = [
    "MODEL_TOUCHPOINT",
    "MatchInput",
    "MentorRecommendation",
    "RadarScores",
    "suggest_mentors",
]


# Suppress unused-import warning when the file is loaded standalone.
_ = College, MentorThresholdConfig
