import { Database, Radio, Wifi } from "lucide-react";

const icons = {
  opencellid: Radio,
  ripe_atlas: Database,
  local_agent: Wifi,
};

export default function SourceStatus({ sources }) {
  return (
    <section className="source-panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Data connections</p>
          <h2>Source status</h2>
        </div>
      </div>
      <div className="source-grid">
        {sources.map((source) => {
          const Icon = icons[source.source] || Database;
          const displayStatus = source.display_status === "disabled"
            ? "disabled"
            : source.stale && source.status === "healthy" ? "stale" : source.status;
          return (
            <article className={`source-card ${displayStatus}`} key={source.source}>
              <Icon size={18} />
              <div>
                <strong>{source.source.replaceAll("_", " ")}</strong>
                <span>{displayStatus}</span>
                <p>{source.message || "Waiting for first sync."}</p>
                <small>
                  {source.last_success_at
                    ? `Last sync: ${new Date(source.last_success_at).toLocaleString()}`
                    : "No successful sync yet"}
                </small>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
