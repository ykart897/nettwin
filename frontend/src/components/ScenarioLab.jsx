import { useMemo, useState } from "react";
import { Play } from "lucide-react";
import { api } from "../api";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function ScenarioLab({ onRun, busy, scenarioResult, scenarios, onSelectScenario }) {
  const [form, setForm] = useState({
    name: "User Surge x2",
    userMultiplier: 2,
    latencyOffset: 0,
    signalOffset: 0,
    steps: 60
  });
  const [compareIds, setCompareIds] = useState(["", ""]);
  const [comparison, setComparison] = useState(null);

  const chartData = useMemo(() => {
    const rows = scenarioResult?.results || [];
    const grouped = {};
    rows.forEach((row) => {
      grouped[row.step] ||= { step: row.step, latency_ms: 0, connected_users: 0, packet_loss_pct: 0, count: 0 };
      grouped[row.step].latency_ms += row.latency_ms;
      grouped[row.step].connected_users += row.connected_users;
      grouped[row.step].packet_loss_pct += row.packet_loss_pct;
      grouped[row.step].count += 1;
    });
    return Object.values(grouped).map((row) => ({
      step: row.step,
      latency_ms: Number((row.latency_ms / row.count).toFixed(2)),
      connected_users: Math.round(row.connected_users / row.count),
      packet_loss_pct: Number((row.packet_loss_pct / row.count).toFixed(2))
    }));
  }, [scenarioResult]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function compare() {
    if (!compareIds[0] || !compareIds[1]) return;
    const response = await api.get("/api/scenarios/compare", {
      params: { first: compareIds[0], second: compareIds[1] }
    });
    setComparison(response.data);
  }

  return (
    <div className="scenario-layout">
      <section className="control-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">What-if runner</p>
            <h2>Scenario Lab</h2>
          </div>
        </div>
        <label>
          Scenario
          <input value={form.name} onChange={(event) => updateField("name", event.target.value)} />
        </label>
        <label>
          User multiplier
          <input
            type="number"
            min="0.5"
            max="5"
            step="0.1"
            value={form.userMultiplier}
            onChange={(event) => updateField("userMultiplier", Number(event.target.value))}
          />
        </label>
        <label>
          Latency offset
          <input
            type="number"
            min="0"
            max="60"
            step="1"
            value={form.latencyOffset}
            onChange={(event) => updateField("latencyOffset", Number(event.target.value))}
          />
        </label>
        <label>
          Signal offset
          <input
            type="number"
            min="-60"
            max="20"
            step="1"
            value={form.signalOffset}
            onChange={(event) => updateField("signalOffset", Number(event.target.value))}
          />
        </label>
        <label>
          Steps
          <input
            type="number"
            min="10"
            max="240"
            step="10"
            value={form.steps}
            onChange={(event) => updateField("steps", Number(event.target.value))}
          />
        </label>
        <button className="primary-button" onClick={() => onRun(form)} disabled={busy}>
          <Play size={17} />
          <span>{busy ? "Running" : "Run scenario"}</span>
        </button>
      </section>

      <section className="chart-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Scenario output</p>
            <h2>{scenarioResult?.scenario?.name || "No run selected"}</h2>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={chartData}>
            <CartesianGrid stroke="#272d2d" />
            <XAxis dataKey="step" stroke="#8b9694" />
            <YAxis stroke="#8b9694" />
            <Tooltip contentStyle={{ background: "#161a1a", border: "1px solid #303838" }} />
            <Line type="monotone" dataKey="connected_users" name="Users" stroke="#f4b942" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="latency_ms" name="Latency" stroke="#39d98a" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="packet_loss_pct" name="Packet loss" stroke="#ff5a5f" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
        <div className="recent-list">
          {scenarios.slice(0, 4).map((scenario) => (
            <button key={scenario.id} className="list-row" onClick={() => onSelectScenario(scenario)}>
              <span>{scenario.name}</span>
              <strong>{scenario.status}</strong>
            </button>
          ))}
        </div>
        <div className="tool-row">
          {[0, 1].map((index) => (
            <select key={index} value={compareIds[index]} onChange={(event) => setCompareIds((current) => current.map((value, itemIndex) => itemIndex === index ? event.target.value : value))}>
              <option value="">Scenario {index + 1}</option>
              {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}
            </select>
          ))}
          <button className="icon-text-button" onClick={compare}>Compare</button>
        </div>
        {comparison && (
          <div className="comparison-grid">
            {[comparison.first, comparison.second].map((side) => (
              <article key={side.scenario.id}><h3>{side.scenario.name}</h3>
                {Object.entries(side.averages).map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")}: <strong>{value ?? "—"}</strong></p>)}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
