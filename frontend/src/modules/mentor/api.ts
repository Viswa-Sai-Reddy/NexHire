import { api } from "@/lib/axios";

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
  reason?: string;
}): Promise<MentorActionResult> {
  const response = await api.post<MentorActionResult>(
    `${ACTION_BASE}/confirm`,
    payload,
  );
  return response.data;
}
