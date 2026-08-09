import { useEffect, useState } from "react";
import type { Item } from "./types";
import { sendFeedback } from "./api";

export default function ItemCard({ item }: { item: Item }) {
  const [feedback, setFeedback] = useState<boolean | null>(item.feedback);

  // item.feedback reflects the server's current vote (post-reload); keep local display in
  // sync if the underlying item prop changes (e.g. a fresh poll after voting elsewhere).
  useEffect(() => {
    setFeedback(item.feedback);
  }, [item.feedback]);

  async function handleFeedback(thumbsUp: boolean) {
    const previous = feedback;
    setFeedback(thumbsUp);
    try {
      await sendFeedback(item.id, thumbsUp);
    } catch {
      setFeedback(previous);
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
