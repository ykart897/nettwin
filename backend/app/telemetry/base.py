from __future__ import annotations

from dataclasses import dataclass, field
import time

import httpx


@dataclass
class ProviderResult:
    source: str
    configured: bool = True
    assets: list[dict] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    message: str = ""


class TelemetryProvider:
    source = "unknown"

    def sync(self) -> ProviderResult:
        raise NotImplementedError


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    attempts: int = 3,
) -> httpx.Response:
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            retryable_status = (
                isinstance(exc, httpx.HTTPStatusError)
                and (exc.response.status_code == 429 or exc.response.status_code >= 500)
            )
            if attempt == attempts - 1 or (
                isinstance(exc, httpx.HTTPStatusError) and not retryable_status
            ):
                raise
            time.sleep(0.5 * (2**attempt))
    raise RuntimeError("HTTP retry loop ended unexpectedly.")
