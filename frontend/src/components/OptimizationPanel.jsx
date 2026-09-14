import { Check, ShieldCheck, X } from "lucide-react";

export default function OptimizationPanel({ optimizations, onUpdate, compact = false }) {
  return (
    <section className="list-panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Rule-based agent</p>
          <h2>Optimization Suggestions</h2>
        </div>
      </div>
      <div className={compact ? "compact-list" : "suggestion-list"}>
        {optimizations.length === 0 && <p className="empty-state">No pending suggestions.</p>}
        {optimizations.map((item) => (
          <article key={item.id} className="suggestion-card">
            <div className="suggestion-icon">
              <ShieldCheck size={18} />
            </div>
            <div>
              <strong>{item.suggestion_type}</strong>
              <span>{item.base_station_id}</span>
              <p>{item.description}</p>
            </div>
            {onUpdate && (
              <div className="row-actions">
                <button title="Apply suggestion" onClick={() => onUpdate(item.id, "Applied")}>
                  <Check size={16} />
                </button>
                <button title="Dismiss suggestion" onClick={() => onUpdate(item.id, "Dismissed")}>
                  <X size={16} />
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

