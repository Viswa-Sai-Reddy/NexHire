/**
 * Mirrors the backend Pydantic shapes in
 * `backend/app/modules/referral/schemas.py`. Whenever a backend schema
 * changes, update this file and re-test the form. We could codegen
 * from FastAPI's OpenAPI doc later (TanStack Query has a generator);
 * for v1, hand-mirroring is faster than introducing the codegen
 * pipeline.
 */

export type PanVerdict =
  | "CLEAR"
  | "HARD_BLOCK"
  | "COOLING_BLOCK"
  | "WARN"
  | "SOFT_BLOCK";

export interface PanCheckResponse {
  verdict: PanVerdict;
  pan_masked: string;
  message: string;
  existing_referral_id?: string | null;
  existing_status?: string | null;
  cooling_end?: string | null;
  cooling_days_remaining?: number | null;
  cooling_terminal_state?: string | null;
  months_duration?: number | null;
  allow_override: boolean;
}

export interface ResumePrefillResponse {
  document_id: string;
  succeeded: boolean;
  user_message?: string | null;
  degradation_reason?: string | null;
  candidate_name?: string | null;
  candidate_name_confidence?: number | null;
  candidate_email?: string | null;
  candidate_email_confidence?: number | null;
  candidate_phone?: string | null;
  candidate_phone_confidence?: number | null;
  candidate_year_of_study?: number | null;
  candidate_year_of_study_confidence?: number | null;
  college_name?: string | null;
  college_name_confidence?: number | null;
  candidate_graduation_year?: number | null;
  candidate_graduation_year_confidence?: number | null;
  skills: string[];
  suggested_project_tracks: string[];
  red_flags: string[];
  recommended_mentor_questions: string[];
  internship_readiness_score: number;
}

export interface CollegeSearchResult {
  id: string;
  canonical_name: string;
  aliases: string[];
  location_state?: string | null;
  type?: string | null;
}

export interface CollegeCapStatus {
  college_id: string;
  used: number;
  limit: number;
  remaining: number;
  can_submit: boolean;
  warning: boolean;
}

export interface MentorPickerEntry {
  user_id: string;
  full_name: string;
  email: string;
  active_mentees: number;
  threshold: number;
  available: boolean;
}

export interface MentorPickerResponse {
  threshold: number;
  mentors: MentorPickerEntry[];
}

export interface ReferralSubmitRequest {
  candidate_name: string;
  candidate_email: string;
  candidate_phone?: string | null;
  candidate_pan: string;
  college_id: string;
  candidate_year_of_study: 2 | 3 | 4;
  candidate_graduation_year: number;
  unpaid_consent: boolean;
  inperson_ready: boolean;
  relationship_declaration?: string | null;
  relationship_declaration_detail?: string | null;
  mentor_id: string;
  project_title: string;
  project_overview?: string | null;
  joining_location: string;
  internship_start_date: string; // YYYY-MM-DD
  internship_end_date: string;
  resume_document_id?: string | null;
}

export interface ReferralSubmitResponse {
  referral_id: string;
  status: string;
  risk_score: number;
  risk_classification: "LOW" | "MEDIUM" | "HIGH";
  duplicate_warning?: string | null;
}

export interface ReferralSummary {
  id: string;
  status: string;
  current_stage: string;
  candidate_name: string;
  candidate_email: string;
  pan_masked: string;
  college_id: string;
  project_title?: string | null;
  submitted_at?: string | null;
  mentor_id?: string | null;
  mentor_attempt_count: number;
  created_at: string;
  intern_id?: string | null;
  intern_status?: string | null;
}

/* ─── S2 — AI-2 mentor matcher ─── */

export interface MentorRadar {
  skill: number;
  availability: number;
  reputation: number;
  familiarity: number;
  responsiveness: number;
}

export interface MentorSuggestion {
  user_id: string;
  full_name: string;
  email: string;
  active_mentees: number;
  threshold: number;
  match_score: number;
  radar: MentorRadar;
  reason: string;
  ai_reason: boolean;
}

export interface MentorSuggestResponse {
  threshold: number;
  suggestions: MentorSuggestion[];
}
