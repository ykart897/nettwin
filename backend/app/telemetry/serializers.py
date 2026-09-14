from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.models import Asset, DataSourceStatus, Observation


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def serialize_asset(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "asset_type": asset.asset_type,
        "source": asset.source,
        "external_id": asset.external_id,
        "name": asset.name,
        "latitude": asset.latitude,
        "longitude": asset.longitude,
        "technology": asset.technology,
        "operator_code": asset.operator_code,
        "metadata": json.loads(asset.metadata_json or "{}"),
        "active": asset.active,
    }


def serialize_observation(observation: Observation, display_mode: str | None = None) -> dict:
    return {
        "id": observation.id,
        "asset_id": observation.asset_id,
        "session_id": observation.session_id,
        "source": observation.source,
        "observed_at": _utc_iso(observation.observed_at),
        "ingested_at": _utc_iso(observation.ingested_at),
        "data_mode": display_mode or observation.data_mode,
        "latency_ms": observation.latency_ms,
        "packet_loss_pct": observation.packet_loss_pct,
        "request_failure_pct": observation.request_failure_pct,
        "download_mbps": observation.download_mbps,
        "upload_mbps": observation.upload_mbps,
        "signal_strength_dbm": observation.signal_strength_dbm,
        "signal_quality_db": observation.signal_quality_db,
        "sinr_db": observation.sinr_db,
        "network_type": observation.network_type,
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "location_accuracy_m": observation.location_accuracy_m,
        "location_observed_at": _utc_iso(observation.location_observed_at),
        "measurement_method": observation.measurement_method,
        "measurement_target": observation.measurement_target,
        "load_index": observation.load_index,
        "confidence": observation.confidence,
        "model_version": observation.model_version,
        "load_inputs": json.loads(observation.estimate_inputs_json or "{}"),
    }


def serialize_source_status(status: DataSourceStatus) -> dict:
    stale_after_seconds = 26 * 60 * 60 if status.source == "opencellid" else 10 * 60
    stale = True
    if status.last_success_at:
        last_success = status.last_success_at
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=timezone.utc)
        stale = (datetime.now(timezone.utc) - last_success).total_seconds() > stale_after_seconds
    enabled = _source_enabled(status.source)
    return {
        "source": status.source,
        "status": status.status,
        "last_attempt_at": status.last_attempt_at.isoformat() if status.last_attempt_at else None,
        "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
        "records_received": status.records_received,
        "message": status.message,
        "stale": stale,
        "enabled": enabled,
        "display_status": status.status if enabled else "disabled",
    }


def _source_enabled(source: str) -> bool:
    if source == "opencellid":
        return bool(os.getenv("OPENCELLID_CSV_PATH"))
    return True
