import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Pause,
  Send,
  Settings,
} from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import * as api from "@/modules/admin/api";
import type { ChatbotResponse } from "@/modules/admin/types";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  Textarea,
} from "@/shared/components/ui";

/**
 * S23 — Executive dashboard.
 *
 * KPIs from /admin/overview, plus an embedded AI-9 chatbot side-panel
 * for ad-hoc program questions.
 */
export function ExecutiveDashboardPage() {
  const overview = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: api.getOverview,
    staleTime: 30_000,
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Program overview
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Pipeline, SLA, cooling, and at-risk counts across the program.
          </p>
        </div>
        <nav className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/admin/audit">
              <BarChart3 className="h-3.5 w-3.5" aria-hidden />
              Audit & SLA
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to="/admin/config">
              <Settings className="h-3.5 w-3.5" aria-hidden />
              Config
            </Link>
          </Button>
        </nav>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          {overview.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Card key={i} className="p-5">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="mt-3 h-9 w-16" />
                </Card>
              ))}
            </div>
          ) : overview.isError || !overview.data ? (
            <Card>
              <CardContent className="p-6">
                <p className="text-sm text-destructive">
                  Could not load overview metrics.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="mb-6 grid gap-4 sm:grid-cols-3">
                <Kpi
                  label="SLA breaches open"
                  value={String(overview.data.sla_breaches_open)}
                  icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
                  tone={
                    overview.data.sla_breaches_open > 0 ? "warning" : "success"
                  }
                />
                <Kpi
                  label="At-risk referrals (AI-5)"
                  value={String(overview.data.at_risk)}
                  icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
                  tone={overview.data.at_risk > 0 ? "warning" : "success"}
                />
                <Kpi
                  label="In cooling"
                  value={String(overview.data.cooling_active)}
                  icon={<Pause className="h-4 w-4" aria-hidden />}
                  tone="muted"
                />
              </div>

              <Card>
                <CardHeader>
                  <CardTitle>Pipeline</CardTitle>
                  <CardDescription>
                    Live referral counts grouped by status.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {Object.entries(overview.data.pipeline).map(
                      ([status, count]) => (
                        <li
                          key={status}
                          className="flex items-center justify-between rounded-md border border-border/60 bg-secondary/40 px-3 py-2 text-sm"
                        >
                          <span className="text-muted-foreground">
                            {status.replace(/_/g, " ")}
                          </span>
                          <span className="font-mono font-semibold tabular-nums">
                            {count}
                          </span>
                        </li>
                      ),
                    )}
                  </ul>
                </CardContent>
              </Card>
            </>
          )}
        </section>

        <aside>
          <ChatbotPanel />
        </aside>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
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
    <Card>
      <div className="flex items-start justify-between p-5">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <p className={`text-3xl font-semibold tracking-tight ${valueTone}`}>
            {value}
          </p>
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

function ChatbotPanel() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<
    { q: string; r: ChatbotResponse | null; error: string | null }[]
  >([]);

  const ask = useMutation({
    mutationFn: (q: string) => api.askChatbot(q),
    onSuccess: (r, q) => {
      setHistory((prev) => [{ q, r, error: null }, ...prev].slice(0, 10));
      setQuestion("");
    },
    onError: (err, q) => {
      const message =
        err instanceof NexHireApiError ? err.message : "Could not answer.";
      setHistory((prev) =>
        [{ q, r: null, error: message }, ...prev].slice(0, 10),
      );
    },
  });

  const tooShort = question.trim().length < 4;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" aria-hidden />
          Program chatbot
        </CardTitle>
        <CardDescription>
          Ask AI-9 anything about your active program.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!tooShort && !ask.isPending) ask.mutate(question.trim());
          }}
        >
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            placeholder="How many at-risk referrals do we have?"
            maxLength={400}
          />
          <Button
            type="submit"
            disabled={tooShort || ask.isPending}
            className="w-full"
          >
            <Send className="h-3.5 w-3.5" aria-hidden />
            {ask.isPending ? "Thinking…" : "Ask"}
          </Button>
        </form>

        {history.length > 0 && (
          <ul className="mt-5 space-y-3">
            {history.map((entry, i) => (
              <li
                key={i}
                className="rounded-md border border-border/60 bg-secondary/30 p-3 text-sm"
              >
                <p className="text-xs font-medium text-muted-foreground">
                  {entry.q}
                </p>
                {entry.r ? (
                  <>
                    <p className="mt-2 whitespace-pre-wrap text-foreground">
                      {entry.r.answer}
                    </p>
                    <p className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground">
                      <CheckCircle2 className="h-3 w-3" aria-hidden />
                      {entry.r.data_source} · confidence {entry.r.confidence}
                    </p>
                  </>
                ) : (
                  <p className="mt-2 text-xs text-destructive">{entry.error}</p>
                )}
              </li>
            ))}
          </ul>
        )}

        {history.length === 0 && (
          <EmptyState
            className="mt-5"
            icon={<ArrowRight className="h-4 w-4" aria-hidden />}
            title="Ask anything"
            description="Recent answers will appear here."
          />
        )}
      </CardContent>
    </Card>
  );
}
