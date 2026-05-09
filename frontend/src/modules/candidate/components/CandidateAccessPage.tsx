import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, ShieldAlert } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import { redeemMagicLink } from "@/modules/candidate/api";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui";

/**
 * `/candidate/access?token=…` — magic-link landing.
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
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">Welcome to NexHire</CardTitle>
        </CardHeader>
        <CardContent>
          {error === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Verifying your access link…
            </p>
          ) : (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {error}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
