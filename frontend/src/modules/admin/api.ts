import { api } from "@/lib/axios";
import type {
  AuditEntry,
  ChatbotResponse,
  ConfigHistoryEntry,
  CoolingPeriodEntry,
  MentorThresholdResponse,
  OverviewResponse,
  SlaBreach,
} from "@/modules/admin/types";

/* ─── S23: Executive overview ─── */

export async function getOverview(): Promise<OverviewResponse> {
  const { data } = await api.get<OverviewResponse>("/admin/overview");
  return data;
}

/* ─── S24: Audit + SLA ─── */

export async function getRecentAudit(): Promise<AuditEntry[]> {
  const { data } = await api.get<AuditEntry[]>("/admin/audit/recent");
  return data;
}

export async function getOpenSlaBreaches(): Promise<SlaBreach[]> {
  const { data } = await api.get<SlaBreach[]>("/admin/sla/open");
  return data;
}

/* ─── S25: Config panel ─── */

export async function getMentorThreshold(): Promise<MentorThresholdResponse> {
  const { data } = await api.get<MentorThresholdResponse>(
    "/admin/config/mentor-threshold",
  );
  return data;
}

export async function setMentorThreshold(
  newValue: number,
  reason?: string,
): Promise<MentorThresholdResponse> {
  const { data } = await api.post<MentorThresholdResponse>(
    "/admin/config/mentor-threshold",
    { new_value: newValue, reason },
  );
  return data;
}

export async function getCoolingPeriods(): Promise<CoolingPeriodEntry[]> {
  const { data } = await api.get<CoolingPeriodEntry[]>(
    "/admin/config/cooling-periods",
  );
  return data;
}

export async function setCoolingPeriod(
  terminalState: string,
  newDurationMonths: number,
  reason?: string,
): Promise<{ terminal_state: string; duration_months: number }> {
  const { data } = await api.post<{
    terminal_state: string;
    duration_months: number;
  }>(`/admin/config/cooling-periods/${terminalState}`, {
    new_duration_months: newDurationMonths,
    reason,
  });
  return data;
}

export async function getConfigHistory(): Promise<ConfigHistoryEntry[]> {
  const { data } = await api.get<ConfigHistoryEntry[]>("/admin/config/history");
  return data;
}

/* ─── AI-9 chatbot ─── */

export async function askChatbot(question: string): Promise<ChatbotResponse> {
  const { data } = await api.post<ChatbotResponse>("/admin/chatbot", {
    question,
  });
  return data;
}
