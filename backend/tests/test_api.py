import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Asset, DataSourceStatus, LiveAnomaly, MeasurementSession, Observation


def test_mode_aware_api_contracts():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/assets").status_code == 200
        assert client.get("/api/observations/latest", params={"mode": "live"}).status_code == 200
        replay = client.get("/api/observations", params={"mode": "replay"})

        live = client.get("/api/dashboard/summary", params={"mode": "live"})
        simulation = client.get("/api/dashboard/summary", params={"mode": "simulation"})

        assert live.status_code == 200
        assert live.json()["mode"] == "live"
        assert "network_load_index" in live.json()
        assert simulation.status_code == 200
        assert simulation.json()["mode"] == "simulation"
        assert replay.status_code == 200
        assert all(row["data_mode"] == "replay" for row in replay.json())
        assert client.get("/api/models").status_code == 200
        evaluation = client.get("/api/anomaly-evaluation")
        assert evaluation.status_code == 200
        assert 0 <= evaluation.json()["precision"] <= 1
        assert 0 <= evaluation.json()["recall"] <= 1
        latest = client.get("/api/observations/latest", params={"mode": "live"}).json()
        if latest:
            asset_id = latest[0]["asset_id"]
            aggregate = client.get(
                "/api/observations/aggregate",
                params={
                    "asset_id": asset_id,
                    "from": "2020-01-01T00:00:00Z",
                    "to": "2030-01-01T00:00:00Z",
                    "bucket_minutes": 15,
                },
            )
            assert aggregate.status_code == 200


def test_invalid_mode_is_rejected():
    with TestClient(app) as client:
        response = client.get("/api/dashboard/summary", params={"mode": "unknown"})
        assert response.status_code == 422


def test_operator_key_protects_mutating_endpoints():
    os.environ["NETTWIN_OPERATOR_API_KEY"] = "operator-test-key"
    try:
        with TestClient(app) as client:
            denied = client.post("/api/metrics/generate", json={"count_per_station": 1})
            allowed = client.post(
                "/api/metrics/generate",
                json={"count_per_station": 1},
                headers={"X-Operator-Key": "operator-test-key"},
            )
            assert denied.status_code == 401
            assert allowed.status_code == 200
    finally:
        os.environ.pop("NETTWIN_OPERATOR_API_KEY", None)


def test_live_dashboard_and_anomaly_api_report_current_state():
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    asset = Asset(
        asset_type="ripe_probe",
        source="api-summary-test",
        external_id="probe-current",
        name="Current Test Probe",
        active=True,
    )
    db.add(asset)
    db.flush()
    observation = Observation(
        asset_id=asset.id,
        source=asset.source,
        source_observation_id="current-observation",
        observed_at=now,
        latency_ms=80,
    )
    db.add(observation)
    db.flush()
    db.add(
        LiveAnomaly(
            observation_id=observation.id,
            asset_id=asset.id,
            anomaly_type="latency_spike",
            severity="Critical",
            score=9,
            model_version="test",
            message="Current test anomaly",
            detected_at=now,
        )
    )
    db.add(
        DataSourceStatus(
            source="api-summary-unconfigured",
            status="unconfigured",
            message="Not configured",
        )
    )
    db.commit()
    try:
        with TestClient(app) as client:
            summary = client.get("/api/dashboard/summary", params={"mode": "live"}).json()
            anomalies = client.get(
                "/api/live-anomalies",
                params={
                    "resolved": False,
                    "since": (now - timedelta(minutes=1)).isoformat(),
                    "limit": 1,
                },
            )

        assert summary["open_alerts"] >= 1
        assert summary["critical_alerts"] >= 1
        assert summary["unconfigured_sources"] >= 1
        assert summary["latest_observation_at"] is not None
        assert anomalies.status_code == 200
        assert len(anomalies.json()) == 1
        assert anomalies.json()[0]["asset_name"] == "Current Test Probe"
        assert anomalies.json()[0]["asset_source"] == "api-summary-test"
    finally:
        db.query(LiveAnomaly).filter(LiveAnomaly.asset_id == asset.id).delete()
        db.query(Observation).filter(Observation.asset_id == asset.id).delete()
        db.query(DataSourceStatus).filter(
            DataSourceStatus.source == "api-summary-unconfigured"
        ).delete()
        db.delete(asset)
        db.commit()
        db.close()


def test_attack_optimization_approval_flow():
    os.environ["NETTWIN_OPERATOR_API_KEY"] = "operator-flow-key"
    headers = {"X-Operator-Key": "operator-flow-key"}
    try:
        with TestClient(app) as client:
            station_id = client.get("/api/base-stations").json()[0]["id"]
            attack = client.post(
                "/api/attack-simulation",
                headers=headers,
                json={
                    "attack_type": "jamming",
                    "target_station_id": station_id,
                    "count_per_station": 6,
                },
            )
            assert attack.status_code == 200
            assert attack.json()["alerts"]
            assert attack.json()["optimizations"]

            optimization_id = attack.json()["optimizations"][0]["id"]
            evaluation = client.post(
                f"/api/optimizations/{optimization_id}/evaluate",
                headers=headers,
            )
            assert evaluation.status_code == 200
            evaluation_id = evaluation.json()["id"]

            approval = client.patch(
                f"/api/optimization-evaluations/{evaluation_id}",
                headers=headers,
                json={"approved": True},
            )
            assert approval.status_code == 200

            applied = client.patch(
                f"/api/optimizations/{optimization_id}",
                headers=headers,
                json={"status": "Applied"},
            )
            assert applied.status_code == 200
            assert applied.json()["status"] == "Applied"
    finally:
        os.environ.pop("NETTWIN_OPERATOR_API_KEY", None)


def test_scenario_returns_every_summary_step_and_validates_parameters():
    with TestClient(app) as client:
        created = client.post(
            "/api/scenarios",
            json={"name": "Full result", "steps": 60, "parameters": {"user_multiplier": 2}},
        )
        assert created.status_code == 200
        assert created.json()["result_count"] == 60 * 12
        assert len(created.json()["summary"]) == 60
        assert created.json()["summary"][-1]["step"] == 59

        invalid = client.post(
            "/api/scenarios",
            json={"parameters": {"user_multiplier": "invalid"}},
        )
        assert invalid.status_code == 422


def test_applied_optimization_is_idempotent():
    with TestClient(app) as client:
        station_id = client.get("/api/base-stations").json()[0]["id"]
        attack = client.post(
            "/api/attack-simulation",
            json={"attack_type": "jamming", "target_station_id": station_id, "count_per_station": 6},
        ).json()
        optimization_id = attack["optimizations"][0]["id"]
        evaluation = client.post(f"/api/optimizations/{optimization_id}/evaluate").json()
        client.patch(
            f"/api/optimization-evaluations/{evaluation['id']}", json={"approved": True}
        )
        first = client.patch(
            f"/api/optimizations/{optimization_id}", json={"status": "Applied"}
        )
        second = client.patch(
            f"/api/optimizations/{optimization_id}", json={"status": "Applied"}
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "Applied"


def test_measurement_session_lifecycle_and_export():
    with TestClient(app) as client:
        session = client.post("/api/measurement-sessions", json={"name": "Walk test"})
        assert session.status_code == 200
        session_id = session.json()["id"]
        db = SessionLocal()
        asset = Asset(
            asset_type="local_agent", source="session-test", external_id=f"pc-{session_id}",
            name="Session test computer", active=True,
        )
        db.add(asset)
        db.flush()
        db.add(Observation(
            asset_id=asset.id, session_id=session_id, source=asset.source,
            source_observation_id=f"session-observation-{session_id}",
            observed_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            latitude=41.01, longitude=28.98, latency_ms=21,
            measurement_method="https_request_and_download", measurement_target="example.test",
        ))
        db.commit()
        db.close()
        exported = client.get(f"/api/measurement-sessions/{session_id}/export?format=json")
        assert exported.status_code == 200
        assert len(exported.json()["observations"]) == 1
        assert "latitude" not in exported.json()["observations"][0]
        completed = client.patch(
            f"/api/measurement-sessions/{session_id}", json={"status": "completed"}
        )
        assert completed.status_code == 200


def test_session_capture_and_comparison_require_compatible_measurements(monkeypatch):
    monkeypatch.setattr(
        "app.main.TelemetryService.sync_all",
        lambda _service, source=None, session_id=None: [
            {"source": source, "status": "healthy", "message": f"session {session_id}", "records_received": 1}
        ],
    )
    with TestClient(app) as client:
        first = client.post("/api/measurement-sessions", json={"name": "Before"}).json()
        second = client.post("/api/measurement-sessions", json={"name": "After"}).json()
        assert client.post(f"/api/measurement-sessions/{first['id']}/capture").status_code == 200

        db = SessionLocal()
        asset = Asset(asset_type="local_agent", source="compare-test", external_id=f"pc-{first['id']}", name="PC", active=True)
        db.add(asset)
        db.flush()
        for index, session_id in enumerate((first["id"], second["id"])):
            db.add(Observation(
                asset_id=asset.id, session_id=session_id, source=asset.source,
                source_observation_id=f"compare-{first['id']}-{index}",
                observed_at=datetime(2026, 9, 14, 12, index, tzinfo=timezone.utc),
                latency_ms=20 + index, measurement_method="https_request_and_download",
                measurement_target="example.test",
            ))
        db.commit()
        db.close()

        compared = client.get("/api/measurement-sessions/compare", params={"first": first["id"], "second": second["id"]})
        assert compared.status_code == 200
        assert compared.json()["compatible"] is True
        assert client.get("/api/measurement-sessions/compare", params={"first": first["id"], "second": first["id"]}).status_code == 422


def test_operator_cookie_authentication():
    os.environ["NETTWIN_OPERATOR_API_KEY"] = "cookie-operator-key"
    try:
        with TestClient(app) as client:
            denied = client.post("/api/measurement-sessions", json={"name": "Denied"})
            assert denied.status_code == 401
            login = client.post("/api/operator/session", json={"api_key": "cookie-operator-key"})
            assert login.status_code == 200
            assert "httponly" in login.headers["set-cookie"].lower()
            allowed = client.post("/api/measurement-sessions", json={"name": "Cookie session"})
            assert allowed.status_code == 200
    finally:
        os.environ.pop("NETTWIN_OPERATOR_API_KEY", None)


def test_ingestion_job_is_trackable(monkeypatch):
    monkeypatch.setattr(
        "app.main.TelemetryService.sync_all",
        lambda _service, source=None: [{"source": source or "all", "status": "healthy"}],
    )
    with TestClient(app) as client:
        queued = client.post("/api/ingestion/sync", json={})
        assert queued.status_code == 202
        completed = client.get(f"/api/ingestion/jobs/{queued.json()['id']}")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["sources"][0]["status"] == "healthy"


def test_observation_cursor_is_deterministic():
    with TestClient(app) as client:
        first_page = client.get("/api/observations", params={"limit": 2})
        assert first_page.status_code == 200
        if len(first_page.json()) == 2:
            cursor_at = first_page.headers["X-Next-Cursor-At"]
            cursor_id = first_page.headers["X-Next-Cursor-Id"]
            second_page = client.get(
                "/api/observations",
                params={"limit": 2, "cursor_at": cursor_at, "cursor_id": cursor_id},
            )
            assert second_page.status_code == 200
            assert {row["id"] for row in first_page.json()}.isdisjoint(
                row["id"] for row in second_page.json()
            )


def test_live_anomaly_can_be_resolved_with_note():
    db = SessionLocal()
    anomaly = db.query(LiveAnomaly).first()
    anomaly_id = anomaly.id if anomaly else None
    db.close()
    if anomaly_id is None:
        return
    with TestClient(app) as client:
        response = client.patch(
            f"/api/live-anomalies/{anomaly_id}",
            json={"resolved": True, "note": "Reviewed during test"},
        )
        assert response.status_code == 200
        assert response.json()["resolution_note"] == "Reviewed during test"


def test_readiness_and_system_status():
    with TestClient(app) as client:
        ready = client.get("/api/health/ready")
        system = client.get("/api/system/status")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
        assert system.status_code == 200
        assert system.json()["database"] == "sqlite"
        assert system.json()["observation_count"] >= 0
