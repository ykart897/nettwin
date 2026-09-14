from __future__ import annotations

import json
from statistics import mean, pstdev

from app.models import Alert, NetworkMetric


def _metric_value(metric, key: str):
    if isinstance(metric, dict):
        return metric[key]
    return getattr(metric, key)


def _snapshot(metric) -> dict:
    if isinstance(metric, dict):
        payload = dict(metric)
        if hasattr(payload.get("timestamp"), "isoformat"):
            payload["timestamp"] = payload["timestamp"].isoformat()
        return payload
    return {
        "base_station_id": metric.base_station_id,
        "timestamp": metric.timestamp.isoformat(),
        "latency_ms": metric.latency_ms,
        "signal_strength_dbm": metric.signal_strength_dbm,
        "throughput_mbps": metric.throughput_mbps,
        "connected_users": metric.connected_users,
        "packet_loss_pct": metric.packet_loss_pct,
        "region": metric.region,
    }


class AnomalyDetector:
    def build_baseline(self, metrics: list[NetworkMetric]) -> dict:
        def stats(field: str) -> tuple[float, float]:
            values = [float(getattr(metric, field)) for metric in metrics if getattr(metric, field) is not None]
            if not values:
                return 0.0, 1.0
            deviation = pstdev(values) if len(values) > 1 else 1.0
            return mean(values), max(deviation, 1.0)

        connected_mean, connected_std = stats("connected_users")
        throughput_mean, throughput_std = stats("throughput_mbps")
        latency_mean, latency_std = stats("latency_ms")
        return {
            "connected_users_mean": connected_mean,
            "connected_users_std": connected_std,
            "throughput_mean": throughput_mean,
            "throughput_std": throughput_std,
            "latency_mean": latency_mean,
            "latency_std": latency_std,
        }

    def detect(self, metric, baseline: dict) -> list[dict]:
        alerts = []
        users = _metric_value(metric, "connected_users")
        signal = _metric_value(metric, "signal_strength_dbm")
        throughput = _metric_value(metric, "throughput_mbps")
        packet_loss = _metric_value(metric, "packet_loss_pct")
        latency = _metric_value(metric, "latency_ms")

        if users > baseline["connected_users_mean"] + 3 * baseline["connected_users_std"]:
            alerts.append(("ddos_surge", "Critical", "DDoS-like user surge detected"))
        if signal < -100:
            alerts.append(("signal_jamming", "High", "Potential signal jamming: abnormal signal degradation"))
        if throughput > baseline["throughput_mean"] + 2 * baseline["throughput_std"] and packet_loss > 5.0:
            alerts.append(("data_exfiltration", "High", "Anomalous throughput with high packet loss detected"))
        if latency > baseline["latency_mean"] + 2 * baseline["latency_std"]:
            alerts.append(("latency_degradation", "Medium", "Sustained latency degradation detected"))

        return [
            {
                "base_station_id": _metric_value(metric, "base_station_id"),
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                "metric_snapshot": _snapshot(metric),
            }
            for alert_type, severity, message in alerts
        ]

    def persist_alerts(self, db, alert_payloads: list[dict]) -> list[Alert]:
        rows = []
        for payload in alert_payloads:
            row = Alert(
                base_station_id=payload["base_station_id"],
                alert_type=payload["alert_type"],
                severity=payload["severity"],
                message=payload["message"],
                metric_snapshot=json.dumps(payload["metric_snapshot"], default=str),
            )
            rows.append(row)
        db.add_all(rows)
        db.commit()
        return rows


def serialize_alert(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "base_station_id": alert.base_station_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "metric_snapshot": json.loads(alert.metric_snapshot) if alert.metric_snapshot else {},
        "detected_at": alert.detected_at.isoformat() if alert.detected_at else None,
        "resolved": alert.resolved,
    }

