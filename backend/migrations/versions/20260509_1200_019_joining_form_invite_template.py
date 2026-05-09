"""seed NOTIF_022_JOINING_FORM_INVITE template row

Revision ID: 0019_joining_form_invite_template
Revises: 0018_skills
Created: 2026-05-09 12:00 UTC

Auto-approval after mentor accept now emails the candidate a magic
link to the joining form. The mailer reads template metadata from
`notification_templates`, so we seed the new row here.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_joining_form_invite_template"
down_revision: str | None = "0018_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TEMPLATE_ID = "NOTIF_022_JOINING_FORM_INVITE"
SUBJECT = "Action required: complete your joining form"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO notification_templates (template_id, subject)
            VALUES (:tid, :subj)
            ON CONFLICT (template_id) DO NOTHING
            """
        ).bindparams(tid=TEMPLATE_ID, subj=SUBJECT)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM notification_templates WHERE template_id = :tid"
        ).bindparams(tid=TEMPLATE_ID)
    )
