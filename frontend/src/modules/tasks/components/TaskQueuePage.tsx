import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCheck, Clock, Sparkles } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import { useAuth } from "@/app/providers/AuthProvider";
import * as api from "@/modules/tasks/api";
import type { TaskQueueEntry } from "@/modules/tasks/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  Input,
  Skeleton,
} from "@/shared/components/ui";

/**
 * S21/S22 — IT and Admin task queue.
 */
export function TaskQueuePage() {
  const { state } = useAuth();
  const role = state.status === "authenticated" ? state.user.role : null;

  const tasks = useQuery({
    queryKey: ["tasks", "mine"],
    queryFn: api.getMyTasks,
    staleTime: 15_000,
  });

  if (tasks.isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-3 px-4 py-8 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-72" />
        <Skeleton className="mt-4 h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (tasks.isError || !tasks.data) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Could not load tasks.
        </p>
      </div>
    );
  }

  const items = tasks.data.items;
  const heading =
    role === "IT_AD" ? "AD provisioning queue" : "Operations queue";
  const subtitle =
    role === "IT_AD"
      ? "Create AD accounts before the start date."
      : "Configure badge access before the start date.";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">{heading}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      {items.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck className="h-5 w-5" aria-hidden />}
          title="You're all caught up"
          description="No open tasks in your queue."
        />
      ) : (
        <ul className="space-y-3">
          {items.map((row) => (
            <TaskRow key={row.id} row={row} />
          ))}
        </ul>
      )}
    </div>
  );
}

function TaskRow({ row }: { row: TaskQueueEntry }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [badgeRef, setBadgeRef] = useState("");

  const onError = (err: unknown) =>
    setError(err instanceof NexHireApiError ? err.message : "Action failed.");
  const onSuccess = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["tasks", "mine"] });
  };

  const adComplete = useMutation({
    mutationFn: (internId: string) => api.completeAdProvisioning(internId),
    onSuccess,
    onError,
  });
  const badgeComplete = useMutation({
    mutationFn: (args: { internId: string; reference: string }) =>
      api.completeBadgeAccess(args.internId, args.reference),
    onSuccess,
    onError,
  });

  const overdue = new Date(row.sla_deadline).getTime() < Date.now();
  const isAdProvision = row.task_type === "AD_PROVISION";
  const isBadgeAccess = row.task_type === "BADGE_ACCESS";

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold tracking-tight">
              {row.task_type.replace(/_/g, " ")}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Intern{" "}
              <span className="font-mono">
                {row.intern_id?.slice(0, 8) ?? "—"}
              </span>{" "}
              · Referral{" "}
              <span className="font-mono">
                {row.referral_id?.slice(0, 8) ?? "—"}
              </span>
            </p>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" aria-hidden />
              SLA {new Date(row.sla_deadline).toLocaleString()}
              {overdue && (
                <Badge variant="danger" className="ml-2">
                  Overdue
                </Badge>
              )}
            </p>
            {row.ai_routing_reason && (
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-stage-review/30 bg-stage-review/10 px-2.5 py-1 text-xs text-stage-review">
                <Sparkles className="h-3 w-3 shrink-0" aria-hidden />
                AI: {row.ai_routing_reason}
              </p>
            )}
          </div>

          {row.intern_id && (
            <div className="min-w-[220px]">
              {isAdProvision && (
                <Button
                  type="button"
                  size="sm"
                  className="w-full"
                  onClick={() => {
                    setError(null);
                    adComplete.mutate(row.intern_id!);
                  }}
                  disabled={adComplete.isPending}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                  {adComplete.isPending
                    ? "Provisioning…"
                    : "Complete provisioning"}
                </Button>
              )}
              {isBadgeAccess && (
                <div className="space-y-2">
                  <Input
                    type="text"
                    value={badgeRef}
                    onChange={(e) => setBadgeRef(e.target.value)}
                    placeholder="Badge reference (≥2 chars)"
                    className="text-xs"
                  />
                  <Button
                    type="button"
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setError(null);
                      badgeComplete.mutate({
                        internId: row.intern_id!,
                        reference: badgeRef.trim(),
                      });
                    }}
                    disabled={
                      badgeComplete.isPending || badgeRef.trim().length < 2
                    }
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                    {badgeComplete.isPending ? "Saving…" : "Mark complete"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

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
