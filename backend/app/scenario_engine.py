from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np

from app.anomaly_detector import AnomalyDetector
from app.data_generator import generate_metric_dict
from app.models import BaseStation, Scenario, ScenarioResult


class ScenarioEngine:
    def run(self, db, name: str, description: str | None, parameters: dict, steps: int = 60) -> Scenario:
        scenario = Scenario(
            name=name,
            description=description,
            parameters=json.dumps(parameters),
            status="Running",
        )
        db.add(scenario)
        db.commit()
        db.refresh(scenario)

        rng = np.random.default_rng(parameters.get("seed", 2026))
        stations = db.query(BaseStation).order_by(BaseStation.id).all()
        rows = []
        now = datetime.now(timezone.utc)
        user_multiplier = float(parameters.get("user_multiplier", 1))
        latency_offset = float(parameters.get("latency_offset", 0))
        signal_offset = float(parameters.get("signal_offset", 0))

        for step in range(steps):
            timestamp = now + timedelta(seconds=step * 5)
            for station in stations:
                metric = generate_metric_dict(station, rng, timestamp=timestamp)
                metric["connected_users"] = int(metric["connected_users"] * user_multiplier)
                metric["latency_ms"] = round(
                    metric["latency_ms"] * (1 + 0.15 * (user_multiplier - 1)) + latency_offset,
                    2,
                )
                metric["packet_loss_pct"] = round(
                    min(100.0, metric["packet_loss_pct"] * max(user_multiplier, 1) ** 0.8),
                    3,
                )
                metric["throughput_mbps"] = round(
                    metric["throughput_mbps"] / (1 + 0.1 * (user_multiplier - 1)),
                    1,
                )
                metric["signal_strength_dbm"] = round(metric["signal_strength_dbm"] + signal_offset, 1)
                rows.append(
                    ScenarioResult(
                        scenario_id=scenario.id,
                        step=step,
                        base_station_id=station.id,
                        latency_ms=metric["latency_ms"],
                        signal_strength_dbm=metric["signal_strength_dbm"],
                        throughput_mbps=metric["throughput_mbps"],
                        connected_users=metric["connected_users"],
                        packet_loss_pct=metric["packet_loss_pct"],
                        timestamp=timestamp,
                    )
                )

        db.add_all(rows)
        scenario.status = "Completed"
        scenario.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(scenario)
        return scenario


def serialize_scenario(scenario: Scenario) -> dict:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "parameters": json.loads(scenario.parameters) if scenario.parameters else {},
        "status": scenario.status,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
        "completed_at": scenario.completed_at.isoformat() if scenario.completed_at else None,
    }


def serialize_scenario_result(row: ScenarioResult) -> dict:
    return {
        "id": row.id,
        "scenario_id": row.scenario_id,
        "step": row.step,
        "base_station_id": row.base_station_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "latency_ms": row.latency_ms,
        "signal_strength_dbm": row.signal_strength_dbm,
        "throughput_mbps": row.throughput_mbps,
        "connected_users": row.connected_users,
        "packet_loss_pct": row.packet_loss_pct,
    }

