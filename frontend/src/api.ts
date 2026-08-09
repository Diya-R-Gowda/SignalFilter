import type { ConnectorHealth, FeedbackInsight, Focus, Item, Settings, SettingsUpdate } from "./types";

const API_BASE = "http://localhost:8000";

export async function getItems(): Promise<Item[]> {
  const res = await fetch(`${API_BASE}/items?limit=100`);
  if (!res.ok) throw new Error(`GET /items failed: ${res.status}`);
  return res.json();
}

export async function getFocus(): Promise<Focus | null> {
  const res = await fetch(`${API_BASE}/focus`);
  if (!res.ok) throw new Error(`GET /focus failed: ${res.status}`);
  return res.json();
}

export async function setFocus(focusText: string): Promise<Focus> {
  const res = await fetch(`${API_BASE}/focus`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ focus_text: focusText }),
  });
  if (!res.ok) throw new Error(`POST /focus failed: ${res.status}`);
  return res.json();
}

export async function getHealth(): Promise<ConnectorHealth[]> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`GET /health failed: ${res.status}`);
  return res.json();
}

export async function getSettings(): Promise<Settings> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error(`GET /settings failed: ${res.status}`);
  return res.json();
}

export class SettingsValidationError extends Error {
  fieldErrors: Record<string, string>;

  constructor(fieldErrors: Record<string, string>) {
    super(
      Object.entries(fieldErrors)
        .map(([field, msg]) => `${field}: ${msg}`)
        .join("; ") || "Validation failed"
    );
    this.fieldErrors = fieldErrors;
  }
}

export async function updateSettings(update: SettingsUpdate): Promise<Settings> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) {
    if (res.status === 422) {
      try {
        const body = await res.json();
        if (Array.isArray(body.detail)) {
          const fieldErrors: Record<string, string> = {};
          for (const d of body.detail as { loc?: unknown[]; msg?: string }[]) {
            const field = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : "value";
            fieldErrors[field] = d.msg ?? "Invalid value";
          }
          throw new SettingsValidationError(fieldErrors);
        }
      } catch (err) {
        if (err instanceof SettingsValidationError) throw err;
        // response body wasn't the JSON shape we expected — fall through to the generic error below
      }
    }
    throw new Error(`POST /settings failed: ${res.status}`);
  }
  return res.json();
}

export async function sendFeedback(itemId: string, thumbsUp: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/items/${itemId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thumbs_up: thumbsUp }),
  });
  if (!res.ok) throw new Error(`POST /items/${itemId}/feedback failed: ${res.status}`);
}

export async function getFeedbackInsights(): Promise<FeedbackInsight[]> {
  const res = await fetch(`${API_BASE}/feedback/insights`);
  if (!res.ok) throw new Error(`GET /feedback/insights failed: ${res.status}`);
  return res.json();
}
