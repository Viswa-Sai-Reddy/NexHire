import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
  Inbox,
  PauseCircle,
  Play,
  XCircle,
} from "lucide-react";

import {
  getMySkills,
  getOutOfOffice,
  setMySkills,
  setOutOfOffice,
} from "@/modules/auth/api";
import * as api from "@/modules/mentor/api";
import type {
  CompletionRequest,
  MentorInternEntry,
} from "@/modules/mentor/types";
import {
  TerminationDialog,
  formatActionError,
} from "@/shared/components/TerminationDialog";
import {
  Badge,
  type BadgeProps,
  Button,
  Card,
  CardContent,
  EmptyState,
  Input,
  Skeleton,
  Textarea,
} from "@/shared/components/ui";
import { cn } from "@/lib/utils";

/**
 * S18/S19/S20 — Mentor workspace.
 */
export function MentorWorkspacePage() {
  const interns = useQuery({
    queryKey: ["mentor", "interns"],
    queryFn: api.getMyInterns,
    staleTime: 30_000,
  });

  if (interns.isLoading) {
    return (
      <div className="mx-auto max-w-7xl space-y-4 px-4 py-8 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (interns.isError || !interns.data) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Could not load interns. Please retry in a moment.
        </p>
      </div>
    );
  }

  return <WorkspaceBody items={interns.data.items} />;
}

type Tab = "pending" | "in_progress" | "completed";

const TERMINAL_STATUSES = new Set([
  "CLOSED",
  "TERMINATED",
  "HR_REJECTED",
  "CANDIDATE_REJECTED",
  "NDA_TIMEOUT_REJECTED",
  "NDA_DECLINED_REJECTED",
]);

function categorize(row: MentorInternEntry): Tab {
  if (TERMINAL_STATUSES.has(row.referral_status)) return "completed";
  if (row.referral_status === "MENTOR_PENDING") return "pending";
  return "in_progress";
}

function WorkspaceBody({ items }: { items: MentorInternEntry[] }) {
  const buckets = useMemo(() => {
    const out: Record<Tab, MentorInternEntry[]> = {
      pending: [],
      in_progress: [],
      completed: [],
    };
    for (const row of items) out[categorize(row)].push(row);
    return out;
  }, [items]);

  const defaultTab: Tab =
    buckets.pending.length > 0
      ? "pending"
      : buckets.in_progress.length > 0
        ? "in_progress"
        : "completed";
  const [tab, setTab] = useState<Tab>(defaultTab);

  const visible = buckets[tab];

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">My interns</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Respond to new assignments, manage active interns, or look up past
          ones.
        </p>
      </header>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <OutOfOfficePanel />
        <SkillsPanel />
      </div>

      <div
        role="tablist"
        aria-label="Intern tabs"
        className="mb-6 flex gap-1 rounded-md border border-border bg-card p-1 shadow-sm"
      >
        <WorkspaceTabButton
          icon={<Inbox className="h-3.5 w-3.5" aria-hidden />}
          label="Action needed"
          count={buckets.pending.length}
          active={tab === "pending"}
          onClick={() => setTab("pending")}
        />
        <WorkspaceTabButton
          icon={<Play className="h-3.5 w-3.5" aria-hidden />}
          label="In progress"
          count={buckets.in_progress.length}
          active={tab === "in_progress"}
          onClick={() => setTab("in_progress")}
        />
        <WorkspaceTabButton
          icon={<ClipboardCheck className="h-3.5 w-3.5" aria-hidden />}
          label="Completed"
          count={buckets.completed.length}
          active={tab === "completed"}
          onClick={() => setTab("completed")}
        />
      </div>

      {visible.length === 0 ? (
        <TabEmpty tab={tab} />
      ) : (
        <ul className="space-y-4">
          {visible.map((row) => (
            <InternRow key={row.referral_id} row={row} />
          ))}
        </ul>
      )}
    </div>
  );
}

function WorkspaceTabButton({
  icon,
  label,
  count,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex flex-1 items-center justify-center gap-2 rounded px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground",
      )}
    >
      {icon}
      {label}
      <span
        className={cn(
          "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
          active
            ? "bg-primary-foreground/20 text-primary-foreground"
            : "bg-secondary text-muted-foreground",
        )}
      >
        {count}
      </span>
    </button>
  );
}

function TabEmpty({ tab }: { tab: Tab }) {
  const message =
    tab === "pending"
      ? "New referrals where you're the selected mentor will show up here."
      : tab === "in_progress"
        ? "No active interns yet. Accepted assignments appear as they progress through HR approval, joining form, NDA, and access provisioning."
        : "No completed or rejected referrals yet.";
  const title =
    tab === "pending"
      ? "No pending assignments"
      : tab === "in_progress"
        ? "No active interns"
        : "Nothing here yet";
  const icon =
    tab === "pending" ? (
      <Inbox className="h-5 w-5" aria-hidden />
    ) : tab === "in_progress" ? (
      <Play className="h-5 w-5" aria-hidden />
    ) : (
      <ClipboardCheck className="h-5 w-5" aria-hidden />
    );
  return <EmptyState icon={icon} title={title} description={message} />;
}

function InternRow({ row }: { row: MentorInternEntry }) {
  const qc = useQueryClient();
  const [activeAction, setActiveAction] = useState<
    "extend" | "closure" | "terminate" | "reject" | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  const internId = row.intern_id;

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["mentor", "interns"] });

  const confirmStart = useMutation({
    mutationFn: () => api.confirmStart({ intern_id: internId! }),
    onSuccess: invalidate,
    onError: (err) => setError(formatActionError(err)),
  });
  const extension = useMutation({
    mutationFn: (body: { new_end_date: string; reason: string }) =>
      api.requestExtension({ intern_id: internId!, ...body }),
    onSuccess: () => {
      setActiveAction(null);
      void invalidate();
    },
    onError: (err) => setError(formatActionError(err)),
  });
  const completion = useMutation({
    mutationFn: (body: Omit<CompletionRequest, "intern_id">) =>
      api.confirmCompletion({ intern_id: internId!, ...body }),
    onSuccess: () => {
      setActiveAction(null);
      void invalidate();
    },
    onError: (err) => setError(formatActionError(err)),
  });
  const termination = useMutation({
    mutationFn: (reason: string) =>
      api.terminateIntern({ intern_id: internId!, reason }),
    onSuccess: () => {
      setActiveAction(null);
      void invalidate();
    },
    onError: (err) => setError(formatActionError(err)),
  });

  const acceptAssignment = useMutation({
    mutationFn: () =>
      api.respondToAssignment({
        referral_id: row.referral_id,
        action: "ACCEPT",
      }),
    onSuccess: invalidate,
    onError: (err) => {
      setError(formatActionError(err));
      void invalidate();
    },
  });

  const viewResume = useMutation({
    mutationFn: () => api.getResumeUrl(row.referral_id),
    onSuccess: (data) => {
      window.open(data.url, "_blank", "noopener,noreferrer");
    },
    onError: (err) => setError(formatActionError(err)),
  });
  const rejectAssignment = useMutation({
    mutationFn: (reason: string) =>
      api.respondToAssignment({
        referral_id: row.referral_id,
        action: "REJECT",
        reason,
      }),
    onSuccess: () => {
      setActiveAction(null);
      void invalidate();
    },
    onError: (err) => {
      setError(formatActionError(err));
      void invalidate();
    },
  });

  const status = row.intern_status;
  const isTerminal =
    status === "CLOSED" ||
    status === "TERMINATED" ||
    TERMINAL_STATUSES.has(row.referral_status);
  const canConfirmStart = internId !== null && status === "ACCESS_PENDING";
  const canManageActive =
    internId !== null && (status === "ACTIVE" || status === "EXTENDED");
  const canRespondToAssignment = row.referral_status === "MENTOR_PENDING";
  const canMarkComplete =
    internId !== null && !isTerminal && !canRespondToAssignment;

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold tracking-tight">
              {row.candidate_name}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {row.candidate_email}
              {row.project_title ? ` · ${row.project_title}` : ""}
            </p>
            <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              <Calendar className="h-3 w-3" aria-hidden />
              Planned{" "}
              {row.internship_start_date && row.internship_end_date
                ? `${row.internship_start_date} → ${row.internship_end_date}`
                : "—"}
              {row.actual_end_date &&
              row.actual_end_date !== row.internship_end_date
                ? ` (extended to ${row.actual_end_date})`
                : ""}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusPill status={status ?? row.referral_status} />
            {row.risk_score !== null && (
              <RiskScoreBadge score={row.risk_score} />
            )}
          </div>
        </div>

        {row.red_flags.length > 0 && (
          <div className="mt-3 rounded-md border border-stage-review/30 bg-stage-review/10 px-3 py-2 text-xs text-stage-review">
            <p className="flex items-center gap-1.5 font-medium">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
              AI flagged:
            </p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {row.red_flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>
        )}

        {internId === null && !canRespondToAssignment && (
          <p className="mt-3 rounded-md bg-secondary/50 px-3 py-2 text-xs text-muted-foreground">
            You've accepted this referral. It's awaiting HR approval — actions
            will appear here once provisioning starts.
          </p>
        )}

        {canRespondToAssignment && activeAction === null && (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setError(null);
                acceptAssignment.mutate();
              }}
              disabled={acceptAssignment.isPending}
            >
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
              {acceptAssignment.isPending ? "Accepting…" : "Accept assignment"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setError(null);
                setActiveAction("reject");
              }}
              className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <XCircle className="h-3.5 w-3.5" aria-hidden />
              Reject assignment
            </Button>
            {row.has_resume && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setError(null);
                  viewResume.mutate();
                }}
                disabled={viewResume.isPending}
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                {viewResume.isPending ? "Opening…" : "View resume"}
              </Button>
            )}
          </div>
        )}

        {activeAction === "reject" && (
          <RejectReasonPanel
            candidateName={row.candidate_name}
            busy={rejectAssignment.isPending}
            onCancel={() => setActiveAction(null)}
            onSubmit={(reason) => rejectAssignment.mutate(reason)}
          />
        )}

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}

        {!isTerminal &&
          activeAction === null &&
          internId !== null &&
          !canRespondToAssignment && (
            <div className="mt-4 flex flex-wrap gap-2">
              {canConfirmStart && (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => {
                    setError(null);
                    confirmStart.mutate();
                  }}
                  disabled={confirmStart.isPending}
                >
                  <Play className="h-3.5 w-3.5" aria-hidden />
                  {confirmStart.isPending ? "Confirming…" : "Confirm start"}
                </Button>
              )}
              {canManageActive && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setError(null);
                    setActiveAction("extend");
                  }}
                  disabled={row.extension_count >= 2}
                  title={
                    row.extension_count >= 2
                      ? "Extension cap reached (max 2)"
                      : undefined
                  }
                >
                  Request extension ({row.extension_count}/2)
                </Button>
              )}
              {canMarkComplete && (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => {
                    setError(null);
                    setActiveAction("closure");
                  }}
                >
                  <ClipboardCheck className="h-3.5 w-3.5" aria-hidden />
                  Mark as completed
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setError(null);
                  setActiveAction("terminate");
                }}
                className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              >
                <XCircle className="h-3.5 w-3.5" aria-hidden />
                Terminate
              </Button>
            </div>
          )}

        {activeAction === "extend" && (
          <ExtensionPanel
            plannedEnd={row.actual_end_date ?? row.internship_end_date}
            busy={extension.isPending}
            onCancel={() => setActiveAction(null)}
            onSubmit={(body) => extension.mutate(body)}
          />
        )}
        {activeAction === "closure" && (
          <ClosurePanel
            busy={completion.isPending}
            onCancel={() => setActiveAction(null)}
            onSubmit={(body) => completion.mutate(body)}
          />
        )}
        {activeAction === "terminate" && (
          <TerminationDialog
            candidateName={row.candidate_name}
            busy={termination.isPending}
            error={error}
            onCancel={() => setActiveAction(null)}
            onConfirm={(reason) => termination.mutate(reason)}
          />
        )}
      </CardContent>
    </Card>
  );
}

function RiskScoreBadge({ score }: { score: number }) {
  const variant: BadgeProps["variant"] =
    score >= 60 ? "rejected" : score >= 25 ? "review" : "active";
  const label =
    score >= 60 ? "High risk" : score >= 25 ? "Medium risk" : "Low risk";
  return (
    <Badge variant={variant} title={`AI-3 risk score: ${score}/100`}>
      {label} · {score}
    </Badge>
  );
}

function RejectReasonPanel({
  candidateName,
  busy,
  onCancel,
  onSubmit,
}: {
  candidateName: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const valid = reason.trim().length >= 10;
  return (
    <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-4">
      <p className="text-sm font-medium">
        Reject mentoring assignment for {candidateName}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Min 10 characters. The referrer will see your reason. Up to 3 mentors
        may be tried before the candidate is auto-rejected.
      </p>
      <Textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={3}
        maxLength={2000}
        placeholder="Briefly explain why you're declining…"
        className="mt-3"
      />
      <div className="mt-3 flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          onClick={() => valid && onSubmit(reason.trim())}
          disabled={busy || !valid}
        >
          {busy ? "Rejecting…" : "Confirm reject"}
        </Button>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    SUBMITTED: "submitted",
    MENTOR_PENDING: "submitted",
    MENTOR_ACCEPTED: "onboarding",
    HR_REVIEW: "review",
    APPROVED: "active",
    JOINING_FORM_PENDING: "submitted",
    JOINING_FORM_SUBMITTED: "submitted",
    JOINING_FORM_LOCKED: "submitted",
    ID_PENDING: "nda",
    ID_ISSUED: "nda",
    NDA_PENDING: "nda",
    NDA_SIGNED: "nda",
    PENDING: "muted",
    ACCESS_PENDING: "review",
    ACTIVE: "active",
    EXTENDED: "extended",
    CLOSURE_PENDING: "submitted",
    CLOSED: "muted",
    TERMINATED: "rejected",
  };
  return (
    <Badge variant={variantMap[status] ?? "muted"}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

function ExtensionPanel({
  plannedEnd,
  busy,
  onCancel,
  onSubmit,
}: {
  plannedEnd: string | null;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: { new_end_date: string; reason: string }) => void;
}) {
  const [newEnd, setNewEnd] = useState(plannedEnd ?? "");
  const [reason, setReason] = useState("");
  const reasonOk = reason.trim().length >= 10;
  const dateOk = newEnd.length > 0;

  return (
    <div className="mt-4 rounded-md border border-border bg-secondary/30 p-4">
      <h4 className="text-sm font-semibold">Request extension</h4>
      <p className="mt-1 text-xs text-muted-foreground">
        Max 2 extensions per intern · max 4 weeks each.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1.5 text-xs">
          <span className="block text-muted-foreground">New end date</span>
          <Input
            type="date"
            value={newEnd}
            onChange={(e) => setNewEnd(e.target.value)}
          />
        </label>
      </div>
      <label className="mt-3 block space-y-1.5 text-xs">
        <span className="block text-muted-foreground">
          Reason (≥ 10 characters)
        </span>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
        />
      </label>
      <div className="mt-3 flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() =>
            onSubmit({ new_end_date: newEnd, reason: reason.trim() })
          }
          disabled={busy || !reasonOk || !dateOk}
        >
          {busy ? "Submitting…" : "Submit extension"}
        </Button>
      </div>
    </div>
  );
}

function ClosurePanel({
  busy,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Omit<CompletionRequest, "intern_id">) => void;
}) {
  const [summary, setSummary] = useState("");
  const [skillsCsv, setSkillsCsv] = useState("");
  const [strength, setStrength] = useState<1 | 2 | 3 | 4 | 5>(4);
  const [contributions, setContributions] = useState("");

  const summaryOk =
    summary.trim().length >= 10 && summary.trim().length <= 200;

  return (
    <div className="mt-4 rounded-md border border-border bg-secondary/30 p-4">
      <h4 className="text-sm font-semibold">Closure feedback</h4>
      <p className="mt-1 text-xs text-muted-foreground">
        AI-8 may auto-generate a certificate citation from this — be specific.
      </p>

      <label className="mt-3 block space-y-1.5 text-xs">
        <span className="block text-muted-foreground">
          Project summary (10 – 200 chars)
        </span>
        <Textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={3}
        />
        <span className="mt-0.5 block text-[11px] text-muted-foreground">
          {summary.trim().length} / 200
        </span>
      </label>

      <label className="mt-3 block space-y-1.5 text-xs">
        <span className="block text-muted-foreground">
          Skills demonstrated (comma-separated)
        </span>
        <Input
          type="text"
          value={skillsCsv}
          onChange={(e) => setSkillsCsv(e.target.value)}
          placeholder="React, FastAPI, A/B testing"
        />
      </label>

      <label className="mt-3 block space-y-1.5 text-xs">
        <span className="block text-muted-foreground">
          Recommendation strength (1 – 5)
        </span>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setStrength(n as 1 | 2 | 3 | 4 | 5)}
              aria-label={`Rate ${n} out of 5`}
              aria-pressed={strength === n}
              className={cn(
                "h-9 w-9 rounded-md border text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                strength === n
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card hover:bg-secondary",
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </label>

      <label className="mt-3 block space-y-1.5 text-xs">
        <span className="block text-muted-foreground">
          Notable contributions (optional, ≤ 500 chars)
        </span>
        <Textarea
          value={contributions}
          onChange={(e) => setContributions(e.target.value)}
          rows={2}
          maxLength={500}
        />
      </label>

      <div className="mt-4 flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() =>
            onSubmit({
              project_summary: summary.trim(),
              skills_demonstrated: skillsCsv
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
              recommendation_strength: strength,
              notable_contributions: contributions.trim() || null,
            })
          }
          disabled={busy || !summaryOk}
        >
          {busy ? "Submitting…" : "Submit closure feedback"}
        </Button>
      </div>
    </div>
  );
}

function OutOfOfficePanel() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draftDate, setDraftDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const status = useQuery({
    queryKey: ["auth", "out-of-office"],
    queryFn: getOutOfOffice,
    staleTime: 60_000,
  });

  const mutate = useMutation({
    mutationFn: (until: string | null) => setOutOfOffice(until),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["auth", "out-of-office"] });
    },
    onError: (err) => setError(formatActionError(err)),
  });

  const current = status.data?.until ?? null;
  const currentLabel = current
    ? new Date(current).toLocaleString()
    : "Available";
  const isOoo = current !== null && new Date(current).getTime() > Date.now();

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-1.5 text-sm font-semibold">
              <PauseCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
              Availability
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Status:{" "}
              <span
                className={cn(
                  "font-medium",
                  isOoo ? "text-stage-review" : "text-stage-active",
                )}
              >
                {isOoo ? `Out of office until ${currentLabel}` : "Available"}
              </span>
              {" · "}AI auto-router skips you for new assignments while OOO.
            </p>
          </div>
          {!editing && (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setError(null);
                  setDraftDate(current ? current.slice(0, 16) : "");
                  setEditing(true);
                }}
              >
                {isOoo ? "Update OOO" : "Set out of office"}
              </Button>
              {isOoo && (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => mutate.mutate(null)}
                  disabled={mutate.isPending}
                >
                  {mutate.isPending ? "Clearing…" : "Mark available"}
                </Button>
              )}
            </div>
          )}
        </div>

        {editing && (
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="block space-y-1.5 text-xs">
              <span className="block text-muted-foreground">
                Out of office until
              </span>
              <Input
                type="datetime-local"
                value={draftDate}
                onChange={(e) => setDraftDate(e.target.value)}
                min={new Date(Date.now() + 60_000).toISOString().slice(0, 16)}
                className="w-64"
              />
            </label>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={!draftDate || mutate.isPending}
                onClick={() => mutate.mutate(new Date(draftDate).toISOString())}
              >
                {mutate.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function SkillsPanel() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const status = useQuery({
    queryKey: ["auth", "skills"],
    queryFn: getMySkills,
    staleTime: 60_000,
  });

  const mutate = useMutation({
    mutationFn: (skills: string[]) => setMySkills(skills),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["auth", "skills"] });
    },
    onError: (err) => setError(formatActionError(err)),
  });

  const skills = status.data?.skills ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Skills</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Feeds the AI-2 mentor matcher. Up to 50 entries · max 64 chars
              each · auto-lowercased and deduped.
            </p>
          </div>
          {!editing && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setError(null);
                setDraft(skills.join(", "));
                setEditing(true);
              }}
            >
              {skills.length === 0 ? "Add skills" : "Edit skills"}
            </Button>
          )}
        </div>

        {!editing && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {skills.length === 0 ? (
              <p className="text-xs italic text-muted-foreground">
                No skills set yet.
              </p>
            ) : (
              skills.map((s) => (
                <Badge key={s} variant="muted">
                  {s}
                </Badge>
              ))
            )}
          </div>
        )}

        {editing && (
          <div className="mt-3">
            <label className="block space-y-1.5 text-xs">
              <span className="block text-muted-foreground">
                Comma-separated list
              </span>
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
                placeholder="react, fastapi, postgres, kubernetes"
              />
            </label>
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={mutate.isPending}
                onClick={() =>
                  mutate.mutate(
                    draft
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  )
                }
              >
                {mutate.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
