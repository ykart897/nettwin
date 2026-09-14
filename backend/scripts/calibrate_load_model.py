from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.telemetry.load_index import load_components


FIELDS = ("latency", "packet_loss", "throughput", "signal", "sinr")


def main():
    parser = argparse.ArgumentParser(description="Calibrate Network Load Index from labeled CSV data.")
    parser.add_argument("input_csv")
    parser.add_argument("output_json")
    args = parser.parse_args()

    features = []
    targets = []
    with Path(args.input_csv).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            components = load_components(
                {
                    "latency_ms": _float(row.get("latency_ms")),
                    "packet_loss_pct": _float(row.get("packet_loss_pct")),
                    "download_mbps": _float(row.get("download_mbps")),
                    "signal_strength_dbm": _float(row.get("signal_strength_dbm")),
                    "sinr_db": _float(row.get("sinr_db")),
                }
            )
            target = _float(row.get("target_load_index"))
            if target is None or len(components) != len(FIELDS):
                continue
            features.append([components[field] for field in FIELDS])
            targets.append(target)

    if len(features) < 20:
        raise SystemExit("At least 20 complete labeled rows are required.")
    weights, *_ = np.linalg.lstsq(np.array(features), np.array(targets), rcond=None)
    weights = np.clip(weights, 0, None)
    if weights.sum() == 0:
        raise SystemExit("Calibration produced zero weights.")
    weights = weights / weights.sum()
    model = {
        "version": f"load-index-calibrated-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "weights": {field: round(float(weight), 6) for field, weight in zip(FIELDS, weights)},
        "training_rows": len(features),
    }
    Path(args.output_json).write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(model)


def _float(value: str | None) -> float | None:
    try:
        parsed = float(value) if value not in (None, "") else None
        return parsed if parsed is not None and math.isfinite(parsed) else None
    except ValueError:
        return None


if __name__ == "__main__":
    main()
