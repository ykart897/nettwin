from datetime import datetime, timezone

from app.database import Base, SessionLocal, engine
from app.models import BaseStation, NetworkMetric, Optimization, OptimizationEvaluation
from app.optimization_evaluator import OptimizationEvaluator
import pytest


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_evaluation_projects_effect_without_mutating_station():
    db = SessionLocal()
    try:
        station = db.get(BaseStation, "EVAL-001")
        if station is None:
            station = BaseStation(
                id="EVAL-001",
                name="Evaluation Station",
                latitude=41,
                longitude=29,
                region="Urban",
                tx_power_dbm=30,
            )
            db.add(station)
            db.flush()
        db.add(
            NetworkMetric(
                base_station_id=station.id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=30,
                signal_strength_dbm=-105,
                throughput_mbps=100,
                connected_users=150,
                packet_loss_pct=5,
                region="Urban",
            )
        )
        item = Optimization(
            base_station_id=station.id,
            suggestion_type="Power Boost",
            description="Test",
            parameters="{}",
        )
        db.add(item)
        db.commit()

        evaluation = OptimizationEvaluator().evaluate(db, item)

        assert evaluation.risk_level == "High"
        assert station.tx_power_dbm == 30
        assert db.query(OptimizationEvaluation).filter_by(id=evaluation.id).one()

        snapshot = OptimizationEvaluator().apply_to_simulation(db, item, evaluation)
        assert station.tx_power_dbm == 35
        assert snapshot.source == "approved_optimization"
    finally:
        db.close()


def test_evaluation_rejects_changed_simulation_state():
    db = SessionLocal()
    try:
        station = db.get(BaseStation, "EVAL-STALE") or BaseStation(
            id="EVAL-STALE", name="Stale Station", latitude=41, longitude=29,
            region="Urban", tx_power_dbm=30,
        )
        db.add(station)
        db.add(NetworkMetric(
            base_station_id=station.id, timestamp=datetime.now(timezone.utc), latency_ms=30,
            signal_strength_dbm=-100, throughput_mbps=100, connected_users=100,
            packet_loss_pct=2, region="Urban",
        ))
        item = Optimization(base_station_id=station.id, suggestion_type="Power Boost", parameters="{}")
        db.add(item)
        db.commit()
        evaluation = OptimizationEvaluator().evaluate(db, item)
        db.add(NetworkMetric(
            base_station_id=station.id, timestamp=datetime.now(timezone.utc), latency_ms=31,
            signal_strength_dbm=-101, throughput_mbps=99, connected_users=101,
            packet_loss_pct=2, region="Urban",
        ))
        db.commit()
        with pytest.raises(ValueError, match="changed after evaluation"):
            OptimizationEvaluator().apply_to_simulation(db, item, evaluation)
    finally:
        db.close()
