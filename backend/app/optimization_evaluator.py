from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models import BaseStation, NetworkMetric, Optimization, OptimizationEvaluation


class OptimizationEvaluator:
    def evaluate(self, db, item: Optimization) -> OptimizationEvaluation:
        station = db.get(BaseStation, item.base_station_id)
        metric = (
            db.query(NetworkMetric)
            .filter(NetworkMetric.base_station_id == item.base_station_id)
            .order_by(NetworkMetric.timestamp.desc())
            .first()
        )
        if station is None or metric is None:
            raise ValueError("Optimization has no station baseline.")

        baseline = {
            "latency_ms": metric.latency_ms,
            "throughput_mbps": metric.throughput_mbps,
            "packet_loss_pct": metric.packet_loss_pct,
            "connected_users": metric.connected_users,
            "tx_power_dbm": station.tx_power_dbm,
        }
        projected = dict(baseline)
        risk = "Medium"
        if item.suggestion_type == "Rate Limiting":
            projected["latency_ms"] = round(metric.latency_ms * 0.8, 2)
            projected["packet_loss_pct"] = round(metric.packet_loss_pct * 0.75, 3)
            risk = "Low"
        elif item.suggestion_type == "Load Balancing":
            projected["connected_users"] = max(0, metric.connected_users - 30)
            projected["latency_ms"] = round(metric.latency_ms * 0.85, 2)
            risk = "Medium"
        elif item.suggestion_type == "Power Boost":
            projected["tx_power_dbm"] = station.tx_power_dbm + 5
            risk = "High"
        elif item.suggestion_type == "Frequency Switch":
            projected["packet_loss_pct"] = round(metric.packet_loss_pct * 0.6, 3)
            risk = "High"
        elif item.suggestion_type == "Capacity Upgrade":
            projected["throughput_mbps"] = round(metric.throughput_mbps * 1.25, 1)
            risk = "Medium"

        evaluation = OptimizationEvaluation(
            optimization_id=item.id,
            baseline_metric_id=metric.id,
            station_state_json=json.dumps({
                "tx_power_dbm": station.tx_power_dbm,
                "frequency_band": station.frequency_band,
                "max_capacity": station.max_capacity,
            }),
            baseline_json=json.dumps(baseline),
            projected_json=json.dumps(projected),
            risk_level=risk,
        )
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)
        return evaluation

    def apply_to_simulation(
        self,
        db,
        item: Optimization,
        evaluation: OptimizationEvaluation,
        *,
        commit: bool = True,
    ) -> NetworkMetric:
        station = db.get(BaseStation, item.base_station_id)
        latest = (
            db.query(NetworkMetric)
            .filter(NetworkMetric.base_station_id == item.base_station_id)
            .order_by(NetworkMetric.timestamp.desc())
            .first()
        )
        if station is None or latest is None:
            raise ValueError("Optimization has no simulation state.")
        if evaluation.baseline_metric_id and latest.id != evaluation.baseline_metric_id:
            raise ValueError("Simulation state changed after evaluation; evaluate the optimization again.")
        expected_state = json.loads(evaluation.station_state_json or "{}")
        current_state = {
            "tx_power_dbm": station.tx_power_dbm,
            "frequency_band": station.frequency_band,
            "max_capacity": station.max_capacity,
        }
        if expected_state and expected_state != current_state:
            raise ValueError("Station state changed after evaluation; evaluate the optimization again.")
        projected = json.loads(evaluation.projected_json)
        if "tx_power_dbm" in projected:
            station.tx_power_dbm = projected["tx_power_dbm"]
        if item.suggestion_type == "Frequency Switch":
            station.frequency_band = "6G-FR3-B2"
        if item.suggestion_type == "Capacity Upgrade":
            station.max_capacity = max(station.max_capacity, int(station.max_capacity * 1.25))

        snapshot = NetworkMetric(
            base_station_id=station.id,
            timestamp=datetime.now(timezone.utc),
            latency_ms=projected.get("latency_ms", latest.latency_ms),
            signal_strength_dbm=latest.signal_strength_dbm,
            throughput_mbps=projected.get("throughput_mbps", latest.throughput_mbps),
            connected_users=projected.get("connected_users", latest.connected_users),
            packet_loss_pct=projected.get("packet_loss_pct", latest.packet_loss_pct),
            region=latest.region,
            data_mode="simulation",
            data_quality="simulated",
            source="approved_optimization",
        )
        db.add(snapshot)
        if item.suggestion_type == "Load Balancing":
            parameters = json.loads(item.parameters or "{}")
            target_id = parameters.get("to")
            user_count = int(parameters.get("user_count", 0))
            target_metric = (
                db.query(NetworkMetric)
                .filter(NetworkMetric.base_station_id == target_id)
                .order_by(NetworkMetric.timestamp.desc())
                .first()
            )
            if not target_id or target_metric is None or user_count <= 0:
                raise ValueError("Load balancing has no valid target state.")
            db.add(
                NetworkMetric(
                    base_station_id=target_id,
                    timestamp=snapshot.timestamp,
                    latency_ms=target_metric.latency_ms,
                    signal_strength_dbm=target_metric.signal_strength_dbm,
                    throughput_mbps=target_metric.throughput_mbps,
                    connected_users=target_metric.connected_users + user_count,
                    packet_loss_pct=target_metric.packet_loss_pct,
                    region=target_metric.region,
                    data_mode="simulation",
                    data_quality="simulated",
                    source="approved_optimization",
                )
            )
        if commit:
            db.commit()
            db.refresh(snapshot)
        else:
            db.flush()
        return snapshot


def serialize_evaluation(row: OptimizationEvaluation) -> dict:
    return {
        "id": row.id,
        "optimization_id": row.optimization_id,
        "baseline_metric_id": row.baseline_metric_id,
        "baseline": json.loads(row.baseline_json),
        "projected": json.loads(row.projected_json),
        "risk_level": row.risk_level,
        "approved": row.approved,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
    }
