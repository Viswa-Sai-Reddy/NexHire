import { forwardRef, type HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary/10 text-primary",
        muted:
          "border-border bg-secondary text-secondary-foreground/80",
        outline: "border-border text-foreground",
        success:
          "border-transparent bg-stage-active/10 text-stage-active",
        warning:
          "border-transparent bg-stage-review/10 text-stage-review",
        danger:
          "border-transparent bg-destructive/10 text-destructive",
        // Stage palette aliases — semantic mirror of pipeline stages.
        submitted:
          "border-transparent bg-stage-submitted/10 text-stage-submitted",
        review:
          "border-transparent bg-stage-review/10 text-stage-review",
        onboarding:
          "border-transparent bg-stage-onboarding/10 text-stage-onboarding",
        nda: "border-transparent bg-stage-nda/10 text-stage-nda",
        active:
          "border-transparent bg-stage-active/10 text-stage-active",
        extended:
          "border-transparent bg-stage-extended/10 text-stage-extended",
        closure:
          "border-transparent bg-stage-closure/10 text-stage-closure",
        rejected:
          "border-transparent bg-stage-rejected/10 text-stage-rejected",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  ),
);
Badge.displayName = "Badge";

export { badgeVariants };
