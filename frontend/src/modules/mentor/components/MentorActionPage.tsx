import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { NexHireApiError } from "@/lib/axios";
import {
  type MentorActionPreview,
  type MentorActionResult,
  confirmMentorAction,
  previewMentorAction,
} from "@/modules/mentor/api";

/**
 * Mounted at /action/mentor. The mentor lands here from the email
 * link. Decision B12: GET previews (non-consuming); user confirms via
 * a button → POST /action/mentor/confirm consumes the token.
 *
 * No SSO required — the token is the credential.
 */
export function MentorActionPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const action = (params.get("action") ?? "").toUpperCase() as "ACCEPT" | "REJECT";

  const [phase, setPhase] = useState<"preview" | "confirming" | "done" | "error">(
    "preview",
  );
  const [preview, setPreview] = useState<MentorActionPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<MentorActionResult | null>(null);

  const validParams = token.length > 10 && (action === "ACCEPT" || action === "REJECT");

  useEffect(() => {
    if (!validParams) {
      setPhase("error");
      setError("This link is malformed. Please use the link in your email.");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = await previewMentorAction(token, action);
        if (cancelled) return;
        setPreview(data);
      } catch (err) {
        if (cancelled) return;
        setPhase("error");
        if (err instanceof NexHireApiError) {
          setError(err.message);
        } else {
          setError("This link is invalid or expired.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, action, validParams]);

  const handleConfirm = async () => {
    setPhase("confirming");
    setError(null);
    try {
      const data = await confirmMentorAction({
        token,
        action,
        reason: action === "REJECT" ? reason.trim() : undefined,
      });
      setResult(data);
      setPhase("done");
    } catch (err) {
      setPhase("preview");
      if (err instanceof NexHireApiError) {
        setError(err.message);
      } else {
        setError("Could not record your response. Please try again.");
      }
    }
  };

  const reasonOk = useMemo(() => reason.trim().length >= 10, [reason]);

  return (
    <div className="min-h-screen bg-background py-12">
      <div className="container max-w-xl">
        <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
          <h1 className="text-2xl font-semibold">
            {action === "ACCEPT" ? "Confirm Mentoring Acceptance" : "Decline Mentoring Request"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            NexHire requires explicit confirmation so that simple email link
            previews don't consume the action.
          </p>

          {phase === "error" && (
            <p role="alert" className="mt-6 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}

          {phase === "done" && result !== null && (
            <div className="mt-6 rounded-md bg-emerald-50 p-4 text-sm text-emerald-900">
              <p className="font-medium">{result.message}</p>
              {result.is_terminal && (
                <p className="mt-2 text-emerald-800/80">
                  Maximum mentor attempts have been reached for this referral
                  — it is now closed.
                </p>
              )}
            </div>
          )}

          {(phase === "preview" || phase === "confirming") && preview !== null && (
            <>
              <p className="mt-6 text-sm">
                Referral <span className="font-mono">#{preview.referral_id.slice(0, 8)}</span>{" "}
                — link expires {new Date(preview.expires_at).toLocaleString()}.
              </p>

              {action === "REJECT" && (
                <label className="mt-4 block text-sm">
                  <span className="font-medium">Reason for declining *</span>
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={4}
                    minLength={10}
                    maxLength={500}
                    placeholder="A brief reason helps the referrer pick a better next mentor."
                    className="mt-1 w-full rounded-md border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Minimum 10 characters.
                  </span>
                </label>
              )}

              {error !== null && phase === "preview" && (
                <p
                  role="alert"
                  className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </p>
              )}

              <button
                type="button"
                onClick={handleConfirm}
                disabled={
                  phase === "confirming" || (action === "REJECT" && !reasonOk)
                }
                className={`mt-6 rounded-md px-5 py-2 text-sm font-medium text-white disabled:opacity-60 ${
                  action === "ACCEPT"
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : "bg-destructive hover:bg-destructive/90"
                }`}
              >
                {phase === "confirming"
                  ? "Submitting…"
                  : action === "ACCEPT"
                    ? "Confirm Acceptance"
                    : "Submit Decline"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
