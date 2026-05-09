import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Inbox,
  Sparkles,
} from "lucide-react";

import * as api from "@/modules/hr/api";
import type { HrQueueEntry, RecentAiActionEntry } from "@/modules/hr/types";
import {
  Badge,
  type BadgeProps,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/shared/components/ui";

/**
 * S11 — HR Dashboard.
 *
 * Two cards side by side:
 *   * Pending HR Review queue (auto-approval engine routed these here).
 *   * Recent AI auto-actions (recall window still open).
 */
export function HrDashboardPage() {
  const queue = useQuery({
    queryKey: ["hr", "queue"],
    queryFn: api.getQueue,
    staleTime: 15_000,
  });
  const recent = useQuery({
    queryKey: ["hr", "recent-ai"],
    queryFn: api.getRecentAiActions,
    staleTime: 15_000,
  });

  const totalPending = queue.data?.total ?? 0;
  const recallWindowOpen =
    recent.data?.items.filter((i) => i.recall_active).length ?? 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            HR Dashboard
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Flagged referrals + recent AI auto-actions you can still recall.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/hr/interns">
            View all Non-Worker IDs
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Button>
      </header>

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KpiCard
          label="Pending HR review"
          value={String(totalPending)}
          icon={<Inbox className="h-4 w-4" aria-hidden />}
          tone="warning"
        />
        <KpiCard
          label="Auto-approvals (recallable)"
          value={String(recallWindowOpen)}
          icon={<CheckCircle2 className="h-4 w-4" aria-hidden />}
          tone="success"
        />
        <KpiCard
          label="AI coverage today"
          value="—"
          hint="(populated in S6)"
          icon={<Sparkles className="h-4 w-4" aria-hidden />}
          tone="muted"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
            <div className="space-y-1">
              <CardTitle>Pending HR Review</CardTitle>
              <CardDescription>
                AI flagged these referrals — open one to review.
              </CardDescription>
            </div>
            {queue.data && queue.data.items.length > 0 && (
              <Badge variant="muted">{queue.data.total}</Badge>
            )}
          </CardHeader>
          <CardContent>
            {queue.isLoading ? (
              <ul className="divide-y divide-border/60">
                {Array.from({ length: 3 }).map((_, i) => (
                  <li key={i} className="py-4">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="mt-2 h-3 w-1/2" />
                  </li>
                ))}
              </ul>
            ) : queue.data && queue.data.items.length > 0 ? (
              <ul className="divide-y divide-border/60">
                {queue.data.items.map((row) => (
                  <QueueRow key={row.id} row={row} />
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<CheckCircle2 className="h-5 w-5" aria-hidden />}
                title="All clear"
                description="AI auto-approved every recent referral."
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent AI Actions</CardTitle>
            <CardDescription>
              Recall window per action: AUTO_APPROVE 2h.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {recent.isLoading ? (
              <ul className="divide-y divide-border/60">
                {Array.from({ length: 3 }).map((_, i) => (
                  <li key={i} className="py-4">
                    <Skeleton className="h-3 w-2/3" />
                    <Skeleton className="mt-2 h-3 w-1/3" />
                  </li>
                ))}
              </ul>
            ) : recent.data && recent.data.items.length > 0 ? (
              <ul className="divide-y divide-border/60">
                {recent.data.items.map((row) => (
                  <RecentRow key={row.auto_action_id} row={row} />
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Sparkles className="h-5 w-5" aria-hidden />}
                title="No recent AI auto-actions"
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: React.ReactNode;
  tone: "success" | "warning" | "muted";
}) {
  const valueTone =
    tone === "warning"
      ? "text-stage-review"
      : tone === "success"
        ? "text-stage-active"
        : "text-foreground";
  return (
    <Card className="transition-colors hover:border-border">
      <div className="flex items-start justify-between p-5">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <p className={`text-3xl font-semibold tracking-tight ${valueTone}`}>
            {value}
          </p>
          {hint && (
            <p className="text-xs text-muted-foreground">{hint}</p>
          )}
        </div>
        <div
          className="flex h-9 w-9 items-center justify-center rounded-md bg-secondary text-muted-foreground"
          aria-hidden
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}

function recommendationVariant(
  rec: string | null,
): NonNullable<BadgeProps["variant"]> {
  if (rec === "LIKELY_REJECT") return "rejected";
  if (rec === "LIKELY_APPROVE") return "active";
  return "review";
}

function QueueRow({ row }: { row: HrQueueEntry }) {
  return (
    <li className="flex items-start justify-between gap-3 py-4 transition-colors hover:bg-muted/40 -mx-6 px-6">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-foreground">
          {row.candidate_name}
        </p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {row.candidate_email} · PAN {row.pan_masked}
        </p>
        {row.flags.length > 0 && (
          <ul className="mt-2 space-y-1">
            {row.flags.slice(0, 3).map((f, i) => (
              <li
                key={i}
                className="flex items-start gap-1.5 text-xs text-stage-review"
              >
                <AlertTriangle
                  className="mt-0.5 h-3 w-3 shrink-0"
                  aria-hidden
                />
                <span>{f}</span>
              </li>
            ))}
            {row.flags.length > 3 && (
              <li className="text-xs text-muted-foreground">
                +{row.flags.length - 3} more flag(s)
              </li>
            )}
          </ul>
        )}
      </div>
      <div className="flex flex-col items-end gap-2">
        {row.hr_recommendation && (
          <Badge variant={recommendationVariant(row.hr_recommendation)}>
            {row.hr_recommendation.replace(/_/g, " ")}
          </Badge>
        )}
        <Button asChild size="sm">
          <Link to={`/hr/referrals/${row.id}`}>
            Review
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Button>
      </div>
    </li>
  );
}

function RecentRow({ row }: { row: RecentAiActionEntry }) {
  return (
    <li className="py-4">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11px] text-secondary-foreground/80">
          {row.referral_id.slice(0, 8)}
        </span>
        <span className="text-xs text-muted-foreground">{row.action_type}</span>
      </div>
      <p className="mt-1.5 flex items-center gap-1 text-xs text-muted-foreground">
        <Clock className="h-3 w-3" aria-hidden />
        Executed {new Date(row.executed_at).toLocaleString()}
      </p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <Badge variant={row.recall_active ? "warning" : "muted"}>
          {row.recall_active
            ? `Recall until ${new Date(row.recall_window_ends_at).toLocaleTimeString()}`
            : "Recall window closed"}
        </Badge>
        {row.recall_active && (
          <Link
            to={`/hr/referrals/${row.referral_id}`}
            className="inline-flex items-center gap-0.5 rounded text-xs font-medium text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Open
            <ArrowRight className="h-3 w-3" aria-hidden />
          </Link>
        )}
      </div>
    </li>
  );
}
