export interface Session {
  id: string;
  title: string | null;
  preview: string | null;
  created_at: string;
  last_active_at: string;
}

export interface AgentUsage {
  usd: number;
  tokens: number;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface CostSummary {
  total_usd: number;
  total_tokens: number;
  total_calls: number;
  by_agent: Record<string, AgentUsage>;
  period: string;
}

export interface Contact {
  id: string;
  name: string;
  email?: string;
  notes?: string;
}

export interface Goal {
  id: string;
  objective: string;
  status: string;
  created_at: string;
}

export interface Reminder {
  id: string;
  label: string;
  fire_at: string;
  fired: boolean;
}

export interface CredibilityFlag {
  type: string;
  label: string;
  detail: string;
}

export interface Article {
  url: string;
  source_key: string;
  title: string;
  summary: string;
  published_at: string;
  tags: string[];
  credibility_flags: CredibilityFlag[];
}
