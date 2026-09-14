from datetime import datetime, timezone

from app.database import Base, SessionLocal, engine
from app.models import Asset, Observation
from app.telemetry.base import ProviderResult, TelemetryProvider
from app.telemetry.service import TelemetryService


class FakeProvider(TelemetryProvider):
    source = "local_agent"

    def sync(self):
        return ProviderResult(
            source=self.source,
            assets=[
                {
                    "asset_type": "local_agent",
                    "source": self.source,
                    "external_id": "test-agent",
                    "name": "Test Agent",
                }
            ],
            observations=[
                {
                    "asset_external_id": "test-agent",
                    "source_observation_id": "obs-1",
                    "observed_at": datetime(2026, 6, 13, tzinfo=timezone.utc),
                    "latency_ms": 25,
                    "packet_loss_pct": 0,
                    "download_mbps": 50,
                }
            ],
        )


class FailingProvider(TelemetryProvider):
    source = "ripe_atlas"

    def sync(self):
        raise TimeoutError("source timed out")


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_sync_is_idempotent_and_keeps_source_metadata():
    service = TelemetryService([FakeProvider()])

    first = service.sync_all()
    second = service.sync_all()

    db = SessionLocal()
    try:
        assert first[0]["records_received"] == 1
        assert second[0]["records_received"] == 0
        assert db.query(Asset).count() == 1
        assert db.query(Asset).filter(Asset.active == True).count() == 1  # noqa: E712
        assert db.query(Observation).count() == 1
        observation = db.query(Observation).one()
        assert observation.data_quality == "observed"
        assert observation.load_index is not None
    finally:
        db.close()


def test_provider_failure_is_reported_without_crashing_service():
    result = TelemetryService([FailingProvider()]).sync_all()

    assert result[0]["status"] == "degraded"
    assert "timed out" in result[0]["message"]
