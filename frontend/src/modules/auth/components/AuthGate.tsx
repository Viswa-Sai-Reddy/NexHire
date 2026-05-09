import { type PropsWithChildren } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";

import { useAuth } from "@/app/providers/AuthProvider";
import { LandingPage } from "@/modules/auth/components/LandingPage";
import { Badge, Button } from "@/shared/components/ui";

const ROLE_LABEL: Record<string, string> = {
  REFERRER: "Referrer",
  MENTOR: "Mentor",
  HR: "HR",
  IT_AD: "IT / AD",
  ADMIN: "Admin",
  PROGRAM_OWNER: "Program Owner",
  CANDIDATE: "Candidate",
  SYSTEM: "System",
};

/**
 * Wraps every authenticated page with a shared header (logo + user info +
 * sign-out) and renders the LandingPage for anonymous users.
 */
export function AuthGate({ children }: PropsWithChildren) {
  const { state, signOut } = useAuth();
  const navigate = useNavigate();

  if (state.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        <span aria-live="polite">Loading…</span>
      </div>
    );
  }

  if (state.status !== "authenticated") {
    return <LandingPage />;
  }

  const user = state.user;
  const roleLabel = ROLE_LABEL[user.role] ?? user.role;

  const handleSignOut = async () => {
    await signOut();
    navigate("/", { replace: true });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-card/80 backdrop-blur supports-[backdrop-filter]:bg-card/70">
        <div className="container flex h-14 items-center justify-between gap-4">
          <Link
            to="/"
            className="flex items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <span
              aria-hidden
              className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-primary to-accent shadow-sm"
            >
              <span className="h-2 w-2 rounded-sm bg-primary-foreground/90" />
            </span>
            <span className="text-base font-semibold tracking-tight">
              NexHire
            </span>
          </Link>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 sm:flex">
              <span className="text-sm font-medium text-foreground">
                {user.full_name || user.email}
              </span>
              <Badge variant="muted" className="font-medium">
                {roleLabel}
              </Badge>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void handleSignOut()}
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
