import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import {
  type MentorActionPreview,
  type MentorActionResult,
  confirmMentorAction,
  previewMentorAction,
} from "@/modules/mentor/api";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  Textarea,
} from "@/shared/components/ui";

/**
 * Mounted at /action/mentor — landed from email link.
 * GET previews (non-consuming); confirmation POSTs to consume the token.
 */
export function MentorActionPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const action = (params.get("action") ?? "").toUpperCase() as
    | "ACCEPT"
    | "REJECT";

  const [phase, setPhase] = useState<
    "preview" | "confirming" | "done" | "error"
  >("preview");
  const [preview, setPreview] = useState<MentorActionPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<MentorActionResult | null>(null);

  const validParams =
    token.length > 10 && (action === "ACCEPT" || action === "REJECT");

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
  const isAccept = action === "ACCEPT";

  return (
    <div className="min-h-screen bg-background py-12">
      <div className="mx-auto max-w-xl px-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-2xl tracking-tight">
              {isAccept ? (
                <CheckCircle2
                  className="h-6 w-6 text-stage-active"
                  aria-hidden
                />
              ) : (
                <XCircle className="h-6 w-6 text-destructive" aria-hidden />
              )}
              {isAccept
                ? "Confirm Mentoring Acceptance"
                : "Decline Mentoring Request"}
            </CardTitle>
            <CardDescription>
              NexHire requires explicit confirmation so that simple email link
              previews don't consume the action.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {phase === "error" && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                {error}
              </p>
            )}

            {phase === "done" && result !== null && (
              <div className="rounded-md border border-stage-active/30 bg-stage-active/10 p-4 text-sm text-stage-active">
                <p className="flex items-center gap-2 font-medium">
                  <CheckCircle2 className="h-4 w-4" aria-hidden />
                  {result.message}
                </p>
                {result.is_terminal && (
                  <p className="mt-2 text-stage-active/80">
                    Maximum mentor attempts have been reached for this referral
                    — it is now closed.
                  </p>
                )}
              </div>
            )}

            {phase !== "error" && phase !== "done" && preview === null && (
              <div className="space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            )}

            {(phase === "preview" || phase === "confirming") &&
              preview !== null && (
                <>
                  <p className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2 text-sm">
                    Referral{" "}
                    <span className="font-mono font-semibold">
                      #{preview.referral_id.slice(0, 8)}
                    </span>{" "}
                    — link expires{" "}
                    {new Date(preview.expires_at).toLocaleString()}.
                  </p>

                  {action === "REJECT" && (
                    <label className="block space-y-1.5 text-sm">
                      <span className="font-medium">
                        Reason for declining *
                      </span>
                      <Textarea
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        rows={4}
                        minLength={10}
                        maxLength={500}
                        placeholder="A brief reason helps the referrer pick a better next mentor."
                      />
                      <span className="block text-xs text-muted-foreground">
                        Minimum 10 characters.
                      </span>
                    </label>
                  )}

                  {error !== null && phase === "preview" && (
                    <p
                      role="alert"
                      className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                    >
                      {error}
                    </p>
                  )}

                  <Button
                    type="button"
                    variant={isAccept ? "default" : "destructive"}
                    onClick={() => {
                      void handleConfirm();
                    }}
                    disabled={
                      phase === "confirming" ||
                      (action === "REJECT" && !reasonOk)
                    }
                  >
                    {phase === "confirming"
                      ? "Submitting…"
                      : isAccept
                        ? "Confirm Acceptance"
                        : "Submit Decline"}
                  </Button>
                </>
              )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
