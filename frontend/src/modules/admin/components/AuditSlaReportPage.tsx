import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, ClipboardList, ShieldAlert } from "lucide-react";

import * as api from "@/modules/admin/api";
import type { AuditEntry, SlaBreach } from "@/modules/admin/types";
import {
  Card,
  EmptyState,
  Skeleton,
  Tab,
  Tabs,
} from "@/shared/components/ui";

/**
 * S24 — Audit & SLA report.
 *
 * Two tabs: open SLA breaches (drilldown) and the most recent
 * audit-log entries from the last 168h.
 */
export function AuditSlaReportPage() {
  const [tab, setTab] = useState<"sla" | "audit">("sla");

  const sla = useQuery({
    queryKey: ["admin", "sla", "open"],
    queryFn: api.getOpenSlaBreaches,
    staleTime: 30_000,
    enabled: tab === "sla",
  });
  const audit = useQuery({
    queryKey: ["admin", "audit", "recent"],
    queryFn: api.getRecentAudit,
    staleTime: 30_000,
    enabled: tab === "audit",
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            to="/admin"
            className="inline-flex items-center gap-1 rounded text-xs font-medium text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <ArrowLeft className="h-3 w-3" aria-hidden />
            Program overview
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            Audit & SLA
          </h1>
        </div>
        <Tabs aria-label="Audit and SLA views">
          <Tab active={tab === "sla"} onClick={() => setTab("sla")}>
            Open SLA breaches
          </Tab>
          <Tab active={tab === "audit"} onClick={() => setTab("audit")}>
            Audit log
          </Tab>
        </Tabs>
      </header>

      {tab === "sla" ? (
        <SlaTable
          loading={sla.isLoading}
          error={sla.isError}
          rows={sla.data ?? []}
        />
      ) : (
        <AuditTable
          loading={audit.isLoading}
          error={audit.isError}
          rows={audit.data ?? []}
        />
      )}
    </div>
  );
}

function TableSkeleton() {
  return (
    <Card className="overflow-hidden">
      <div className="space-y-2 p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    </Card>
  );
}

function SlaTable({
  loading,
  error,
  rows,
}: {
  loading: boolean;
  error: boolean;
  rows: SlaBreach[];
}) {
  if (loading) return <TableSkeleton />;
  if (error)
    return (
      <Card>
        <p className="p-10 text-center text-sm text-destructive">
          Could not load SLA breaches.
        </p>
      </Card>
    );
  if (rows.length === 0)
    return (
      <EmptyState
        icon={<CheckCircle2 className="h-5 w-5" aria-hidden />}
        title="No open SLA breaches"
        description="Nice. Everything is on track."
      />
    );

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-secondary/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <Th>Task</Th>
              <Th>Status</Th>
              <Th>Deadline</Th>
              <Th className="text-right">Hours overdue</Th>
              <Th>Intern / Referral</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {rows.map((r) => (
              <tr key={r.id} className="transition-colors hover:bg-muted/40">
                <Td className="font-medium">{r.task_type.replace(/_/g, " ")}</Td>
                <Td>{r.status}</Td>
                <Td className="text-muted-foreground">
                  {new Date(r.sla_deadline).toLocaleString()}
                </Td>
                <Td className="text-right font-mono font-semibold tabular-nums text-destructive">
                  {r.hours_overdue.toFixed(1)}h
                </Td>
                <Td className="font-mono text-xs text-muted-foreground">
                  {r.intern_id?.slice(0, 8) ?? "—"} /{" "}
                  {r.referral_id?.slice(0, 8) ?? "—"}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function AuditTable({
  loading,
  error,
  rows,
}: {
  loading: boolean;
  error: boolean;
  rows: AuditEntry[];
}) {
  const sorted = useMemo(
    () =>
      [...rows].sort(
        (a, b) =>
          new Date(b.event_timestamp).getTime() -
          new Date(a.event_timestamp).getTime(),
      ),
    [rows],
  );

  if (loading) return <TableSkeleton />;
  if (error)
    return (
      <Card>
        <p className="p-10 text-center text-sm text-destructive">
          Could not load audit log.
        </p>
      </Card>
    );
  if (sorted.length === 0)
    return (
      <EmptyState
        icon={<ClipboardList className="h-5 w-5" aria-hidden />}
        title="No audit events in the last 168h"
      />
    );

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-secondary/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <Th>When</Th>
              <Th>Event</Th>
              <Th>Entity</Th>
              <Th>Actor</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {sorted.map((r, i) => (
              <tr key={i} className="transition-colors hover:bg-muted/40">
                <Td className="whitespace-nowrap text-xs text-muted-foreground">
                  {new Date(r.event_timestamp).toLocaleString()}
                </Td>
                <Td className="font-medium">
                  <span className="inline-flex items-center gap-1.5">
                    <ShieldAlert
                      className="h-3 w-3 text-muted-foreground"
                      aria-hidden
                    />
                    {r.event_type}
                  </span>
                </Td>
                <Td className="font-mono text-xs text-muted-foreground">
                  {r.entity_type} {r.entity_id.slice(0, 8)}
                </Td>
                <Td className="text-xs">
                  {r.actor_role ?? "—"}
                  {r.actor_user_id && (
                    <span className="ml-1 font-mono text-muted-foreground">
                      ({r.actor_user_id.slice(0, 8)})
                    </span>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th className={`px-4 py-2.5 text-left font-medium ${className ?? ""}`}>
      {children}
    </th>
  );
}

function Td({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={`px-4 py-2.5 ${className ?? ""}`}>{children}</td>
  );
}
