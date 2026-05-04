import { useAuth } from "@/app/providers/AuthProvider";

/**
 * Pre-auth landing page. Mirrors the InternFlow UI sample:
 *   - Dark hero with "AI-Powered Internship Automation Platform" chip.
 *   - "Intern management, reimagined." H1 with cyan accent.
 *   - Submit a Referral / View Dashboard CTAs (locked until sign-in).
 *
 * The user-facing brand is NexHire (decision in plan).
 */
export function LandingPage() {
  const { state, signIn } = useAuth();
  const busy = state.status === "loading";
  const errorMessage = state.status === "error" ? state.message : null;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              aria-hidden
              className="h-6 w-6 rounded-md bg-primary"
            />
            <span className="text-lg font-semibold">NexHire</span>
          </div>
          <nav
            className="flex items-center gap-6 text-sm text-muted-foreground"
            aria-label="primary"
          >
            <a className="hover:text-foreground" href="#features">
              Features
            </a>
            <button
              type="button"
              onClick={() => void signIn()}
              disabled={busy}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Get Started"}
            </button>
          </nav>
        </div>
      </header>

      <main className="bg-hero-gradient">
        <div className="container py-24">
          <span className="inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white/80 backdrop-blur">
            • AI-Powered Internship Automation Platform
          </span>
          <h1 className="mt-6 text-5xl font-semibold leading-tight text-white">
            Intern management,
            <br />
            <span className="text-accent">reimagined.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg text-white/70">
            NexHire replaces fragmented emails and manual workflows with a secure,
            AI-assisted portal — from referral intake to certificate issuance.
            Faster cycles, full compliance, zero chaos.
          </p>
          <div className="mt-8 flex gap-4">
            <button
              type="button"
              onClick={() => void signIn()}
              disabled={busy}
              className="rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in with Microsoft"}
            </button>
          </div>
          {errorMessage !== null && (
            <p
              role="alert"
              className="mt-6 max-w-xl rounded-md border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive-foreground"
            >
              {errorMessage}
            </p>
          )}
        </div>
      </main>

      <section
        id="features"
        className="border-t border-border bg-secondary/40"
        aria-labelledby="features-heading"
      >
        <div className="container py-16">
          <h2
            id="features-heading"
            className="text-center text-3xl font-semibold"
          >
            Everything you need to run a compliant internship program
          </h2>
          <p className="mt-2 text-center text-muted-foreground">
            Built for HR, IT, Admin, and Program Owners — with AI handling the
            heavy lifting.
          </p>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {[
              {
                title: "AI Resume Parsing",
                body:
                  "Extracts candidate details, skills, and education from resumes with 90%+ accuracy and confidence scoring.",
              },
              {
                title: "Automated Workflows",
                body:
                  "Event-driven notifications and tasks across HR, IT, Admin, and Compliance — with SLA tracking and escalation paths.",
              },
              {
                title: "Digital NDA & E-Sign",
                body:
                  "Issue and archive NDAs digitally via e-sign. Internship start is blocked until the document is fully executed.",
              },
            ].map((card) => (
              <div
                key={card.title}
                className="rounded-xl border border-border bg-card p-6 shadow-sm"
              >
                <h3 className="text-lg font-semibold">{card.title}</h3>
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
