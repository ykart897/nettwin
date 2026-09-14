from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path


DEFAULT_MODEL = {
    "version": "load-index-v2",
    "weights": {
        "latency": 0.25,
        "packet_loss": 0.3,
        "throughput": 0.2,
        "signal": 0.15,
        "sinr": 0.1,
    },
}
MODEL_VERSION = DEFAULT_MODEL["version"]


def calculate_load_index(payload: dict) -> tuple[float | None, str | None, dict]:
    components = load_components(payload)
    if not components:
        return None, None, {}

    model = load_model()
    weights = model["weights"]
    active_weight = sum(float(weights.get(name, 0)) for name in components)
    if active_weight <= 0:
        return None, None, components
    score = sum(components[name] * float(weights.get(name, 0)) for name in components) / active_weight
    confidence = "High" if len(components) >= 3 else "Medium" if len(components) == 2 else "Low"
    return round(min(100.0, max(0.0, score)), 1), confidence, components


def load_components(payload: dict) -> dict[str, float]:
    components = {}
    latency = payload.get("latency_ms")
    if latency is not None:
        components["latency"] = min(100.0, max(0.0, (float(latency) - 10.0) / 1.4))

    loss = payload.get("packet_loss_pct")
    if loss is not None:
        components["packet_loss"] = min(100.0, max(0.0, float(loss) * 10.0))

    throughput = payload.get("download_mbps")
    if throughput is not None:
        components["throughput"] = min(100.0, max(0.0, 100.0 - float(throughput)))

    signal = payload.get("signal_strength_dbm")
    if signal is not None:
        components["signal"] = min(100.0, max(0.0, (-70.0 - float(signal)) * 2.0))

    sinr = payload.get("sinr_db")
    if sinr is not None:
        components["sinr"] = min(100.0, max(0.0, (20.0 - float(sinr)) * 4.0))
    return components


@lru_cache(maxsize=1)
def load_model() -> dict:
    configured_path = os.getenv("NETTWIN_LOAD_MODEL_PATH")
    if not configured_path:
        return DEFAULT_MODEL
    path = Path(configured_path)
    with path.open("r", encoding="utf-8") as handle:
        model = json.load(handle)
    weights = model.get("weights")
    if not model.get("version") or not isinstance(weights, dict):
        raise ValueError("Load model must include version and weights.")
    configured = [weights.get(name) for name in DEFAULT_MODEL["weights"]]
    if any(
        not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
        for value in configured
    ) or sum(configured) <= 0:
        raise ValueError("Load model weights must be finite, non-negative, and have a positive sum.")
    return model


def model_version() -> str:
    return str(load_model()["version"])
