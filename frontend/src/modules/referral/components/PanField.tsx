import { AlertCircle, CheckCircle2, Clock, ShieldX } from "lucide-react";

import { usePanCheck } from "@/modules/referral/hooks";
import type { PanVerdict } from "@/modules/referral/types";
import { Input } from "@/shared/components/ui";

interface Props {
  value: string;
  onChange: (next: string) => void;
  onVerdictChange: (verdict: PanVerdict | null) => void;
}

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

export function PanField({ value, onChange, onVerdictChange }: Props) {
  const cleaned = value.trim().toUpperCase();
  const isValidShape = PAN_RE.test(cleaned);
  const check = usePanCheck(cleaned);

  const verdict = check.data?.verdict ?? null;
  if (verdict !== null) onVerdictChange(verdict);

  return (
    <div className="space-y-2">
      <label htmlFor="pan" className="block text-sm font-medium">
        PAN Card Number *
      </label>
      <Input
        id="pan"
        type="text"
        autoComplete="off"
        spellCheck={false}
        maxLength={10}
        value={cleaned}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        placeholder="ABCDE1234F"
        aria-invalid={value.length > 0 && !isValidShape}
        className="font-mono uppercase"
      />
      <p className="text-xs text-muted-foreground">
        We use this to prevent duplicate referrals across HRs. Stored
        encrypted; HR sees a masked form by default.
      </p>

      {value.length > 0 && !isValidShape && (
        <p role="alert" className="text-sm text-destructive">
          Format must be ABCDE1234F (5 letters · 4 digits · 1 letter).
        </p>
      )}

      {isValidShape && check.isLoading && (
        <p className="text-sm text-muted-foreground">Checking PAN…</p>
      )}

      {check.data && <PanVerdictBanner data={check.data} />}
    </div>
  );
}

function PanVerdictBanner({
  data,
}: {
  data: NonNullable<ReturnType<typeof usePanCheck>["data"]>;
}) {
  if (data.verdict === "CLEAR") {
    return (
      <p className="flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-3 py-2 text-sm text-stage-active">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        {data.message}
      </p>
    );
  }
  if (data.verdict === "HARD_BLOCK") {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm"
      >
        <p className="flex items-center gap-2 font-medium text-destructive">
          <ShieldX className="h-4 w-4" aria-hidden />
          {data.message}
        </p>
        <p className="mt-1 pl-6 text-xs text-destructive/80">
          PAN is a unique government identifier — override is not permitted.
        </p>
      </div>
    );
  }
  if (data.verdict === "COOLING_BLOCK") {
    return (
      <div
        role="alert"
        className="rounded-md border border-stage-review/30 bg-stage-review/10 p-3 text-sm"
      >
        <p className="flex items-center gap-2 font-medium text-stage-review">
          <Clock className="h-4 w-4" aria-hidden />
          {data.message}
        </p>
        {data.cooling_days_remaining !== null &&
          data.cooling_days_remaining !== undefined && (
            <p className="mt-1 pl-6 text-xs text-stage-review/80">
              {data.cooling_days_remaining} days remaining · ends{" "}
              {data.cooling_end}
            </p>
          )}
        {data.allow_override && (
          <p className="mt-2 pl-6 text-xs text-stage-review/80">
            Program Owner can override this with justification.
          </p>
        )}
      </div>
    );
  }
  return (
    <p className="flex items-start gap-2 rounded-md border border-stage-review/30 bg-stage-review/10 px-3 py-2 text-sm text-stage-review">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      {data.message}
    </p>
  );
}
