/**
 * Mirrors `backend/app/modules/admin/router.py`.
 */

export interface OverviewResponse {
  pipeline: Record<string, number>;
  sla_breaches_open: number;
  cooling_active: number;
  at_risk: number;
}

export interface AuditEntry {
  event_type: string;
  entity_type: string;
  entity_id: string;
  actor_user_id: string | null;
  actor_role: string | null;
  event_timestamp: string;
  payload: Record<string, unknown>;
}

export interface SlaBreach {
  id: string;
  task_type: string;
  intern_id: string | null;
  referral_id: string | null;
  assigned_to: string | null;
  sla_deadline: string;
  status: string;
  hours_overdue: number;
}

export interface MentorThresholdResponse {
  max_mentees: number;
}

export interface CoolingPeriodEntry {
  terminal_state: string;
  duration_months: number;
  description: string;
  set_by: string | null;
  reason: string | null;
}

export interface ConfigHistoryEntry {
  id: string;
  config_type: string;
  config_key: string;
  previous_value: string | null;
  new_value: string;
  unit: string;
  reason: string | null;
  changed_by: string | null;
  changed_at: string;
  applies_to: string | null;
}

export type ChatbotConfidence = "LOW" | "MEDIUM" | "HIGH";

export interface ChatbotResponse {
  answer: string;
  data_source: string;
  confidence: string;
}
