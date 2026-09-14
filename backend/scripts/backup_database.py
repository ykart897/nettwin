from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.database import DATABASE_URL


def main():
    parser = argparse.ArgumentParser(description="Create a consistent local NetTwin SQLite backup.")
    parser.add_argument("--output-dir", default="backups")
    args = parser.parse_args()
    if not DATABASE_URL.startswith("sqlite:///"):
        raise SystemExit("This command supports the local SQLite database only.")
    source_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path
    if not source_path.exists():
        raise SystemExit(f"Database does not exist: {source_path}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_path = output_dir / f"nettwin-{stamp}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise SystemExit(f"Backup integrity check failed: {result}")
    print(target_path.resolve())


if __name__ == "__main__":
    main()
