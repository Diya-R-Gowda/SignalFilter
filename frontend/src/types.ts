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
}
