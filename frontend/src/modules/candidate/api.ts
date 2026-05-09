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

export interface CandidateIntern {
  intern_id: string;
  referral_id: string;
  status: string;
  candidate_name: string;
  non_worker_id: string | null;
  project_title: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  internship_start_date: string | null;
  internship_end_date: string | null;
}

export async function getMyIntern(): Promise<CandidateIntern> {
  const { data } = await api.get<CandidateIntern>("/candidate/intern");
  return data;
}

export async function getCertificateUrl(): Promise<{
  url: string;
  file_name: string;
}> {
  const { data } = await api.get<{ url: string; file_name: string }>(
    "/candidate/certificate",
  );
  return data;
}

export interface CandidateLoginResponse {
  access_token: string;
  expires_in: number;
  redirect_to: string;
  intern_id: string;
}

export async function candidateLogin(
  email: string,
  nonWorkerId: string,
): Promise<CandidateLoginResponse> {
  const { data } = await api.post<CandidateLoginResponse>("/candidate/login", {
    email,
    non_worker_id: nonWorkerId,
  });
  setAccessToken(data.access_token);
  return data;
}

export async function requestMagicLink(email: string): Promise<void> {
  await api.post("/candidate/request-magic-link", { email });
}

export async function terminateMyIntern(
  internId: string,
  reason: string,
): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>("/interns/terminate", {
    intern_id: internId,
    reason,
  });
  return data;
}

export interface CandidateNda {
  intern_id: string;
  status: "PENDING" | "SENT" | "SIGNED" | "DECLINED" | "EXPIRED";
  candidate_name: string;
  text_html: string;
  text_sha256: string;
  signed_at: string | null;
  typed_name: string | null;
}

export async function getNda(): Promise<CandidateNda> {
  const { data } = await api.get<CandidateNda>("/candidate/nda");
  return data;
}

export async function acceptNda(
  typedName: string,
  textSha256: string,
): Promise<CandidateNda> {
  const { data } = await api.post<CandidateNda>("/candidate/nda/accept", {
    typed_name: typedName,
    text_sha256: textSha256,
  });
  return data;
}
