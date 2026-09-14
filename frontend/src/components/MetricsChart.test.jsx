import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import MetricsChart from "./MetricsChart";


describe("MetricsChart empty state", () => {
  it("explains when telemetry is unavailable", () => {
    const html = renderToStaticMarkup(
      <MetricsChart metrics={[]} stations={[]} mode="live" />
    );

    expect(html).toContain("No telemetry is available");
  });
});
