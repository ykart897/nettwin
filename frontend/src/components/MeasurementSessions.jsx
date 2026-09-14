import { useEffect, useState } from "react";
import { CheckCircle2, Download, Plus } from "lucide-react";
import { api, apiErrorMessage } from "../api";

export default function MeasurementSessions() {
  const [sessions, setSessions] = useState([]);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [system, setSystem] = useState(null);
  const [compareIds, setCompareIds] = useState(["", ""]);
  const [comparison, setComparison] = useState(null);

  async function load() {
    try {
      const [response, systemResponse] = await Promise.all([
        api.get("/api/measurement-sessions"), api.get("/api/system/status")
      ]);
      setSessions(response.data);
      setSystem(systemResponse.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  useEffect(() => { load(); }, []);

  async function createSession(event) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/measurement-sessions", { name, notes: notes || null });
      setName("");
      setNotes("");
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function completeSession(id) {
    setError("");
    try {
      await api.patch(`/api/measurement-sessions/${id}`, { status: "completed" });
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function captureSession(id) {
    setError("");
    try {
      await api.post(`/api/measurement-sessions/${id}/capture`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function compareSessions() {
    if (!compareIds[0] || !compareIds[1]) return;
    try {
      const response = await api.get("/api/measurement-sessions/compare", {
        params: { first: compareIds[0], second: compareIds[1] }
      });
      setComparison(response.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="stack">
      <section className="control-panel">
        <div className="section-heading">
          <div><p className="section-kicker">Field research</p><h2>Measurement sessions</h2></div>
        </div>
        <form onSubmit={createSession} className="session-form">
          <label>Name<input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label>Notes<textarea maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
          <button className="primary-button" type="submit"><Plus size={17} /> Create session</button>
        </form>
        {error && <div className="connection-banner">{error}</div>}
      </section>
      {system && (
        <section className="stats-grid">
          <article className="stat-card neutral"><div><span>Database</span><strong>{system.database}</strong></div></article>
          <article className="stat-card green"><div><span>Observations</span><strong>{system.observation_count}</strong></div></article>
          <article className="stat-card cyan"><div><span>Assets</span><strong>{system.asset_count}</strong></div></article>
          <article className="stat-card amber"><div><span>Last backup</span><strong>{system.latest_backup_at ? new Date(system.latest_backup_at).toLocaleString() : "—"}</strong></div></article>
        </section>
      )}
      <section className="list-panel">
        <div className="tool-row">
          {[0, 1].map((index) => (
            <select key={index} value={compareIds[index]} onChange={(event) => setCompareIds((current) => current.map((value, itemIndex) => itemIndex === index ? event.target.value : value))}>
              <option value="">Choose session {index + 1}</option>
              {sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          ))}
          <button className="icon-text-button" onClick={compareSessions} disabled={compareIds[0] === compareIds[1]}>Compare</button>
        </div>
        {comparison && (
          <div className="comparison-grid">
            {[comparison.first, comparison.second].map((side) => (
              <article key={side.session.id}>
                <h3>{side.session.name}</h3>
                {Object.entries(side.metrics).map(([metric, stats]) => (
                  <p key={metric}>{metric.replaceAll("_", " ")}: median <strong>{stats.median ?? "—"}</strong>, p95 <strong>{stats.p95 ?? "—"}</strong> ({stats.count} samples)</p>
                ))}
              </article>
            ))}
          </div>
        )}
        <div className="session-list">
          {sessions.length === 0 && <p className="empty-state">No measurement sessions yet.</p>}
          {sessions.map((item) => (
            <article className="list-row" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <span>#{item.id} · {item.status} · {item.observation_count} observations · {new Date(item.started_at).toLocaleString()}</span>
                {item.notes && <p>{item.notes}</p>}
              </div>
              <div className="row-actions">
                {item.status === "active" && <button onClick={() => captureSession(item.id)}>Capture now</button>}
                {item.status === "active" && <button onClick={() => completeSession(item.id)} title="Complete session"><CheckCircle2 size={17} /></button>}
                <a className="icon-text-button" href={`${api.defaults.baseURL}/api/measurement-sessions/${item.id}/export?format=csv`}><Download size={17} /> CSV</a>
                <a className="icon-text-button" target="_blank" rel="noreferrer" href={`${api.defaults.baseURL}/api/measurement-sessions/${item.id}/report?format=html`}>Report</a>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
