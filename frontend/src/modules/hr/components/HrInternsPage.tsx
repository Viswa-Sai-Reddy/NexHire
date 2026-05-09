import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Search, Users } from "lucide-react";

import { getAllInterns } from "@/modules/hr/api";
import type { HrInternsParams } from "@/modules/hr/types";
import {
  Badge,
  type BadgeProps,
  Button,
  Card,
  EmptyState,
  Input,
  Skeleton,
} from "@/shared/components/ui";

const STATUS_OPTIONS = [
  "ALL",
  "PENDING",
  "ACCESS_PENDING",
  "ACTIVE",
  "EXTENDED",
  "CLOSURE_PENDING",
  "CLOSED",
  "TERMINATED",
] as const;

const PAGE_SIZE = 50;

/**
 * HR roster of every intern with an assigned Non-Worker ID.
 */
export function HrInternsPage() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<(typeof STATUS_OPTIONS)[number]>("ALL");
  const [offset, setOffset] = useState(0);

  // Debounce search input → 300ms.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const params = useMemo<HrInternsParams>(() => {
    const base: HrInternsParams = { limit: PAGE_SIZE, offset };
    if (search) base.q = search;
    if (status !== "ALL") base.intern_status = status;
    return base;
  }, [search, status, offset]);

  const interns = useQuery({
    queryKey: ["hr", "interns", params],
    queryFn: () => getAllInterns(params),
    staleTime: 15_000,
  });

  const total = interns.data?.total ?? 0;
  const items = interns.data?.items ?? [];
  const showingFrom = items.length === 0 ? 0 : offset + 1;
  const showingTo = offset + items.length;
  const canPrev = offset > 0;
  const canNext = showingTo < total;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          All Non-Worker IDs
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every intern with an assigned NW-ID. Use search to look up by ID,
          name, or email.
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            placeholder="Search NW-ID, name, or email…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-72 pl-9"
          />
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as (typeof STATUS_OPTIONS)[number]);
            setOffset(0);
          }}
          className="h-9 rounded-md border border-border bg-card px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === "ALL" ? "All statuses" : s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted-foreground">
          {interns.isLoading
            ? "Loading…"
            : `Showing ${showingFrom}–${showingTo} of ${total}`}
        </span>
      </div>

      {interns.isError && (
        <p
          role="alert"
          className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          Could not load interns. Please retry.
        </p>
      )}

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-secondary/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5">Non-Worker ID</th>
                <th className="px-4 py-2.5">Candidate</th>
                <th className="px-4 py-2.5">Email</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Project</th>
                <th className="px-4 py-2.5">Start</th>
                <th className="px-4 py-2.5">End</th>
                <th className="px-4 py-2.5">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {interns.isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={8} className="px-4 py-2.5">
                      <Skeleton className="h-5 w-full" />
                    </td>
                  </tr>
                ))}
              {!interns.isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10">
                    <EmptyState
                      icon={<Users className="h-5 w-5" aria-hidden />}
                      title="No interns match your filters"
                      description="Try clearing the search or selecting a different status."
                    />
                  </td>
                </tr>
              )}
              {items.map((row) => (
                <tr
                  key={row.intern_id}
                  className="transition-colors hover:bg-muted/40"
                >
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-xs">
                        {row.non_worker_id}
                      </code>
                      <CopyButton text={row.non_worker_id} />
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-medium">
                    {row.candidate_name}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.candidate_email}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusPill status={row.intern_status} />
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.project_title ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.actual_start_date ?? row.internship_start_date ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.actual_end_date ?? row.internship_end_date ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.created_at.slice(0, 10)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-4 flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canPrev}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canNext}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard unavailable (insecure context) — silently no-op.
        }
      }}
      className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      title="Copy to clipboard"
      aria-label={copied ? "Copied" : "Copy"}
    >
      {copied ? (
        <Check className="h-3 w-3" aria-hidden />
      ) : (
        <Copy className="h-3 w-3" aria-hidden />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function StatusPill({ status }: { status: string }) {
  const variantMap: Record<string, BadgeProps["variant"]> = {
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
