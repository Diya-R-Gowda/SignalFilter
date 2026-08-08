import type { ConnectorHealth, Focus, Item } from "./types";

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

export async function sendFeedback(itemId: string, thumbsUp: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/items/${itemId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thumbs_up: thumbsUp }),
  });
  if (!res.ok) throw new Error(`POST /items/${itemId}/feedback failed: ${res.status}`);
}
