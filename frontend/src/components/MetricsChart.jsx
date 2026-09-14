import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

const simulationMetricOptions = [
  { key: "latency_ms", label: "Latency", unit: "ms", color: "#39d98a" },
  { key: "throughput_mbps", label: "Throughput", unit: "Mbps", color: "#5cc8ff" },
  { key: "connected_users", label: "Users", unit: "", color: "#f4b942" },
  { key: "packet_loss_pct", label: "Packet Loss", unit: "%", color: "#ff5a5f" },
  { key: "signal_strength_dbm", label: "Signal", unit: "dBm", color: "#c792ea" }
];

const liveMetricOptions = [
  { key: "latency_ms", label: "Latency", unit: "ms", color: "#39d98a" },
  { key: "download_mbps", label: "Download", unit: "Mbps", color: "#5cc8ff" },
  { key: "packet_loss_pct", label: "Packet Loss", unit: "%", color: "#ff5a5f" },
  { key: "request_failure_pct", label: "Request Failures", unit: "%", color: "#ff8b3d" },
  { key: "signal_strength_dbm", label: "Signal", unit: "dBm", color: "#c792ea" },
  { key: "load_index", label: "Network Load", unit: "/100", color: "#f4b942" }
];

export default function MetricsChart({ metrics, stations, mode }) {
  const metricOptions = mode === "simulation" ? simulationMetricOptions : liveMetricOptions;
  const [stationId, setStationId] = useState("");
  const [metricKey, setMetricKey] = useState("latency_ms");
  const metricMeta = metricOptions.find((item) => item.key === metricKey) || metricOptions[0];

  useEffect(() => {
    if (!stations.length) return;
    if (!stations.some((station) => String(station.id) === stationId)) {
      setStationId(String(stations[0].id));
    }
  }, [stationId, stations]);

  useEffect(() => {
    if (!metricOptions.some((item) => item.key === metricKey)) {
      setMetricKey(metricOptions[0].key);
    }
  }, [metricKey, metricOptions]);

  const stationSeries = useMemo(() => {
    return metrics
      .filter((metric) => String(metric.base_station_id || metric.asset_id) === stationId)
      .slice(-80)
      .map((metric) => ({
        ...metric,
        time: new Date(metric.timestamp || metric.observed_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit"
        })
      }));
  }, [metrics, stationId]);

  const groupedAverages = useMemo(() => {
    const groups = {};
    metrics.slice(-120).forEach((metric) => {
      const groupName = metric.region || metric.source || "Unknown";
      groups[groupName] ||= { group: groupName, latency_ms: 0, latencyCount: 0, throughput: 0, throughputCount: 0, load: 0, loadCount: 0 };
      if (metric.latency_ms != null) {
        groups[groupName].latency_ms += metric.latency_ms;
        groups[groupName].latencyCount += 1;
      }
      if ((metric.throughput_mbps ?? metric.download_mbps) != null) {
        groups[groupName].throughput += metric.throughput_mbps ?? metric.download_mbps;
        groups[groupName].throughputCount += 1;
      }
      if (metric.load_index != null) {
        groups[groupName].load += metric.load_index;
        groups[groupName].loadCount += 1;
      }
    });
    return Object.values(groups).map((group) => ({
      group: group.group,
      latency_ms: group.latencyCount ? Number((group.latency_ms / group.latencyCount).toFixed(2)) : null,
      throughput_mbps: group.throughputCount ? Number((group.throughput / group.throughputCount).toFixed(1)) : null,
      load_index: group.loadCount ? Number((group.load / group.loadCount).toFixed(1)) : null
    }));
  }, [metrics]);

  if (metrics.length === 0 || stations.length === 0) {
    return <section className="loading-panel">No telemetry is available for this selection.</section>;
  }

  return (
    <div className="stack">
      <section className="tool-row">
        <select value={stationId} onChange={(event) => setStationId(event.target.value)}>
          {stations.map((station) => (
            <option key={`${station.source || "simulation"}-${station.id}`} value={String(station.id)}>
              {station.name}
            </option>
          ))}
        </select>
        <div className="segmented-control">
          {metricOptions.map((option) => (
            <button
              key={option.key}
              className={metricKey === option.key ? "active" : ""}
              onClick={() => setMetricKey(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      <section className="chart-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Time series</p>
            <h2>
              {metricMeta.label} {metricMeta.unit && `(${metricMeta.unit})`}
            </h2>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={stationSeries}>
            <CartesianGrid stroke="#272d2d" />
            <XAxis dataKey="time" stroke="#8b9694" minTickGap={28} />
            <YAxis stroke="#8b9694" width={64} />
            <Tooltip contentStyle={{ background: "#161a1a", border: "1px solid #303838" }} />
            <Legend />
            <Line type="monotone" dataKey={metricKey} name={metricMeta.label} stroke={metricMeta.color} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <section className="chart-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Regional averages</p>
            <h2>{mode === "simulation" ? "Regional averages" : "Source averages"}</h2>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={groupedAverages}>
            <CartesianGrid stroke="#272d2d" />
            <XAxis dataKey="group" stroke="#8b9694" />
            <YAxis stroke="#8b9694" />
            <Tooltip contentStyle={{ background: "#161a1a", border: "1px solid #303838" }} />
            <Area type="monotone" dataKey="throughput_mbps" name="Throughput" stroke="#5cc8ff" fill="#5cc8ff33" />
            <Area type="monotone" dataKey="load_index" name="Network Load" stroke="#f4b942" fill="#f4b94233" />
            <Area type="monotone" dataKey="latency_ms" name="Latency" stroke="#39d98a" fill="#39d98a33" />
          </AreaChart>
        </ResponsiveContainer>
      </section>
    </div>
  );
}
