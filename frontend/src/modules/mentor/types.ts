/**
 * Mirrors the Pydantic shapes in `backend/app/modules/lifecycle/router.py`.
 */

export type InternStatus =
  | "PENDING"
  | "ACCESS_PENDING"
  | "ACTIVE"
  | "EXTENDED"
  | "CLOSURE_PENDING"
  | "CLOSED"
  | "TERMINATED";

export interface MentorInternEntry {
  // intern-specific fields are null until HR approves the referral and
  // an Intern row is created. Pre-approval rows still appear in the
  // mentor's pipeline view so they can track what's coming.
  intern_id: string | null;
  referral_id: string;
  candidate_name: string;
  candidate_email: string;
  referral_status: string;
  intern_status: InternStatus | null;
  project_title: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  extension_count: number;
  internship_start_date: string | null;
  internship_end_date: string | null;
  submitted_at: string | null;
  // AI context surfaced for the dashboard accept/reject decision.
  risk_score: number | null;
  red_flags: string[];
  // True when a resume is attached — UI shows a "View resume" link.
  has_resume: boolean;
}

export interface MentorRespondRequest {
  referral_id: string;
  action: "ACCEPT" | "REJECT";
  reason?: string;
}

export interface MentorRespondResponse {
  referral_id: string;
  assignment_status: string;
  referral_status: string;
  is_terminal: boolean;
}

export interface MentorInternsResponse {
  items: MentorInternEntry[];
}

export interface ConfirmStartRequest {
  intern_id: string;
}

export interface ExtensionRequest {
  intern_id: string;
  new_end_date: string; // YYYY-MM-DD
  reason: string;
}

export interface CompletionRequest {
  intern_id: string;
  project_summary: string;
  skills_demonstrated: string[];
  recommendation_strength: 1 | 2 | 3 | 4 | 5;
  notable_contributions?: string | null;
}

export interface TerminationRequest {
  intern_id: string;
  reason: string;
}

export interface ConfirmStartResult {
  status: string;
  actual_start_date: string;
}

export interface ExtensionResult {
  status: string;
  new_end_date: string;
  extension_count: number;
}

export interface SimpleStatusResult {
  status: string;
}
