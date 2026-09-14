import { useState } from "react";
import { RadioReceiver, ShieldAlert } from "lucide-react";

const attackTypes = [
  { id: "ddos", label: "DDoS Surge" },
  { id: "jamming", label: "Jamming" },
  { id: "exfiltration", label: "Exfiltration" }
];

export default function AttackSimulation({ stations, alerts, onRun, busy }) {
  const [attackType, setAttackType] = useState("ddos");
  const [targetStation, setTargetStation] = useState("");

  return (
    <div className="scenario-layout">
      <section className="control-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Defensive simulation</p>
            <h2>Attack Simulation</h2>
          </div>
        </div>
        <div className="segmented-control vertical">
          {attackTypes.map((attack) => (
            <button
              key={attack.id}
              className={attackType === attack.id ? "active" : ""}
              onClick={() => setAttackType(attack.id)}
            >
              {attack.label}
            </button>
          ))}
        </div>
        <label>
          Target station
          <select value={targetStation} onChange={(event) => setTargetStation(event.target.value)}>
            <option value="">All stations</option>
            {stations.map((station) => (
              <option key={station.id} value={station.id}>
                {station.id} - {station.name}
              </option>
            ))}
          </select>
        </label>
        <button className="primary-button danger" onClick={() => onRun({ attackType, targetStation })} disabled={busy}>
          <ShieldAlert size={17} />
          <span>{busy ? "Injecting" : "Inject pattern"}</span>
        </button>
      </section>

      <section className="timeline-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Detection timeline</p>
            <h2>Recent anomalies</h2>
          </div>
        </div>
        <div className="timeline">
          {alerts.slice(0, 12).map((alert) => (
            <article key={alert.id} className={`timeline-item ${alert.severity.toLowerCase()}`}>
              <RadioReceiver size={18} />
              <div>
                <strong>{alert.alert_type.replaceAll("_", " ")}</strong>
                <span>
                  {alert.base_station_id} - {alert.severity}
                </span>
                <p>{alert.message}</p>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
