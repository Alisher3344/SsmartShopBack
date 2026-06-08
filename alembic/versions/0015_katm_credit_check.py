"""KATM kredit byurosi — kredit tarixi tekshiruvi (Faza 1).

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-04

Yangi:
- users: KATM identifikatsiya ustunlari (katm_client_id=KATM-SIR, doc series/number/type,
  region/local_region SOATO kodlari) — bir marta aniqlanib qayta ishlatiladi.
- katm_consents: mijoz roziligi (pAgreementId/pAgreementDate manbai).
- katm_requests: har claim/report/ban chaqiruvi auditi + async report poll holati.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: KATM identifikatsiya ustunlari
    op.add_column("users", sa.Column("katm_client_id", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("katm_doc_series", sa.String(length=5), nullable=True))
    op.add_column("users", sa.Column("katm_doc_number", sa.String(length=10), nullable=True))
    op.add_column("users", sa.Column("katm_doc_type", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("katm_region", sa.String(length=2), nullable=True))
    op.add_column("users", sa.Column("katm_local_region", sa.String(length=3), nullable=True))

    # katm_consents
    op.create_table(
        "katm_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("agreement_id", sa.String(length=10), nullable=False),
        sa.Column("agreement_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=True),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("agreement_id", name="uq_katm_consents_agreement_id"),
    )
    op.create_index("ix_katm_consents_user_id", "katm_consents", ["user_id"])

    # katm_requests
    op.create_table(
        "katm_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("consent_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("claim_id", sa.String(length=20), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("katm_client_id", sa.String(length=32), nullable=True),
        sa.Column("report_token", sa.Text(), nullable=True),
        sa.Column("report_format", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="CREATED"),
        sa.Column("ban_status", sa.Integer(), nullable=True),
        sa.Column("result_code", sa.String(length=8), nullable=True),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("report_base64", sa.Text(), nullable=True),
        sa.Column("report_decoded", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_claim", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["consent_id"], ["katm_consents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_katm_requests_user_id", "katm_requests", ["user_id"])
    op.create_index("ix_katm_requests_status", "katm_requests", ["status"])
    op.create_index("ix_katm_requests_claim_id", "katm_requests", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_katm_requests_claim_id", table_name="katm_requests")
    op.drop_index("ix_katm_requests_status", table_name="katm_requests")
    op.drop_index("ix_katm_requests_user_id", table_name="katm_requests")
    op.drop_table("katm_requests")
    op.drop_index("ix_katm_consents_user_id", table_name="katm_consents")
    op.drop_table("katm_consents")
    op.drop_column("users", "katm_local_region")
    op.drop_column("users", "katm_region")
    op.drop_column("users", "katm_doc_type")
    op.drop_column("users", "katm_doc_number")
    op.drop_column("users", "katm_doc_series")
    op.drop_column("users", "katm_client_id")
