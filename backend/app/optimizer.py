from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt

from app.models import Alert, BaseStation, NetworkMetric, Optimization


class Optimizer:
    def suggestions_for_alert(self, db, alert: Alert) -> list[Optimization]:
        station = db.get(BaseStation, alert.base_station_id)
        if station is None:
            return []

        latest_metric = (
            db.query(NetworkMetric)
            .filter(NetworkMetric.base_station_id == station.id)
            .order_by(NetworkMetric.timestamp.desc())
            .first()
        )
        payloads = []

        if alert.alert_type == "ddos_surge":
            payloads.append(
                {
                    "suggestion_type": "Rate Limiting",
                    "description": f"Throttle suspicious connection bursts at {station.name}.",
                    "parameters": {"action": "rate_limit", "station": station.id, "max_conn_per_sec": 50},
                }
            )

        if latest_metric and latest_metric.connected_users > station.max_capacity * 0.8:
            target = self._nearest_underutilized_station(db, station.id)
            if target:
                payloads.append(
                {
                    "suggestion_type": "Load Balancing",
                    "description": f"Redirect overflow traffic away from {station.name}.",
                    "parameters": {
                        "action": "redirect",
                        "from": station.id,
                        "to": target.id if target else None,
                        "user_count": 30,
                    },
                }
                )

        if alert.alert_type == "signal_jamming" or (latest_metric and latest_metric.signal_strength_dbm < -90):
            payloads.append(
                {
                    "suggestion_type": "Power Boost",
                    "description": f"Increase transmit power to recover coverage around {station.name}.",
                    "parameters": {"action": "power_adjust", "station": station.id, "new_tx_power": station.tx_power_dbm + 5},
                }
            )

        if latest_metric and latest_metric.packet_loss_pct > 3:
            payloads.append(
                {
                    "suggestion_type": "Frequency Switch",
                    "description": f"Move {station.name} to a cleaner 6G-FR3 band.",
                    "parameters": {"action": "freq_change", "station": station.id, "new_band": "6G-FR3-B2"},
                }
            )

        if latest_metric and latest_metric.throughput_mbps < 200:
            payloads.append(
                {
                    "suggestion_type": "Capacity Upgrade",
                    "description": f"Flag {station.name} for hardware capacity review.",
                    "parameters": {"action": "upgrade_flag", "station": station.id, "reason": "sustained_low_throughput"},
                }
            )

        rows = [
            Optimization(
                alert_id=alert.id,
                base_station_id=station.id,
                suggestion_type=payload["suggestion_type"],
                description=payload["description"],
                parameters=json.dumps(payload["parameters"]),
            )
            for payload in payloads
        ]
        db.add_all(rows)
        db.commit()
        return rows

    def _nearest_underutilized_station(self, db, source_station_id: str):
        source = db.get(BaseStation, source_station_id)
        stations = db.query(BaseStation).filter(BaseStation.id != source_station_id).all()
        candidates = []
        for station in stations:
            metric = (
                db.query(NetworkMetric)
                .filter(NetworkMetric.base_station_id == station.id)
                .order_by(NetworkMetric.timestamp.desc())
                .first()
            )
            if metric and metric.connected_users < station.max_capacity * 0.6:
                candidates.append(station)
        if source is None or not candidates:
            return None
        return min(candidates, key=lambda station: (_distance_km(source, station), station.id))


def _distance_km(source: BaseStation, target: BaseStation) -> float:
    dlat = radians(target.latitude - source.latitude)
    dlon = radians(target.longitude - source.longitude)
    a = sin(dlat / 2) ** 2 + cos(radians(source.latitude)) * cos(radians(target.latitude)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def serialize_optimization(item: Optimization) -> dict:
    return {
        "id": item.id,
        "alert_id": item.alert_id,
        "base_station_id": item.base_station_id,
        "suggestion_type": item.suggestion_type,
        "description": item.description,
        "parameters": json.loads(item.parameters) if item.parameters else {},
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
