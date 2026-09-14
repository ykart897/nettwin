from __future__ import annotations

import argparse

from app.database import SessionLocal, init_db
from app.telemetry.opencellid import OpenCellIdProvider
from app.telemetry.service import TelemetryService
from app.topology import TopologyService


def main():
    parser = argparse.ArgumentParser(description="Import a free OpenCellID CSV/CSV.GZ export.")
    parser.add_argument("path", help="Path to the downloaded OpenCellID file")
    args = parser.parse_args()

    init_db()
    result = TelemetryService([OpenCellIdProvider(args.path)]).sync_all()[0]
    db = SessionLocal()
    try:
        relation_count = TopologyService().rebuild(db)
    finally:
        db.close()
    print({**result, "relations_created": relation_count})


if __name__ == "__main__":
    main()
