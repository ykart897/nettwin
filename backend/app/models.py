from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.database import Base


class BaseStation(Base):
    __tablename__ = "base_stations"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    region = Column(String, nullable=False)
    frequency_band = Column(String, default="6G-FR3")
    max_capacity = Column(Integer, default=200)
    tx_power_dbm = Column(Float, default=30.0)
    status = Column(String, default="Active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("region IN ('Urban', 'Suburban', 'Rural')"),
        CheckConstraint("status IN ('Active', 'Degraded', 'Offline')"),
    )


class NetworkMetric(Base):
    __tablename__ = "network_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_station_id = Column(String, ForeignKey("base_stations.id"), index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    latency_ms = Column(Float)
    signal_strength_dbm = Column(Float)
    throughput_mbps = Column(Float)
    connected_users = Column(Integer)
    packet_loss_pct = Column(Float)
    region = Column(String)
    is_anomaly = Column(Boolean, default=False)
    anomaly_type = Column(String, nullable=True)
    data_mode = Column(String, nullable=False, default="simulation")
    data_quality = Column(String, nullable=False, default="simulated")
    source = Column(String, nullable=False, default="generator")

    __table_args__ = (
        CheckConstraint("data_mode IN ('live', 'replay', 'simulation')"),
        CheckConstraint("data_quality IN ('observed', 'estimated', 'simulated')"),
    )


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_type = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    technology = Column(String, nullable=True)
    operator_code = Column(String, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("asset_type IN ('cell_site', 'ripe_probe', 'local_agent')"),
        UniqueConstraint("source", "external_id", name="uq_asset_source_external_id"),
    )


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("measurement_sessions.id"), nullable=True, index=True)
    source = Column(String, nullable=False, index=True)
    source_observation_id = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    data_mode = Column(String, nullable=False, default="live")
    data_quality = Column(String, nullable=False, default="observed")
    latency_ms = Column(Float, nullable=True)
    packet_loss_pct = Column(Float, nullable=True)
    request_failure_pct = Column(Float, nullable=True)
    download_mbps = Column(Float, nullable=True)
    upload_mbps = Column(Float, nullable=True)
    signal_strength_dbm = Column(Float, nullable=True)
    signal_quality_db = Column(Float, nullable=True)
    sinr_db = Column(Float, nullable=True)
    network_type = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_accuracy_m = Column(Float, nullable=True)
    location_observed_at = Column(DateTime(timezone=True), nullable=True)
    measurement_method = Column(String, nullable=True)
    measurement_target = Column(String, nullable=True)
    load_index = Column(Float, nullable=True)
    confidence = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    estimate_inputs_json = Column(Text, nullable=False, default="{}")
    raw_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        CheckConstraint("data_mode IN ('live', 'replay')"),
        CheckConstraint("data_quality IN ('observed', 'estimated')"),
        CheckConstraint("confidence IS NULL OR confidence IN ('Low', 'Medium', 'High')"),
        UniqueConstraint(
            "source",
            "source_observation_id",
            name="uq_observation_source_observation",
        ),
    )


class MeasurementSession(Base):
    __tablename__ = "measurement_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active")
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (CheckConstraint("status IN ('active', 'completed')"),)


class DataSourceStatus(Base):
    __tablename__ = "data_source_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="unconfigured")
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    records_received = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('healthy', 'degraded', 'unconfigured')"),
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued")
    result_json = Column(Text, nullable=False, default="[]")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')"),)


class AssetRelation(Base):
    __tablename__ = "asset_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    target_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    relation_type = Column(String, nullable=False)
    distance_km = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("relation_type IN ('NEIGHBOR_OF', 'MEASURED_BY', 'CONNECTED_TO')"),
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "relation_type",
            name="uq_asset_relation",
        ),
    )


class LiveAnomaly(Base):
    __tablename__ = "live_anomalies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    anomaly_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Boolean, nullable=False, default=False)
    resolution_note = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("severity IN ('Low', 'Medium', 'High', 'Critical')"),
        UniqueConstraint("observation_id", "anomaly_type", name="uq_live_anomaly_observation_type"),
    )


class OptimizationEvaluation(Base):
    __tablename__ = "optimization_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    optimization_id = Column(Integer, ForeignKey("optimizations.id"), nullable=False, index=True)
    baseline_metric_id = Column(Integer, ForeignKey("network_metrics.id"), nullable=True)
    station_state_json = Column(Text, nullable=False, default="{}")
    baseline_json = Column(Text, nullable=False)
    projected_json = Column(Text, nullable=False)
    risk_level = Column(String, nullable=False)
    approved = Column(Boolean, nullable=False, default=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("risk_level IN ('Low', 'Medium', 'High')"),
    )


class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    parameters = Column(Text, nullable=False)
    status = Column(String, default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('Pending', 'Running', 'Completed', 'Failed')"),
    )


class ScenarioResult(Base):
    __tablename__ = "scenario_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), index=True)
    step = Column(Integer)
    base_station_id = Column(String, ForeignKey("base_stations.id"), index=True)
    latency_ms = Column(Float)
    signal_strength_dbm = Column(Float)
    throughput_mbps = Column(Float)
    connected_users = Column(Integer)
    packet_loss_pct = Column(Float)
    timestamp = Column(DateTime(timezone=True))


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_station_id = Column(String, ForeignKey("base_stations.id"), index=True)
    alert_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    message = Column(Text)
    metric_snapshot = Column(Text)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("severity IN ('Low', 'Medium', 'High', 'Critical')"),
    )


class Optimization(Base):
    __tablename__ = "optimizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    base_station_id = Column(String, ForeignKey("base_stations.id"), index=True)
    suggestion_type = Column(String)
    description = Column(Text)
    parameters = Column(Text)
    status = Column(String, default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('Pending', 'Applied', 'Dismissed')"),
    )
