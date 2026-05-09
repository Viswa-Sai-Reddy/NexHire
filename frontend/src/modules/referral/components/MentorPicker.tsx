import { useState } from "react";

import {
  useEligibleMentors,
  useMentorSuggestions,
} from "@/modules/referral/hooks";
import type {
  MentorPickerEntry,
  MentorSuggestion,
} from "@/modules/referral/types";
import { cn } from "@/lib/utils";

interface Props {
  value: string | null;
  onChange: (mentorId: string) => void;
  /** AI-2 inputs. When `collegeId` is null, picker shows the flat list. */
  collegeId: string | null;
  candidateSkills: string[];
}

/**
 * Two-mode mentor picker:
 *   * "AI Recommended" — top-3 from POST /mentors/suggest with radar
 *     scores + a per-mentor reason.
 *   * "Browse all"     — flat /mentors/eligible list (S1 fallback).
 *
 * AI mode is the default whenever a college has been chosen.
 */
export function MentorPicker({
  value,
  onChange,
  collegeId,
  candidateSkills,
}: Props) {
  const [mode, setMode] = useState<"ai" | "all">("ai");
  const aiMode = mode === "ai" && collegeId !== null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {aiMode
            ? "Top 3 mentors ranked by skill, capacity, history, and responsiveness."
            : "All mentors with current capacity."}
        </p>
        <button
          type="button"
          onClick={() => setMode((m) => (m === "ai" ? "all" : "ai"))}
          className="text-xs font-medium text-primary hover:underline"
        >
          {aiMode ? "Browse all mentors ▼" : "Show AI suggestions ▲"}
        </button>
      </div>

      {aiMode ? (
        <AiSuggestions
          value={value}
          onChange={onChange}
          collegeId={collegeId}
          candidateSkills={candidateSkills}
        />
      ) : (
        <FlatList value={value} onChange={onChange} />
      )}
    </div>
  );
}

/* ──────────────────────── AI-2 mode ──────────────────────── */
function AiSuggestions({
  value,
  onChange,
  collegeId,
  candidateSkills,
}: {
  value: string | null;
  onChange: (id: string) => void;
  collegeId: string | null;
  candidateSkills: string[];
}) {
  const query = useMentorSuggestions({
    college_id: collegeId,
    candidate_skills: candidateSkills,
  });

  if (query.isLoading) {
    return (
      <p className="text-sm text-muted-foreground">
        Computing ranked recommendations…
      </p>
    );
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="text-sm text-destructive">
        Could not load recommendations. Switch to "Browse all" or refresh.
      </p>
    );
  }
  if (query.data.suggestions.length === 0) {
    return (
      <p className="rounded-md border border-stage-review/30 bg-stage-review/10 px-3 py-2 text-sm text-stage-review">
        No mentors with capacity right now. Try the "Browse all" view, or
        contact HR.
      </p>
    );
  }

  return (
    <ul className="grid gap-3">
      {query.data.suggestions.map((s) => (
        <li key={s.user_id}>
          <SuggestionCard
            suggestion={s}
            selected={value === s.user_id}
            onSelect={() => onChange(s.user_id)}
          />
        </li>
      ))}
    </ul>
  );
}

function SuggestionCard({
  suggestion,
  selected,
  onSelect,
}: {
  suggestion: MentorSuggestion;
  selected: boolean;
  onSelect: () => void;
}) {
  const initials = suggestion.full_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex w-full items-stretch gap-4 rounded-xl border p-4 text-left transition",
        selected
          ? "border-primary bg-primary/5"
          : "border-border bg-card hover:border-primary/50",
      )}
    >
      <div className="flex flex-col items-center justify-center">
        <span
          aria-hidden
          className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-base font-semibold text-primary"
        >
          {initials || "?"}
        </span>
        <span className="mt-2 text-xs font-medium text-muted-foreground">
          {suggestion.active_mentees} / {suggestion.threshold}
        </span>
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">{suggestion.full_name}</p>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            Match: {suggestion.match_score}%
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{suggestion.email}</p>
        <p className="mt-2 text-sm text-foreground">{suggestion.reason}</p>
        <RadarBars radar={suggestion.radar} />
        {!suggestion.ai_reason && (
          <p className="mt-1 text-[11px] italic text-muted-foreground">
            (Reason generated from rule template — AI narrative unavailable.)
          </p>
        )}
      </div>
    </button>
  );
}

function RadarBars({
  radar,
}: {
  radar: MentorSuggestion["radar"];
}) {
  const bars: { key: keyof MentorSuggestion["radar"]; label: string }[] = [
    { key: "skill", label: "Skill" },
    { key: "availability", label: "Avail" },
    { key: "reputation", label: "Rep" },
    { key: "familiarity", label: "Familiar" },
    { key: "responsiveness", label: "Speed" },
  ];
  return (
    <ul className="mt-3 grid gap-1 sm:grid-cols-5">
      {bars.map((b) => (
        <li key={b.key} className="text-[11px]">
          <div className="flex items-center justify-between text-muted-foreground">
            <span>{b.label}</span>
            <span>{radar[b.key]}</span>
          </div>
          <div className="mt-0.5 h-1.5 rounded-full bg-secondary" aria-hidden>
            <div
              className="h-1.5 rounded-full bg-primary"
              style={{ width: `${(radar[b.key] / 20) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ──────────────────────── Flat list mode ──────────────────────── */
function FlatList({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (id: string) => void;
}) {
  const query = useEligibleMentors();
  if (query.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading mentors…</p>;
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="text-sm text-destructive">
        Could not load mentors. Refresh to try again.
      </p>
    );
  }
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {query.data.mentors.map((m) => (
        <li key={m.user_id}>
          <MentorCard
            mentor={m}
            selected={value === m.user_id}
            onSelect={() => onChange(m.user_id)}
          />
        </li>
      ))}
    </ul>
  );
}

function MentorCard({
  mentor,
  selected,
  onSelect,
}: {
  mentor: MentorPickerEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  const initials = mentor.full_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!mentor.available}
      aria-pressed={selected}
      className={cn(
        "flex w-full items-center justify-between gap-3 rounded-xl border p-4 text-left transition",
        selected
          ? "border-primary bg-primary/5"
          : "border-border bg-card hover:border-primary/50",
        !mentor.available && "cursor-not-allowed opacity-60",
      )}
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
        >
          {initials || "?"}
        </span>
        <div>
          <p className="text-sm font-medium">{mentor.full_name}</p>
          <p className="text-xs text-muted-foreground">{mentor.email}</p>
        </div>
      </div>
      <div className="text-right">
        <p
          className={cn(
            "text-xs font-medium",
            mentor.available ? "text-stage-active" : "text-destructive",
          )}
        >
          {mentor.active_mentees} / {mentor.threshold} mentees
        </p>
        {!mentor.available && (
          <p className="mt-0.5 text-[10px] uppercase tracking-wide text-destructive">
            Full
          </p>
        )}
      </div>
    </button>
  );
}
