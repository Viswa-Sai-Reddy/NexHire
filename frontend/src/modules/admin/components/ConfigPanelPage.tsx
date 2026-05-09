import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, History, Lock, XCircle } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import * as api from "@/modules/admin/api";
import type {
  ConfigHistoryEntry,
  CoolingPeriodEntry,
} from "@/modules/admin/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  Skeleton,
  Tab,
  Tabs,
} from "@/shared/components/ui";
import { cn } from "@/lib/utils";

/**
 * S25 — Program-Owner config panel.
 *
 * Three tabs: mentor threshold, cooling periods, and change history.
 */
export function ConfigPanelPage() {
  const [tab, setTab] = useState<"mentor" | "cooling" | "history">("mentor");

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
            Configuration
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Program-Owner only. Changes are audit-logged.
          </p>
        </div>
        <Tabs aria-label="Configuration sections">
          <Tab active={tab === "mentor"} onClick={() => setTab("mentor")}>
            Mentor threshold
          </Tab>
          <Tab active={tab === "cooling"} onClick={() => setTab("cooling")}>
            Cooling periods
          </Tab>
          <Tab active={tab === "history"} onClick={() => setTab("history")}>
            History
          </Tab>
        </Tabs>
      </header>

      {tab === "mentor" && <MentorThresholdTab />}
      {tab === "cooling" && <CoolingPeriodsTab />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}

function FeedbackBanner({
  feedback,
}: {
  feedback: { kind: "ok" | "err"; message: string };
}) {
  return (
    <p
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
        feedback.kind === "ok"
          ? "border-stage-active/30 bg-stage-active/10 text-stage-active"
          : "border-destructive/30 bg-destructive/10 text-destructive",
      )}
    >
      {feedback.kind === "ok" ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      )}
      <span>{feedback.message}</span>
    </p>
  );
}

function MentorThresholdTab() {
  const qc = useQueryClient();
  const current = useQuery({
    queryKey: ["admin", "config", "mentor-threshold"],
    queryFn: api.getMentorThreshold,
  });

  const [value, setValue] = useState<number>(0);
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState<{
    kind: "ok" | "err";
    message: string;
  } | null>(null);

  useEffect(() => {
    if (current.data) setValue(current.data.max_mentees);
  }, [current.data]);

  const save = useMutation({
    mutationFn: () => api.setMentorThreshold(value, reason.trim() || undefined),
    onSuccess: (r) => {
      setFeedback({
        kind: "ok",
        message: `Saved — new value ${r.max_mentees}.`,
      });
      void qc.invalidateQueries({ queryKey: ["admin", "config"] });
      setReason("");
    },
    onError: (err) => {
      setFeedback({
        kind: "err",
        message:
          err instanceof NexHireApiError ? err.message : "Could not save.",
      });
    },
  });

  const dirty = current.data ? value !== current.data.max_mentees : false;
  const valid = value >= 1 && value <= 10;

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Maximum active mentees</CardTitle>
        <CardDescription>
          Affects the mentor matcher's availability score and capacity gate.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {current.isLoading ? (
          <Skeleton className="h-9 w-32" />
        ) : current.isError ? (
          <p className="text-sm text-destructive">
            Could not load current value.
          </p>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <Input
                type="number"
                min={1}
                max={10}
                value={value}
                onChange={(e) => setValue(Number(e.target.value))}
                className="w-24"
              />
              <span className="text-xs text-muted-foreground">
                Current: {current.data?.max_mentees}
              </span>
            </div>
            <label className="block space-y-1.5">
              <span className="block text-xs font-medium text-muted-foreground">
                Reason (optional but recommended)
              </span>
              <Input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>

            {feedback && <FeedbackBanner feedback={feedback} />}

            <Button
              type="button"
              onClick={() => {
                setFeedback(null);
                save.mutate();
              }}
              disabled={!dirty || !valid || save.isPending}
            >
              {save.isPending ? "Saving…" : "Save threshold"}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function CoolingPeriodsTab() {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["admin", "config", "cooling"],
    queryFn: api.getCoolingPeriods,
  });

  if (list.isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
    );
  }
  if (list.isError || !list.data) {
    return (
      <p className="text-sm text-destructive">Could not load cooling periods.</p>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {list.data.map((entry) => (
        <CoolingRow
          key={entry.terminal_state}
          entry={entry}
          onSaved={() => {
            void qc.invalidateQueries({ queryKey: ["admin", "config"] });
          }}
        />
      ))}
    </div>
  );
}

function CoolingRow({
  entry,
  onSaved,
}: {
  entry: CoolingPeriodEntry;
  onSaved: () => void;
}) {
  const [value, setValue] = useState<number>(entry.duration_months);
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState<{
    kind: "ok" | "err";
    message: string;
  } | null>(null);

  const locked = entry.terminal_state === "CANDIDATE_REJECTED";

  const save = useMutation({
    mutationFn: () =>
      api.setCoolingPeriod(
        entry.terminal_state,
        value,
        reason.trim() || undefined,
      ),
    onSuccess: (r) => {
      setFeedback({
        kind: "ok",
        message: `Saved — ${r.terminal_state} now ${r.duration_months} months.`,
      });
      setReason("");
      onSaved();
    },
    onError: (err) => {
      setFeedback({
        kind: "err",
        message:
          err instanceof NexHireApiError ? err.message : "Could not save.",
      });
    },
  });

  const dirty = value !== entry.duration_months;
  const valid = value >= 0 && value <= 24;

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">{entry.terminal_state}</h3>
            <p className="text-xs text-muted-foreground">{entry.description}</p>
          </div>
          {entry.reason && (
            <p className="max-w-md text-right text-[11px] italic text-muted-foreground">
              Last reason: {entry.reason}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Input
            type="number"
            min={0}
            max={24}
            disabled={locked}
            value={value}
            onChange={(e) => setValue(Number(e.target.value))}
            className="w-24"
          />
          <span className="text-xs text-muted-foreground">months</span>
          {locked && (
            <Badge variant="muted">
              <Lock className="h-3 w-3" aria-hidden />
              Locked at 0
            </Badge>
          )}
        </div>

        {!locked && (
          <>
            <label className="block space-y-1.5">
              <span className="block text-xs font-medium text-muted-foreground">
                Reason for change
              </span>
              <Input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>

            {feedback && <FeedbackBanner feedback={feedback} />}

            <Button
              type="button"
              size="sm"
              onClick={() => {
                setFeedback(null);
                save.mutate();
              }}
              disabled={!dirty || !valid || save.isPending}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryTab() {
  const history = useQuery({
    queryKey: ["admin", "config", "history"],
    queryFn: api.getConfigHistory,
  });

  if (history.isLoading) {
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
  if (history.isError || !history.data) {
    return <p className="text-sm text-destructive">Could not load history.</p>;
  }
  if (history.data.length === 0) {
    return (
      <EmptyState
        icon={<History className="h-5 w-5" aria-hidden />}
        title="No configuration changes recorded yet"
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-secondary/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium">When</th>
              <th className="px-4 py-2.5 text-left font-medium">Setting</th>
              <th className="px-4 py-2.5 text-left font-medium">Change</th>
              <th className="px-4 py-2.5 text-left font-medium">Reason</th>
              <th className="px-4 py-2.5 text-left font-medium">Changed by</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {history.data.map((row) => (
              <HistoryRow key={row.id} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function HistoryRow({ row }: { row: ConfigHistoryEntry }) {
  return (
    <tr className="transition-colors hover:bg-muted/40">
      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-muted-foreground">
        {new Date(row.changed_at).toLocaleString()}
      </td>
      <td className="px-4 py-2.5 font-medium">
        {row.config_type}
        {row.applies_to ? ` · ${row.applies_to}` : ""}
      </td>
      <td className="px-4 py-2.5 font-mono text-xs">
        {row.previous_value ?? "—"} → {row.new_value} {row.unit}
      </td>
      <td className="px-4 py-2.5 text-xs">{row.reason ?? "—"}</td>
      <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
        {row.changed_by?.slice(0, 8) ?? "—"}
      </td>
    </tr>
  );
}
