"""Buyurtma "jo'natildi" belgisi — punktga jo'natish auditi.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-05

Yangi (orders):
- dispatched_at: admin mahsulot kodini chop etib punktga jo'natgan vaqt.
- dispatched_by_id: jo'natgan admin (FK users, SET NULL).
- dispatched_by_name: jo'natgan admin ismi (snapshot, ko'rsatish uchun).

Maqsad: bir buyurtmani superadmin va do'kon admini birga ko'radi; bu belgi
bo'lsa kartochka "hira" ko'rinadi va ikkinchi admin qayta qabul qilmaydi.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("dispatched_by_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("dispatched_by_name", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        "fk_orders_dispatched_by_id_users",
        "orders",
        "users",
        ["dispatched_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_orders_dispatched_by_id_users", "orders", type_="foreignkey")
    op.drop_column("orders", "dispatched_by_name")
    op.drop_column("orders", "dispatched_by_id")
    op.drop_column("orders", "dispatched_at")
