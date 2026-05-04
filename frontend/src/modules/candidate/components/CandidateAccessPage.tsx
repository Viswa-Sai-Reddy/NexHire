import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { NexHireApiError } from "@/lib/axios";
import { redeemMagicLink } from "@/modules/candidate/api";

/**
 * `/candidate/access?token=…` — magic-link landing.
 *
 * Redeems the token (single-use), stores the candidate JWT in memory
 * via the axios interceptor, and redirects per F-03 step 5 (status →
 * page mapping).
 */
export function CandidateAccessPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = params.get("token") ?? "";
    if (token.length < 10) {
      setError("This link is malformed. Please use the link in your email.");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const result = await redeemMagicLink(token);
        if (cancelled) return;
        navigate(result.redirect_to, { replace: true });
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof NexHireApiError
            ? err.message
            : "This link is invalid or expired.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, params]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-sm">
        <h1 className="text-xl font-semibold">Welcome to NexHire</h1>
        {error === null ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Verifying your access link…
          </p>
        ) : (
          <p
            role="alert"
            className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
