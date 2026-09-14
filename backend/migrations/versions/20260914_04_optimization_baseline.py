"""bind optimization evaluations to their baseline state

Revision ID: 20260914_04
Revises: 20260914_03
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_04"
down_revision = "20260914_03"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("optimization_evaluations")}
    with op.batch_alter_table("optimization_evaluations") as batch:
        if "baseline_metric_id" not in columns:
            batch.add_column(sa.Column(
                "baseline_metric_id",
                sa.Integer(),
                sa.ForeignKey("network_metrics.id", name="fk_optimization_evaluation_metric"),
            ))
        if "station_state_json" not in columns:
            batch.add_column(sa.Column("station_state_json", sa.Text(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("optimization_evaluations") as batch:
        batch.drop_column("station_state_json")
        batch.drop_column("baseline_metric_id")
