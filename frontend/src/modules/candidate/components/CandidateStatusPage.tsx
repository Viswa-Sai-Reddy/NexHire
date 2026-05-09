import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Award,
  Calendar,
  CheckCircle2,
  Loader2,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/app/providers/AuthProvider";
import {
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

const TERMINAL_STATUSES = new Set(["CLOSED", "TERMINATED"]);

/**
 * Candidate-facing status portal.
 */
export function CandidateStatusPage() {
  const { state } = useAuth();
  const isAuthed = state.status === "authenticated";

  if (!isAuthed) {
    return <GenericLanding />;
  }

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
  const isTerminal = TERMINAL_STATUSES.has(data.status);
  const canTerminate = !isTerminal;

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
