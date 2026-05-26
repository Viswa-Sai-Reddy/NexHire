import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Award,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  KeyRound,
  Loader2,
  Play,
  ScrollText,
  XCircle,
} from "lucide-react";

import {
  type CandidateIntern,
  getCertificateUrl,
  getMyIntern,
  terminateMyIntern,
} from "@/modules/candidate/api";
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
} from "@/shared/components/ui";
import { cn } from "@/lib/utils";

const TERMINATABLE_STATUSES = new Set(["ACTIVE", "EXTENDED"]);

/**
 * Candidate-facing status portal.
 *
 * The AuthProvider only tracks employee SSO sessions; candidate JWTs are
 * set directly on the axios client by candidateLogin()/redeemMagicLink().
 * Render AuthedStatus unconditionally and let the API call decide —
 * unauthenticated requests 401, and the error branch falls back to the
 * generic landing.
 */
export function CandidateStatusPage() {
  return <AuthedStatus />;
}

function GenericLanding() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <Card>
        <CardContent className="p-8">
          <h1 className="text-2xl font-semibold tracking-tight">
            Your application is in progress
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            We're processing the next stage of your onboarding. We'll send you
            an email when there's something for you to do — please keep an eye
            on your inbox.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function AuthedStatus() {
  const qc = useQueryClient();
  const [showTerminate, setShowTerminate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const intern = useQuery({
    queryKey: ["candidate", "intern"],
    queryFn: getMyIntern,
    staleTime: 30_000,
  });

  const termination = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      terminateMyIntern(id, reason),
    onSuccess: () => {
      setShowTerminate(false);
      void qc.invalidateQueries({ queryKey: ["candidate", "intern"] });
    },
    onError: (err) => setError(formatActionError(err)),
  });

  const certificate = useMutation({
    mutationFn: () => getCertificateUrl(),
    onSuccess: (data) => {
      window.open(data.url, "_blank", "noopener,noreferrer");
    },
    onError: (err) => setError(formatActionError(err)),
  });

  if (intern.isLoading) {
    return (
      <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-12 text-sm text-muted-foreground sm:px-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading your status…
      </div>
    );
  }

  if (intern.isError || !intern.data) {
    return <GenericLanding />;
  }

  const data = intern.data;
  const stage = stageInfoFor(data);
  const canTerminate = TERMINATABLE_STATUSES.has(data.status);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <Card>
        <CardContent className="p-8">
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                {data.candidate_name}
              </h1>
              {data.project_title && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {data.project_title}
                </p>
              )}
            </div>
            <StatusPill status={data.status} />
          </header>

          <StageBanner stage={stage} />

          <StageProgress currentIndex={stage.index} />

          {data.non_worker_id && (
            <div className="mt-6 rounded-md border border-border/60 bg-muted/40 p-4">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Non-Worker ID
              </div>
              <div className="mt-1 font-mono text-lg font-semibold tracking-tight text-foreground">
                {data.non_worker_id}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Use this ID for badge collection and any HR correspondence.
              </p>
            </div>
          )}

          <dl className="mt-6 grid gap-4 sm:grid-cols-2">
            <Field
              icon={<Calendar className="h-3 w-3" aria-hidden />}
              label="Planned start"
              value={data.internship_start_date ?? "—"}
            />
            <Field
              icon={<Calendar className="h-3 w-3" aria-hidden />}
              label="Planned end"
              value={data.internship_end_date ?? "—"}
            />
            <Field
              icon={<Calendar className="h-3 w-3" aria-hidden />}
              label="Actual start"
              value={data.actual_start_date ?? "Not yet started"}
            />
            <Field
              icon={<Calendar className="h-3 w-3" aria-hidden />}
              label="Actual end"
              value={data.actual_end_date ?? "—"}
            />
          </dl>

          {error && (
            <p
              role="alert"
              className="mt-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {error}
            </p>
          )}

          {data.status === "CLOSED" && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-stage-active/30 bg-stage-active/10 p-4">
              <p className="flex items-center gap-2 text-sm text-stage-active">
                <Award className="h-4 w-4" aria-hidden />
                Your internship is complete. Download your participation
                certificate below.
              </p>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  setError(null);
                  certificate.mutate();
                }}
                disabled={certificate.isPending}
              >
                {certificate.isPending ? "Opening…" : "Download certificate"}
              </Button>
            </div>
          )}

          {canTerminate && !showTerminate && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4">
              <p className="text-xs text-muted-foreground">
                Need to end your internship early? A 6-month cooling period
                will apply before you can be re-referred.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setError(null);
                  setShowTerminate(true);
                }}
                className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              >
                End my internship
              </Button>
            </div>
          )}

          {showTerminate && (
            <TerminationDialog
              candidateName={data.candidate_name}
              busy={termination.isPending}
              error={error}
              onCancel={() => setShowTerminate(false)}
              onConfirm={(reason) =>
                termination.mutate({ id: data.intern_id, reason })
              }
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Stage messaging + progress

interface StageInfo {
  index: number; // 0..4, matches STAGES ordering
  headline: string;
  detail: string;
  countdown: string | null;
}

function stageInfoFor(data: CandidateIntern): StageInfo {
  const today = startOfToday();
  const plannedStart = parseDate(data.internship_start_date);
  const effectiveEnd =
    parseDate(data.actual_end_date) ?? parseDate(data.internship_end_date);

  switch (data.status) {
    case "PENDING": {
      const daysToStart = plannedStart ? daysBetween(today, plannedStart) : null;
      return {
        index: 1,
        headline: "Waiting on access setup",
        detail:
          "Your AD account and badge are being arranged by IT and Admin. Once both are ready, your mentor will confirm your start date.",
        countdown:
          daysToStart !== null && daysToStart > 0
            ? `Planned start in ${daysToStart} day${daysToStart === 1 ? "" : "s"}`
            : null,
      };
    }
    case "ACCESS_PENDING": {
      const daysToStart = plannedStart ? daysBetween(today, plannedStart) : null;
      return {
        index: 1,
        headline: "Access being provisioned",
        detail:
          "IT is creating your account and Admin is configuring your badge. You'll get a separate email with login credentials before your start date.",
        countdown:
          daysToStart !== null && daysToStart > 0
            ? `Starts in ${daysToStart} day${daysToStart === 1 ? "" : "s"}`
            : daysToStart === 0
              ? "Starting today"
              : null,
      };
    }
    case "ACTIVE":
    case "EXTENDED": {
      const daysLeft = effectiveEnd ? daysBetween(today, effectiveEnd) : null;
      return {
        index: 2,
        headline:
          data.status === "EXTENDED"
            ? "Internship extended and ongoing"
            : "Your internship is underway",
        detail:
          data.status === "EXTENDED"
            ? "Your mentor extended your internship. Keep up the good work — the end date below has been updated."
            : "Welcome aboard! Check in with your mentor regularly. We'll prompt them to confirm your completion as your end date approaches.",
        countdown:
          daysLeft === null
            ? null
            : daysLeft > 1
              ? `${daysLeft} days remaining`
              : daysLeft === 1
                ? "1 day remaining"
                : daysLeft === 0
                  ? "Last day"
                  : `Ended ${-daysLeft} day${-daysLeft === 1 ? "" : "s"} ago`,
      };
    }
    case "CLOSURE_PENDING":
      return {
        index: 3,
        headline: "Mentor closure submitted",
        detail:
          "Your mentor has confirmed your completion and your certificate is being generated. Refresh in a moment — the download button will appear when it's ready.",
        countdown: null,
      };
    case "CLOSED":
      return {
        index: 4,
        headline: "Internship complete",
        detail:
          "Congratulations! You can download your participation certificate below. Keep your Non-Worker ID for your records.",
        countdown: null,
      };
    case "TERMINATED":
      return {
        index: -1,
        headline: "Internship ended early",
        detail:
          "This internship was terminated before completion. If you have questions, please contact HR. A cooling-off period applies before a fresh referral can be submitted.",
        countdown: null,
      };
    default:
      return {
        index: 0,
        headline: "Onboarding in progress",
        detail:
          "We're processing the next step of your onboarding. We'll email you when something needs your attention.",
        countdown: null,
      };
  }
}

function StageBanner({ stage }: { stage: StageInfo }) {
  return (
    <div className="mt-6 rounded-md border border-primary/20 bg-primary/5 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">
            {stage.headline}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {stage.detail}
          </p>
        </div>
        {stage.countdown && (
          <Badge variant="active" className="shrink-0 whitespace-nowrap">
            <Clock className="h-3 w-3" aria-hidden />
            {stage.countdown}
          </Badge>
        )}
      </div>
    </div>
  );
}

const STAGES: Array<{ label: string; icon: React.ReactNode }> = [
  { label: "Onboarded", icon: <ScrollText className="h-3.5 w-3.5" aria-hidden /> },
  { label: "Access", icon: <KeyRound className="h-3.5 w-3.5" aria-hidden /> },
  { label: "Internship", icon: <Play className="h-3.5 w-3.5" aria-hidden /> },
  { label: "Closure", icon: <ScrollText className="h-3.5 w-3.5" aria-hidden /> },
  { label: "Certificate", icon: <Award className="h-3.5 w-3.5" aria-hidden /> },
];

function StageProgress({ currentIndex }: { currentIndex: number }) {
  // Hidden for terminated interns (index = -1) — the journey doesn't apply.
  if (currentIndex < 0) return null;

  return (
    <ol
      className="mt-4 flex items-center gap-1.5"
      aria-label="Internship progress"
    >
      {STAGES.map((step, i) => {
        const done = i < currentIndex;
        const current = i === currentIndex;
        const upcoming = i > currentIndex;
        return (
          <li
            key={step.label}
            className={cn(
              "flex flex-1 items-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium",
              done && "bg-stage-active/15 text-stage-active",
              current && "bg-primary/15 text-primary ring-1 ring-primary/30",
              upcoming && "bg-muted text-muted-foreground",
            )}
            aria-current={current ? "step" : undefined}
          >
            <span className="flex h-4 w-4 shrink-0 items-center justify-center">
              {done ? (
                <Check className="h-3.5 w-3.5" aria-hidden />
              ) : (
                step.icon
              )}
            </span>
            <span className="truncate">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Date helpers

function parseDate(iso: string | null): Date | null {
  if (!iso) return null;
  // Treat backend YYYY-MM-DD strings as local midnight to avoid TZ drift.
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function startOfToday(): Date {
  const t = new Date();
  return new Date(t.getFullYear(), t.getMonth(), t.getDate());
}

function daysBetween(from: Date, to: Date): number {
  const ms = to.getTime() - from.getTime();
  return Math.round(ms / 86_400_000);
}

// ─────────────────────────────────────────────────────────────────────

function Field({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div>
      <dt className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    PENDING: "submitted",
    ACCESS_PENDING: "review",
    ACTIVE: "active",
    EXTENDED: "extended",
    CLOSURE_PENDING: "submitted",
    CLOSED: "muted",
    TERMINATED: "rejected",
  };
  return (
    <Badge variant={variantMap[status] ?? "muted"}>
      {status === "CLOSED" && (
        <CheckCircle2 className="h-3 w-3" aria-hidden />
      )}
      {status.replace(/_/g, " ")}
    </Badge>
  );
}
