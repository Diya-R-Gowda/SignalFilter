import { useEffect, useState } from "react";
import { getFeedbackInsights, getSettings, SettingsValidationError, updateSettings } from "./api";
import type { FeedbackInsight, Settings } from "./types";

// Must match backend/app/config.py's feedback_min_votes — the API reports informative_votes
// and gate_met but not the denominator itself, since it's a backend constant, not a setting.
const FEEDBACK_MIN_VOTES = 10;

interface FieldConfig {
  key: "embedding_threshold" | "interrupt_score_threshold" | "gmail_interrupt_score_threshold";
  sourceKey:
    | "embedding_threshold_source"
    | "interrupt_score_threshold_source"
    | "gmail_interrupt_score_threshold_source";
  label: string;
  step: string;
}

const FIELDS: FieldConfig[] = [
  { key: "embedding_threshold", sourceKey: "embedding_threshold_source", label: "Embedding threshold (stage 1)", step: "0.01" },
  { key: "interrupt_score_threshold", sourceKey: "interrupt_score_threshold_source", label: "Slack notify threshold", step: "1" },
  { key: "gmail_interrupt_score_threshold", sourceKey: "gmail_interrupt_score_threshold_source", label: "Gmail notify threshold", step: "1" },
];

function suggestionText(insight: FeedbackInsight | undefined): string | null {
  if (!insight) return null;
  if (!insight.gate_met) {
    return `${insight.informative_votes}/${FEEDBACK_MIN_VOTES} votes so far — not enough data yet`;
  }
  const verb = insight.direction === "raise" ? "raising" : "lowering";
  return `${insight.informative_votes}/${FEEDBACK_MIN_VOTES} votes suggest ${verb} this threshold`;
}

export default function SettingsPanel() {
  const [settings, setSettingsState] = useState<Settings | null>(null);
  const [insights, setInsights] = useState<FeedbackInsight[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettingsState(s);
        setDraft({
          embedding_threshold: String(s.embedding_threshold),
          interrupt_score_threshold: String(s.interrupt_score_threshold),
          gmail_interrupt_score_threshold: String(s.gmail_interrupt_score_threshold),
        });
      })
      .catch(() => {
        // Settings failing to load isn't fatal to the rest of the dashboard — panel just stays hidden.
      });
    getFeedbackInsights()
      .then(setInsights)
      .catch(() => {
        // Insights are a bonus hint, not core functionality — silently skip on failure.
      });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    setSaving(true);
    try {
      const updated = await updateSettings({
        embedding_threshold: Number(draft.embedding_threshold),
        interrupt_score_threshold: Number(draft.interrupt_score_threshold),
        gmail_interrupt_score_threshold: Number(draft.gmail_interrupt_score_threshold),
      });
      setSettingsState(updated);
      setDraft({
        embedding_threshold: String(updated.embedding_threshold),
        interrupt_score_threshold: String(updated.interrupt_score_threshold),
        gmail_interrupt_score_threshold: String(updated.gmail_interrupt_score_threshold),
      });
    } catch (err) {
      setFieldErrors(
        err instanceof SettingsValidationError
          ? err.fieldErrors
          : { _general: err instanceof Error ? err.message : "Failed to save settings" }
      );
    } finally {
      setSaving(false);
    }
  }

  if (!settings) return null;

  return (
    <form onSubmit={handleSubmit} className="settings-panel">
      {FIELDS.map(({ key, sourceKey, label, step }) => (
        <div className="settings-field" key={key}>
          <label>
            {label}
            {settings[sourceKey] === "default" && <span className="settings-default-hint"> (default)</span>}
          </label>
          <input
            type="number"
            step={step}
            value={draft[key] ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
          />
          {fieldErrors[key] && <p className="settings-error">{fieldErrors[key]}</p>}
          {(() => {
            const text = suggestionText(insights.find((i) => i.threshold === key));
            return text && <p className="settings-suggestion">{text}</p>;
          })()}
        </div>
      ))}
      {fieldErrors._general && <p className="settings-error">{fieldErrors._general}</p>}
      <button type="submit" disabled={saving}>
        {saving ? "Saving…" : "Save settings"}
      </button>
    </form>
  );
}
