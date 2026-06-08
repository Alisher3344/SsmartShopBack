"""Paymo instalment integratsiyasi.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-21

Yangi:
- users ga 5 KYC ustun (passport/PINFL, middlename, address, address_payer, work_place)
- stores ga paymo_store_id (Paymo'da ro'yxatdan o'tgan magazin ID)
- instalments jadval (Order 1:1, Paymo lifecycle: NOT_CONFIRMED -> ACTIVE/CANCELLED/...)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: KYC ustunlar
    op.add_column("users", sa.Column("passport", sa.String(length=14), nullable=True))
    op.add_column("users", sa.Column("middlename", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("address", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("address_payer", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("work_place", sa.String(length=255), nullable=True))

    # stores: Paymo store id
    op.add_column("stores", sa.Column("paymo_store_id", sa.Integer(), nullable=True))

    # instalments jadval
    op.create_table(
        "instalments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=True),
        sa.Column("paymo_instalment_id", sa.String(length=64), nullable=True),
        sa.Column("paymo_store_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="NOT_CONFIRMED",
        ),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("card_expiry", sa.String(length=5), nullable=True),
        sa.Column("total_amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "initial_amount",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("start_month", sa.String(length=4), nullable=True),
        sa.Column("pay_day", sa.Integer(), nullable=True),
        sa.Column("holder_name", sa.String(length=255), nullable=True),
        sa.Column("bank", sa.String(length=64), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("contract_file_url", sa.Text(), nullable=True),
        sa.Column("balance", sa.BigInteger(), nullable=True),
        sa.Column("offer", sa.Text(), nullable=True),
        sa.Column("raw_create_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_last_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("order_id", name="uq_instalments_order_id"),
        sa.UniqueConstraint(
            "paymo_instalment_id", name="uq_instalments_paymo_instalment_id"
        ),
    )
    op.create_index("ix_instalments_user_id", "instalments", ["user_id"])
    op.create_index("ix_instalments_store_id", "instalments", ["store_id"])
    op.create_index("ix_instalments_status", "instalments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_instalments_status", table_name="instalments")
    op.drop_index("ix_instalments_store_id", table_name="instalments")
    op.drop_index("ix_instalments_user_id", table_name="instalments")
    op.drop_table("instalments")

    op.drop_column("stores", "paymo_store_id")
    op.drop_column("users", "work_place")
    op.drop_column("users", "address_payer")
    op.drop_column("users", "address")
    op.drop_column("users", "middlename")
    op.drop_column("users", "passport")
