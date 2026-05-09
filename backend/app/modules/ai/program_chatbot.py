"""AI-9 — Program intelligence chatbot (F-28).

GPT-4o function-calling against a fixed set of read-only DB queries.
Returns a structured `ChatAnswer { answer, data_source, suggested_followups }`.

The function whitelist is small (six queries) — RBAC is enforced by
the calling principal's role; the chatbot itself never bypasses it.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure import azure_openai
from app.shared.exceptions import (
    AzureOpenAiError,
    AzureOpenAiQuotaExceededError,
)

logger = logging.getLogger("nexhire.ai.chatbot")

MODEL_TOUCHPOINT = "PROGRAM_CHATBOT"


@dataclass(frozen=True, slots=True)
class ChatAnswer:
    answer: str
    data_source: str
    confidence: str = "MEDIUM"
    suggested_followups: tuple[str, ...] = ()


# ────────────────────────────────────────────────────────────────────
# Function whitelist + executors.
# ────────────────────────────────────────────────────────────────────
async def get_referral_pipeline_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text("SELECT status, COUNT(*) FROM referrals GROUP BY status")
        )
    ).all()
    return {str(r[0]): int(r[1]) for r in rows}


async def get_at_risk_referrals(session: AsyncSession) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT r.id, r.candidate_name, r.current_stage,
                       (a.raw_output ->> 'risk')::float AS risk
                FROM referrals r
                JOIN LATERAL (
                  SELECT raw_output FROM ai_parse_results
                  WHERE referral_id = r.id
                    AND ai_touchpoint = 'BOTTLENECK_PREDICTION'
                  ORDER BY parsed_at DESC LIMIT 1
                ) a ON true
                WHERE (a.raw_output ->> 'risk')::float >= 0.4
                ORDER BY (a.raw_output ->> 'risk')::float DESC
                LIMIT 20
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_mentor_stats(session: AsyncSession, *, period: str = "all") -> list[dict[str, object]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT u.full_name,
                       COUNT(*) FILTER (WHERE ma.status = 'REJECTED') AS rejections,
                       COUNT(*) FILTER (WHERE ma.status = 'ACCEPTED') AS accepted,
                       COUNT(*) AS total
                FROM mentor_assignments ma
                JOIN users u ON u.id = ma.mentor_id
                GROUP BY u.full_name
                ORDER BY rejections DESC
                LIMIT 10
                """
            )
        )
    ).mappings().all()
    _ = period  # unused in S6 v1
    return [dict(r) for r in rows]


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_referral_pipeline_counts",
            "description": "Count of referrals at each status in the pipeline.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_at_risk_referrals",
            "description": "Top at-risk referrals from AI-5 bottleneck predictions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mentor_stats",
            "description": "Per-mentor accept/reject counts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Time window."}
                },
            },
        },
    },
]


_FUNCTIONS = {
    "get_referral_pipeline_counts": get_referral_pipeline_counts,
    "get_at_risk_referrals": get_at_risk_referrals,
    "get_mentor_stats": get_mentor_stats,
}


# ────────────────────────────────────────────────────────────────────
# Public entry.
# ────────────────────────────────────────────────────────────────────
async def ask(session: AsyncSession, *, question: str) -> ChatAnswer:
    cfg = get_settings()
    if not cfg.azure_openai_endpoint:
        return ChatAnswer(
            answer="AI chatbot is not configured.",
            data_source="none",
            confidence="LOW",
        )
    try:
        client = azure_openai.get_client()
        # Round 1: ask which function to call.
        plan = await azure_openai.call_with_retry(
            "chatbot_plan",
            client.chat.completions.create,
            model=cfg.azure_openai_deployment_gpt4o,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are NexHire's program intelligence assistant. "
                        "Use the provided tools to ground every answer in live DB data. "
                        "Never fabricate metrics."
                    ),
                },
                {"role": "user", "content": question},
            ],
            tools=_TOOLS,
            temperature=0.0,
            max_tokens=300,
        )
        tool_calls = getattr(plan.choices[0].message, "tool_calls", None) or []
        tool_results: list[dict[str, object]] = []
        for call in tool_calls:
            fn_name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            handler = _FUNCTIONS.get(fn_name)
            if handler is None:
                continue
            data = await handler(session, **args)
            tool_results.append({"name": fn_name, "data": data})

        # Round 2: synthesize a natural-language answer.
        followup = await azure_openai.call_with_retry(
            "chatbot_answer",
            client.chat.completions.create,
            model=cfg.azure_openai_deployment_gpt4o,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer the user's question concisely (≤4 sentences). "
                        "Cite the function-call source briefly."
                    ),
                },
                {"role": "user", "content": question},
                {
                    "role": "user",
                    "content": "Tool results:\n" + json.dumps(tool_results, default=str),
                },
            ],
            temperature=0.2,
            max_tokens=350,
        )
        answer = (followup.choices[0].message.content or "").strip()
        return ChatAnswer(
            answer=answer or "I don't have enough data to answer this yet.",
            data_source=",".join(str(t["name"]) for t in tool_results) or "none",
            confidence="HIGH" if tool_results else "LOW",
        )
    except (AzureOpenAiError, AzureOpenAiQuotaExceededError):
        return ChatAnswer(
            answer="AI chatbot is temporarily unavailable. Please retry shortly.",
            data_source="none",
            confidence="LOW",
        )
    except Exception:
        logger.exception("nexhire.ai.chatbot.unexpected")
        return ChatAnswer(
            answer="Could not process the question. Please rephrase.",
            data_source="none",
            confidence="LOW",
        )


__all__ = ["MODEL_TOUCHPOINT", "ChatAnswer", "ask"]
