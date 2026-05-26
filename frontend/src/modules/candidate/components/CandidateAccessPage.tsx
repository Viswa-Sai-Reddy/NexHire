import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, Send, ShieldAlert } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import { redeemMagicLink, requestMagicLink } from "@/modules/candidate/api";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input as UiInput,
} from "@/shared/components/ui";

interface ErrorState {
  message: string;
  recoverable: boolean;
}

// Recoverable = a fresh magic link would unblock the candidate. Other
// failures (network, server) fall through to a flat error with no resend
// affordance.
const RECOVERABLE_CODES = new Set([
  "ACTION_TOKEN_USED",
  "ACTION_TOKEN_EXPIRED",
  "MAGIC_LINK_INVALID",
]);

/**
 * `/candidate/access?token=…` — magic-link landing.
 */
export function CandidateAccessPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<ErrorState | null>(null);
  // Action tokens are single-use server-side. Without this gate, React 18
  // StrictMode's double-invocation of the effect would consume the token
  // on its first run and fail with "already submitted" on the second.
  const ranForTokenRef = useRef<string | null>(null);

  useEffect(() => {
    const token = params.get("token") ?? "";
    if (token.length < 10) {
      setError({
        message: "This link is malformed. Please use the link in your email.",
        recoverable: false,
      });
      return;
    }
    if (ranForTokenRef.current === token) return;
    ranForTokenRef.current = token;

    // No `cancelled` flag here on purpose: the ref-gate already prevents
    // the StrictMode double-mount from issuing a second redeem, and React
    // 18 silently drops setState calls on unmounted components, so the
    // earlier `cancelled` short-circuit was actively swallowing the only
    // resolution we get back from the single in-flight request.
    void (async () => {
      try {
        const result = await redeemMagicLink(token);
        navigate(result.redirect_to, { replace: true });
      } catch (err) {
        if (err instanceof NexHireApiError) {
          setError({
            message: err.message,
            recoverable: RECOVERABLE_CODES.has(err.code),
          });
        } else {
          setError({
            message: "This link is invalid or expired.",
            recoverable: false,
          });
        }
      }
    })();
  }, [navigate, params]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">Welcome to NexHire</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {error === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Verifying your access link…
            </p>
          ) : (
            <>
              <p
                role="alert"
                className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                {error.message}
              </p>
              {error.recoverable && <RecoveryForm />}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RecoveryForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmed = email.trim().toLowerCase();
    if (trimmed.length === 0) return;
    setBusy(true);
    setLocalError(null);
    try {
      await requestMagicLink(trimmed);
      setSentTo(trimmed);
    } catch (err) {
      // The endpoint is 204 either way, so this branch is defensive
      // (network errors, server unreachable).
      setLocalError(
        err instanceof NexHireApiError
          ? err.message
          : "Couldn't send a new link. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (sentTo !== null) {
    return (
      <p className="flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-3 py-2 text-sm text-stage-active">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>
          If an account exists for <strong>{sentTo}</strong>, a new link is on
          its way. Check your inbox.
        </span>
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <label
          htmlFor="recovery-email"
          className="text-sm font-medium text-foreground"
        >
          Get a fresh link
        </label>
        <p className="text-xs text-muted-foreground">
          Enter the email this invitation was sent to and we'll mail you a new
          link.
        </p>
        <UiInput
          id="recovery-email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
          required
        />
      </div>
      {localError !== null && (
        <p
          role="alert"
          className="text-xs text-destructive"
        >
          {localError}
        </p>
      )}
      <Button
        type="submit"
        disabled={busy || email.trim().length === 0}
        className="w-full"
      >
        {busy ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Sending…
          </>
        ) : (
          <>
            <Send className="h-4 w-4" aria-hidden />
            Send me a new link
          </>
        )}
      </Button>
    </form>
  );
}
