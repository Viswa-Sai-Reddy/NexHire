import { api } from "@/lib/axios";
import type {
  CollegeCapStatus,
  CollegeSearchResult,
  MentorPickerResponse,
  MentorSuggestResponse,
  PanCheckResponse,
  ReferralSubmitRequest,
  ReferralSubmitResponse,
  ReferralSummary,
  ResumePrefillResponse,
} from "@/modules/referral/types";

export async function uploadResume(file: File): Promise<ResumePrefillResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ResumePrefillResponse>(
    "/referrals/upload-resume",
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

export async function checkPan(pan: string): Promise<PanCheckResponse> {
  const { data } = await api.post<PanCheckResponse>("/referrals/check-pan", { pan });
  return data;
}

export async function getCollegeCap(collegeId: string): Promise<CollegeCapStatus> {
  const { data } = await api.get<CollegeCapStatus>("/referrals/college-cap", {
    params: { college_id: collegeId },
  });
  return data;
}

export async function searchColleges(q: string): Promise<CollegeSearchResult[]> {
  if (!q.trim()) return [];
  const { data } = await api.get<CollegeSearchResult[]>("/colleges/search", {
    params: { q, limit: 10 },
  });
  return data;
}

export async function getEligibleMentors(): Promise<MentorPickerResponse> {
  const { data } = await api.get<MentorPickerResponse>("/mentors/eligible");
  return data;
}

export async function suggestMentors(body: {
  college_id: string;
  candidate_skills: string[];
  excluded_mentor_ids?: string[];
  top_n?: number;
}): Promise<MentorSuggestResponse> {
  const { data } = await api.post<MentorSuggestResponse>("/mentors/suggest", {
    college_id: body.college_id,
    candidate_skills: body.candidate_skills,
    excluded_mentor_ids: body.excluded_mentor_ids ?? [],
    top_n: body.top_n ?? 3,
  });
  return data;
}

export async function submitReferral(
  body: ReferralSubmitRequest,
): Promise<ReferralSubmitResponse> {
  const { data } = await api.post<ReferralSubmitResponse>("/referrals", body);
  return data;
}

export async function listMyReferrals(): Promise<ReferralSummary[]> {
  const { data } = await api.get<ReferralSummary[]>("/referrals/me");
  return data;
}
