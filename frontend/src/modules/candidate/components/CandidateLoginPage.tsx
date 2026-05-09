import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Mail, XCircle } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import { candidateLogin, requestMagicLink } from "@/modules/candidate/api";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
} from "@/shared/components/ui";

type Mode = "credential" | "magic";

/**
 * Candidate sign-in.
 */
export function CandidateLoginPage() {
  const [mode, setMode] = useState<Mode>("credential");
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <Card className="w-full max-w-md">
        {mode === "credential" ? (
          <CredentialForm onSwitchToMagic={() => setMode("magic")} />
        ) : (
          <MagicLinkForm onSwitchToCredential={() => setMode("credential")} />
        )}
      </Card>
    </div>
  );
}

function CredentialForm({
  onSwitchToMagic,
}: {
  onSwitchToMagic: () => void;
}) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [nonWorkerId, setNonWorkerId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !nonWorkerId.trim()) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await candidateLogin(email.trim(), nonWorkerId.trim());
      navigate(result.redirect_to, { replace: true });
    } catch (err) {
      setError(
        err instanceof NexHireApiError
          ? err.message
          : "Sign-in failed. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <CardHeader>
        <CardTitle className="text-2xl">Candidate sign in</CardTitle>
        <CardDescription>
          Sign in with the email you received your NexHire invitation on and
          the Non-Worker ID we sent you after your NDA was signed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block space-y-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Email
            </span>
            <Input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Non-Worker ID
            </span>
            <Input
              type="text"
              required
              autoComplete="off"
              spellCheck={false}
              placeholder="NW-XXXXXXXXXX-2026"
              value={nonWorkerId}
              onChange={(e) => setNonWorkerId(e.target.value)}
              className="font-mono uppercase"
            />
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

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="text-xs text-muted-foreground">
          Forgot your Non-Worker ID?{" "}
          <button
            type="button"
            onClick={onSwitchToMagic}
            className="rounded font-medium text-primary underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Email me a sign-in link
          </button>
        </p>
      </CardContent>
    </>
  );
}

function MagicLinkForm({
  onSwitchToCredential,
}: {
  onSwitchToCredential: () => void;
}) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim()) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await requestMagicLink(email.trim());
      setSubmitted(true);
    } catch {
      setError("Something went wrong. Please try again in a moment.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <CardHeader>
        <CardTitle className="text-2xl">Email me a sign-in link</CardTitle>
        <CardDescription>
          Enter the email you received your NexHire invitation on. We'll send
          you a one-time sign-in link.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {submitted ? (
          <div
            role="status"
            className="flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-4 py-3 text-sm text-stage-active"
          >
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              If <strong>{email}</strong> is registered with NexHire, we've
              sent you a sign-in link. Check your inbox (and spam folder). The
              link expires in a few hours — you can request a new one from
              this page anytime.
            </span>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={handleSubmit}>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Email
              </span>
              <Input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
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

            <Button type="submit" disabled={submitting} className="w-full">
              <Mail className="h-4 w-4" aria-hidden />
              {submitting ? "Sending…" : "Send sign-in link"}
            </Button>
          </form>
        )}

        <p className="text-xs text-muted-foreground">
          <button
            type="button"
            onClick={onSwitchToCredential}
            className="rounded font-medium text-primary underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Back to sign in with Non-Worker ID
          </button>
        </p>
      </CardContent>
    </>
  );
}
