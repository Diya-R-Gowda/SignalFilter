import type { ConnectorHealth } from "./types";

function formatLabel(health: ConnectorHealth): string {
  const name = health.name.charAt(0).toUpperCase() + health.name.slice(1);
  if (health.last_error_message) {
    return `${name} — crashed: ${health.last_error_message}`;
  }
  if (health.seconds_since === null) {
    return `${name} — no heartbeat yet`;
  }
  return `${name} — checked ${health.seconds_since}s ago`;
}

function dotClass(health: ConnectorHealth): string {
  // Crashed (known cause) is a distinct state from merely stale (gone quiet, unknown why) —
  // a recorded failure is knowable the instant it happens, not just after the staleness window.
  if (health.last_error_message) return "crashed";
  return health.stale ? "stale" : "healthy";
}

export default function ConnectorStatus({ health }: { health: ConnectorHealth[] }) {
  if (health.length === 0) return null;

  return (
    <div className="connector-status">
      {health.map((h) => (
        <span key={h.name} className="connector-status-item" title={formatLabel(h)}>
          <span className={`connector-dot ${dotClass(h)}`} />
          {formatLabel(h)}
        </span>
      ))}
    </div>
  );
}
