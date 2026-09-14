import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import Dashboard from "./Dashboard";


describe("Dashboard live mode", () => {
  it("shows a neutral load index name without an estimated label", () => {
    const html = renderToStaticMarkup(
      <Dashboard
        mode="live"
        summary={{
          avg_latency_ms: 20,
          avg_throughput_mbps: 40,
          network_load_index: 35,
          active_assets: 2,
          degraded_sources: 0,
          stale_sources: 1,
          unconfigured_sources: 1,
          latest_observation_at: "2026-06-15T12:00:00Z"
        }}
        alerts={[]}
        optimizations={[]}
        latest={[]}
        sources={[]}
      />
    );

    expect(html).toContain("Network Load Index");
    expect(html).toContain("Source Issues");
    expect(html).toContain(">2<");
    expect(html).toContain("Latest observation:");
    expect(html).not.toContain("Estimated");
  });
});
