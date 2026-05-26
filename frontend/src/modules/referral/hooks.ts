import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "@/modules/referral/api";
import type {
  CollegeCapStatus,
  MentorPickerResponse,
  PanCheckResponse,
} from "@/modules/referral/types";

/* ───────────────────────── Mentor picker ──────────────────────── */
export function useEligibleMentors() {
  return useQuery<MentorPickerResponse>({
    queryKey: ["mentors", "eligible"],
    queryFn: api.getEligibleMentors,
    staleTime: 60_000,
  });
}

/**
 * AI-2 ranked suggestions. Disabled until we have a college; matches
 * the backend cache TTL so re-renders don't re-hit the network.
 */
export function useMentorSuggestions(args: {
  college_id: string | null;
  candidate_skills: string[];
}) {
  const ready = Boolean(args.college_id);
  return useQuery({
    queryKey: [
      "mentors",
      "suggest",
      args.college_id,
      [...args.candidate_skills].sort().join("|"),
    ],
    queryFn: () =>
      api.suggestMentors({
        college_id: args.college_id as string,
        candidate_skills: args.candidate_skills,
      }),
    enabled: ready,
    staleTime: 60 * 60 * 1_000,
    retry: false,
  });
}

/* ───────────────────────── College autocomplete ───────────────── */
export function useCollegeSearch(
  query: string,
  options?: { skipCache?: boolean },
) {
  return useQuery({
    queryKey: ["colleges", "search", query, options?.skipCache ?? false],
    queryFn: () => api.searchColleges(query, options),
    enabled: query.trim().length > 1,
    staleTime: 60_000,
  });
}

/* ───────────────────────── College cap (live) ─────────────────── */
export function useCollegeCap(collegeId: string | null) {
  return useQuery<CollegeCapStatus>({
    queryKey: ["referrals", "college-cap", collegeId],
    queryFn: () => api.getCollegeCap(collegeId as string),
    enabled: collegeId !== null,
    staleTime: 30_000,
  });
}

/* ───────────────────────── Resume upload + AI prefill ─────────── */
export function useResumeUpload() {
  return useMutation({ mutationFn: api.uploadResume });
}

/* ───────────────────────── Realtime PAN check ─────────────────── */
const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

export function usePanCheck(rawPan: string) {
  const cleaned = rawPan.trim().toUpperCase();
  const debounced = useDebounced(cleaned, 350);
  const isValidShape = PAN_RE.test(debounced);

  return useQuery<PanCheckResponse>({
    queryKey: ["referrals", "check-pan", debounced],
    queryFn: () => api.checkPan(debounced),
    enabled: isValidShape,
    staleTime: 10_000,
    retry: false,
  });
}

/* ───────────────────────── Submit ─────────────────────────────── */
export function useSubmitReferral() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.submitReferral,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["referrals", "me"] });
      void qc.invalidateQueries({ queryKey: ["mentors", "eligible"] });
    },
  });
}

/* ───────────────────────── Helper: debounce ──────────────────── */
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  const timerRef = useRef<number | null>(null);
  useEffect(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setDebounced(value), delayMs);
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, [value, delayMs]);
  return debounced;
}
