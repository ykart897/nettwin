import { useState } from "react";
import { CheckCircle2, Info } from "lucide-react";
import { api } from "../api";

export default function AlertsLog({ alerts, onResolve, compact = false }) {
  const [detail, setDetail] = useState(null);

  async function inspect(alert) {
    if (!alert.asset_id) return;
    const response = await api.get(`/api/live-anomalies/${alert.id}`);
    setDetail(response.data);
  }
  return (
    <section className="list-panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Security events</p>
          <h2>Alerts & Logs</h2>
        </div>
      </div>
      <div className={compact ? "compact-list" : "alert-table"}>
        {alerts.length === 0 && <p className="empty-state">No open alerts.</p>}
        {alerts.map((alert) => (
          <article key={alert.id} className={`alert-row ${alert.severity.toLowerCase()}`}>
            <span className="severity-dot" />
            <div>
              <strong>{alert.alert_type.replaceAll("_", " ")}</strong>
              <span>
                {alert.base_station_id} - {alert.severity} - {new Date(alert.detected_at).toLocaleString()}
              </span>
              <p>{alert.message}</p>
            </div>
            {onResolve && (
              <div className="row-actions">
                {alert.asset_id && <button title="Explain alert" onClick={() => inspect(alert)}><Info size={17} /></button>}
                <button title="Resolve alert" onClick={() => onResolve(alert.id, true)}><CheckCircle2 size={17} /></button>
              </div>
            )}
          </article>
        ))}
      </div>
      {detail && (
        <aside className="alert-explanation">
          <button onClick={() => setDetail(null)}>Close</button>
          <h3>{detail.anomaly_type.replaceAll("_", " ")}</h3>
          <p>Observed {detail.field}: <strong>{detail.value ?? "—"}</strong></p>
          <p>Baseline median: <strong>{detail.baseline_median ?? "—"}</strong> from {detail.baseline_sample_count} samples</p>
          <p>Deviation score: <strong>{detail.score}</strong> · model {detail.model_version}</p>
        </aside>
      )}
    </section>
  );
}
