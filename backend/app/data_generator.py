from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

import numpy as np

from app.models import BaseStation, NetworkMetric


BASE_STATIONS = [
    {"id": "BS-001", "name": "Taksim Tower", "latitude": 41.037, "longitude": 28.985, "region": "Urban"},
    {"id": "BS-002", "name": "Kadikoy Hub", "latitude": 40.990, "longitude": 29.029, "region": "Urban"},
    {"id": "BS-003", "name": "Besiktas Central", "latitude": 41.043, "longitude": 29.007, "region": "Urban"},
    {"id": "BS-004", "name": "Levent Business", "latitude": 41.077, "longitude": 29.010, "region": "Urban"},
    {"id": "BS-005", "name": "Eminonu Historic", "latitude": 41.017, "longitude": 28.973, "region": "Urban"},
    {"id": "BS-006", "name": "Umraniye Relay", "latitude": 41.028, "longitude": 29.095, "region": "Suburban"},
    {"id": "BS-007", "name": "Pendik South", "latitude": 40.878, "longitude": 29.231, "region": "Suburban"},
    {"id": "BS-008", "name": "Cekmekoy Ridge", "latitude": 41.075, "longitude": 29.175, "region": "Suburban"},
    {"id": "BS-009", "name": "Sariyer North", "latitude": 41.167, "longitude": 29.050, "region": "Suburban"},
    {"id": "BS-010", "name": "Sile Coastal", "latitude": 41.175, "longitude": 29.610, "region": "Rural"},
    {"id": "BS-011", "name": "Silivri West", "latitude": 41.073, "longitude": 28.247, "region": "Rural"},
    {"id": "BS-012", "name": "Catalca Plains", "latitude": 41.143, "longitude": 28.460, "region": "Rural"},
]

REGION_PROFILES = {
    "Urban": {"latency": 5, "users": 80, "capacity": 200},
    "Suburban": {"latency": 8, "users": 50, "capacity": 160},
    "Rural": {"latency": 12, "users": 20, "capacity": 120},
}


def seed_base_stations(db) -> int:
    inserted = 0
    for station in BASE_STATIONS:
        if db.get(BaseStation, station["id"]):
            continue
        profile = REGION_PROFILES[station["region"]]
        db.add(
            BaseStation(
                **station,
                max_capacity=profile["capacity"],
                tx_power_dbm=30.0 if station["region"] != "Rural" else 34.0,
            )
        )
        inserted += 1
    db.commit()
    return inserted


def generate_metric_dict(station: BaseStation, rng: np.random.Generator, timestamp: datetime | None = None) -> dict:
    profile = REGION_PROFILES[station.region]
    timestamp = timestamp or datetime.now(timezone.utc)
    latency = max(1.0, rng.normal(profile["latency"], 2))
    signal_noise = rng.normal(0, 2.5)
    signal_strength = np.clip(rng.uniform(-90, -30) + signal_noise, -120, -30)
    throughput = max(10.0, rng.lognormal(6.9, 0.5))
    connected_users = int(rng.poisson(profile["users"]))
    packet_loss = min(100.0, max(0.0, rng.exponential(0.3)))

    return {
        "base_station_id": station.id,
        "timestamp": timestamp,
        "latency_ms": round(float(latency), 2),
        "signal_strength_dbm": round(float(signal_strength), 1),
        "throughput_mbps": round(float(throughput), 1),
        "connected_users": connected_users,
        "packet_loss_pct": round(float(packet_loss), 3),
        "region": station.region,
    }


def inject_anomaly(metric: dict, anomaly_type: str | None) -> dict:
    if not anomaly_type:
        return metric
    mutated = dict(metric)
    if anomaly_type == "ddos":
        mutated["connected_users"] = int(mutated["connected_users"] * 5)
        mutated["latency_ms"] = round(mutated["latency_ms"] * 3, 2)
        mutated["packet_loss_pct"] = round(min(100.0, mutated["packet_loss_pct"] + 15), 3)
    elif anomaly_type == "jamming":
        mutated["signal_strength_dbm"] = round(max(-120.0, mutated["signal_strength_dbm"] - 40), 1)
        mutated["throughput_mbps"] = round(max(1.0, mutated["throughput_mbps"] * 0.1), 1)
    elif anomaly_type == "exfiltration":
        mutated["throughput_mbps"] = round(mutated["throughput_mbps"] * 3, 1)
        mutated["packet_loss_pct"] = round(min(100.0, mutated["packet_loss_pct"] + 8), 3)
    return mutated


def metric_from_dict(payload: dict) -> NetworkMetric:
    return NetworkMetric(
        base_station_id=payload["base_station_id"],
        timestamp=payload["timestamp"],
        latency_ms=payload["latency_ms"],
        signal_strength_dbm=payload["signal_strength_dbm"],
        throughput_mbps=payload["throughput_mbps"],
        connected_users=payload["connected_users"],
        packet_loss_pct=payload["packet_loss_pct"],
        region=payload["region"],
        is_anomaly=payload.get("is_anomaly", False),
        anomaly_type=payload.get("anomaly_type"),
        data_mode="simulation",
        data_quality="simulated",
        source="generator",
    )


def generate_metric_batch(
    db,
    count_per_station: int = 12,
    anomaly_type: str | None = None,
    target_station_id: str | None = None,
    seed: int | None = 42,
) -> list[NetworkMetric]:
    rng = np.random.default_rng(seed)
    stations = db.query(BaseStation).order_by(BaseStation.id).all()
    now = datetime.now(timezone.utc)
    rows: list[NetworkMetric] = []

    for step in range(count_per_station):
        timestamp = now - timedelta(seconds=(count_per_station - step) * 5)
        for station in stations:
            metric = generate_metric_dict(station, rng, timestamp=timestamp)
            should_inject = anomaly_type and (target_station_id in (None, station.id))
            if should_inject and step >= max(0, count_per_station - 3):
                metric = inject_anomaly(metric, anomaly_type)
                metric["is_anomaly"] = True
                metric["anomaly_type"] = anomaly_type
            rows.append(metric_from_dict(metric))

    db.add_all(rows)
    db.commit()
    return rows


def serialize_metric(metric: NetworkMetric) -> dict:
    return {
        "id": metric.id,
        "base_station_id": metric.base_station_id,
        "timestamp": metric.timestamp.isoformat(),
        "latency_ms": metric.latency_ms,
        "signal_strength_dbm": metric.signal_strength_dbm,
        "throughput_mbps": metric.throughput_mbps,
        "connected_users": metric.connected_users,
        "packet_loss_pct": metric.packet_loss_pct,
        "region": metric.region,
        "is_anomaly": metric.is_anomaly,
        "anomaly_type": metric.anomaly_type,
        "data_mode": getattr(metric, "data_mode", "simulation"),
        "data_quality": getattr(metric, "data_quality", "simulated"),
        "source": getattr(metric, "source", "generator"),
    }


def serialize_station(station: BaseStation) -> dict:
    return {
        "id": station.id,
        "name": station.name,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "region": station.region,
        "frequency_band": station.frequency_band,
        "max_capacity": station.max_capacity,
        "tx_power_dbm": station.tx_power_dbm,
        "status": station.status,
    }


def latest_by_station(metrics: Iterable[NetworkMetric]) -> dict[str, NetworkMetric]:
    latest: dict[str, NetworkMetric] = {}
    for metric in metrics:
        current = latest.get(metric.base_station_id)
        if current is None or metric.timestamp > current.timestamp:
            latest[metric.base_station_id] = metric
    return latest
