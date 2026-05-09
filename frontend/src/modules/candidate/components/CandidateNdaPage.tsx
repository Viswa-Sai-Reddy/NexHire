import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import { acceptNda, getNda } from "@/modules/candidate/api";
import {
  Button,
  Card,
  CardContent,
  Input,
} from "@/shared/components/ui";

/**
 * In-app NDA click-to-accept page.
 */
export function CandidateNdaPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [agreed, setAgreed] = useState(false);
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const nda = useQuery({
    queryKey: ["candidate", "nda"],
    queryFn: getNda,
    staleTime: 0,
  });

  const accept = useMutation({
    mutationFn: ({ name, sha }: { name: string; sha: string }) =>
      acceptNda(name, sha),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["candidate"] });
      navigate("/candidate/status", { replace: true });
    },
    onError: (err) => setError(formatError(err)),
  });

  useEffect(() => {
    if (nda.data?.status === "SIGNED") {
      const t = setTimeout(
        () => navigate("/candidate/status", { replace: true }),
        2000,
      );
      return () => clearTimeout(t);
    }
    return undefined;
  }, [nda.data?.status, navigate]);

  if (nda.isLoading) {
    return (
      <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-12 text-sm text-muted-foreground sm:px-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading the agreement…
      </div>
    );
  }

  if (nda.isError || !nda.data) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Could not load the NDA. Please refresh the page or contact HR.
        </p>
      </div>
    );
  }

  const data = nda.data;

  if (data.status === "SIGNED") {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12 sm:px-6">
        <Card>
          <CardContent className="p-8">
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <CheckCircle2 className="h-6 w-6 text-stage-active" aria-hidden />
              NDA already signed
            </h1>
            <p className="mt-3 text-sm text-muted-foreground">
              You signed this agreement
              {data.signed_at
                ? ` on ${new Date(data.signed_at).toLocaleString()}`
                : ""}
              . Redirecting you to your status page…
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const namesMatch =
    typedName.trim().toLowerCase() ===
    data.candidate_name.trim().toLowerCase();
  const canSubmit = agreed && namesMatch && !accept.isPending;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Sign the NDA</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Please read the agreement below in full. Tick the box and type your
          full legal name to accept.
        </p>
      </header>

      <Card>
        <article
          className="prose prose-sm dark:prose-invert max-h-[60vh] max-w-none overflow-y-auto p-6"
          dangerouslySetInnerHTML={{ __html: data.text_html }}
        />
      </Card>

      <Card className="mt-6">
        <CardContent className="space-y-5 p-6">
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            />
            <span>
              I have read the NDA above in its entirety and agree to be bound
              by its terms.
            </span>
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Type your full legal name to confirm
            </span>
            <Input
              type="text"
              value={typedName}
              onChange={(e) => setTypedName(e.target.value)}
              placeholder={data.candidate_name}
              autoComplete="off"
              spellCheck={false}
            />
            {typedName.length > 0 && !namesMatch && (
              <span className="block text-xs text-destructive">
                Must match the name on your referral exactly:{" "}
                <strong>{data.candidate_name}</strong>
              </span>
            )}
          </label>

          {error && (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate("/candidate/status")}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!canSubmit}
              onClick={() => {
                setError(null);
                accept.mutate({
                  name: typedName.trim(),
                  sha: data.text_sha256,
                });
              }}
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden />
              {accept.isPending ? "Signing…" : "Sign and accept"}
            </Button>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Your acceptance is recorded with timestamp, IP address, browser
            fingerprint, and a cryptographic hash of this exact agreement
            version (sha256: <code>{data.text_sha256.slice(0, 12)}…</code>).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function formatError(err: unknown): string {
  if (err instanceof NexHireApiError) return err.message;
  return "Could not record your acceptance. Please try again.";
}
