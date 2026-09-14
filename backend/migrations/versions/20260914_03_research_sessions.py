"""add research sessions and reliable telemetry metadata

Revision ID: 20260914_03
Revises: 20260613_02
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_03"
down_revision = "20260613_02"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "measurement_sessions" not in tables:
        op.create_table(
            "measurement_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("notes", sa.Text()),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("ended_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if "ingestion_jobs" not in tables:
        op.create_table(
            "ingestion_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source", sa.String()),
            sa.Column("status", sa.String(), nullable=False, server_default="queued"),
            sa.Column("result_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
        )
    columns = {column["name"] for column in sa.inspect(bind).get_columns("observations")}
    additions = (
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("measurement_sessions.id", name="fk_observations_session_id"),
        ),
        sa.Column("request_failure_pct", sa.Float()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("location_accuracy_m", sa.Float()),
        sa.Column("location_observed_at", sa.DateTime(timezone=True)),
        sa.Column("measurement_method", sa.String()),
        sa.Column("measurement_target", sa.String()),
    )
    with op.batch_alter_table("observations") as batch:
        for column in additions:
            if column.name not in columns:
                batch.add_column(column)
        if "session_id" not in columns:
            batch.create_index("ix_observations_session_id", ["session_id"])


def downgrade():
    with op.batch_alter_table("observations") as batch:
        batch.drop_index("ix_observations_session_id")
        for name in (
            "measurement_target",
            "measurement_method",
            "location_observed_at",
            "location_accuracy_m",
            "longitude",
            "latitude",
            "request_failure_pct",
            "session_id",
        ):
            batch.drop_column(name)
    op.drop_table("ingestion_jobs")
    op.drop_table("measurement_sessions")
