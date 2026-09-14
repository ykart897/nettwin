import { RadioTower } from "lucide-react";

export default function Sidebar({ sections, activeSection, onSelect }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <RadioTower size={24} />
        <div>
          <strong>NetTwin</strong>
          <span>6G Twin</span>
        </div>
      </div>
      <nav className="nav-list">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <button
              key={section.id}
              className={section.id === activeSection ? "nav-item active" : "nav-item"}
              onClick={() => onSelect(section.id)}
              title={section.label}
            >
              <Icon size={18} />
              <span>{section.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

