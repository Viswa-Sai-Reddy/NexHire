import { useEffect, useRef, useState } from "react";

import { NexHireApiError } from "@/lib/axios";

/**
 * Shared termination dialog (A20 — RULE-CP2 cooling applied server-side).
 *
 * Backend gates this with the `INITIATE_TERMINATION` permission, so the
 * caller only needs to pass the intern_id. The reason is required and
 * must be ≥10 characters per the Pydantic contract.
 */
export function TerminationDialog({
  candidateName,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  candidateName: string;
  busy: boolean;
  error: string | null;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const tooShort = reason.trim().length < 10;

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-lg">
        <h2 className="text-lg font-semibold">Terminate internship</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Ends <strong>{candidateName}</strong>'s internship and applies the
          configured cooling period to their PAN.
        </p>

        <label
          htmlFor="termination-reason"
          className="mt-4 block text-xs font-medium uppercase tracking-wide text-muted-foreground"
        >
          Reason (≥ 10 characters)
        </label>
        <textarea
          id="termination-reason"
          ref={textareaRef}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={4}
          className="mt-1 w-full rounded-md border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="What happened? This is recorded in the audit trail."
        />

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="flex-1 rounded-md border border-border px-3 py-2 text-sm hover:bg-secondary disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(reason.trim())}
            disabled={busy || tooShort}
            className="flex-1 rounded-md bg-destructive px-3 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60"
          >
            {busy ? "Terminating…" : "Terminate"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function formatActionError(err: unknown): string {
  return err instanceof NexHireApiError ? err.message : "Action failed.";
}
