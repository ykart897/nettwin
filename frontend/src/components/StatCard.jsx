export default function StatCard({ label, value, tone = "neutral", icon: Icon, suffix = "" }) {
  return (
    <article className={`stat-card ${tone}`}>
      <div className="stat-icon">{Icon && <Icon size={19} />}</div>
      <div>
        <span>{label}</span>
        <strong>
          {value == null ? "—" : `${value}${suffix}`}
        </strong>
      </div>
    </article>
  );
}
