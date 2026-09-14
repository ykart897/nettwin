import { Pause, Play } from "lucide-react";

export default function ReplayControls({ range, onRangeChange, speed, onSpeedChange, playing, onToggle, cursor, progress, onSeek }) {
  return (
    <div className="replay-controls">
      <label>
        From
        <input
          type="datetime-local"
          value={range.fromLocal}
          onChange={(event) => onRangeChange("fromLocal", event.target.value)}
        />
      </label>
      <label>
        To
        <input
          type="datetime-local"
          value={range.toLocal}
          onChange={(event) => onRangeChange("toLocal", event.target.value)}
        />
      </label>
      <label>
        Speed
        <select value={speed} onChange={(event) => onSpeedChange(Number(event.target.value))}>
          <option value={1}>1x</option>
          <option value={2}>2x</option>
          <option value={5}>5x</option>
        </select>
      </label>
      <button className="icon-text-button" onClick={onToggle}>
        {playing ? <Pause size={17} /> : <Play size={17} />}
        <span>{playing ? "Pause" : "Play"}</span>
      </button>
      <label className="replay-progress">
        Timeline
        <input type="range" min="0" max="1000" value={Math.round(progress * 1000)} onChange={(event) => onSeek(Number(event.target.value) / 1000)} />
        <span>{cursor ? new Date(cursor).toLocaleString() : "No observations"}</span>
      </label>
    </div>
  );
}
