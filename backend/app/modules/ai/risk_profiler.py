"""AI-3 — Eligibility & Risk Profiler.

Two-layer design (Blueprint §7):
  * **Rule engine** — deterministic, auditable. Walks RULE-E1..E5 and
    scores known risk factors (commute distance, exam-period overlap,
    education gaps).
  * **GPT-4o narrative** — converts the rule output into one short
    advisory paragraph for HR. Optional; degrades to "" if AI is down.

Output:
  RiskProfile {
    risk_score:   0–100 (sum of factor weights)
    factors:      list of {code, weight, detail}
    narrative:    str (AI-drafted, may be empty on degradation)
    classification: LOW | MEDIUM | HIGH
  }

The risk score is **not** a candidate ranking — it's a structural
review prompt for HR. Bias monitoring (Blueprint §11.2) tracks the
override rate by college tier weekly.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.config import get_settings
from app.infrastructure import azure_openai
from app.shared.exceptions import AzureOpenAiError, AzureOpenAiQuotaExceededError

logger = logging.getLogger("nexhire.ai.risk")

MODEL_TOUCHPOINT = "ELIGIBILITY_RISK"

RiskClass = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True, slots=True)
class RiskFactor:
    code: str
    weight: int
    detail: str


@dataclass(frozen=True, slots=True)
class RiskProfileResult:
    risk_score: int
    factors: tuple[RiskFactor, ...]
    classification: RiskClass
    narrative: str
    succeeded_ai: bool = True

    def factors_payload(self) -> list[dict[str, Any]]:
        return [{"code": f.code, "weight": f.weight, "detail": f.detail} for f in self.factors]


# ────────────────────────────────────────────────────────────────────
# Inputs — kept as a dataclass so we don't depend on ORM models here.
# Caller (referral.service) maps the Referral row to this shape.
# ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class RiskInput:
    candidate_name: str
    college_name: str
    college_state: str | None
    joining_location: str | None
    joining_state: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    distance_km: int | None = None
    education_gaps: tuple[str, ...] = ()
    exam_period_overlap: bool = False


# ────────────────────────────────────────────────────────────────────
# Rule engine.
# ────────────────────────────────────────────────────────────────────
def _evaluate_rules(form: RiskInput) -> list[RiskFactor]:
    factors: list[RiskFactor] = []

    # Commute / location risk (Blueprint §7 AI-3 example).
    if form.distance_km is not None and form.distance_km > 200:
        factors.append(
            RiskFactor(
                code="LONG_COMMUTE",
                weight=15,
                detail=(
                    f"College ({form.college_name}) is {form.distance_km}km from "
                    f"the joining location. Confirm commute / accommodation plan."
                ),
            )
        )
    elif (
        form.college_state
        and form.joining_state
        and form.college_state != form.joining_state
    ):
        factors.append(
            RiskFactor(
                code="DIFFERENT_STATE",
                weight=10,
                detail=(
                    f"College is in {form.college_state}; joining location is in "
                    f"{form.joining_state}. Confirm relocation arrangements."
                ),
            )
        )

    # Exam-period overlap.
    if form.exam_period_overlap:
        factors.append(
            RiskFactor(
                code="EXAM_OVERLAP",
                weight=20,
                detail="Internship dates overlap with the candidate's exam period.",
            )
        )

    # Education-history gaps.
    for gap in form.education_gaps:
        factors.append(
            RiskFactor(
                code="EDUCATION_GAP",
                weight=5,
                detail=f"Unaccounted gap in education history: {gap}.",
            )
        )

    return factors


def _classify(score: int) -> RiskClass:
    if score <= 20:
        return "LOW"
    if score <= 40:
        return "MEDIUM"
    return "HIGH"


# ────────────────────────────────────────────────────────────────────
# Narrative — best-effort GPT-4o.
# ────────────────────────────────────────────────────────────────────
_NARRATIVE_SYSTEM = (
    "You write short, neutral advisory notes for an HR reviewer. "
    "Two sentences maximum. Be specific and actionable. "
    "Never speculate beyond the provided risk factors."
)


async def _generate_narrative(
    *, candidate_name: str, factors: list[RiskFactor], score: int
) -> str:
    cfg = get_settings()
    if not cfg.azure_openai_endpoint or not factors:
        return ""

    user_payload = {
        "candidate_name": candidate_name,
        "risk_score": score,
        "factors": [
            {"code": f.code, "weight": f.weight, "detail": f.detail} for f in factors
        ],
    }

    try:
        client = azure_openai.get_client()
        response = await azure_openai.call_with_retry(
            "risk_narrative",
            client.chat.completions.create,
            model=cfg.azure_openai_deployment_gpt4o,
            messages=[
                {"role": "system", "content": _NARRATIVE_SYSTEM},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            temperature=0.2,
            max_tokens=200,
            timeout=10.0,
        )
        return (response.choices[0].message.content or "").strip()
    except (AzureOpenAiError, AzureOpenAiQuotaExceededError):
        logger.warning("nexhire.ai.risk.narrative_unavailable")
        return ""
    except Exception:  # noqa: BLE001 — narrative is best-effort
        logger.exception("nexhire.ai.risk.narrative_unexpected")
        return ""


# ────────────────────────────────────────────────────────────────────
# Public entry.
# ────────────────────────────────────────────────────────────────────
async def assess(form: RiskInput) -> RiskProfileResult:
    factors = _evaluate_rules(form)
    score = sum(f.weight for f in factors)
    classification = _classify(score)
    narrative = await _generate_narrative(
        candidate_name=form.candidate_name, factors=factors, score=score
    )

    return RiskProfileResult(
        risk_score=score,
        factors=tuple(factors),
        classification=classification,
        narrative=narrative,
        succeeded_ai=bool(narrative) or not factors,
    )


__all__ = [
    "MODEL_TOUCHPOINT",
    "RiskClass",
    "RiskFactor",
    "RiskInput",
    "RiskProfileResult",
    "assess",
]
