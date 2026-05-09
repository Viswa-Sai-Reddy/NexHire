/**
 * Mirrors the Pydantic shapes in `backend/app/modules/referral/hr_router.py`.
 */

import type { ReferralSummary } from "@/modules/referral/types";

export interface HrQueueEntry extends ReferralSummary {
  flags: string[];
  hr_recommendation: string | null;
  auto_action_id: string | null;
  routed_at: string | null;
}

export interface HrQueueResponse {
  total: number;
  items: HrQueueEntry[];
}

export interface RecentAiActionEntry {
  auto_action_id: string;
  referral_id: string;
  action_type: string;
  decision: string;
  executed_at: string;
  recall_window_ends_at: string;
  recall_active: boolean;
}

export interface RecentAiActionsResponse {
  items: RecentAiActionEntry[];
}

export interface HrReviewContext {
  referral: ReferralDetail;
  risk_score: number | null;
  risk_classification: "LOW" | "MEDIUM" | "HIGH" | null;
  risk_factors: { code: string; weight: number; detail: string }[];
  risk_narrative: string | null;
  duplicate_recommendation: string | null;
  duplicate_similarity: number | null;
  duplicate_match_reasons: string[];
  duplicate_matched_referral_id: string | null;
  resume_skills: string[];
  resume_red_flags: string[];
  resume_recommended_questions: string[];
  resume_internship_readiness: number | null;
  auto_action_id: string | null;
  auto_action_decision: string | null;
  auto_action_flags: string[];
  auto_action_recommendation: string | null;
  auto_action_executed_at: string | null;
  recall_window_ends_at: string | null;
  recall_active: boolean;
}

export interface ReferralDetail extends ReferralSummary {
  candidate_phone: string | null;
  candidate_year_of_study: number;
  candidate_graduation_year: number;
  project_overview: string | null;
  joining_location: string | null;
  internship_start_date: string | null;
  internship_end_date: string | null;
  rejection_reason: string | null;
}

export interface HrInternEntry {
  intern_id: string;
  referral_id: string;
  non_worker_id: string;
  candidate_name: string;
  candidate_email: string;
  intern_status: string;
  referral_status: string;
  project_title: string | null;
  joining_location: string | null;
  internship_start_date: string | null;
  internship_end_date: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  created_at: string;
}

export interface HrInternsResponse {
  total: number;
  items: HrInternEntry[];
  limit: number;
  offset: number;
}

export interface HrInternsParams {
  q?: string;
  intern_status?: string;
  limit?: number;
  offset?: number;
}
