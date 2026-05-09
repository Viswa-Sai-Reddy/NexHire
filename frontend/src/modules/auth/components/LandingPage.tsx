import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ChevronDown,
  ChevronUp,
  FileSignature,
  Sparkles,
  Workflow,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/app/providers/AuthProvider";
import { Button } from "@/shared/components/ui";

const FEATURES = [
  {
    title: "AI Resume Parsing",
    body: "Extracts candidate details, skills, and education from resumes with 90%+ accuracy and confidence scoring.",
    Icon: Sparkles,
  },
  {
    title: "Automated Workflows",
    body: "Event-driven notifications and tasks across HR, IT, Admin, and Compliance — with SLA tracking and escalation paths.",
    Icon: Workflow,
  },
  {
    title: "Digital NDA & E-Sign",
    body: "Issue and archive NDAs digitally via e-sign. Internship start is blocked until the document is fully executed.",
    Icon: FileSignature,
  },
];

const DEMO_ACCOUNTS = [
  { email: "po@karthikirisoutlook.onmicrosoft.com", role: "Program Owner" },
  { email: "hr@karthikirisoutlook.onmicrosoft.com", role: "HR" },
  { email: "referrer@karthikirisoutlook.onmicrosoft.com", role: "Referrer" },
  { email: "admin@karthikirisoutlook.onmicrosoft.com", role: "Admin (badge)" },
  { email: "itad@karthikirisoutlook.onmicrosoft.com", role: "IT/AD" },
  { email: "mentor.lead@karthikirisoutlook.onmicrosoft.com", role: "Mentor lead" },
];

/**
 * Pre-auth landing page.
 */
export function LandingPage() {
  const { state, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showDemo, setShowDemo] = useState(false);

  const busy = state.status === "loading";
  const errorMessage = state.status === "error" ? state.message : null;

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!email || !password || busy) return;
    await signIn(email, password);
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="container flex h-16 items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
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
          <nav
            className="flex items-center gap-3 text-sm"
            aria-label="primary"
          >
            <a
              className="hidden rounded-md px-3 py-1.5 text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
              href="#features"
            >
              Features
            </a>
            <Button asChild variant="outline" size="sm">
              <Link to="/register">Create account</Link>
            </Button>
          </nav>
        </div>
      </header>

      <main className="bg-hero-gradient">
        <div className="container grid gap-12 py-20 lg:grid-cols-2 lg:py-24">
          <div className="flex flex-col justify-center">
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium text-white/80 backdrop-blur">
              <Sparkles className="h-3 w-3" aria-hidden />
              AI-Powered Internship Automation Platform
            </span>
            <h1 className="mt-6 text-4xl font-semibold leading-tight tracking-tight text-white sm:text-5xl">
              Intern management,
              <br />
              <span className="bg-gradient-to-r from-accent to-primary bg-clip-text text-transparent">
                reimagined.
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-base text-white/70 sm:text-lg">
              NexHire replaces fragmented emails and manual workflows with a
              secure, AI-assisted portal — from referral intake to certificate
              issuance. Faster cycles, full compliance, zero chaos.
            </p>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20 backdrop-blur">
            <h2 className="text-xl font-semibold tracking-tight text-white">
              Sign in
            </h2>
            <p className="mt-1 text-sm text-white/70">
              Welcome back. Enter your email and password to continue.
            </p>
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <label className="block space-y-1.5">
                <span className="block text-xs font-medium uppercase tracking-wide text-white/70">
                  Email
                </span>
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-white/20 bg-white/10 px-3 py-2 text-sm text-white shadow-sm transition-colors placeholder:text-white/50 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
                  placeholder="you@company.com"
                />
              </label>
              <label className="block space-y-1.5">
                <span className="block text-xs font-medium uppercase tracking-wide text-white/70">
                  Password
                </span>
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-white/20 bg-white/10 px-3 py-2 text-sm text-white shadow-sm transition-colors placeholder:text-white/50 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
                  placeholder="••••••••"
                />
              </label>
              <button
                type="submit"
                disabled={busy}
                className="flex h-9 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? "Signing in…" : "Sign in"}
                {!busy && <ArrowRight className="h-4 w-4" aria-hidden />}
              </button>
              {errorMessage !== null && (
                <p
                  role="alert"
                  className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/15 px-3 py-2 text-sm text-white"
                >
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  {errorMessage}
                </p>
              )}
            </form>
            <p className="mt-4 text-center text-sm text-white/70">
              No account?{" "}
              <Link
                to="/register"
                className="rounded font-medium text-accent underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                Create one
              </Link>
            </p>

            <div className="mt-6 border-t border-white/10 pt-4">
              <button
                type="button"
                onClick={() => setShowDemo((v) => !v)}
                className="inline-flex items-center gap-1 rounded text-xs text-white/60 outline-none transition-colors hover:text-white focus-visible:ring-2 focus-visible:ring-accent"
              >
                {showDemo ? (
                  <ChevronUp className="h-3 w-3" aria-hidden />
                ) : (
                  <ChevronDown className="h-3 w-3" aria-hidden />
                )}
                {showDemo ? "Hide" : "Show"} demo accounts
              </button>
              {showDemo && (
                <div className="mt-3 space-y-2 rounded-md border border-white/10 bg-black/30 p-3 text-xs text-white/80">
                  <p>
                    Shared password:{" "}
                    <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-accent">
                      NexHireDemo2026!
                    </code>
                  </p>
                  <ul className="space-y-1 leading-relaxed">
                    {DEMO_ACCOUNTS.map((acc) => (
                      <li
                        key={acc.email}
                        className="flex items-center justify-between gap-2"
                      >
                        <code className="truncate font-mono text-[11px] text-white/70">
                          {acc.email}
                        </code>
                        <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium text-white/80">
                          {acc.role}
                        </span>
                      </li>
                    ))}
                    <li className="text-[11px] italic text-white/60">
                      mentor1…mentor10@karthikirisoutlook.onmicrosoft.com —
                      Mentors
                    </li>
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      <section
        id="features"
        className="border-t border-border bg-secondary/40"
        aria-labelledby="features-heading"
      >
        <div className="container py-16 lg:py-20">
          <div className="mx-auto max-w-2xl text-center">
            <h2
              id="features-heading"
              className="text-3xl font-semibold tracking-tight"
            >
              Everything you need to run a compliant internship program
            </h2>
            <p className="mt-3 text-muted-foreground">
              Built for HR, IT, Admin, and Program Owners — with AI handling
              the heavy lifting.
            </p>
          </div>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {FEATURES.map((card) => (
              <div
                key={card.title}
                className="group rounded-xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-md"
              >
                <div
                  aria-hidden
                  className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground"
                >
                  <card.Icon className="h-5 w-5" />
                </div>
                <h3 className="mt-4 text-lg font-semibold tracking-tight">
                  {card.title}
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {card.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
