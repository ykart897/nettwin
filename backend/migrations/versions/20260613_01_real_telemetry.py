"""add real telemetry assets and observations

Revision ID: 20260613_01
Revises:
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa


revision = "20260613_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "network_metrics" not in tables:
        from app import models  # noqa: F401
        from app.database import Base

        Base.metadata.create_all(bind=bind)
        return

    metric_columns = {column["name"] for column in inspector.get_columns("network_metrics")}
    with op.batch_alter_table("network_metrics") as batch:
        if "data_mode" not in metric_columns:
            batch.add_column(sa.Column("data_mode", sa.String(), nullable=False, server_default="simulation"))
        if "data_quality" not in metric_columns:
            batch.add_column(sa.Column("data_quality", sa.String(), nullable=False, server_default="simulated"))
        if "source" not in metric_columns:
            batch.add_column(sa.Column("source", sa.String(), nullable=False, server_default="generator"))

    if "assets" not in tables:
        _create_assets()
    if "observations" not in tables:
        _create_observations()
    if "data_source_status" not in tables:
        _create_source_status()


def _create_assets():
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("technology", sa.String()),
        sa.Column("operator_code", sa.String()),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "external_id", name="uq_asset_source_external_id"),
    )
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_source", "assets", ["source"])


def _create_observations():
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_observation_id", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("data_mode", sa.String(), nullable=False, server_default="live"),
        sa.Column("data_quality", sa.String(), nullable=False, server_default="observed"),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("packet_loss_pct", sa.Float()),
        sa.Column("download_mbps", sa.Float()),
        sa.Column("upload_mbps", sa.Float()),
        sa.Column("signal_strength_dbm", sa.Float()),
        sa.Column("load_index", sa.Float()),
        sa.Column("confidence", sa.String()),
        sa.Column("estimate_inputs_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("raw_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("source", "source_observation_id", name="uq_observation_source_observation"),
    )
    op.create_index("ix_observations_asset_id", "observations", ["asset_id"])
    op.create_index("ix_observations_source", "observations", ["source"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])


def _create_source_status():
    op.create_table(
        "data_source_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False, server_default="unconfigured"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text()),
    )
    op.create_index("ix_data_source_status_source", "data_source_status", ["source"])


def downgrade():
    op.drop_table("data_source_status")
    op.drop_table("observations")
    op.drop_table("assets")
    with op.batch_alter_table("network_metrics") as batch:
        batch.drop_column("source")
        batch.drop_column("data_quality")
        batch.drop_column("data_mode")
