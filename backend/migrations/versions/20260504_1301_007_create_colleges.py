"""create colleges + seed top Indian engineering colleges

Revision ID: 0007_colleges
Revises: 0006_config_tables
Created: 2026-05-04 13:01 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_colleges"
down_revision: str | None = "0006_config_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Decision A7: master college list, autocomplete-driven, RULE-E2 cap by college_id.
# Initial seed = top engineering colleges + IITs + IIITs + NITs + a few private ones.
# More can be added later via the admin S25 college-management UI.
COLLEGES = [
    # IITs
    ("IIT Bombay", ["IITB", "Indian Institute of Technology Bombay"], "Maharashtra", "GOVT_AUTONOMOUS"),
    ("IIT Delhi", ["IITD", "Indian Institute of Technology Delhi"], "Delhi", "GOVT_AUTONOMOUS"),
    ("IIT Madras", ["IITM", "Indian Institute of Technology Madras"], "Tamil Nadu", "GOVT_AUTONOMOUS"),
    ("IIT Kanpur", ["IITK", "Indian Institute of Technology Kanpur"], "Uttar Pradesh", "GOVT_AUTONOMOUS"),
    ("IIT Kharagpur", ["IIT KGP", "Indian Institute of Technology Kharagpur"], "West Bengal", "GOVT_AUTONOMOUS"),
    ("IIT Roorkee", ["IITR", "Indian Institute of Technology Roorkee"], "Uttarakhand", "GOVT_AUTONOMOUS"),
    ("IIT Guwahati", ["IITG", "Indian Institute of Technology Guwahati"], "Assam", "GOVT_AUTONOMOUS"),
    ("IIT Hyderabad", ["IITH", "Indian Institute of Technology Hyderabad"], "Telangana", "GOVT_AUTONOMOUS"),
    ("IIT Indore", ["IITI", "Indian Institute of Technology Indore"], "Madhya Pradesh", "GOVT_AUTONOMOUS"),
    ("IIT BHU", ["IIT (BHU)", "IIT Varanasi"], "Uttar Pradesh", "GOVT_AUTONOMOUS"),
    # NITs
    ("NIT Trichy", ["NITT", "National Institute of Technology Tiruchirappalli"], "Tamil Nadu", "GOVT_AUTONOMOUS"),
    ("NIT Surathkal", ["NITK", "NIT Karnataka"], "Karnataka", "GOVT_AUTONOMOUS"),
    ("NIT Warangal", ["NITW"], "Telangana", "GOVT_AUTONOMOUS"),
    ("NIT Calicut", ["NITC"], "Kerala", "GOVT_AUTONOMOUS"),
    ("NIT Rourkela", ["NITRKL"], "Odisha", "GOVT_AUTONOMOUS"),
    ("NIT Allahabad", ["MNNIT", "Motilal Nehru NIT"], "Uttar Pradesh", "GOVT_AUTONOMOUS"),
    ("NIT Surat", ["SVNIT"], "Gujarat", "GOVT_AUTONOMOUS"),
    ("NIT Nagpur", ["VNIT"], "Maharashtra", "GOVT_AUTONOMOUS"),
    # IIITs
    ("IIIT Hyderabad", ["IIITH"], "Telangana", "GOVT_AUTONOMOUS"),
    ("IIIT Bangalore", ["IIITB"], "Karnataka", "GOVT_AUTONOMOUS"),
    ("IIIT Allahabad", ["IIIT-A"], "Uttar Pradesh", "GOVT_AUTONOMOUS"),
    ("IIIT Delhi", ["IIITD"], "Delhi", "GOVT_AUTONOMOUS"),
    # BITS
    ("BITS Pilani", ["BITS Pilani Pilani Campus"], "Rajasthan", "PRIVATE_AUTONOMOUS"),
    ("BITS Pilani Goa", ["BITS Goa"], "Goa", "PRIVATE_AUTONOMOUS"),
    ("BITS Pilani Hyderabad", ["BITS Hyderabad"], "Telangana", "PRIVATE_AUTONOMOUS"),
    # VIT / SRM / Manipal etc.
    ("VIT Vellore", ["VIT", "Vellore Institute of Technology"], "Tamil Nadu", "PRIVATE_AUTONOMOUS"),
    ("VIT Chennai", [], "Tamil Nadu", "PRIVATE_AUTONOMOUS"),
    ("SRM University Chennai", ["SRM IST", "SRM Institute"], "Tamil Nadu", "PRIVATE_AUTONOMOUS"),
    ("Manipal Institute of Technology", ["MIT Manipal", "MAHE"], "Karnataka", "PRIVATE_AUTONOMOUS"),
    ("Thapar University", ["TIET"], "Punjab", "PRIVATE_AUTONOMOUS"),
    ("PES University", ["PESU"], "Karnataka", "PRIVATE_AUTONOMOUS"),
    # Delhi / DTU / NSUT / IPU
    ("Delhi Technological University", ["DTU"], "Delhi", "GOVT_AUTONOMOUS"),
    ("Netaji Subhas University of Technology", ["NSUT"], "Delhi", "GOVT_AUTONOMOUS"),
    ("Indraprastha Institute of Information Technology", ["IIIT-Delhi"], "Delhi", "GOVT_AUTONOMOUS"),
    # Anna University & affiliates
    ("Anna University", ["CEG", "MIT Chennai"], "Tamil Nadu", "GOVT_AFFILIATING"),
    ("College of Engineering Pune", ["COEP"], "Maharashtra", "GOVT_AUTONOMOUS"),
    ("Veermata Jijabai Technological Institute", ["VJTI"], "Maharashtra", "GOVT_AUTONOMOUS"),
    # IISc
    ("Indian Institute of Science", ["IISc"], "Karnataka", "GOVT_AUTONOMOUS"),
    # Other notable
    ("R V College of Engineering", ["RVCE"], "Karnataka", "PRIVATE_AFFILIATED"),
    ("BMS College of Engineering", ["BMSCE"], "Karnataka", "PRIVATE_AFFILIATED"),
    ("PSG College of Technology", ["PSG Tech"], "Tamil Nadu", "PRIVATE_AFFILIATED"),
    ("Jadavpur University", ["JU"], "West Bengal", "GOVT_AUTONOMOUS"),
    ("Heritage Institute of Technology", ["HITK"], "West Bengal", "PRIVATE_AFFILIATED"),
]


def upgrade() -> None:
    op.create_table(
        "colleges",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("canonical_name", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "aliases",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("location_state", sa.String(100), nullable=True),
        sa.Column("type", sa.String(50), nullable=True),  # GOVT_AUTONOMOUS, PRIVATE_AFFILIATED, etc.
        sa.Column(
            "is_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # GIN index for alias / fuzzy text search.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "idx_colleges_canonical_trgm",
        "colleges",
        ["canonical_name"],
        postgresql_using="gin",
        postgresql_ops={"canonical_name": "gin_trgm_ops"},
    )

    # Seed.
    for name, aliases, state, kind in COLLEGES:
        op.execute(
            sa.text(
                """
                INSERT INTO colleges (canonical_name, aliases, location_state, type)
                VALUES (:n, CAST(:a AS jsonb), :s, :t)
                ON CONFLICT (canonical_name) DO NOTHING
                """
            ).bindparams(
                n=name,
                a=__import__("json").dumps(aliases),
                s=state,
                t=kind,
            )
        )


def downgrade() -> None:
    op.drop_index("idx_colleges_canonical_trgm", table_name="colleges")
    op.drop_table("colleges")
