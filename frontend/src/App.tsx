import { useEffect, useState } from "react";
import "./App.css";
import { getFocus, getHealth, getItems, setFocus } from "./api";
import ConnectorStatus from "./ConnectorStatus";
import ItemCard from "./ItemCard";
import SettingsPanel from "./SettingsPanel";
import type { ConnectorHealth, Focus, Item } from "./types";

const POLL_INTERVAL_MS = 5000;

// Must match backend/app/config.py's attention_budget_daily — a plain backend constant,
// not exposed via /settings, same pattern as SettingsPanel.tsx's FEEDBACK_MIN_VOTES.
const ATTENTION_BUDGET_DAILY = 10;

// item.created_at comes back from the API with no timezone suffix even though the
// underlying value is UTC wall-clock (the DB column has no tz). Appending "Z" makes JS
// parse it as UTC rather than (incorrectly) local time, so the local-calendar-day
// comparison below actually lines up with the backend's own local-midnight boundary.
function isLocalToday(utcIsoString: string): boolean {
  const parsed = new Date(utcIsoString.endsWith("Z") ? utcIsoString : `${utcIsoString}Z`);
  const now = new Date();
  return (
    parsed.getFullYear() === now.getFullYear() &&
    parsed.getMonth() === now.getMonth() &&
    parsed.getDate() === now.getDate()
  );
}

function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [focus, setFocusState] = useState<Focus | null>(null);
  const [focusInput, setFocusInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showLowRelevance, setShowLowRelevance] = useState(false);
  const [health, setHealth] = useState<ConnectorHealth[]>([]);

  useEffect(() => {
    async function refresh() {
      try {
        const [itemsRes, focusRes, healthRes] = await Promise.all([getItems(), getFocus(), getHealth()]);
        setItems(itemsRes);
        setFocusState(focusRes);
        setHealth(healthRes);
        setError(null);
      } catch {
        setError("Can't reach the API — is `uvicorn app.main:app` running on port 8000?");
      }
    }
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  async function handleFocusSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!focusInput.trim()) return;
    const updated = await setFocus(focusInput.trim());
    setFocusState(updated);
    setFocusInput("");
  }

  const isLowRelevance = (item: Item) =>
    !item.passed_stage1 || (item.llm_score !== null && item.llm_score <= 1);
  const isDigestWorthy = (item: Item) =>
    item.passed_stage1 &&
    item.llm_score !== null &&
    item.llm_score > 1 &&
    !item.notified &&
    item.digested_at === null &&
    item.queued_at === null;
  const isQueued = (item: Item) => item.queued_at !== null;

  const surfaced = items.filter((item) => item.notified);
  const filtered = items.filter((item) => !item.notified && !isQueued(item));
  const digest = items.filter(isDigestWorthy);
  const queued = items.filter(isQueued);
  const lowRelevanceCount = filtered.filter(isLowRelevance).length;
  const visibleFiltered = showLowRelevance ? filtered : filtered.filter((item) => !isLowRelevance(item));
  const notifiedToday = items.filter((item) => item.notified && isLocalToday(item.created_at)).length;

  return (
    <div className="app">
      <header>
        <h1>Signal Filter</h1>
        <p className="current-focus">
          Current focus: <strong>{focus?.focus_text ?? "not set"}</strong>
        </p>
        <ConnectorStatus health={health} />
        <p className="budget-indicator">
          {notifiedToday}/{ATTENTION_BUDGET_DAILY} notifications used today
        </p>
        <SettingsPanel />
        <form onSubmit={handleFocusSubmit} className="focus-form">
          <input
            value={focusInput}
            onChange={(e) => setFocusInput(e.target.value)}
            placeholder="What are you focused on right now?"
          />
          <button type="submit">Set focus</button>
        </form>
        {error && <p className="error">{error}</p>}
      </header>

      <main className="columns">
        <section>
          <h2>Surfaced ({surfaced.length})</h2>
          {surfaced.length === 0 && <p className="empty">Nothing notified yet.</p>}
          {surfaced.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </section>

        <section className="queued-section">
          <h2>Queued ({queued.length})</h2>
          <p className="queued-hint">Cleared the notify threshold but held back by today's attention budget.</p>
          {queued.length === 0 && <p className="empty">Nothing queued right now.</p>}
          {queued.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </section>

        <section>
          <h2>Digest ({digest.length})</h2>
          {digest.length === 0 && <p className="empty">Nothing digest-worthy right now.</p>}
          {digest.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </section>

        <section>
          <h2>Filtered ({visibleFiltered.length})</h2>
          {lowRelevanceCount > 0 && (
            <button className="toggle-low-relevance" onClick={() => setShowLowRelevance((v) => !v)}>
              {showLowRelevance
                ? `Hide ${lowRelevanceCount} low-relevance (marketing/bulk) items`
                : `${lowRelevanceCount} low-relevance (marketing/bulk) items hidden — show`}
            </button>
          )}
          {visibleFiltered.length === 0 && <p className="empty">Nothing filtered yet.</p>}
          {visibleFiltered.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </section>
      </main>
    </div>
  );
}

export default App;
