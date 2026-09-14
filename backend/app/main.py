from __future__ import annotations

import asyncio
import csv
import hmac
import html
import io
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.anomaly_detector import AnomalyDetector, serialize_alert
from app.data_generator import (
    generate_metric_batch,
    latest_by_station,
    seed_base_stations,
    serialize_metric,
    serialize_station,
)
from app.database import engine, get_db, init_db
from app.models import (
    Alert,
    Asset,
    AssetRelation,
    BaseStation,
    DataSourceStatus,
    IngestionJob,
    LiveAnomaly,
    MeasurementSession,
    NetworkMetric,
    Observation,
    Optimization,
    OptimizationEvaluation,
    Scenario,
    ScenarioResult,
)
from app.optimization_evaluator import OptimizationEvaluator, serialize_evaluation
from app.optimizer import Optimizer, serialize_optimization
from app.scenario_engine import ScenarioEngine, serialize_scenario, serialize_scenario_result
from app.telemetry import TelemetryService
from app.telemetry.load_index import model_version
from app.telemetry.serializers import serialize_asset, serialize_observation, serialize_source_status
from app.topology import TopologyService


scheduler = BackgroundScheduler(timezone="UTC")
operator_sessions: dict[str, float] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    on_startup()
    try:
        yield
    finally:
        on_shutdown()


app = FastAPI(
    title="NetTwin Radio Network Digital Twin API",
    description="Observed network telemetry, replay, research sessions, simulations, anomaly detection, and evaluated optimization suggestions.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:15173", "http://127.0.0.1:15173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MetricGenerationRequest(BaseModel):
    count_per_station: int = Field(default=6, ge=1, le=120)
    anomaly_type: str | None = Field(default=None, pattern="^(ddos|jamming|exfiltration)$")
    target_station_id: str | None = None
    seed: int | None = None


class ScenarioParameters(BaseModel):
    user_multiplier: float = Field(default=1, ge=0.5, le=5)
    latency_offset: float = Field(default=0, ge=0, le=60)
    signal_offset: float = Field(default=0, ge=-60, le=20)
    seed: int = 2026


class ScenarioRequest(BaseModel):
    name: str = Field(default="User Surge", min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    parameters: ScenarioParameters = Field(default_factory=ScenarioParameters)
    steps: int = Field(default=60, ge=1, le=240)


class AttackSimulationRequest(BaseModel):
    attack_type: str = Field(pattern="^(ddos|jamming|exfiltration)$")
    target_station_id: str | None = None
    count_per_station: int = Field(default=6, ge=3, le=60)


class AlertPatchRequest(BaseModel):
    resolved: bool
    note: str | None = Field(default=None, max_length=2000)


class OptimizationPatchRequest(BaseModel):
    status: str = Field(pattern="^(Pending|Applied|Dismissed)$")


class IngestionSyncRequest(BaseModel):
    source: str | None = Field(default=None, pattern="^(opencellid|ripe_atlas|local_agent)$")


class ApprovalRequest(BaseModel):
    approved: bool


class OperatorLoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


class MeasurementSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class MeasurementSessionPatch(BaseModel):
    status: str = Field(pattern="^(active|completed)$")


def require_operator(request: Request, x_operator_key: str | None = Header(default=None)):
    expected_key = os.getenv("NETTWIN_OPERATOR_API_KEY")
    if not expected_key:
        return
    cookie = request.cookies.get("nettwin_operator")
    cookie_valid = bool(cookie and operator_sessions.get(cookie, 0) > time.time())
    header_valid = bool(x_operator_key and hmac.compare_digest(x_operator_key, expected_key))
    if not cookie_valid and not header_valid:
        raise HTTPException(status_code=401, detail="Invalid operator key")


@app.post("/api/operator/session")
def create_operator_session(payload: OperatorLoginRequest, response: Response):
    expected_key = os.getenv("NETTWIN_OPERATOR_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="Operator protection is not configured")
    if not hmac.compare_digest(payload.api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid operator key")
    token = secrets.token_urlsafe(32)
    operator_sessions[token] = time.time() + 8 * 60 * 60
    response.set_cookie(
        "nettwin_operator", token, max_age=8 * 60 * 60, httponly=True, samesite="strict"
    )
    return {"authenticated": True, "expires_in_seconds": 8 * 60 * 60}


@app.delete("/api/operator/session")
def delete_operator_session(request: Request, response: Response):
    token = request.cookies.get("nettwin_operator")
    if token:
        operator_sessions.pop(token, None)
    response.delete_cookie("nettwin_operator")
    return {"authenticated": False}


def on_startup():
    init_db()
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        seed_base_stations(db)
        metric_count = db.scalar(select(func.count(NetworkMetric.id))) or 0
        if metric_count == 0:
            generate_metric_batch(db, count_per_station=24, seed=2026)
        for source in ("opencellid", "ripe_atlas", "local_agent"):
            if not db.query(DataSourceStatus).filter(DataSourceStatus.source == source).first():
                db.add(DataSourceStatus(source=source, status="unconfigured"))
        db.query(IngestionJob).filter(IngestionJob.status.in_(("queued", "running"))).update(
            {
                IngestionJob.status: "failed",
                IngestionJob.error: "Backend restarted before the ingestion job completed.",
                IngestionJob.completed_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
    if os.getenv("NETTWIN_DISABLE_SCHEDULER") != "1" and not scheduler.running:
        scheduler.add_job(
            lambda: TelemetryService().sync_all("local_agent"),
            "interval",
            minutes=5,
            id="local-agent-sync",
            replace_existing=True,
        )
        scheduler.add_job(
            lambda: TelemetryService().sync_all("ripe_atlas"),
            "interval",
            minutes=5,
            id="ripe-atlas-sync",
            replace_existing=True,
        )
        scheduler.add_job(
            lambda: TelemetryService().sync_all("opencellid"),
            "interval",
            hours=24,
            id="opencellid-sync",
            replace_existing=True,
        )
        scheduler.add_job(
            cleanup_observations,
            "interval",
            hours=24,
            id="observation-retention",
            replace_existing=True,
        )
        scheduler.start()


def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nettwin-api", "version": app.version}


@app.get("/api/health/ready")
def readiness(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ready", "database": engine.dialect.name}


@app.get("/api/system/status")
def system_status(db: Session = Depends(get_db)):
    db.execute(select(1))
    database_size = None
    latest_backup = None
    if engine.dialect.name == "sqlite":
        database_path = Path(engine.url.database or "")
        if database_path.exists():
            database_size = database_path.stat().st_size
        backups = sorted((Path(__file__).resolve().parent.parent / "backups").glob("nettwin-*.db"))
        if backups:
            latest_backup = datetime.fromtimestamp(
                backups[-1].stat().st_mtime, timezone.utc
            ).isoformat()
    return {
        "status": "ready",
        "database": engine.dialect.name,
        "database_size_bytes": database_size,
        "latest_backup_at": latest_backup,
        "active_ingestion_jobs": db.scalar(
            select(func.count(IngestionJob.id)).where(IngestionJob.status.in_(("queued", "running")))
        ) or 0,
        "observation_count": db.scalar(select(func.count(Observation.id))) or 0,
        "asset_count": db.scalar(select(func.count(Asset.id))) or 0,
    }


@app.get("/api/base-stations")
def list_base_stations(db: Session = Depends(get_db)):
    stations = db.query(BaseStation).order_by(BaseStation.id).all()
    return [serialize_station(station) for station in stations]


@app.get("/api/base-stations/{station_id}")
def get_base_station(station_id: str, db: Session = Depends(get_db)):
    station = db.get(BaseStation, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Base station not found")
    return serialize_station(station)


@app.get("/api/assets")
def list_assets(
    asset_type: str | None = Query(default=None, alias="type"),
    source: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Asset).filter(Asset.active == True)  # noqa: E712
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    if source:
        query = query.filter(Asset.source == source)
    return [serialize_asset(row) for row in query.order_by(Asset.source, Asset.external_id).all()]


@app.get("/api/observations")
def list_observations(
    response: Response,
    asset_id: int | None = Query(default=None),
    session_id: int | None = Query(default=None),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    mode: str = Query(default="live", pattern="^(live|replay)$"),
    limit: int = Query(default=1000, ge=1, le=5000),
    cursor_at: datetime | None = Query(default=None),
    cursor_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    query = db.query(Observation)
    if asset_id is not None:
        query = query.filter(Observation.asset_id == asset_id)
    if session_id is not None:
        query = query.filter(Observation.session_id == session_id)
    if from_at is not None:
        query = query.filter(Observation.observed_at >= from_at)
    if to_at is not None:
        query = query.filter(Observation.observed_at <= to_at)
    if (cursor_at is None) != (cursor_id is None):
        raise HTTPException(status_code=422, detail="cursor_at and cursor_id must be provided together")
    if cursor_at is not None and cursor_id is not None:
        query = query.filter(or_(
            Observation.observed_at < cursor_at,
            and_(Observation.observed_at == cursor_at, Observation.id < cursor_id),
        ))
    rows = query.order_by(Observation.observed_at.desc(), Observation.id.desc()).limit(limit).all()
    if len(rows) == limit:
        response.headers["X-Next-Cursor-At"] = rows[-1].observed_at.isoformat()
        response.headers["X-Next-Cursor-Id"] = str(rows[-1].id)
    return [serialize_observation(row, display_mode=mode) for row in reversed(rows)]


@app.get("/api/observations/latest")
def latest_observations(
    mode: str = Query(default="live", pattern="^(live|replay)$"),
    db: Session = Depends(get_db),
):
    latest_times = (
        db.query(Observation.asset_id, func.max(Observation.observed_at).label("observed_at"))
        .group_by(Observation.asset_id)
        .subquery()
    )
    rows = (
        db.query(Observation)
        .join(Asset, Observation.asset_id == Asset.id)
        .join(
            latest_times,
            (Observation.asset_id == latest_times.c.asset_id)
            & (Observation.observed_at == latest_times.c.observed_at),
        )
        .filter(Asset.active == True)  # noqa: E712
        .order_by(Observation.asset_id)
        .all()
    )
    return [serialize_observation(row, display_mode=mode) for row in rows]


@app.get("/api/observations/aggregate")
def aggregate_observations(
    response: Response,
    asset_id: int,
    from_at: datetime = Query(alias="from"),
    to_at: datetime = Query(alias="to"),
    bucket_minutes: int = Query(default=15, ge=1, le=1440),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Observation)
        .filter(
            Observation.asset_id == asset_id,
            Observation.observed_at >= from_at,
            Observation.observed_at <= to_at,
        )
        .order_by(Observation.observed_at)
        .limit(100000)
        .all()
    )
    if len(rows) == 100000:
        response.headers["X-Results-Truncated"] = "true"
    buckets: dict[datetime, list[Observation]] = {}
    for row in rows:
        timestamp = row.observed_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        bucket_seconds = bucket_minutes * 60
        bucket_epoch = int(timestamp.timestamp()) // bucket_seconds * bucket_seconds
        bucket = datetime.fromtimestamp(bucket_epoch, timezone.utc)
        buckets.setdefault(bucket, []).append(row)

    fields = (
        "latency_ms", "packet_loss_pct", "request_failure_pct", "download_mbps",
        "signal_strength_dbm", "sinr_db", "load_index",
    )
    return [
        {
            "bucket": bucket.isoformat(),
            "count": len(bucket_rows),
            **{
                field: _average_optional(getattr(row, field) for row in bucket_rows)
                for field in fields
            },
        }
        for bucket, bucket_rows in sorted(buckets.items())
    ]


@app.get("/api/data-sources/status")
def data_source_statuses(db: Session = Depends(get_db)):
    rows = db.query(DataSourceStatus).order_by(DataSourceStatus.source).all()
    return [serialize_source_status(row) for row in rows]


@app.post(
    "/api/ingestion/sync",
    dependencies=[Depends(require_operator)],
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_ingestion(
    request: IngestionSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    active = db.query(IngestionJob).filter(
        IngestionJob.status.in_(("queued", "running")),
        IngestionJob.source == request.source,
    ).first()
    if active:
        return _serialize_ingestion_job(active)
    job = IngestionJob(source=request.source)
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_ingestion_job, job.id)
    return _serialize_ingestion_job(job)


@app.get("/api/ingestion/jobs/{job_id}")
def ingestion_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return _serialize_ingestion_job(job)


@app.get("/api/measurement-sessions")
def list_measurement_sessions(db: Session = Depends(get_db)):
    rows = db.query(MeasurementSession).order_by(MeasurementSession.started_at.desc()).all()
    return [_serialize_measurement_session(db, row) for row in rows]


@app.post("/api/measurement-sessions", dependencies=[Depends(require_operator)])
def create_measurement_session(
    request: MeasurementSessionRequest,
    db: Session = Depends(get_db),
):
    row = MeasurementSession(name=request.name.strip(), notes=request.notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_measurement_session(db, row)


@app.patch("/api/measurement-sessions/{session_id}", dependencies=[Depends(require_operator)])
def update_measurement_session(
    session_id: int,
    request: MeasurementSessionPatch,
    db: Session = Depends(get_db),
):
    row = db.get(MeasurementSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Measurement session not found")
    row.status = request.status
    row.ended_at = datetime.now(timezone.utc) if request.status == "completed" else None
    db.commit()
    db.refresh(row)
    return _serialize_measurement_session(db, row)


@app.post("/api/measurement-sessions/{session_id}/capture", dependencies=[Depends(require_operator)])
def capture_measurement_session(session_id: int, db: Session = Depends(get_db)):
    row = db.get(MeasurementSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Measurement session not found")
    if row.status != "active":
        raise HTTPException(status_code=409, detail="Measurement session is completed")
    result = TelemetryService().sync_all("local_agent", session_id=session_id)[0]
    if result["status"] != "healthy":
        raise HTTPException(status_code=502, detail=result["message"])
    return {"session": _serialize_measurement_session(db, row), "source": result}


@app.get("/api/measurement-sessions/{session_id}/export")
def export_measurement_session(
    session_id: int,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    include_location: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    session = db.get(MeasurementSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Measurement session not found")
    rows = db.query(Observation).filter(Observation.session_id == session_id).order_by(
        Observation.observed_at, Observation.id
    ).all()
    payloads = [serialize_observation(row) for row in rows]
    for payload in payloads:
        if not include_location:
            for key in ("latitude", "longitude", "location_accuracy_m", "location_observed_at"):
                payload.pop(key, None)
    if format == "json":
        return {"session": _serialize_measurement_session(db, session), "observations": payloads}
    output = io.StringIO()
    fieldnames = list(payloads[0].keys()) if payloads else ["id", "observed_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for payload in payloads:
        writer.writerow({key: json.dumps(value) if isinstance(value, dict) else value for key, value in payload.items()})
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="nettwin-session-{session_id}.csv"'},
    )


@app.get("/api/measurement-sessions/{session_id}/report")
def measurement_session_report(
    session_id: int,
    format: str = Query(default="json", pattern="^(json|html)$"),
    db: Session = Depends(get_db),
):
    session = db.get(MeasurementSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Measurement session not found")
    rows = db.query(Observation).filter(Observation.session_id == session_id).order_by(
        Observation.observed_at, Observation.id
    ).all()
    metrics = {
        field: _metric_statistics(getattr(row, field) for row in rows)
        for field in (
            "latency_ms", "packet_loss_pct", "request_failure_pct", "download_mbps",
            "signal_strength_dbm", "sinr_db", "load_index",
        )
    }
    report = {
        "session": _serialize_measurement_session(db, session),
        "model_versions": sorted({row.model_version for row in rows if row.model_version}),
        "methods": sorted({row.measurement_method for row in rows if row.measurement_method}),
        "metrics": metrics,
    }
    if format == "json":
        return report
    title = html.escape(session.name)
    metric_rows = "".join(
        f"<tr><th>{html.escape(field)}</th><td>{stats['count']}</td><td>{stats['median']}</td><td>{stats['p95']}</td></tr>"
        for field, stats in metrics.items()
    )
    document = f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>
<style>body{{font:16px system-ui;max-width:900px;margin:40px auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border:1px solid #ccc;text-align:left}}@media print{{button{{display:none}}}}</style>
</head><body><button onclick='print()'>Print / Save PDF</button><h1>{title}</h1>
<p>{len(rows)} observations · {html.escape(str(session.started_at))} – {html.escape(str(session.ended_at or 'active'))}</p>
<table><thead><tr><th>Metric</th><th>Samples</th><th>Median</th><th>P95</th></tr></thead><tbody>{metric_rows}</tbody></table>
<p>Methods: {html.escape(', '.join(report['methods']) or 'unspecified')}</p>
<p>Model versions: {html.escape(', '.join(report['model_versions']) or 'none')}</p></body></html>"""
    return Response(document, media_type="text/html")


@app.get("/api/measurement-sessions/compare")
def compare_measurement_sessions(
    first: int,
    second: int,
    db: Session = Depends(get_db),
):
    reports = []
    for session_id in (first, second):
        session = db.get(MeasurementSession, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Measurement session {session_id} not found")
        rows = db.query(Observation).filter(Observation.session_id == session_id).all()
        methods = sorted({row.measurement_method for row in rows if row.measurement_method})
        targets = sorted({row.measurement_target for row in rows if row.measurement_target})
        reports.append({
            "session": _serialize_measurement_session(db, session),
            "methods": methods,
            "targets": targets,
            "metrics": {
                field: _metric_statistics(getattr(row, field) for row in rows)
                for field in ("latency_ms", "packet_loss_pct", "request_failure_pct", "download_mbps", "signal_strength_dbm", "sinr_db")
            },
        })
    if first == second:
        raise HTTPException(status_code=422, detail="Choose two different measurement sessions")
    if not reports[0]["session"]["observation_count"] or not reports[1]["session"]["observation_count"]:
        raise HTTPException(status_code=422, detail="Both sessions must contain observations")
    if reports[0]["methods"] != reports[1]["methods"] or reports[0]["targets"] != reports[1]["targets"]:
        raise HTTPException(
            status_code=422,
            detail="Sessions must use the same measurement methods and targets",
        )
    return {"compatible": True, "first": reports[0], "second": reports[1]}


@app.get("/api/topology")
def topology(db: Session = Depends(get_db)):
    rows = db.query(AssetRelation).order_by(AssetRelation.relation_type, AssetRelation.id).all()
    return [
        {
            "id": row.id,
            "source_asset_id": row.source_asset_id,
            "target_asset_id": row.target_asset_id,
            "relation_type": row.relation_type,
            "distance_km": row.distance_km,
            "confidence": row.confidence,
            "metadata": json.loads(row.metadata_json or "{}"),
        }
        for row in rows
    ]


@app.post("/api/topology/rebuild", dependencies=[Depends(require_operator)])
def rebuild_topology(db: Session = Depends(get_db)):
    return {"relations_created": TopologyService().rebuild(db)}


@app.get("/api/live-anomalies")
def list_live_anomalies(
    resolved: bool | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(LiveAnomaly, Asset).join(Asset, LiveAnomaly.asset_id == Asset.id)
    if resolved is not None:
        query = query.filter(LiveAnomaly.resolved == resolved)
    if since is not None:
        query = query.filter(LiveAnomaly.detected_at >= since)
    if until is not None:
        query = query.filter(LiveAnomaly.detected_at <= until)
    rows = query.order_by(LiveAnomaly.detected_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "asset_id": row.asset_id,
            "asset_name": asset.name,
            "asset_source": asset.source,
            "observation_id": row.observation_id,
            "anomaly_type": row.anomaly_type,
            "severity": row.severity,
            "score": row.score,
            "model_version": row.model_version,
            "message": row.message,
            "detected_at": row.detected_at.isoformat() if row.detected_at else None,
            "resolved": row.resolved,
            "resolution_note": row.resolution_note,
        }
        for row, asset in rows
    ]


@app.patch("/api/live-anomalies/{anomaly_id}", dependencies=[Depends(require_operator)])
def update_live_anomaly(
    anomaly_id: int,
    request: AlertPatchRequest,
    db: Session = Depends(get_db),
):
    anomaly = db.get(LiveAnomaly, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Live anomaly not found")
    anomaly.resolved = request.resolved
    anomaly.resolution_note = request.note
    db.commit()
    db.refresh(anomaly)
    asset = db.get(Asset, anomaly.asset_id)
    return {
        "id": anomaly.id,
        "asset_id": anomaly.asset_id,
        "asset_name": asset.name if asset else None,
        "anomaly_type": anomaly.anomaly_type,
        "severity": anomaly.severity,
        "score": anomaly.score,
        "model_version": anomaly.model_version,
        "message": anomaly.message,
        "detected_at": anomaly.detected_at.isoformat() if anomaly.detected_at else None,
        "resolved": anomaly.resolved,
        "resolution_note": anomaly.resolution_note,
    }


@app.get("/api/live-anomalies/{anomaly_id}")
def live_anomaly_detail(anomaly_id: int, db: Session = Depends(get_db)):
    anomaly = db.get(LiveAnomaly, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Live anomaly not found")
    observation = db.get(Observation, anomaly.observation_id)
    if observation is None:
        raise HTTPException(status_code=409, detail="Anomaly observation is unavailable")
    history = db.query(Observation).filter(
        Observation.asset_id == observation.asset_id,
        Observation.source == observation.source,
        Observation.measurement_method == observation.measurement_method,
        Observation.measurement_target == observation.measurement_target,
        Observation.observed_at < observation.observed_at,
    ).order_by(Observation.observed_at.desc()).limit(96).all()
    field = {
        "latency_spike": "latency_ms",
        "packet_loss_spike": "packet_loss_pct",
        "signal_degradation": "signal_strength_dbm",
        "sinr_degradation": "sinr_db",
    }.get(anomaly.anomaly_type)
    baseline_values = [getattr(row, field) for row in history if field and getattr(row, field) is not None]
    return {
        "id": anomaly.id,
        "anomaly_type": anomaly.anomaly_type,
        "severity": anomaly.severity,
        "score": anomaly.score,
        "model_version": anomaly.model_version,
        "message": anomaly.message,
        "field": field,
        "value": getattr(observation, field) if field else None,
        "baseline_median": round(median(baseline_values), 3) if baseline_values else None,
        "baseline_sample_count": len(baseline_values),
        "observation": serialize_observation(observation),
    }


@app.get("/api/anomaly-evaluation")
def anomaly_evaluation(db: Session = Depends(get_db)):
    detector = AnomalyDetector()
    rows = db.query(NetworkMetric).order_by(NetworkMetric.base_station_id, NetworkMetric.timestamp).all()
    by_station: dict[str, list[NetworkMetric]] = {}
    for row in rows:
        by_station.setdefault(row.base_station_id, []).append(row)

    true_positive = false_positive = false_negative = true_negative = 0
    for station_rows in by_station.values():
        normal_rows = [row for row in station_rows if not row.is_anomaly]
        baseline = detector.build_baseline(normal_rows)
        for row in station_rows:
            predicted = bool(detector.detect(row, baseline))
            actual = bool(row.is_anomaly)
            if predicted and actual:
                true_positive += 1
            elif predicted:
                false_positive += 1
            elif actual:
                false_negative += 1
            else:
                true_negative += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
    return {
        "model_version": "simulation-threshold-v2",
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "dataset": "labeled simulation metrics",
    }


@app.get("/api/models")
def model_inventory():
    return [
        {
            "name": "Network Load Index",
            "version": model_version(),
            "type": "weighted explainable score",
            "inputs": ["latency", "packet_loss", "throughput", "signal", "sinr"],
        },
        {
            "name": "Live Anomaly Detector",
            "version": "robust-mad-v1",
            "type": "per-asset rolling robust baseline",
            "minimum_history": 12,
        },
        {
            "name": "Simulation Anomaly Detector",
            "version": "simulation-threshold-v2",
            "type": "per-station labeled threshold model",
        },
    ]


@app.get("/api/events")
async def live_events():
    async def stream():
        while True:
            payload = {"type": "refresh", "at": datetime.now(timezone.utc).isoformat()}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/metrics")
def list_metrics(
    station_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    query = db.query(NetworkMetric)
    if station_id:
        query = query.filter(NetworkMetric.base_station_id == station_id)
    if region:
        query = query.filter(NetworkMetric.region == region)
    rows = query.order_by(NetworkMetric.timestamp.desc()).limit(limit).all()
    return [serialize_metric(row) for row in reversed(rows)]


@app.get("/api/metrics/latest")
def latest_metrics(db: Session = Depends(get_db)):
    metrics = db.query(NetworkMetric).order_by(NetworkMetric.timestamp.desc()).limit(2000).all()
    latest = latest_by_station(metrics)
    return [serialize_metric(metric) for metric in sorted(latest.values(), key=lambda item: item.base_station_id)]


@app.post("/api/metrics/generate", dependencies=[Depends(require_operator)])
def generate_metrics(request: MetricGenerationRequest, db: Session = Depends(get_db)):
    baselines = _station_baselines(db)
    rows = generate_metric_batch(
        db,
        count_per_station=request.count_per_station,
        anomaly_type=request.anomaly_type,
        target_station_id=request.target_station_id,
        seed=request.seed,
    )
    detector = AnomalyDetector()
    payloads = []
    for row in rows:
        detected = detector.detect(row, baselines[row.base_station_id])
        payloads.extend(detected)
    db.commit()
    alerts = detector.persist_alerts(db, payloads) if payloads else []
    optimizer = Optimizer()
    optimizations = []
    for alert in alerts:
        optimizations.extend(optimizer.suggestions_for_alert(db, alert))
    return {
        "generated": len(rows),
        "alerts_created": len(alerts),
        "optimizations_created": len(optimizations),
        "latest": [serialize_metric(row) for row in rows[-12:]],
    }


@app.get("/api/scenarios")
def list_scenarios(db: Session = Depends(get_db)):
    rows = db.query(Scenario).order_by(Scenario.created_at.desc()).all()
    return [serialize_scenario(row) for row in rows]


@app.post("/api/scenarios", dependencies=[Depends(require_operator)])
def create_scenario(request: ScenarioRequest, db: Session = Depends(get_db)):
    scenario = ScenarioEngine().run(
        db,
        request.name.strip(),
        request.description,
        request.parameters.model_dump(),
        request.steps,
    )
    return {
        "scenario": serialize_scenario(scenario),
        "result_count": db.scalar(
            select(func.count(ScenarioResult.id)).where(ScenarioResult.scenario_id == scenario.id)
        ) or 0,
        "summary": get_scenario_summary(scenario.id, db=db),
    }


@app.get("/api/scenarios/{scenario_id}/summary")
def get_scenario_summary(scenario_id: int, db: Session = Depends(get_db)):
    if db.get(Scenario, scenario_id) is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    rows = (
        db.query(
            ScenarioResult.step,
            func.avg(ScenarioResult.latency_ms),
            func.avg(ScenarioResult.connected_users),
            func.avg(ScenarioResult.packet_loss_pct),
            func.avg(ScenarioResult.throughput_mbps),
            func.avg(ScenarioResult.signal_strength_dbm),
            func.count(ScenarioResult.id),
        )
        .filter(ScenarioResult.scenario_id == scenario_id)
        .group_by(ScenarioResult.step)
        .order_by(ScenarioResult.step)
        .all()
    )
    return [
        {
            "step": step,
            "latency_ms": round(float(latency), 2),
            "connected_users": round(float(users)),
            "packet_loss_pct": round(float(loss), 3),
            "throughput_mbps": round(float(throughput), 2),
            "signal_strength_dbm": round(float(signal), 2),
            "sample_count": count,
        }
        for step, latency, users, loss, throughput, signal, count in rows
    ]


@app.get("/api/scenarios/compare")
def compare_scenarios(first: int, second: int, db: Session = Depends(get_db)):
    comparisons = []
    for scenario_id in (first, second):
        scenario = db.get(Scenario, scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
        row = db.query(
            func.avg(ScenarioResult.latency_ms),
            func.avg(ScenarioResult.connected_users),
            func.avg(ScenarioResult.packet_loss_pct),
            func.avg(ScenarioResult.throughput_mbps),
        ).filter(ScenarioResult.scenario_id == scenario_id).one()
        comparisons.append({
            "scenario": serialize_scenario(scenario),
            "averages": {
                "latency_ms": round(float(row[0]), 2) if row[0] is not None else None,
                "connected_users": round(float(row[1]), 2) if row[1] is not None else None,
                "packet_loss_pct": round(float(row[2]), 3) if row[2] is not None else None,
                "throughput_mbps": round(float(row[3]), 2) if row[3] is not None else None,
            },
        })
    return {"first": comparisons[0], "second": comparisons[1]}


@app.get("/api/scenarios/{scenario_id}/results")
def get_scenario_results(
    scenario_id: int,
    limit: int = Query(default=500, ge=1, le=3000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    rows = (
        db.query(ScenarioResult)
        .filter(ScenarioResult.scenario_id == scenario_id)
        .order_by(ScenarioResult.step, ScenarioResult.base_station_id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [serialize_scenario_result(row) for row in rows]


@app.post("/api/attack-simulation", dependencies=[Depends(require_operator)])
def run_attack_simulation(request: AttackSimulationRequest, db: Session = Depends(get_db)):
    baselines = _station_baselines(db)
    rows = generate_metric_batch(
        db,
        count_per_station=request.count_per_station,
        anomaly_type=request.attack_type,
        target_station_id=request.target_station_id,
    )
    detector = AnomalyDetector()
    payloads = []
    for row in rows:
        payloads.extend(detector.detect(row, baselines[row.base_station_id]))
    alerts = detector.persist_alerts(db, payloads)
    optimizer = Optimizer()
    optimizations = []
    for alert in alerts:
        optimizations.extend(optimizer.suggestions_for_alert(db, alert))
    return {
        "attack_type": request.attack_type,
        "generated": len(rows),
        "alerts": [serialize_alert(alert) for alert in alerts],
        "optimizations": [serialize_optimization(item) for item in optimizations],
    }


@app.get("/api/alerts")
def list_alerts(
    severity: str | None = Query(default=None),
    station_id: str | None = Query(default=None),
    resolved: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Alert)
    if severity:
        query = query.filter(Alert.severity == severity)
    if station_id:
        query = query.filter(Alert.base_station_id == station_id)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    rows = query.order_by(Alert.detected_at.desc()).limit(300).all()
    return [serialize_alert(row) for row in rows]


@app.patch("/api/alerts/{alert_id}", dependencies=[Depends(require_operator)])
def update_alert(alert_id: int, request: AlertPatchRequest, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = request.resolved
    db.commit()
    db.refresh(alert)
    return serialize_alert(alert)


@app.get("/api/optimizations")
def list_optimizations(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Optimization)
    if status:
        query = query.filter(Optimization.status == status)
    rows = query.order_by(Optimization.created_at.desc()).limit(300).all()
    return [serialize_optimization(row) for row in rows]


@app.patch("/api/optimizations/{optimization_id}", dependencies=[Depends(require_operator)])
def update_optimization(
    optimization_id: int,
    request: OptimizationPatchRequest,
    db: Session = Depends(get_db),
):
    item = db.get(Optimization, optimization_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Optimization not found")
    if item.status == "Applied":
        if request.status == "Applied":
            return serialize_optimization(item)
        raise HTTPException(status_code=409, detail="An applied optimization cannot be changed")
    if request.status == "Applied":
        approved = (
            db.query(OptimizationEvaluation)
            .filter(
                OptimizationEvaluation.optimization_id == optimization_id,
                OptimizationEvaluation.approved == True,  # noqa: E712
            )
            .order_by(OptimizationEvaluation.evaluated_at.desc())
            .first()
        )
        if approved is None:
            raise HTTPException(status_code=409, detail="Optimization requires an approved evaluation")
        try:
            OptimizationEvaluator().apply_to_simulation(db, item, approved, commit=False)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    item.status = request.status
    db.commit()
    db.refresh(item)
    return serialize_optimization(item)


@app.post("/api/optimizations/{optimization_id}/evaluate", dependencies=[Depends(require_operator)])
def evaluate_optimization(optimization_id: int, db: Session = Depends(get_db)):
    item = db.get(Optimization, optimization_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Optimization not found")
    try:
        return serialize_evaluation(OptimizationEvaluator().evaluate(db, item))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch(
    "/api/optimization-evaluations/{evaluation_id}",
    dependencies=[Depends(require_operator)],
)
def approve_evaluation(
    evaluation_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
):
    evaluation = db.get(OptimizationEvaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    evaluation.approved = request.approved
    db.commit()
    db.refresh(evaluation)
    return serialize_evaluation(evaluation)


@app.get("/api/dashboard/summary")
def dashboard_summary(
    mode: str = Query(default="simulation", pattern="^(live|replay|simulation)$"),
    db: Session = Depends(get_db),
):
    if mode in ("live", "replay"):
        return _live_dashboard_summary(db, mode)
    latest = latest_by_station(db.query(NetworkMetric).order_by(NetworkMetric.timestamp.desc()).limit(2000).all())
    latest_metrics = list(latest.values())
    alerts_count = db.scalar(select(func.count(Alert.id)).where(Alert.resolved == False)) or 0  # noqa: E712
    critical_count = db.scalar(
        select(func.count(Alert.id)).where(Alert.resolved == False, Alert.severity == "Critical")  # noqa: E712
    ) or 0
    optimization_count = db.scalar(
        select(func.count(Optimization.id)).where(Optimization.status == "Pending")
    ) or 0

    def avg(field: str) -> float:
        values = [float(getattr(metric, field)) for metric in latest_metrics]
        return round(mean(values), 2) if values else 0.0

    return {
        "avg_latency_ms": avg("latency_ms"),
        "avg_throughput_mbps": avg("throughput_mbps"),
        "avg_packet_loss_pct": avg("packet_loss_pct"),
        "total_connected_users": sum(metric.connected_users for metric in latest_metrics),
        "active_base_stations": len(latest_metrics),
        "open_alerts": alerts_count,
        "critical_alerts": critical_count,
        "pending_optimizations": optimization_count,
        "mode": "simulation",
    }


def _live_dashboard_summary(db: Session, mode: str) -> dict:
    latest_times = (
        db.query(Observation.asset_id, func.max(Observation.observed_at).label("observed_at"))
        .group_by(Observation.asset_id)
        .subquery()
    )
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    rows = (
        db.query(Observation)
        .join(Asset, Observation.asset_id == Asset.id)
        .join(
            latest_times,
            (Observation.asset_id == latest_times.c.asset_id)
            & (Observation.observed_at == latest_times.c.observed_at),
        )
        .filter(Asset.active == True)  # noqa: E712
        .filter(Observation.observed_at >= freshness_cutoff)
        .all()
    )

    def avg(field: str) -> float:
        values = [float(getattr(row, field)) for row in rows if getattr(row, field) is not None]
        return round(mean(values), 2) if values else None

    source_rows = db.query(DataSourceStatus).all()
    serialized_sources = [serialize_source_status(status) for status in source_rows]
    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    open_alerts = db.scalar(
        select(func.count(LiveAnomaly.id)).where(
            LiveAnomaly.resolved == False,  # noqa: E712
            LiveAnomaly.detected_at >= recent_cutoff,
        )
    ) or 0
    critical_alerts = db.scalar(
        select(func.count(LiveAnomaly.id)).where(
            LiveAnomaly.resolved == False,  # noqa: E712
            LiveAnomaly.severity == "Critical",
            LiveAnomaly.detected_at >= recent_cutoff,
        )
    ) or 0
    latest_observation_at = db.scalar(select(func.max(Observation.observed_at)))
    return {
        "mode": mode,
        "avg_latency_ms": avg("latency_ms"),
        "avg_throughput_mbps": avg("download_mbps"),
        "avg_packet_loss_pct": avg("packet_loss_pct"),
        "network_load_index": avg("load_index"),
        "active_assets": len(rows),
        "degraded_sources": sum(
            row["enabled"] and row["status"] == "degraded" for row in serialized_sources
        ),
        "stale_sources": sum(
            row["enabled"] and row["status"] == "healthy" and row["stale"] for row in serialized_sources
        ),
        "unconfigured_sources": sum(
            row["enabled"] and row["status"] == "unconfigured" for row in serialized_sources
        ),
        "open_alerts": open_alerts,
        "critical_alerts": critical_alerts,
        "pending_optimizations": 0,
        "latest_observation_at": (
            latest_observation_at.isoformat() if latest_observation_at else None
        ),
    }


def _station_baselines(db: Session) -> dict[str, dict]:
    detector = AnomalyDetector()
    rows = db.query(NetworkMetric).order_by(NetworkMetric.timestamp.desc()).limit(2000).all()
    by_station: dict[str, list[NetworkMetric]] = {}
    for row in rows:
        if row.data_mode == "simulation":
            by_station.setdefault(row.base_station_id, []).append(row)
    return {
        station.id: detector.build_baseline(by_station.get(station.id, []))
        for station in db.query(BaseStation).all()
    }


def cleanup_observations():
    retention_days = int(os.getenv("OBSERVATION_RETENTION_DAYS", "0"))
    if retention_days <= 0:
        return 0
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        observation_ids = select(Observation.id).where(Observation.observed_at < cutoff)
        db.query(LiveAnomaly).filter(LiveAnomaly.observation_id.in_(observation_ids)).delete(
            synchronize_session=False
        )
        deleted = db.query(Observation).filter(Observation.observed_at < cutoff).delete(
            synchronize_session=False
        )
        db.commit()
        return deleted
    finally:
        db.close()


def _average_optional(values) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(mean(present), 3) if present else None


def _metric_statistics(values) -> dict:
    present = sorted(float(value) for value in values if value is not None)
    if not present:
        return {"count": 0, "median": None, "p95": None}
    index = min(len(present) - 1, max(0, int(0.95 * len(present) + 0.999999) - 1))
    return {"count": len(present), "median": round(median(present), 3), "p95": round(present[index], 3)}


def _serialize_measurement_session(db: Session, row: MeasurementSession) -> dict:
    observation_count = db.scalar(
        select(func.count(Observation.id)).where(Observation.session_id == row.id)
    ) or 0
    return {
        "id": row.id,
        "name": row.name,
        "notes": row.notes,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "observation_count": observation_count,
    }


def _run_ingestion_job(job_id: int):
    from app.database import SessionLocal

    db = SessionLocal()
    job = db.get(IngestionJob, job_id)
    if job is None:
        db.close()
        return
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    source = job.source
    db.close()
    try:
        result = TelemetryService().sync_all(source)
        db = SessionLocal()
        job = db.get(IngestionJob, job_id)
        job.status = "completed"
        job.result_json = json.dumps(result)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
    except Exception as exc:
        db = SessionLocal()
        job = db.get(IngestionJob, job_id)
        job.status = "failed"
        job.error = str(exc)[:500]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.close()


def _serialize_ingestion_job(job: IngestionJob) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "status": job.status,
        "sources": json.loads(job.result_json or "[]"),
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
