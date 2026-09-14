from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.live_anomaly import LiveAnomalyDetector
from app.models import Asset, LiveAnomaly, Observation


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_robust_detector_flags_asset_specific_latency_spike():
    db = SessionLocal()
    try:
        asset = (
            db.query(Asset)
            .filter(Asset.source == "anomaly-test", Asset.external_id == "probe")
            .first()
        )
        if asset is None:
            asset = Asset(
                asset_type="ripe_probe",
                source="anomaly-test",
                external_id="probe",
                name="Probe",
            )
            db.add(asset)
            db.flush()
        else:
            observation_ids = [
                row[0] for row in db.query(Observation.id).filter(Observation.asset_id == asset.id).all()
            ]
            if observation_ids:
                db.query(LiveAnomaly).filter(
                    LiveAnomaly.observation_id.in_(observation_ids)
                ).delete(synchronize_session=False)
                db.query(Observation).filter(Observation.asset_id == asset.id).delete(
                    synchronize_session=False
                )
                db.commit()
        start = datetime(2026, 6, 13, tzinfo=timezone.utc)
        for index in range(12):
            db.add(
                Observation(
                    asset_id=asset.id,
                    source="anomaly-test",
                    source_observation_id=f"baseline-{index}",
                    observed_at=start + timedelta(minutes=index),
                    latency_ms=20 + index % 2,
                )
            )
        db.commit()
        spike = Observation(
            asset_id=asset.id,
            source="anomaly-test",
            source_observation_id="spike",
            observed_at=start + timedelta(minutes=20),
            latency_ms=120,
        )
        db.add(spike)
        db.flush()

        anomalies = LiveAnomalyDetector().evaluate(db, spike)
        db.commit()

        assert any(row.anomaly_type == "latency_spike" for row in anomalies)
        assert db.query(LiveAnomaly).filter(LiveAnomaly.observation_id == spike.id).count() >= 1
    finally:
        db.close()
