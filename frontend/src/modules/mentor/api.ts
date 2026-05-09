import { api } from "@/lib/axios";
import type {
  CompletionRequest,
  ConfirmStartRequest,
  ConfirmStartResult,
  ExtensionRequest,
  ExtensionResult,
  MentorInternsResponse,
  MentorRespondRequest,
  MentorRespondResponse,
  SimpleStatusResult,
  TerminationRequest,
} from "@/modules/mentor/types";

export interface MentorActionPreview {
  valid: boolean;
  action: "ACCEPT" | "REJECT";
  referral_id: string;
  expires_at: string;
}

export interface MentorActionResult {
  status: "ACCEPTED" | "REJECTED";
  referral_id: string;
  is_terminal: boolean;
  message: string;
}

const ACTION_BASE = `${import.meta.env.VITE_API_BASE_URL.replace(/\/api\/v1\/?$/, "")}/action/mentor`;

/**
 * The mentor action endpoints sit *outside* /api/v1 so the email links
 * stay short. We hit them with a fresh axios call rather than the
 * shared `api` instance (which prefixes /api/v1).
 */
export async function previewMentorAction(
  token: string,
  action: "ACCEPT" | "REJECT",
): Promise<MentorActionPreview> {
  const response = await api.get<MentorActionPreview>(ACTION_BASE, {
    params: { token, action },
  });
  return response.data;
}

export async function confirmMentorAction(payload: {
  token: string;
  action: "ACCEPT" | "REJECT";
  reason?: string | undefined;
}): Promise<MentorActionResult> {
  const response = await api.post<MentorActionResult>(
    `${ACTION_BASE}/confirm`,
    payload,
  );
  return response.data;
}

/* ─── S5 lifecycle (post-onboarding) ─── */

export async function getMyInterns(): Promise<MentorInternsResponse> {
  const { data } = await api.get<MentorInternsResponse>("/interns/mine");
  return data;
}

export async function getResumeUrl(
  referralId: string,
): Promise<{ url: string; file_name: string }> {
  const { data } = await api.get<{ url: string; file_name: string }>(
    `/referrals/${referralId}/resume`,
  );
  return data;
}

export async function respondToAssignment(
  body: MentorRespondRequest,
): Promise<MentorRespondResponse> {
  const { data } = await api.post<MentorRespondResponse>("/interns/respond", body);
  return data;
}

export async function confirmStart(
  body: ConfirmStartRequest,
): Promise<ConfirmStartResult> {
  const { data } = await api.post<ConfirmStartResult>(
    "/interns/confirm-start",
    body,
  );
  return data;
}

export async function requestExtension(
  body: ExtensionRequest,
): Promise<ExtensionResult> {
  const { data } = await api.post<ExtensionResult>("/interns/extend", body);
  return data;
}

export async function confirmCompletion(
  body: CompletionRequest,
): Promise<SimpleStatusResult> {
  const { data } = await api.post<SimpleStatusResult>(
    "/interns/confirm-completion",
    body,
  );
  return data;
}

export async function terminateIntern(
  body: TerminationRequest,
): Promise<SimpleStatusResult> {
  const { data } = await api.post<SimpleStatusResult>(
    "/interns/terminate",
    body,
  );
  return data;
}
