import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Plus, XCircle } from "lucide-react";

import { listMyReferrals, terminateIntern } from "@/modules/referral/api";
import type { ReferralSummary } from "@/modules/referral/types";
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
  Skeleton,
} from "@/shared/components/ui";

const TERMINAL_INTERN_STATUSES = new Set(["CLOSED", "TERMINATED"]);

/**
 * Referrer's own list of submitted referrals with inline actions.
 */
export function MyReferralsPage() {
  const referrals = useQuery({
    queryKey: ["referrer", "referrals"],
    queryFn: listMyReferrals,
    staleTime: 30_000,
  });

  const location = useLocation();
  const navigate = useNavigate();
  const flashFromState =
    (location.state as { flash?: string } | null)?.flash ?? null;
  const [flash, setFlash] = useState<string | null>(flashFromState);
  useEffect(() => {
    if (!flashFromState) return;
    navigate(location.pathname, { replace: true, state: null });
    const t = window.setTimeout(() => setFlash(null), 6_000);
    return () => window.clearTimeout(t);
  }, [flashFromState, location.pathname, navigate]);

  if (referrals.isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-3 px-4 py-8 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-64" />
        <Skeleton className="mt-4 h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (referrals.isError || !referrals.data) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Could not load referrals. Please retry in a moment.
        </p>
      </div>
    );
  }

  const items = referrals.data;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            My referrals
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Submissions you've made, with their current stage and any actions
            still available to you.
          </p>
        </div>
        <Button asChild size="sm">
          <Link to="/referrals/new">
            <Plus className="h-3.5 w-3.5" aria-hidden />
            New referral
          </Link>
        </Button>
      </header>

      {flash !== null && (
        <div
          role="status"
          className="mb-6 flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-4 py-3 text-sm text-stage-active"
        >
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {flash}
        </div>
      )}

      {items.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" aria-hidden />}
          title="No referrals yet"
          description="You haven't submitted any referrals yet."
          action={
            <Button asChild size="sm">
              <Link to="/referrals/new">
                <Plus className="h-3.5 w-3.5" aria-hidden />
                Submit your first referral
              </Link>
            </Button>
          }
        />
      ) : (
        <ul className="space-y-4">
          {items.map((row) => (
            <ReferralRow key={row.id} row={row} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ReferralRow({ row }: { row: ReferralSummary }) {
  const qc = useQueryClient();
  const [showTerminate, setShowTerminate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const termination = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      terminateIntern(id, reason),
    onSuccess: () => {
      setShowTerminate(false);
      void qc.invalidateQueries({ queryKey: ["referrer", "referrals"] });
    },
    onError: (err) => setError(formatActionError(err)),
  });

  const internStatus = row.intern_status;
  const canTerminate =
    row.intern_id !== null &&
    row.intern_id !== undefined &&
    internStatus !== null &&
    internStatus !== undefined &&
    !TERMINAL_INTERN_STATUSES.has(internStatus);

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
            <p className="mt-1 text-xs text-muted-foreground">
              Submitted{" "}
              {row.submitted_at
                ? new Date(row.submitted_at).toLocaleString()
                : "—"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <ReferralStatusBadge status={row.status} />
            {internStatus && <InternStatusBadge status={internStatus} />}
          </div>
        </div>

        {error && (
          <p
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {error}
          </p>
        )}

        {canTerminate && (
          <div className="mt-4 flex justify-end">
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
              <XCircle className="h-3.5 w-3.5" aria-hidden />
              Terminate
            </Button>
          </div>
        )}

        {showTerminate && row.intern_id && (
          <TerminationDialog
            candidateName={row.candidate_name}
            busy={termination.isPending}
            error={error}
            onCancel={() => setShowTerminate(false)}
            onConfirm={(reason) =>
              termination.mutate({ id: row.intern_id!, reason })
            }
          />
        )}
      </CardContent>
    </Card>
  );
}

function ReferralStatusBadge({ status }: { status: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    SUBMITTED: "submitted",
    MENTOR_PENDING: "submitted",
    MENTOR_ACCEPTED: "onboarding",
    HR_REVIEW: "review",
    APPROVED: "active",
    JOINING_FORM_PENDING: "submitted",
    JOINING_FORM_SUBMITTED: "submitted",
    JOINING_FORM_LOCKED: "submitted",
    NDA_PENDING: "nda",
    NDA_SIGNED: "nda",
    HR_REJECTED: "rejected",
    CANDIDATE_REJECTED: "rejected",
    NDA_TIMEOUT_REJECTED: "rejected",
    NDA_DECLINED_REJECTED: "rejected",
  };
  return (
    <Badge variant={variantMap[status] ?? "muted"}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

function InternStatusBadge({ status }: { status: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
    PENDING: "muted",
    ACCESS_PENDING: "review",
    ACTIVE: "active",
    EXTENDED: "extended",
    CLOSURE_PENDING: "submitted",
    CLOSED: "closure",
    TERMINATED: "rejected",
  };
  return (
    <Badge variant={variantMap[status] ?? "muted"}>
      intern: {status.replace(/_/g, " ")}
    </Badge>
  );
}
