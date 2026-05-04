import { cn } from "@/lib/utils";

export interface StepDef {
  key: string;
  label: string;
}

/**
 * Horizontal 4-step indicator matching the InternFlow UI sample. The
 * referral form has five logical steps but Step 5 (Review) sits as a
 * sub-state of "Review & Submit" — visually we show four pills.
 */
export function Stepper({
  steps,
  currentIndex,
  completedIndexes,
}: {
  steps: StepDef[];
  currentIndex: number;
  completedIndexes: ReadonlySet<number>;
}) {
  return (
    <ol
      role="list"
      aria-label="Referral form steps"
      className="flex flex-wrap items-center gap-2 md:gap-4"
    >
      {steps.map((step, i) => {
        const isCurrent = i === currentIndex;
        const isDone = completedIndexes.has(i);
        return (
          <li key={step.key} className="flex items-center gap-2">
            <span
              aria-current={isCurrent ? "step" : undefined}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
                isDone
                  ? "bg-primary text-primary-foreground"
                  : isCurrent
                    ? "border border-primary bg-primary/10 text-primary"
                    : "border border-border bg-secondary text-muted-foreground",
              )}
            >
              {isDone ? "✓" : i + 1}
            </span>
            <span
              className={cn(
                "text-sm",
                isCurrent
                  ? "font-medium text-foreground"
                  : "text-muted-foreground",
              )}
            >
              {step.label}
            </span>
            {i < steps.length - 1 && (
              <span aria-hidden className="hidden h-px w-8 bg-border md:block" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
