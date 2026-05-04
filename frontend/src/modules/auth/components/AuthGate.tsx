import { type PropsWithChildren } from "react";

import { useAuth } from "@/app/providers/AuthProvider";
import { LandingPage } from "@/modules/auth/components/LandingPage";

/**
 * Shows the marketing landing page until the user has a NexHire JWT;
 * once authenticated, renders children (the app shell).
 *
 * S0 only mounts the landing page. The post-login dashboard is wired
 * in S1 alongside the first vertical slice.
 */
export function AuthGate({ children }: PropsWithChildren) {
  const { state } = useAuth();

  if (state.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
        <span aria-live="polite">Loading…</span>
      </div>
    );
  }

  if (state.status !== "authenticated") {
    return <LandingPage />;
  }

  return <>{children}</>;
}
