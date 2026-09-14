from __future__ import annotations

import os
from math import asin, cos, radians, sin, sqrt
from datetime import datetime, timedelta, timezone

import httpx

from app.telemetry.base import ProviderResult, TelemetryProvider, get_with_retry


API_ROOT = "https://atlas.ripe.net/api/v2"
ISTANBUL_CENTER = (41.0082, 28.9784)
MAX_PROBES = 25


class RipeAtlasProvider(TelemetryProvider):
    source = "ripe_atlas"

    def __init__(self, measurement_ids: list[int] | None = None, include_history: bool = False):
        configured = os.getenv("RIPE_ATLAS_MEASUREMENT_IDS", "")
        self.measurement_ids = measurement_ids or [
            int(value.strip()) for value in configured.split(",") if value.strip().isdigit()
        ]
        self.include_history = include_history

    def sync(self) -> ProviderResult:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            probes = self._turkish_probes(client)
            if not probes:
                raise RuntimeError("RIPE Atlas returned no connected Turkish probes.")

            measurement_ids = self.measurement_ids or self._public_ping_measurements(client)
            observations = []
            used_probe_ids = set()
            measurement_limit = 3 if self.include_history else 10
            for measurement_id in measurement_ids[:measurement_limit]:
                if self.include_history:
                    stop = datetime.now(timezone.utc)
                    start = stop - timedelta(hours=24)
                    response = get_with_retry(
                        client,
                        f"{API_ROOT}/measurements/{measurement_id}/results/",
                        params={
                            "start": int(start.timestamp()),
                            "stop": int(stop.timestamp()),
                            "probe_ids": ",".join(str(probe_id) for probe_id in probes),
                        },
                    )
                else:
                    response = get_with_retry(
                        client,
                        f"{API_ROOT}/measurements/{measurement_id}/latest/",
                    )
                payload = response.json()
                rows = payload if isinstance(payload, list) else payload.get("results", [])
                for row in rows:
                    probe_id = row.get("prb_id")
                    if probe_id not in probes:
                        continue
                    parsed = _parse_ping(row, measurement_id)
                    if parsed:
                        observations.append(parsed)
                        used_probe_ids.add(probe_id)

        assets = [
            {
                "asset_type": "ripe_probe",
                "source": self.source,
                "external_id": str(probe_id),
                "name": f"RIPE Atlas Probe {probe_id}",
                "latitude": probes[probe_id]["latitude"],
                "longitude": probes[probe_id]["longitude"],
                "technology": "Internet probe",
                "operator_code": probes[probe_id].get("asn"),
                "metadata": {"tags": probes[probe_id].get("tags", [])},
            }
            for probe_id in sorted(probes.keys())
        ]
        return ProviderResult(
            source=self.source,
            assets=assets,
            observations=observations,
            message=(
                f"Read {len(observations)} public ping observations"
                f"{' from the last 24 hours' if self.include_history else ''}."
            ),
        )

    def _turkish_probes(self, client: httpx.Client) -> dict[int, dict]:
        response = get_with_retry(
            client,
            f"{API_ROOT}/probes/",
            params={"country_code": "TR", "status": 1, "page_size": 500},
        )
        rows = response.json().get("results", [])
        probes = {}
        for row in rows:
            geometry = row.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) < 2:
                continue
            probes[row["id"]] = {
                "longitude": coordinates[0],
                "latitude": coordinates[1],
                "asn": str(row.get("asn_v4") or row.get("asn_v6") or ""),
                "tags": [tag.get("slug") for tag in row.get("tags", []) if tag.get("slug")],
            }
        nearest = sorted(
            probes.items(),
            key=lambda item: _distance_km(
                ISTANBUL_CENTER[0],
                ISTANBUL_CENTER[1],
                item[1]["latitude"],
                item[1]["longitude"],
            ),
        )
        return dict(nearest[:MAX_PROBES])

    def _public_ping_measurements(self, client: httpx.Client) -> list[int]:
        response = get_with_retry(
            client,
            f"{API_ROOT}/measurements/",
            params={"type": "ping", "status": 2, "is_public": "true", "page_size": 25},
        )
        return [row["id"] for row in response.json().get("results", [])]


def _parse_ping(row: dict, measurement_id: int) -> dict | None:
    samples = row.get("result") or []
    successful = [sample.get("rtt") for sample in samples if sample.get("rtt") is not None]
    sent = len(samples)
    if not sent:
        return None
    timestamp = int(row.get("timestamp") or 0)
    return {
        "asset_external_id": str(row["prb_id"]),
        "source": "ripe_atlas",
        "source_observation_id": f"{measurement_id}:{row['prb_id']}:{timestamp}",
        "observed_at": datetime.fromtimestamp(timestamp, timezone.utc),
        "latency_ms": round(sum(successful) / len(successful), 2) if successful else None,
        "packet_loss_pct": round((sent - len(successful)) / sent * 100, 2),
        "raw": {"measurement_id": measurement_id, "destination": row.get("dst_addr")},
    }


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))
