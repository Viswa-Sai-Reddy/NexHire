import { api } from "@/lib/axios";
import type { ReferralSummary } from "@/modules/referral/types";
import type {
  HrInternsParams,
  HrInternsResponse,
  HrQueueResponse,
  HrReviewContext,
  RecentAiActionsResponse,
} from "@/modules/hr/types";

export async function getQueue(): Promise<HrQueueResponse> {
  const { data } = await api.get<HrQueueResponse>("/referrals/hr/queue");
  return data;
}

export async function getRecentAiActions(): Promise<RecentAiActionsResponse> {
  const { data } = await api.get<RecentAiActionsResponse>(
    "/referrals/hr/recent-ai",
  );
  return data;
}

export async function getReviewContext(
  referralId: string,
): Promise<HrReviewContext> {
  const { data } = await api.get<HrReviewContext>(
    `/referrals/hr/${referralId}/review`,
  );
  return data;
}

export async function approveReferral(
  referralId: string,
  notes?: string,
): Promise<ReferralSummary> {
  const { data } = await api.post<ReferralSummary>(
    `/referrals/hr/${referralId}/approve`,
    { notes },
  );
  return data;
}

export async function rejectReferral(
  referralId: string,
  reason: string,
): Promise<ReferralSummary> {
  const { data } = await api.post<ReferralSummary>(
    `/referrals/hr/${referralId}/reject`,
    { reason },
  );
  return data;
}

export async function requestCorrection(
  referralId: string,
  notes: string,
): Promise<ReferralSummary> {
  const { data } = await api.post<ReferralSummary>(
    `/referrals/hr/${referralId}/request-correction`,
    { notes },
  );
  return data;
}

export async function recallAutoApprove(
  referralId: string,
  reason?: string,
): Promise<ReferralSummary> {
  const { data } = await api.post<ReferralSummary>(
    `/referrals/hr/${referralId}/recall`,
    { reason },
  );
  return data;
}

export async function getAllInterns(
  params: HrInternsParams = {},
): Promise<HrInternsResponse> {
  const { data } = await api.get<HrInternsResponse>("/referrals/hr/interns", {
    params,
  });
  return data;
}
