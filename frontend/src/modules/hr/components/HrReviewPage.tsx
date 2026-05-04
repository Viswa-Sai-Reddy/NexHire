import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { NexHireApiError } from "@/lib/axios";
import * as api from "@/modules/hr/api";

/**
 * S12 — Referral Review Panel.
 *
 * Single-referral context: candidate facts, AI risk, dedup matches,
 * resume highlights, auto-approval flags, and the four HR actions
 * (approve / reject / request-correction / recall).
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
    mutationFn: (notes: string | undefined) => api.approveReferral(referralId, notes),
    onSuccess: () => onMutationOk("Referral approved."),
    onError: onMutationErr,
  });
  const reject = useMutation({
    mutationFn: (reason: string) => api.rejectReferral(referralId, reason),
    onSuccess: () => onMutationOk("Referral rejected. 3-month cooling applied."),
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
    onSuccess: () => onMutationOk("Auto-approval recalled. Status reverted to HR_REVIEW."),
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
      <div className="container py-10 text-sm text-muted-foreground">
        Loading review context…
      </div>
    );
  }
  if (review.isError || !ctx) {
    return (
      <div className="container py-10 text-sm text-destructive">
        Could not load this referral. It may have been recalled or deleted.
      </div>
    );
  }

  return (
    <div className="container py-10">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <Link
            to="/hr"
            className="text-xs font-medium text-primary hover:underline"
          >
            ← HR Dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold">
            {ctx.referral.candidate_name}
          </h1>
          <p className="text-sm text-muted-foreground">
            Status: <strong>{ctx.referral.status}</strong> · PAN{" "}
            {ctx.referral.pan_masked}
          </p>
        </div>
        {ctx.auto_action_recommendation && (
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              ctx.auto_action_recommendation === "LIKELY_REJECT"
                ? "bg-destructive/10 text-destructive"
                : ctx.auto_action_recommendation === "LIKELY_APPROVE"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-amber-100 text-amber-800"
            }`}
          >
            AI: {ctx.auto_action_recommendation.replace(/_/g, " ")}
          </span>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-xl border border-border bg-card p-6 shadow-sm lg:col-span-2">
          <h2 className="text-base font-semibold">AI Analysis</h2>

          {ctx.auto_action_flags.length > 0 && (
            <div className="mt-4">
              <h3 className="text-sm font-medium">Why this was flagged</h3>
              <ul className="mt-2 space-y-1">
                {ctx.auto_action_flags.map((f, i) => (
                  <li
                    key={i}
                    className="rounded-md bg-amber-50 px-3 py-1.5 text-sm text-amber-900"
                  >
                    ⚠️ {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <dl className="mt-6 grid gap-4 sm:grid-cols-3">
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
            <p className="mt-6 rounded-md bg-secondary/50 p-3 text-sm">
              {ctx.risk_narrative}
            </p>
          )}

          {ctx.resume_red_flags.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-medium">Resume red flags</h3>
              <ul className="mt-2 list-disc pl-5 text-sm text-amber-800">
                {ctx.resume_red_flags.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          {ctx.resume_recommended_questions.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-medium">
                Suggested mentor questions
              </h3>
              <ul className="mt-2 list-disc pl-5 text-sm">
                {ctx.resume_recommended_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <aside className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 className="text-base font-semibold">Actions</h2>

          {actionError && (
            <p
              role="alert"
              className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {actionError}
            </p>
          )}
          {actionSuccess && (
            <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
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
            <p className="mt-3 text-sm text-muted-foreground">
              No actions available — this referral is not in HR_REVIEW and
              has no open recall window.
            </p>
          )}
        </aside>
      </div>

      <button
        type="button"
        onClick={() => navigate("/hr")}
        className="mt-8 text-xs text-muted-foreground hover:text-foreground"
      >
        ← Back to dashboard
      </button>
    </div>
  );
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
        ? "text-amber-700"
        : "text-emerald-700";
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
    <Stat label="Readiness" value={`${score} / 100`} hint={`${skills} skills`} />
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
  hint?: string;
  valueClass?: string;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className={`mt-1 text-2xl font-semibold ${valueClass ?? ""}`}>
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
  const [active, setActive] = useState<"approve" | "reject" | "correction" | null>(
    null,
  );
  const [text, setText] = useState("");

  return (
    <div className="mt-3 space-y-3">
      {active === null ? (
        <>
          <ActionButton
            label="Approve"
            color="emerald"
            onClick={() => setActive("approve")}
            disabled={busy}
          />
          <ActionButton
            label="Request correction"
            color="amber"
            onClick={() => setActive("correction")}
            disabled={busy}
          />
          <ActionButton
            label="Reject"
            color="destructive"
            onClick={() => setActive("reject")}
            disabled={busy}
          />
        </>
      ) : (
        <>
          <textarea
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
            className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <div className="flex gap-2">
            <button
              type="button"
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
              className="flex-1 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              Confirm{" "}
              {active === "approve"
                ? "Approve"
                : active === "reject"
                  ? "Reject"
                  : "Correction"}
            </button>
            <button
              type="button"
              onClick={() => {
                setActive(null);
                setText("");
              }}
              disabled={busy}
              className="rounded-md border border-border px-3 py-2 text-sm hover:bg-secondary"
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ActionButton({
  label,
  color,
  onClick,
  disabled,
}: {
  label: string;
  color: "emerald" | "amber" | "destructive";
  onClick: () => void;
  disabled: boolean;
}) {
  const cls =
    color === "emerald"
      ? "bg-emerald-600 text-white hover:bg-emerald-700"
      : color === "amber"
        ? "border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
        : "bg-destructive text-destructive-foreground hover:bg-destructive/90";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full rounded-md px-3 py-2 text-sm font-medium disabled:opacity-60 ${cls}`}
    >
      {label}
    </button>
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
    <div className="mt-3 space-y-3">
      <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
        AI auto-approved this referral. You can recall until{" "}
        <strong>{new Date(endsAt).toLocaleString()}</strong>.
      </p>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Optional: why are you recalling?"
        rows={3}
        className="w-full rounded-md border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <button
        type="button"
        onClick={() => onRecall(reason.trim() || undefined)}
        disabled={busy}
        className="w-full rounded-md bg-amber-600 px-3 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
      >
        Recall auto-approval
      </button>
    </div>
  );
}
