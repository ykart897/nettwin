import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("NETTWIN_DATABASE_URL", f"sqlite:///{BASE_DIR / 'nettwin.db'}")

engine_options = {"future": True, "pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _migrate_legacy_network_metrics()
        _migrate_observations()
        _migrate_optimization_evaluations()
        _migrate_live_anomalies()


def _migrate_legacy_network_metrics():
    columns = {column["name"] for column in inspect(engine).get_columns("network_metrics")}
    additions = {
        "data_mode": "VARCHAR NOT NULL DEFAULT 'simulation'",
        "data_quality": "VARCHAR NOT NULL DEFAULT 'simulated'",
        "source": "VARCHAR NOT NULL DEFAULT 'generator'",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE network_metrics ADD COLUMN {name} {definition}"))
        connection.execute(
            text(
                "UPDATE network_metrics "
                "SET data_mode='simulation', data_quality='simulated', source='generator' "
                "WHERE data_mode IS NULL OR data_quality IS NULL OR source IS NULL"
            )
        )


def _migrate_observations():
    columns = {column["name"] for column in inspect(engine).get_columns("observations")}
    additions = {
        "signal_quality_db": "FLOAT",
        "sinr_db": "FLOAT",
        "network_type": "VARCHAR",
        "model_version": "VARCHAR",
        "request_failure_pct": "FLOAT",
        "latitude": "FLOAT",
        "longitude": "FLOAT",
        "location_accuracy_m": "FLOAT",
        "location_observed_at": "DATETIME",
        "measurement_method": "VARCHAR",
        "measurement_target": "VARCHAR",
        "session_id": "INTEGER REFERENCES measurement_sessions(id)",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE observations ADD COLUMN {name} {definition}"))


def _migrate_optimization_evaluations():
    columns = {
        column["name"] for column in inspect(engine).get_columns("optimization_evaluations")
    }
    additions = {
        "baseline_metric_id": "INTEGER REFERENCES network_metrics(id)",
        "station_state_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE optimization_evaluations ADD COLUMN {name} {definition}")
                )


def _migrate_live_anomalies():
    columns = {column["name"] for column in inspect(engine).get_columns("live_anomalies")}
    if "resolution_note" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE live_anomalies ADD COLUMN resolution_note TEXT"))
