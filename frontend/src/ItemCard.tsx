import { useState } from "react";
import type { Item } from "./types";
import { sendFeedback } from "./api";

export default function ItemCard({ item }: { item: Item }) {
  const [feedback, setFeedback] = useState<boolean | null>(null);

  async function handleFeedback(thumbsUp: boolean) {
    setFeedback(thumbsUp);
    try {
      await sendFeedback(item.id, thumbsUp);
    } catch {
      setFeedback(null);
    }
  }

  return (
    <div className="item-card">
      <div className="item-header">
        <span className="item-source">{item.source}</span>
        <span className="item-sender">{item.sender}</span>
        <span className="item-time">{new Date(item.created_at).toLocaleTimeString()}</span>
      </div>
      <p className="item-content">{item.content}</p>
      <div className="item-footer">
        <span className="item-scores">
          embedding {item.embedding_score?.toFixed(2) ?? "—"} · llm{" "}
          {item.llm_score ?? "—"}
          {item.llm_reason ? ` (${item.llm_reason})` : ""}
        </span>
        <span className="item-feedback">
          <button
            className={feedback === true ? "active" : ""}
            onClick={() => handleFeedback(true)}
            aria-label="Thumbs up"
          >
            👍
          </button>
          <button
            className={feedback === false ? "active" : ""}
            onClick={() => handleFeedback(false)}
            aria-label="Thumbs down"
          >
            👎
          </button>
        </span>
      </div>
    </div>
  );
}
