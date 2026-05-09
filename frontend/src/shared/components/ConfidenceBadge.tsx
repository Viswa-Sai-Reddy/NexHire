import { cn } from "@/lib/utils";

/**
 * Visualizes AI prefill confidence (Blueprint §6.2):
 *   ≥ 0.90 → no badge (high confidence; stay quiet).
 *   0.75–0.89 → amber "AI Suggested".
 *   0.00–0.75 → red "Please verify".
 *
 * Hidden when `confidence` is null/undefined, exactly 0 (AI didn't
 * extract anything — the value came from the user, no need to nudge),
 * or ≥ 0.9.
 */
export function ConfidenceBadge({
  confidence,
  className,
}: {
  confidence: number | null | undefined;
  className?: string;
}) {
  if (
    confidence === null ||
    confidence === undefined ||
    confidence === 0 ||
    confidence >= 0.9
  ) {
    return null;
  }
  const low = confidence < 0.75;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        low
          ? "bg-destructive/10 text-destructive"
          : "bg-amber-100 text-amber-800",
        className,
      )}
      title={`AI confidence: ${Math.round(confidence * 100)}%`}
    >
      {low ? "Please verify" : "AI Suggested"}
      <span className="opacity-60">{Math.round(confidence * 100)}%</span>
    </span>
  );
}
