import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import * as api from "@/modules/hr/api";
import type { HrQueueEntry, RecentAiActionEntry } from "@/modules/hr/types";

/**
 * S11 — HR Dashboard.
 *
 * Two cards side by side:
 *   * Pending HR Review queue (auto-approval engine routed these here).
 *   * Recent AI auto-actions (recall window still open).
 *
 * Mirrors the InternFlow reference: KPI strip up top + workspace
 * cards below.
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
    <div className="container py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">HR Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Flagged referrals + recent AI auto-actions you can still recall.
        </p>
      </header>

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <KpiCard
          label="Pending HR review"
          value={String(totalPending)}
          accent="warning"
        />
        <KpiCard
          label="Auto-approvals (recallable)"
          value={String(recallWindowOpen)}
          accent="ok"
        />
        <KpiCard
          label="AI coverage today"
          value="—"
          hint="(populated in S6)"
          accent="muted"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-xl border border-border bg-card p-6 shadow-sm lg:col-span-2">
          <h2 className="text-lg font-semibold">Pending HR Review</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            AI flagged these referrals — open one to review.
          </p>
          {queue.isLoading ? (
            <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
          ) : queue.data && queue.data.items.length > 0 ? (
            <ul className="mt-4 divide-y divide-border">
              {queue.data.items.map((row) => (
                <QueueRow key={row.id} row={row} />
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              All clear. AI auto-approved every recent referral.
            </p>
          )}
        </section>

        <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Recent AI Actions</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Recall window per action: AUTO_APPROVE 2h.
          </p>
          {recent.isLoading ? (
            <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
          ) : recent.data && recent.data.items.length > 0 ? (
            <ul className="mt-4 divide-y divide-border">
              {recent.data.items.map((row) => (
                <RecentRow key={row.auto_action_id} row={row} />
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              No recent AI auto-actions.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent: "ok" | "warning" | "muted";
}) {
  const accentClass =
    accent === "warning"
      ? "text-amber-700"
      : accent === "ok"
        ? "text-emerald-700"
        : "text-muted-foreground";
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className={`mt-2 text-3xl font-semibold ${accentClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function QueueRow({ row }: { row: HrQueueEntry }) {
  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div>
        <p className="text-sm font-medium">{row.candidate_name}</p>
        <p className="text-xs text-muted-foreground">
          {row.candidate_email} · PAN {row.pan_masked}
        </p>
        {row.flags.length > 0 && (
          <ul className="mt-1.5 space-y-0.5">
            {row.flags.slice(0, 3).map((f, i) => (
              <li key={i} className="text-xs text-amber-800">
                ⚠️ {f}
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
      <div className="flex flex-col items-end gap-1">
        {row.hr_recommendation && (
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
              row.hr_recommendation === "LIKELY_REJECT"
                ? "bg-destructive/10 text-destructive"
                : row.hr_recommendation === "LIKELY_APPROVE"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-amber-100 text-amber-800"
            }`}
          >
            {row.hr_recommendation.replace(/_/g, " ")}
          </span>
        )}
        <Link
          to={`/hr/referrals/${row.id}`}
          className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          Review →
        </Link>
      </div>
    </li>
  );
}

function RecentRow({ row }: { row: RecentAiActionEntry }) {
  return (
    <li className="py-3">
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono text-xs">
          {row.referral_id.slice(0, 8)}
        </span>
        <span className="text-xs text-muted-foreground">{row.action_type}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Executed {new Date(row.executed_at).toLocaleString()}
      </p>
      <div className="mt-2 flex items-center justify-between">
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
            row.recall_active
              ? "bg-amber-100 text-amber-800"
              : "bg-secondary text-muted-foreground"
          }`}
        >
          {row.recall_active
            ? `Recall until ${new Date(row.recall_window_ends_at).toLocaleTimeString()}`
            : "Recall window closed"}
        </span>
        {row.recall_active && (
          <Link
            to={`/hr/referrals/${row.referral_id}`}
            className="text-xs font-medium text-primary hover:underline"
          >
            Open →
          </Link>
        )}
      </div>
    </li>
  );
}
