import { api, setAccessToken } from "@/lib/axios";

export interface CandidateRedeemResponse {
  access_token: string;
  expires_in: number;
  redirect_to: string;
  intern_id: string;
}

export interface JoiningFormDraft {
  intern_id: string;
  status: "DRAFT" | "SUBMITTED" | "LOCKED";
  version: number;
  personal_details: Record<string, unknown>;
  address: Record<string, unknown>;
  emergency_contact: Record<string, unknown>;
  education_history: unknown[];
  employment_history: unknown[];
  govt_ids: Record<string, unknown>;
  uploaded_documents: unknown[];
  declaration_signed: boolean;
  submitted_at: string | null;
  locked_at: string | null;
  locked_by_label: string | null;
  updated_at: string;
}

export interface JoiningFormSubmitResponse {
  decision: "AUTO_LOCK" | "ROUTED_TO_HR";
  high_flags: string[];
  low_flags: string[];
  next_redirect: string;
}

export async function redeemMagicLink(
  token: string,
): Promise<CandidateRedeemResponse> {
  const { data } = await api.post<CandidateRedeemResponse>(
    "/candidate/redeem",
    { token },
  );
  setAccessToken(data.access_token);
  return data;
}

export async function getJoiningForm(): Promise<JoiningFormDraft> {
  const { data } = await api.get<JoiningFormDraft>("/candidate/joining-form");
  return data;
}

export async function saveJoiningForm(
  body: { expected_version: number } & Partial<JoiningFormDraft>,
): Promise<JoiningFormDraft> {
  const { data } = await api.patch<JoiningFormDraft>(
    "/candidate/joining-form",
    body,
  );
  return data;
}

export async function submitJoiningForm(): Promise<JoiningFormSubmitResponse> {
  const { data } = await api.post<JoiningFormSubmitResponse>(
    "/candidate/joining-form/submit",
  );
  return data;
}
