import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  RotateCcw,
  Sparkles,
  XCircle,
} from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import * as api from "@/modules/hr/api";
import {
  Badge,
  type BadgeProps,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
  Textarea,
} from "@/shared/components/ui";
import { cn } from "@/lib/utils";

/**
 * S12 — Referral Review Panel.
 */
export function HrReviewPage() {
  const { referralId = "" } = useParams<{ referralId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const review = useQuery({
    queryKey: ["hr", "review", referralId],
    queryFn: () => api.getReviewContext(referralId),
    enabled: Boolean(referralId),
  });

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const approve = useMutation({
    mutationFn: (notes: string | undefined) =>
      api.approveReferral(referralId, notes),
    onSuccess: () => onMutationOk("Referral approved."),
    onError: onMutationErr,
  });
  const reject = useMutation({
    mutationFn: (reason: string) => api.rejectReferral(referralId, reason),
    onSuccess: () =>
      onMutationOk("Referral rejected. 3-month cooling applied."),
    onError: onMutationErr,
  });
  const correction = useMutation({
    mutationFn: (notes: string) => api.requestCorrection(referralId, notes),
    onSuccess: () =>
      onMutationOk("Correction requested — referrer can edit and resubmit."),
    onError: onMutationErr,
  });
  const recall = useMutation({
    mutationFn: (reason: string | undefined) =>
      api.recallAutoApprove(referralId, reason),
    onSuccess: () =>
      onMutationOk("Auto-approval recalled. Status reverted to HR_REVIEW."),
    onError: onMutationErr,
  });

  function onMutationOk(message: string) {
    setActionError(null);
    setActionSuccess(message);
    void qc.invalidateQueries({ queryKey: ["hr", "review", referralId] });
    void qc.invalidateQueries({ queryKey: ["hr", "queue"] });
    void qc.invalidateQueries({ queryKey: ["hr", "recent-ai"] });
  }
  function onMutationErr(err: unknown) {
    setActionSuccess(null);
    setActionError(
      err instanceof NexHireApiError ? err.message : "Action failed.",
    );
  }

  const ctx = review.data;
  const isHrReview = ctx?.referral.status === "HR_REVIEW";
  const recallable = useMemo(
    () => Boolean(ctx?.recall_active),
    [ctx?.recall_active],
  );

  if (review.isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="mt-3 h-8 w-64" />
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }
  if (review.isError || !ctx) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Could not load this referral. It may have been recalled or deleted.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            to="/hr"
            className="inline-flex items-center gap-1 rounded text-xs font-medium text-primary outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <ArrowLeft className="h-3 w-3" aria-hidden />
            HR Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {ctx.referral.candidate_name}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Status: <strong>{ctx.referral.status}</strong> · PAN{" "}
            {ctx.referral.pan_masked}
          </p>
        </div>
        {ctx.auto_action_recommendation && (
          <Badge
            variant={recommendationVariant(ctx.auto_action_recommendation)}
          >
            <Sparkles className="h-3 w-3" aria-hidden />
            AI: {ctx.auto_action_recommendation.replace(/_/g, " ")}
          </Badge>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>AI Analysis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {ctx.auto_action_flags.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium">
                  Why this was flagged
                </h3>
                <ul className="space-y-1.5">
                  {ctx.auto_action_flags.map((f, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-md border border-stage-review/30 bg-stage-review/10 px-3 py-2 text-sm text-stage-review"
                    >
                      <AlertTriangle
                        className="mt-0.5 h-4 w-4 shrink-0"
                        aria-hidden
                      />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <dl className="grid gap-4 sm:grid-cols-3">
              <RiskBlock
                score={ctx.risk_score}
                classification={ctx.risk_classification}
              />
              <DupBlock
                recommendation={ctx.duplicate_recommendation}
                similarity={ctx.duplicate_similarity}
                reasons={ctx.duplicate_match_reasons}
              />
              <ReadinessBlock
                score={ctx.resume_internship_readiness}
                skills={ctx.resume_skills.length}
              />
            </dl>

            {ctx.risk_narrative && (
              <p className="rounded-md border border-border/60 bg-secondary/50 p-3 text-sm">
                {ctx.risk_narrative}
              </p>
            )}

            {ctx.resume_red_flags.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium">Resume red flags</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm text-stage-review">
                  {ctx.resume_red_flags.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}

            {ctx.resume_recommended_questions.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium">
                  Suggested mentor questions
                </h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {ctx.resume_recommended_questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {actionError && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                {actionError}
              </p>
            )}
            {actionSuccess && (
              <p className="flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-3 py-2 text-sm text-stage-active">
                <CheckCircle2
                  className="mt-0.5 h-4 w-4 shrink-0"
                  aria-hidden
                />
                {actionSuccess}
              </p>
            )}

            {isHrReview ? (
              <HrReviewActions
                busy={
                  approve.isPending ||
                  reject.isPending ||
                  correction.isPending
                }
                onApprove={(notes) => approve.mutate(notes)}
                onReject={(reason) => reject.mutate(reason)}
                onCorrection={(notes) => correction.mutate(notes)}
              />
            ) : recallable ? (
              <RecallAction
                busy={recall.isPending}
                endsAt={ctx.recall_window_ends_at ?? ""}
                onRecall={(reason) => recall.mutate(reason)}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                No actions available — this referral is not in HR_REVIEW and
                has no open recall window.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => navigate("/hr")}
        className="mt-8"
      >
        <ArrowLeft className="h-3 w-3" aria-hidden />
        Back to dashboard
      </Button>
    </div>
  );
}

function recommendationVariant(
  rec: string,
): NonNullable<BadgeProps["variant"]> {
  if (rec === "LIKELY_REJECT") return "rejected";
  if (rec === "LIKELY_APPROVE") return "active";
  return "review";
}

function RiskBlock({
  score,
  classification,
}: {
  score: number | null;
  classification: string | null;
}) {
  if (score === null) {
    return (
      <Stat label="Risk score" value="—" hint="No risk profile recorded." />
    );
  }
  const color =
    classification === "HIGH"
      ? "text-destructive"
      : classification === "MEDIUM"
        ? "text-stage-review"
        : "text-stage-active";
  return (
    <Stat
      label="Risk score"
      value={`${score} / 100`}
      hint={classification ? `${classification} risk` : undefined}
      valueClass={color}
    />
  );
}

function DupBlock({
  recommendation,
  similarity,
  reasons,
}: {
  recommendation: string | null;
  similarity: number | null;
  reasons: string[];
}) {
  if (recommendation === null) {
    return <Stat label="Duplicate check" value="—" />;
  }
  return (
    <Stat
      label="Duplicate check"
      value={
        similarity !== null
          ? `${Math.round(similarity * 100)}% match`
          : recommendation
      }
      hint={reasons.slice(0, 2).join(" · ") || recommendation}
    />
  );
}

function ReadinessBlock({
  score,
  skills,
}: {
  score: number | null;
  skills: number;
}) {
  if (score === null) {
    return <Stat label="Resume" value="—" />;
  }
  return (
    <Stat
      label="Readiness"
      value={`${score} / 100`}
      hint={`${skills} skills`}
    />
  );
}

function Stat({
  label,
  value,
  hint,
  valueClass,
}: {
  label: string;
  value: string;
  hint?: string | undefined;
  valueClass?: string | undefined;
}) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd
        className={cn("mt-1 text-2xl font-semibold tracking-tight", valueClass)}
      >
        {value}
      </dd>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function HrReviewActions({
  busy,
  onApprove,
  onReject,
  onCorrection,
}: {
  busy: boolean;
  onApprove: (notes: string | undefined) => void;
  onReject: (reason: string) => void;
  onCorrection: (notes: string) => void;
}) {
  const [active, setActive] = useState<
    "approve" | "reject" | "correction" | null
  >(null);
  const [text, setText] = useState("");

  if (active === null) {
    return (
      <div className="space-y-2">
        <Button
          type="button"
          className="w-full"
          onClick={() => setActive("approve")}
          disabled={busy}
        >
          <CheckCircle2 className="h-4 w-4" aria-hidden />
          Approve
        </Button>
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={() => setActive("correction")}
          disabled={busy}
        >
          <RotateCcw className="h-4 w-4" aria-hidden />
          Request correction
        </Button>
        <Button
          type="button"
          variant="destructive"
          className="w-full"
          onClick={() => setActive("reject")}
          disabled={busy}
        >
          <XCircle className="h-4 w-4" aria-hidden />
          Reject
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          active === "reject"
            ? "Rejection reason (≥10 chars). Triggers a 3-month cooling period."
            : active === "correction"
              ? "What needs to change? (≥10 chars)"
              : "Optional approval notes."
        }
        rows={4}
      />
      <div className="flex gap-2">
        <Button
          type="button"
          className="flex-1"
          onClick={() => {
            if (active === "approve") {
              onApprove(text.trim() || undefined);
            } else if (active === "reject") {
              if (text.trim().length < 10) return;
              onReject(text.trim());
            } else {
              if (text.trim().length < 10) return;
              onCorrection(text.trim());
            }
            setText("");
            setActive(null);
          }}
          disabled={
            busy ||
            ((active === "reject" || active === "correction") &&
              text.trim().length < 10)
          }
        >
          Confirm{" "}
          {active === "approve"
            ? "Approve"
            : active === "reject"
              ? "Reject"
              : "Correction"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setActive(null);
            setText("");
          }}
          disabled={busy}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

function RecallAction({
  busy,
  endsAt,
  onRecall,
}: {
  busy: boolean;
  endsAt: string;
  onRecall: (reason: string | undefined) => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <div className="space-y-3">
      <p className="flex items-start gap-2 rounded-md border border-stage-review/30 bg-stage-review/10 px-3 py-2 text-sm text-stage-review">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>
          AI auto-approved this referral. You can recall until{" "}
          <strong>{new Date(endsAt).toLocaleString()}</strong>.
        </span>
      </p>
      <Textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Optional: why are you recalling?"
        rows={3}
      />
      <Button
        type="button"
        variant="destructive"
        className="w-full"
        onClick={() => onRecall(reason.trim() || undefined)}
        disabled={busy}
      >
        <RotateCcw className="h-4 w-4" aria-hidden />
        Recall auto-approval
      </Button>
    </div>
  );
}
