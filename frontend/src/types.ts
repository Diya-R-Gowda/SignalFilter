export interface Item {
  id: string;
  source: string;
  sender: string;
  content: string;
  thread_id: string | null;
  source_timestamp: string;
  focus_text: string;
  embedding_score: number | null;
  passed_stage1: boolean;
  llm_score: number | null;
  llm_reason: string | null;
  notified: boolean;
  created_at: string;
}

export interface Focus {
  focus_text: string;
  created_at: string;
}

export interface ConnectorHealth {
  name: string;
  last_heartbeat: string | null;
  seconds_since: number | null;
  stale: boolean;
  last_error_at: string | null;
  last_error_message: string | null;
}

export type SettingSource = "default" | "override";

export interface Settings {
  embedding_threshold: number;
  embedding_threshold_source: SettingSource;
  interrupt_score_threshold: number;
  interrupt_score_threshold_source: SettingSource;
  gmail_interrupt_score_threshold: number;
  gmail_interrupt_score_threshold_source: SettingSource;
}

export interface SettingsUpdate {
  embedding_threshold?: number;
  interrupt_score_threshold?: number;
  gmail_interrupt_score_threshold?: number;
}
