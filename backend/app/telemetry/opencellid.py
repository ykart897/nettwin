from __future__ import annotations

import csv
import gzip
import os
from datetime import datetime, timezone
from pathlib import Path

from app.telemetry.base import ProviderResult, TelemetryProvider


ISTANBUL_BOUNDS = (27.95, 40.75, 30.05, 41.35)


class OpenCellIdProvider(TelemetryProvider):
    source = "opencellid"

    def __init__(self, csv_path: str | None = None):
        self.csv_path = csv_path or os.getenv("OPENCELLID_CSV_PATH")

    def sync(self) -> ProviderResult:
        if not self.csv_path:
            return ProviderResult(
                source=self.source,
                configured=False,
                message="Set OPENCELLID_CSV_PATH to an OpenCellID CSV or CSV.GZ export.",
            )

        path = Path(self.csv_path)
        if not path.exists():
            return ProviderResult(
                source=self.source,
                configured=False,
                message=f"OpenCellID file not found: {path}",
            )

        assets = []
        observations = []
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                normalized = {str(key).strip().lower(): value for key, value in row.items()}
                mcc = _value(normalized, "mcc")
                if mcc and mcc != "286":
                    continue
                latitude = _float(normalized, "lat", "latitude")
                longitude = _float(normalized, "lon", "longitude")
                if latitude is None or longitude is None or not _in_istanbul(latitude, longitude):
                    continue

                radio = _value(normalized, "radio", "act") or "Unknown"
                network = _value(normalized, "net", "mnc") or "unknown"
                area = _value(normalized, "area", "lac", "tac") or "unknown"
                cell = _value(normalized, "cell", "cellid", "cid")
                if not cell:
                    continue
                external_id = f"286-{network}-{area}-{cell}"
                assets.append(
                    {
                        "asset_type": "cell_site",
                        "source": self.source,
                        "external_id": external_id,
                        "name": f"{radio} Cell {cell}",
                        "latitude": latitude,
                        "longitude": longitude,
                        "technology": radio,
                        "operator_code": f"286-{network}",
                        "metadata": {
                            "area": area,
                            "samples": _value(normalized, "samples"),
                            "range_m": _value(normalized, "range"),
                            "updated": _value(normalized, "updated"),
                        },
                    }
                )
                signal = _float(normalized, "averagesignal", "average_signal", "signal")
                updated = _unix_datetime(_value(normalized, "updated", "measured_at"))
                if signal is not None and -140 <= signal <= -20 and updated is not None:
                    observations.append(
                        {
                            "asset_external_id": external_id,
                            "source": self.source,
                            "source_observation_id": f"{external_id}:{int(updated.timestamp())}",
                            "observed_at": updated,
                            "signal_strength_dbm": signal,
                            "raw": {"samples": _value(normalized, "samples")},
                        }
                    )

        return ProviderResult(
            source=self.source,
            assets=assets,
            observations=observations,
            message=(
                f"Imported {len(assets)} Istanbul cell records and "
                f"{len(observations)} signal observations."
            ),
        )


def _value(row: dict, *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _float(row: dict, *names: str) -> float | None:
    value = _value(row, *names)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _in_istanbul(latitude: float, longitude: float) -> bool:
    west, south, east, north = ISTANBUL_BOUNDS
    return south <= latitude <= north and west <= longitude <= east


def _unix_datetime(value: str | None) -> datetime | None:
    try:
        timestamp = int(float(value)) if value else 0
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return datetime.fromtimestamp(timestamp, timezone.utc) if timestamp > 0 else None
    except (ValueError, OSError, OverflowError):
        return None
