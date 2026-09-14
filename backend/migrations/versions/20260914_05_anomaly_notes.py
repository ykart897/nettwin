"""add live anomaly resolution notes

Revision ID: 20260914_05
Revises: 20260914_04
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_05"
down_revision = "20260914_04"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("live_anomalies")}
    if "resolution_note" not in columns:
        with op.batch_alter_table("live_anomalies") as batch:
            batch.add_column(sa.Column("resolution_note", sa.Text()))


def downgrade():
    with op.batch_alter_table("live_anomalies") as batch:
        batch.drop_column("resolution_note")
