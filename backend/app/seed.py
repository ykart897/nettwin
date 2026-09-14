from app.data_generator import generate_metric_batch, seed_base_stations
from app.database import SessionLocal, init_db
from app.models import NetworkMetric
from sqlalchemy import func, select


def seed_database(initial_metric_count: int = 24) -> dict:
    init_db()
    db = SessionLocal()
    try:
        inserted = seed_base_stations(db)
        existing_metrics = db.scalar(select(func.count(NetworkMetric.id))) or 0
        generated = 0
        if existing_metrics == 0:
            rows = generate_metric_batch(db, count_per_station=initial_metric_count, seed=2026)
            generated = len(rows)
        return {"base_stations_inserted": inserted, "metrics_generated": generated}
    finally:
        db.close()


if __name__ == "__main__":
    print(seed_database())
