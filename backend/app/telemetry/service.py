from __future__ import annotations

import json
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Asset, DataSourceStatus, Observation
from app.live_anomaly import LiveAnomalyDetector
from app.telemetry.base import TelemetryProvider
from app.telemetry.load_index import calculate_load_index, model_version
from app.telemetry.local_agent import LocalAgentProvider
from app.telemetry.opencellid import OpenCellIdProvider
from app.telemetry.ripe_atlas import RipeAtlasProvider


class TelemetryService:
    def __init__(self, providers: list[TelemetryProvider] | None = None):
        self.providers = providers or [
            OpenCellIdProvider(),
            RipeAtlasProvider(),
            LocalAgentProvider(),
        ]

    def sync_all(self, source: str | None = None, session_id: int | None = None) -> list[dict]:
        selected = [provider for provider in self.providers if source in (None, provider.source)]
        if source and not selected:
            raise ValueError(f"Unknown telemetry source: {source}")
        if session_id is not None and any(provider.source != "local_agent" for provider in selected):
            raise ValueError("Measurement sessions only support the local agent")
        return [self._sync_provider(provider, session_id=session_id) for provider in selected]

    def _sync_provider(self, provider: TelemetryProvider, session_id: int | None = None) -> dict:
        db = SessionLocal()
        now = datetime.now(timezone.utc)
        status = db.query(DataSourceStatus).filter(DataSourceStatus.source == provider.source).first()
        if status is None:
            status = DataSourceStatus(source=provider.source)
            db.add(status)
        status.last_attempt_at = now
        try:
            if isinstance(provider, RipeAtlasProvider):
                provider.include_history = (
                    db.query(Observation).filter(Observation.source == provider.source).count() == 0
                )
            result = provider.sync()
            if not result.configured:
                status.status = "unconfigured"
                status.message = result.message
                db.commit()
                return _serialize_status(status)

            db.query(Asset).filter(Asset.source == provider.source).update(
                {Asset.active: False},
                synchronize_session=False,
            )
            assets = {
                payload["external_id"]: self._upsert_asset(db, payload)
                for payload in result.assets
            }
            inserted = 0
            for payload in result.observations:
                asset = assets.get(payload["asset_external_id"])
                if asset is None:
                    continue
                exists = (
                    db.query(Observation.id)
                    .filter(
                        Observation.source == provider.source,
                        Observation.source_observation_id == payload["source_observation_id"],
                    )
                    .first()
                )
                if exists:
                    continue
                score, confidence, inputs = calculate_load_index(payload)
                row = Observation(
                    asset_id=asset.id,
                    session_id=session_id,
                    source=provider.source,
                    source_observation_id=payload["source_observation_id"],
                    observed_at=payload["observed_at"],
                    data_mode="live",
                    data_quality="observed",
                    latency_ms=payload.get("latency_ms"),
                    packet_loss_pct=payload.get("packet_loss_pct"),
                    request_failure_pct=payload.get("request_failure_pct"),
                    download_mbps=payload.get("download_mbps"),
                    upload_mbps=payload.get("upload_mbps"),
                    signal_strength_dbm=payload.get("signal_strength_dbm"),
                    signal_quality_db=payload.get("signal_quality_db"),
                    sinr_db=payload.get("sinr_db"),
                    network_type=payload.get("network_type"),
                    latitude=payload.get("latitude"),
                    longitude=payload.get("longitude"),
                    measurement_method=payload.get("measurement_method"),
                    measurement_target=payload.get("measurement_target"),
                    load_index=score,
                    confidence=confidence,
                    model_version=model_version(),
                    estimate_inputs_json=json.dumps(inputs),
                    raw_json=json.dumps(payload.get("raw", {}), default=str),
                )
                db.add(row)
                db.flush()
                LiveAnomalyDetector().evaluate(db, row)
                inserted += 1

            status.status = "healthy"
            status.last_success_at = now
            status.records_received = inserted
            status.message = result.message
            db.commit()
            return _serialize_status(status)
        except Exception as exc:
            db.rollback()
            status = db.query(DataSourceStatus).filter(DataSourceStatus.source == provider.source).first()
            if status is None:
                status = DataSourceStatus(source=provider.source)
                db.add(status)
            status.status = "degraded"
            status.last_attempt_at = now
            status.message = str(exc)[:500]
            db.commit()
            return _serialize_status(status)
        finally:
            db.close()

    def _upsert_asset(self, db, payload: dict) -> Asset:
        asset = (
            db.query(Asset)
            .filter(Asset.source == payload["source"], Asset.external_id == payload["external_id"])
            .first()
        )
        if asset is None:
            asset = Asset(source=payload["source"], external_id=payload["external_id"])
            db.add(asset)
        asset.asset_type = payload["asset_type"]
        asset.name = payload["name"]
        asset.latitude = payload.get("latitude")
        asset.longitude = payload.get("longitude")
        asset.technology = payload.get("technology")
        asset.operator_code = payload.get("operator_code")
        asset.metadata_json = json.dumps(payload.get("metadata", {}), default=str)
        asset.active = True
        db.flush()
        return asset


def _serialize_status(status: DataSourceStatus) -> dict:
    return {
        "source": status.source,
        "status": status.status,
        "last_attempt_at": status.last_attempt_at.isoformat() if status.last_attempt_at else None,
        "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
        "records_received": status.records_received,
        "message": status.message,
    }
