from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def run(base_url: str, duration: float, interval: float, concurrency: int) -> None:
    endpoints = ("/api/health/ready", "/api/dashboard/summary?mode=live", "/api/system/status")
    latencies: list[float] = []
    failures: list[str] = []
    deadline = time.monotonic() + duration

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        while time.monotonic() < deadline:
            async def probe(endpoint: str) -> None:
                started = time.perf_counter()
                try:
                    response = await client.get(endpoint)
                    response.raise_for_status()
                    if endpoint == "/api/health/ready" and response.json().get("status") != "ready":
                        raise RuntimeError("readiness endpoint did not report ready")
                    latencies.append((time.perf_counter() - started) * 1000)
                except Exception as exc:
                    failures.append(f"{endpoint}: {exc}")

            await asyncio.gather(*(probe(endpoints[index % len(endpoints)]) for index in range(concurrency)))
            await asyncio.sleep(interval)

    if failures:
        raise SystemExit(f"{len(failures)} failed requests; first failure: {failures[0]}")
    ordered = sorted(latencies)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    print(
        f"PASS requests={len(ordered)} median_ms={statistics.median(ordered):.1f} "
        f"p95_ms={p95:.1f} max_ms={max(ordered):.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise NetTwin read paths for a fixed duration.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    if args.duration <= 0 or args.interval < 0 or args.concurrency <= 0:
        parser.error("duration and concurrency must be positive; interval cannot be negative")
    asyncio.run(run(args.base_url.rstrip("/"), args.duration, args.interval, args.concurrency))


if __name__ == "__main__":
    main()
