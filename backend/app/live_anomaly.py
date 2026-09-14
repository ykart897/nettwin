from __future__ import annotations

from statistics import median

from app.models import LiveAnomaly, Observation


MODEL_VERSION = "robust-mad-v1"


class LiveAnomalyDetector:
    fields = (
        ("latency_ms", "latency_spike", False),
        ("packet_loss_pct", "packet_loss_spike", False),
        ("signal_strength_dbm", "signal_degradation", True),
        ("sinr_db", "sinr_degradation", True),
    )

    def evaluate(self, db, observation: Observation) -> list[LiveAnomaly]:
        history = (
            db.query(Observation)
            .filter(
                Observation.asset_id == observation.asset_id,
                Observation.source == observation.source,
                Observation.measurement_method == observation.measurement_method,
                Observation.measurement_target == observation.measurement_target,
                Observation.id != observation.id,
                Observation.observed_at < observation.observed_at,
            )
            .order_by(Observation.observed_at.desc())
            .limit(96)
            .all()
        )
        anomalies = []
        for field, anomaly_type, lower_is_bad in self.fields:
            current = getattr(observation, field)
            values = [getattr(row, field) for row in history if getattr(row, field) is not None]
            if current is None or len(values) < 12:
                continue
            center = median(values)
            mad = median(abs(value - center) for value in values)
            scale = max(mad * 1.4826, 0.1)
            signed_score = (center - current) / scale if lower_is_bad else (current - center) / scale
            if signed_score < 3.5:
                continue
            severity = "Critical" if signed_score >= 8 else "High" if signed_score >= 5 else "Medium"
            anomalies.append(
                LiveAnomaly(
                    observation_id=observation.id,
                    asset_id=observation.asset_id,
                    anomaly_type=anomaly_type,
                    severity=severity,
                    score=round(signed_score, 2),
                    model_version=MODEL_VERSION,
                    message=f"{field} deviated {signed_score:.1f} robust standard deviations from baseline.",
                )
            )
        db.add_all(anomalies)
        return anomalies
