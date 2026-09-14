from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

from app.telemetry.base import ProviderResult, TelemetryProvider


DEFAULT_TARGETS = (
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.google.com/generate_204",
)
DEFAULT_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=250000"


class LocalAgentProvider(TelemetryProvider):
    source = "local_agent"

    def __init__(self, targets: tuple[str, ...] | None = None):
        configured = os.getenv("LOCAL_AGENT_TARGETS")
        if targets:
            self.targets = targets
        elif configured:
            self.targets = tuple(item.strip() for item in configured.split(",") if item.strip())
        else:
            self.targets = DEFAULT_TARGETS
        self.download_url = os.getenv("LOCAL_AGENT_DOWNLOAD_URL", DEFAULT_DOWNLOAD_URL)

    def sync(self) -> ProviderResult:
        latencies = []
        failures = 0
        raw = []

        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            for target in self.targets:
                started = time.perf_counter()
                try:
                    response = client.get(target)
                    elapsed = max(time.perf_counter() - started, 0.001)
                    response.raise_for_status()
                    latencies.append(elapsed * 1000)
                    raw.append({"target": target, "status": response.status_code})
                except httpx.HTTPError as exc:
                    failures += 1
                    raw.append({"target": target, "error": str(exc)})

        if not latencies:
            raise RuntimeError("All local HTTP measurement targets failed.")

        download_mbps = None
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                started = time.perf_counter()
                response = client.get(self.download_url)
                elapsed = max(time.perf_counter() - started, 0.001)
                response.raise_for_status()
                download_mbps = (len(response.content) * 8) / elapsed / 1_000_000
                raw.append(
                    {
                        "download_target": self.download_url,
                        "status": response.status_code,
                        "bytes": len(response.content),
                    }
                )
        except httpx.HTTPError as exc:
            raw.append({"download_target": self.download_url, "error": str(exc)})

        now = datetime.now(timezone.utc)
        external_id = os.getenv("LOCAL_AGENT_ID", "local-pc")
        observation_id = f"{external_id}:{int(now.timestamp() // 300)}"
        observation = {
            "asset_external_id": external_id,
            "source": self.source,
            "source_observation_id": observation_id,
            "observed_at": now,
            "latency_ms": round(sum(latencies) / len(latencies), 2),
            "request_failure_pct": round(failures / len(self.targets) * 100, 2),
            "download_mbps": round(download_mbps, 3) if download_mbps is not None else None,
            "measurement_method": "https_request_and_download",
            "measurement_target": ",".join(self.targets),
            "raw": {"targets": raw},
        }
        asset = {
            "asset_type": "local_agent",
            "source": self.source,
            "external_id": external_id,
            "name": os.getenv("LOCAL_AGENT_NAME", "NetTwin Local Agent"),
            "latitude": _env_float("LOCAL_AGENT_LAT"),
            "longitude": _env_float("LOCAL_AGENT_LON"),
            "technology": "HTTP",
            "metadata": {"targets": list(self.targets), "download_target": self.download_url},
        }
        return ProviderResult(
            source=self.source,
            assets=[asset],
            observations=[observation],
            message=f"Measured {len(latencies)} of {len(self.targets)} targets.",
        )


def _env_float(name: str) -> float | None:
    value = os.getenv(name)
    try:
        return float(value) if value else None
    except ValueError:
        return None
