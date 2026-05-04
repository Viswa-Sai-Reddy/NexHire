/**
 * Generic "you're past this stage" landing for the candidate.
 * S4 fills in NDA-specific UI; S5 fills in active/closure status.
 */
export function CandidateStatusPage() {
  return (
    <div className="container py-12">
      <div className="rounded-xl border border-border bg-card p-8 shadow-sm">
        <h1 className="text-2xl font-semibold">Your application is in progress</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          We're processing the next stage of your onboarding. We'll send you
          an email when there's something for you to do — please keep an eye
          on your inbox.
        </p>
      </div>
    </div>
  );
}
