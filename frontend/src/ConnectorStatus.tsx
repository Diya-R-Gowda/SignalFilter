import type { ConnectorHealth } from "./types";

function formatLabel(health: ConnectorHealth): string {
  const name = health.name.charAt(0).toUpperCase() + health.name.slice(1);
  if (health.seconds_since === null) {
    return `${name} — no heartbeat yet`;
  }
  return `${name} — checked ${health.seconds_since}s ago`;
}

export default function ConnectorStatus({ health }: { health: ConnectorHealth[] }) {
  if (health.length === 0) return null;

  return (
    <div className="connector-status">
      {health.map((h) => (
        <span key={h.name} className="connector-status-item">
          <span className={`connector-dot ${h.stale ? "stale" : "healthy"}`} />
          {formatLabel(h)}
        </span>
      ))}
    </div>
  );
}
