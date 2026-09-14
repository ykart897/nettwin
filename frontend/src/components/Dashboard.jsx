import { AlertOctagon, Gauge, Radio, Signal, TrendingUp, Users } from "lucide-react";
import StatCard from "./StatCard";
import AlertsLog from "./AlertsLog";
import OptimizationPanel from "./OptimizationPanel";
import SourceStatus from "./SourceStatus";

export default function Dashboard({ summary, alerts, optimizations, latest, mode, sources, onResolve }) {
  const healthiest = latest.filter((metric) => !metric.is_anomaly).length;
  const isSimulation = mode === "simulation";
  const sourceIssues =
    (summary.degraded_sources || 0) +
    (summary.stale_sources || 0) +
    (summary.unconfigured_sources || 0);

  return (
    <div className="stack">
      <section className="stats-grid">
        <StatCard label="Avg Latency" value={summary.avg_latency_ms} suffix=" ms" icon={Gauge} tone="green" />
        <StatCard label="Throughput" value={summary.avg_throughput_mbps} suffix=" Mbps" icon={TrendingUp} tone="cyan" />
        <StatCard
          label={isSimulation ? "Connected Users" : "Network Load Index"}
          value={isSimulation ? summary.total_connected_users ?? 0 : summary.network_load_index}
          suffix={isSimulation ? "" : " / 100"}
          icon={Users}
          tone="amber"
        />
        <StatCard
          label={isSimulation ? "Open Alerts" : "Source Issues"}
          value={isSimulation ? summary.open_alerts ?? 0 : sourceIssues}
          icon={AlertOctagon}
          tone="red"
        />
        <StatCard
          label={isSimulation ? "Active Stations" : "Active Assets"}
          value={isSimulation ? summary.active_base_stations ?? 0 : summary.active_assets ?? 0}
          icon={Radio}
          tone="neutral"
        />
        <StatCard label={isSimulation ? "Healthy Snapshots" : "Latest Observations"} value={healthiest} icon={Signal} tone="green" />
      </section>

      <section className="overview-band">
        <div>
          <p className="section-kicker">Network posture</p>
          <h2>
            {isSimulation
              ? summary.critical_alerts
                ? "Critical investigation active"
                : "Simulation twin operating normally"
              : sourceIssues
                ? "Some real data sources need attention"
                : "Real telemetry sources are healthy"}
          </h2>
          {!isSimulation && summary.latest_observation_at && (
            <p>Latest observation: {new Date(summary.latest_observation_at).toLocaleString()}</p>
          )}
        </div>
        <div className="posture-meter">
          <span style={{ width: `${Math.max(12, Math.min(100, 100 - (summary.open_alerts || 0) * 8))}%` }} />
        </div>
      </section>

      {isSimulation ? (
        <div className="two-column">
          <AlertsLog alerts={alerts.slice(0, 5)} compact />
          <OptimizationPanel optimizations={optimizations.slice(0, 4)} compact />
        </div>
      ) : (
        <>
          <SourceStatus sources={sources} />
          <AlertsLog alerts={alerts.slice(0, 8)} compact onResolve={onResolve} />
        </>
      )}
    </div>
  );
}
