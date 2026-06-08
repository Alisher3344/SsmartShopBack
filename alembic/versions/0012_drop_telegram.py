"""Telegram auth oqimini olib tashlash: auth_sessions jadvali drop qilinadi.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-21

Telegram OTP/Auth oqimi olib tashlandi (RBAC tozalash). Foydalanuvchilar
SMS OTP yoki email + parol bilan ro'yxatdan o'tadi. `users.telegram_id` va
`users.telegram_username` ustunlari hozir saqlanadi va kelajakda alohida
migratsiyada drop qilinadi.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_auth_sessions_token", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("code", sa.String(length=8), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_auth_sessions_id", "auth_sessions", ["id"])
    op.create_index("ix_auth_sessions_token", "auth_sessions", ["token"], unique=True)
