import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, Radio, RefreshCcw, ShieldCheck, Users, Zap } from "lucide-react";
import { api, apiErrorMessage, fetchPanelData } from "./api";
import Dashboard from "./components/Dashboard";
import AttackSimulation from "./components/AttackSimulation";
import OptimizationPanel from "./components/OptimizationPanel";
import AlertsLog from "./components/AlertsLog";
import Sidebar from "./components/Sidebar";
import ReplayControls from "./components/ReplayControls";
import MeasurementSessions from "./components/MeasurementSessions";
import "./App.css";

const NetworkMap = lazy(() => import("./components/NetworkMap"));
const MetricsChart = lazy(() => import("./components/MetricsChart"));
const ScenarioLab = lazy(() => import("./components/ScenarioLab"));

const sections = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "map", label: "Network Map", icon: Radio },
  { id: "metrics", label: "Live Metrics", icon: Zap },
  { id: "sessions", label: "Sessions", icon: Radio },
  { id: "scenarios", label: "Scenario Lab", icon: Users },
  { id: "attacks", label: "Attack Simulation", icon: AlertTriangle },
  { id: "optimizations", label: "Optimizations", icon: ShieldCheck }
];

export default function App() {
  const [mode, setMode] = useState("live");
  const [activeSection, setActiveSection] = useState("overview");
  const [data, setData] = useState({
    summary: {},
    stations: [],
    latest: [],
    metrics: [],
    alerts: [],
    optimizations: [],
    scenarios: [],
    sources: [],
    topology: []
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [scenarioResult, setScenarioResult] = useState(null);
  const now = useMemo(() => new Date(), []);
  const [replayRange, setReplayRange] = useState({
    fromLocal: toLocalInput(new Date(now.getTime() - 24 * 60 * 60 * 1000)),
    toLocal: toLocalInput(now)
  });
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replayIndex, setReplayIndex] = useState(0);
  const refreshSequence = useRef(0);

  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    setError("");
    try {
      const range = mode === "replay"
        ? {
            from: replayRange.fromLocal ? new Date(replayRange.fromLocal).toISOString() : undefined,
            to: replayRange.toLocal ? new Date(replayRange.toLocal).toISOString() : undefined
          }
        : {};
      const next = await fetchPanelData(mode, range);
      if (sequence !== refreshSequence.current) return;
      setData(next);
      if (mode === "replay") setReplayIndex(0);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [mode, replayRange.fromLocal, replayRange.toLocal]);

  useEffect(() => {
    refresh();
    if (mode === "replay") return undefined;
    const timer = window.setInterval(refresh, 15000);
    return () => window.clearInterval(timer);
  }, [mode, refresh]);

  const replayTimeline = useMemo(
    () => [...new Set(data.metrics.map((item) => item.observed_at))].sort(),
    [data.metrics]
  );

  useEffect(() => {
    if (mode !== "replay" || !replayPlaying || replayTimeline.length === 0) return undefined;
    const timer = window.setInterval(() => {
      setReplayIndex((current) => {
        const next = current + replaySpeed;
        if (next >= replayTimeline.length) {
          setReplayPlaying(false);
          return replayTimeline.length - 1;
        }
        return next;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, [mode, replayPlaying, replaySpeed, replayTimeline.length]);

  const visibleMetrics = useMemo(() => {
    if (mode !== "replay") return data.metrics;
    if (!replayTimeline.length) return [];
    const cursor = replayTimeline[Math.min(replayIndex, replayTimeline.length - 1)];
    return data.metrics.filter((item) => item.observed_at <= cursor);
  }, [data.metrics, mode, replayIndex, replayTimeline]);

  const visibleLatest = useMemo(() => {
    if (mode !== "replay") return data.latest;
    const latest = {};
    visibleMetrics.forEach((metric) => {
      latest[metric.asset_id] = metric;
    });
    return Object.values(latest);
  }, [data.latest, mode, visibleMetrics]);

  const visibleAlerts = useMemo(() => {
    if (mode !== "replay" || !replayTimeline.length) return data.alerts;
    const cursor = replayTimeline[Math.min(replayIndex, replayTimeline.length - 1)];
    return data.alerts.filter((alert) => alert.detected_at <= cursor);
  }, [data.alerts, mode, replayIndex, replayTimeline]);

  const visibleSummary = useMemo(() => {
    if (mode !== "replay") return data.summary;
    const average = (key) => {
      const values = visibleMetrics.map((item) => item[key]).filter((value) => value != null);
      if (!values.length) return null;
      return Number((values.reduce((total, value) => total + value, 0) / values.length).toFixed(2));
    };
    return {
      ...data.summary,
      mode: "replay",
      avg_latency_ms: average("latency_ms"),
      avg_throughput_mbps: average("download_mbps"),
      avg_packet_loss_pct: average("packet_loss_pct"),
      network_load_index: average("load_index"),
      active_assets: visibleLatest.length
    };
  }, [data.summary, mode, visibleLatest.length, visibleMetrics]);

  const latestByStation = useMemo(() => {
    return Object.fromEntries(
      visibleLatest.map((metric) => [metric.base_station_id || metric.asset_id, metric])
    );
  }, [visibleLatest]);

  const visibleSections = useMemo(
    () => sections.filter((section) => mode === "simulation" || !["scenarios", "attacks", "optimizations"].includes(section.id)),
    [mode]
  );

  function changeMode(nextMode) {
    setMode(nextMode);
    setActiveSection("overview");
    setReplayPlaying(false);
  }

  async function operatorLogin() {
    const apiKey = window.prompt("Enter the local NetTwin operator key");
    if (!apiKey) return;
    try {
      await api.post("/api/operator/session", { api_key: apiKey });
      setError("");
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function generateMetrics() {
    setBusy(true);
    setError("");
    try {
      await api.post("/api/metrics/generate", { count_per_station: 4 });
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function syncLiveData() {
    setBusy(true);
    setError("");
    try {
      const response = await api.post("/api/ingestion/sync", {});
      let job = response.data;
      while (["queued", "running"].includes(job.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        job = (await api.get(`/api/ingestion/jobs/${job.id}`)).data;
      }
      if (job.status === "failed") throw new Error(job.error || "Telemetry sync failed");
      const failed = job.sources.filter((source) => source.status === "degraded");
      if (failed.length) setError(failed.map((source) => `${source.source}: ${source.message}`).join(" | "));
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function runScenario(parameters) {
    setBusy(true);
    setError("");
    try {
      const response = await api.post("/api/scenarios", {
        name: parameters.name,
        description: "Interactive what-if simulation from the dashboard.",
        parameters: {
          user_multiplier: parameters.userMultiplier,
          latency_offset: parameters.latencyOffset,
          signal_offset: parameters.signalOffset
        },
        steps: parameters.steps
      });
      setScenarioResult({ ...response.data, results: response.data.summary });
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function loadScenario(scenario) {
    setError("");
    try {
      const response = await api.get(`/api/scenarios/${scenario.id}/summary`);
      setScenarioResult({ scenario, results: response.data, summary: response.data });
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function runAttack(attack) {
    setBusy(true);
    setError("");
    try {
      await api.post("/api/attack-simulation", {
        attack_type: attack.attackType,
        target_station_id: attack.targetStation || null,
        count_per_station: 6
      });
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function patchAlert(alertId, resolved) {
    setError("");
    try {
      await api.patch(mode === "simulation" ? `/api/alerts/${alertId}` : `/api/live-anomalies/${alertId}`, { resolved });
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function patchOptimization(optimizationId, status) {
    setError("");
    try {
      if (status === "Applied") {
        const evaluationResponse = await api.post(`/api/optimizations/${optimizationId}/evaluate`);
        const evaluation = evaluationResponse.data;
        const approved = window.confirm(
          `Risk: ${evaluation.risk_level}\n\n` +
          `Baseline:\n${JSON.stringify(evaluation.baseline, null, 2)}\n\n` +
          `Projected:\n${JSON.stringify(evaluation.projected, null, 2)}\n\n` +
          "Approve this simulated change?"
        );
        if (!approved) return;
        await api.patch(`/api/optimization-evaluations/${evaluation.id}`, { approved: true });
      }
      await api.patch(`/api/optimizations/${optimizationId}`, { status });
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="app-shell">
      <Sidebar sections={visibleSections} activeSection={activeSection} onSelect={setActiveSection} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{mode} Radio Network Digital Twin</p>
            <h1>NetTwin Security Panel</h1>
          </div>
          <div className="topbar-actions">
            <button className="icon-text-button" onClick={operatorLogin}><ShieldCheck size={18} /><span>Operator login</span></button>
            <div className="segmented-control mode-switcher">
              {["live", "replay", "simulation"].map((item) => (
                <button className={mode === item ? "active" : ""} key={item} onClick={() => changeMode(item)}>
                  {item}
                </button>
              ))}
            </div>
            <button
              className="icon-text-button"
              onClick={mode === "simulation" ? generateMetrics : syncLiveData}
              disabled={busy}
            >
              <RefreshCcw size={18} />
              <span>{busy ? "Running" : mode === "simulation" ? "Generate" : "Sync now"}</span>
            </button>
          </div>
        </header>

        {mode === "replay" && (
          <ReplayControls
            range={replayRange}
            onRangeChange={(field, value) => setReplayRange((current) => ({ ...current, [field]: value }))}
            speed={replaySpeed}
            onSpeedChange={setReplaySpeed}
            playing={replayPlaying}
            onToggle={() => {
              if (replayIndex >= replayTimeline.length - 1) setReplayIndex(0);
              setReplayPlaying((current) => !current);
            }}
            cursor={replayTimeline[replayIndex]}
            progress={replayTimeline.length ? replayIndex / Math.max(1, replayTimeline.length - 1) : 0}
            onSeek={(fraction) => setReplayIndex(Math.round(fraction * Math.max(0, replayTimeline.length - 1)))}
          />
        )}
        {error && <div className="connection-banner">{error}</div>}
        {loading ? (
          <section className="loading-panel">Loading digital twin telemetry...</section>
        ) : (
          <>
            {activeSection === "overview" && (
              <Dashboard
                summary={visibleSummary}
                alerts={visibleAlerts}
                optimizations={data.optimizations}
                latest={visibleLatest}
                mode={mode}
                sources={data.sources}
                onResolve={patchAlert}
              />
            )}
            <Suspense fallback={<section className="loading-panel">Loading module...</section>}>
              {activeSection === "map" && (
                <NetworkMap
                  stations={data.stations}
                  latestByStation={latestByStation}
                  alerts={visibleAlerts}
                  topology={data.topology}
                />
              )}
              {activeSection === "metrics" && (
                <MetricsChart metrics={visibleMetrics} stations={data.stations} mode={mode} />
              )}
              {activeSection === "scenarios" && (
                <ScenarioLab
                  onRun={runScenario}
                  busy={busy}
                  scenarioResult={scenarioResult}
                  scenarios={data.scenarios}
                  onSelectScenario={loadScenario}
                />
              )}
            </Suspense>
            {activeSection === "attacks" && (
              <AttackSimulation
                stations={data.stations}
                alerts={visibleAlerts}
                onRun={runAttack}
                busy={busy}
              />
            )}
            {activeSection === "optimizations" && (
              <div className="stack">
                <OptimizationPanel optimizations={data.optimizations} onUpdate={patchOptimization} />
                <AlertsLog alerts={data.alerts} onResolve={patchAlert} />
              </div>
            )}
            {activeSection === "sessions" && <MeasurementSessions />}
          </>
        )}
      </main>
    </div>
  );
}

function toLocalInput(date) {
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
