import { usePanCheck } from "@/modules/referral/hooks";
import type { PanVerdict } from "@/modules/referral/types";

interface Props {
  value: string;
  onChange: (next: string) => void;
  onVerdictChange: (verdict: PanVerdict | null) => void;
}

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

/**
 * PAN input with realtime F-40 verdict banner.
 *
 * The hook debounces 350ms so we don't fire a request per keystroke.
 * `onVerdictChange` lets the wizard host disable the "Next" button
 * for HARD_BLOCK / COOLING_BLOCK without re-fetching.
 */
export function PanField({ value, onChange, onVerdictChange }: Props) {
  const cleaned = value.trim().toUpperCase();
  const isValidShape = PAN_RE.test(cleaned);
  const check = usePanCheck(cleaned);

  // Bubble verdict changes up.
  const verdict = check.data?.verdict ?? null;
  if (verdict !== null) onVerdictChange(verdict);

  return (
    <div className="space-y-2">
      <label
        htmlFor="pan"
        className="block text-sm font-medium"
      >
        PAN Card Number *
      </label>
      <input
        id="pan"
        type="text"
        autoComplete="off"
        spellCheck={false}
        maxLength={10}
        value={cleaned}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        placeholder="ABCDE1234F"
        aria-invalid={value.length > 0 && !isValidShape}
        className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-sm uppercase focus:outline-none focus:ring-2 focus:ring-primary"
      />
      <p className="text-xs text-muted-foreground">
        We use this to prevent duplicate referrals across HRs.
        Stored encrypted; HR sees a masked form by default.
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
      <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
        ✅ {data.message}
      </p>
    );
  }
  if (data.verdict === "HARD_BLOCK") {
    return (
      <div role="alert" className="rounded-md bg-destructive/10 p-3 text-sm">
        <p className="font-medium text-destructive">⛔ {data.message}</p>
        <p className="mt-1 text-xs text-destructive/80">
          PAN is a unique government identifier — override is not permitted.
        </p>
      </div>
    );
  }
  if (data.verdict === "COOLING_BLOCK") {
    return (
      <div role="alert" className="rounded-md bg-amber-50 p-3 text-sm">
        <p className="font-medium text-amber-900">⏳ {data.message}</p>
        {data.cooling_days_remaining !== null && data.cooling_days_remaining !== undefined && (
          <p className="mt-1 text-xs text-amber-800">
            {data.cooling_days_remaining} days remaining · ends {data.cooling_end}
          </p>
        )}
        {data.allow_override && (
          <p className="mt-2 text-xs text-amber-900/80">
            Program Owner can override this with justification.
          </p>
        )}
      </div>
    );
  }
  return (
    <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
      ⚠️ {data.message}
    </p>
  );
}
