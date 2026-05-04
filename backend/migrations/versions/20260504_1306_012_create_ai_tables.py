"""create AI result tables (parse, risk, duplicate)

Revision ID: 0012_ai_tables
Revises: 0011_mentor_assignments
Created: 2026-05-04 13:06 UTC

Three normalized tables (decisions E9 + E10) instead of one giant
JSONB blob. Lets us index per-touchpoint metrics without disturbing
the rest of the AI output.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_ai_tables"
down_revision: str | None = "0011_mentor_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AI_TOUCHPOINTS = (
    "RESUME_PARSE",
    "MENTOR_MATCH",
    "ELIGIBILITY_RISK",
    "DUPLICATE_DETECTION",
    "FORM_ASSIST",
    "BOTTLENECK_PREDICTION",
    "COMPLIANCE_CHECK",
    "CERTIFICATE_CITATION",
    "PROGRAM_CHATBOT",
    "WORKFLOW_ROUTING",
)


def upgrade() -> None:
    # ── ai_parse_results ──────────────────────────────────────────
    op.create_table(
        "ai_parse_results",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("ai_touchpoint", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("azure_openai_request_id", sa.String(255), nullable=True),
        sa.Column(
            "parsed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "raw_output",
            sa.dialects.postgresql.JSONB,
            nullable=False,
        ),
        sa.Column("confidence_scores", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column(
            "human_overrides",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("succeeded", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("degradation_reason", sa.String(100), nullable=True),
        sa.CheckConstraint(
            "ai_touchpoint IN ('" + "','".join(AI_TOUCHPOINTS) + "')",
            name="ck_ai_parse_touchpoint_enum",
        ),
    )
    op.create_index(
        "idx_ai_parse_referral_touchpoint",
        "ai_parse_results",
        ["referral_id", "ai_touchpoint", "parsed_at"],
    )
    op.create_index(
        "idx_ai_parse_touchpoint_time",
        "ai_parse_results",
        ["ai_touchpoint", "parsed_at"],
    )

    # ── risk_profiles ─────────────────────────────────────────────
    op.create_table(
        "risk_profiles",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("risk_score", sa.SmallInteger, nullable=False),
        sa.Column(
            "factors",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("narrative", sa.Text, nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 100",
            name="ck_risk_profile_score_range",
        ),
    )

    # ── duplicate_check_results ───────────────────────────────────
    op.create_table(
        "duplicate_check_results",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("match_type", sa.String(50), nullable=False),
        sa.Column("similarity_score", sa.Float, nullable=False),
        sa.Column(
            "match_reasons",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "matched_referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recommendation", sa.String(20), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "recommendation IN ('PASS', 'WARN', 'SOFT_BLOCK', 'HARD_BLOCK', "
            "'COOLING_BLOCK', 'CLEAR')",
            name="ck_duplicate_recommendation_enum",
        ),
    )
    op.create_index(
        "idx_duplicate_check_referral",
        "duplicate_check_results",
        ["referral_id", "checked_at"],
    )

    # ── ai_auto_actions (Blueprint §18.7) ────────────────────────
    op.create_table(
        "ai_auto_actions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "intern_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,  # FK added in S3 when interns table lands
        ),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("conditions_met", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("flags", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("hr_recommendation", sa.String(50), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recalled_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recall_reason", sa.Text, nullable=True),
        sa.CheckConstraint(
            "action_type IN ('AUTO_APPROVE', 'AUTO_LOCK', 'AUTO_SEND_OFFER', "
            "'AUTO_SEND_CERT', 'AUTO_GENERATE_NW_ID')",
            name="ck_ai_auto_action_type",
        ),
        sa.CheckConstraint(
            "decision IN ('EXECUTED', 'ROUTED_TO_HR', 'HARD_BLOCK')",
            name="ck_ai_auto_action_decision",
        ),
    )
    op.create_index(
        "idx_ai_auto_actions_referral",
        "ai_auto_actions",
        ["referral_id", "executed_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_auto_actions_referral", table_name="ai_auto_actions")
    op.drop_table("ai_auto_actions")
    op.drop_index("idx_duplicate_check_referral", table_name="duplicate_check_results")
    op.drop_table("duplicate_check_results")
    op.drop_table("risk_profiles")
    op.drop_index("idx_ai_parse_touchpoint_time", table_name="ai_parse_results")
    op.drop_index("idx_ai_parse_referral_touchpoint", table_name="ai_parse_results")
    op.drop_table("ai_parse_results")
