"""add observation metadata, topology, and evaluations

Revision ID: 20260613_02
Revises: 20260613_01
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa


revision = "20260613_02"
down_revision = "20260613_01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    observation_columns = {column["name"] for column in inspector.get_columns("observations")}
    with op.batch_alter_table("observations") as batch:
        if "signal_quality_db" not in observation_columns:
            batch.add_column(sa.Column("signal_quality_db", sa.Float()))
        if "sinr_db" not in observation_columns:
            batch.add_column(sa.Column("sinr_db", sa.Float()))
        if "network_type" not in observation_columns:
            batch.add_column(sa.Column("network_type", sa.String()))
        if "model_version" not in observation_columns:
            batch.add_column(sa.Column("model_version", sa.String()))

    if "asset_relations" not in tables:
        op.create_table(
            "asset_relations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
            sa.Column("target_asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
            sa.Column("relation_type", sa.String(), nullable=False),
            sa.Column("distance_km", sa.Float()),
            sa.Column("confidence", sa.Float()),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint(
                "source_asset_id",
                "target_asset_id",
                "relation_type",
                name="uq_asset_relation",
            ),
        )
        op.create_index("ix_asset_relations_source_asset_id", "asset_relations", ["source_asset_id"])
        op.create_index("ix_asset_relations_target_asset_id", "asset_relations", ["target_asset_id"])

    if "live_anomalies" not in tables:
        op.create_table(
            "live_anomalies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("observation_id", sa.Integer(), sa.ForeignKey("observations.id"), nullable=False),
            sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
            sa.Column("anomaly_type", sa.String(), nullable=False),
            sa.Column("severity", sa.String(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("model_version", sa.String(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint(
                "observation_id",
                "anomaly_type",
                name="uq_live_anomaly_observation_type",
            ),
        )
        op.create_index("ix_live_anomalies_observation_id", "live_anomalies", ["observation_id"])
        op.create_index("ix_live_anomalies_asset_id", "live_anomalies", ["asset_id"])

    if "optimization_evaluations" not in tables:
        op.create_table(
            "optimization_evaluations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("optimization_id", sa.Integer(), sa.ForeignKey("optimizations.id"), nullable=False),
            sa.Column("baseline_json", sa.Text(), nullable=False),
            sa.Column("projected_json", sa.Text(), nullable=False),
            sa.Column("risk_level", sa.String(), nullable=False),
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_optimization_evaluations_optimization_id",
            "optimization_evaluations",
            ["optimization_id"],
        )


def downgrade():
    op.drop_table("optimization_evaluations")
    op.drop_table("live_anomalies")
    op.drop_table("asset_relations")
    with op.batch_alter_table("observations") as batch:
        batch.drop_column("model_version")
        batch.drop_column("network_type")
        batch.drop_column("sinr_db")
        batch.drop_column("signal_quality_db")
