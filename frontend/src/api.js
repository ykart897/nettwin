import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://127.0.0.1:8000",
  timeout: 15000,
  withCredentials: true
});

export function apiErrorMessage(error) {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => `${item.loc?.slice(1).join(".") || "input"}: ${item.msg}`).join(" | ");
  }
  return detail || error.message || "API operation failed";
}

export async function fetchPanelData(mode = "live", replayRange = {}) {
  if (mode !== "simulation") {
    const params = {
      mode,
      limit: 5000,
      ...(replayRange.from ? { from: replayRange.from } : {}),
      ...(replayRange.to ? { to: replayRange.to } : {})
    };
    const anomalySince = replayRange.from || new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const [summary, assets, latest, observations, sources, anomalies, topology] = await Promise.all([
      api.get("/api/dashboard/summary", { params: { mode } }),
      api.get("/api/assets"),
      api.get("/api/observations/latest", { params: { mode } }),
      api.get("/api/observations", { params }),
      api.get("/api/data-sources/status"),
      api.get("/api/live-anomalies", {
        params: { resolved: false, since: anomalySince, ...(replayRange.to ? { until: replayRange.to } : {}), limit: 100 }
      }),
      api.get("/api/topology")
    ]);
    return {
      summary: summary.data,
      stations: assets.data,
      latest: latest.data,
      metrics: observations.data,
      sources: mode === "replay" ? [] : sources.data,
      alerts: anomalies.data.map((item) => ({
        ...item,
        base_station_id: item.asset_name,
        alert_type: item.anomaly_type
      })),
      topology: topology.data,
      optimizations: [],
      scenarios: []
    };
  }

  const [summary, stations, latest, metrics, alerts, optimizations, scenarios] = await Promise.all([
    api.get("/api/dashboard/summary", { params: { mode } }),
    api.get("/api/base-stations"),
    api.get("/api/metrics/latest"),
    api.get("/api/metrics", { params: { limit: 360 } }),
    api.get("/api/alerts", { params: { resolved: false } }),
    api.get("/api/optimizations", { params: { status: "Pending" } }),
    api.get("/api/scenarios")
  ]);

  return {
    summary: summary.data,
    stations: stations.data,
    latest: latest.data,
    metrics: metrics.data,
    alerts: alerts.data,
    optimizations: optimizations.data,
    scenarios: scenarios.data,
    sources: [],
    topology: []
  };
}
