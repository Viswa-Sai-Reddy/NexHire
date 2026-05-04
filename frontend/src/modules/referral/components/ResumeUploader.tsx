import { useRef, useState } from "react";

import { useResumeUpload } from "@/modules/referral/hooks";
import type { ResumePrefillResponse } from "@/modules/referral/types";

const ALLOWED = ["application/pdf", "image/jpeg", "image/png"];
const ALLOWED_LABEL = "PDF, DOCX, JPG, PNG · 5MB max";

interface Props {
  onParsed: (result: ResumePrefillResponse) => void;
}

/**
 * AI-prefill upload card. Mirrors the InternFlow visual reference:
 * dotted-border drop zone with the "AI Resume Parsing Enabled" pill.
 */
export function ResumeUploader({ onParsed }: Props) {
  const upload = useResumeUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const file = files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("File size exceeds the 5MB limit.");
      return;
    }
    if (!ALLOWED.includes(file.type) && !file.name.endsWith(".docx")) {
      setError("Only PDF, DOCX, JPG, and PNG are accepted.");
      return;
    }
    setError(null);
    try {
      const result = await upload.mutateAsync(file);
      onParsed(result);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Upload failed. Please try again.",
      );
    }
  };

  return (
    <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        className="sr-only"
        onChange={(e) => void handleFiles(e.target.files)}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={upload.isPending}
        className="mx-auto flex flex-col items-center gap-2 disabled:opacity-60"
      >
        <span aria-hidden className="text-2xl">📄</span>
        <span className="text-sm font-medium">
          {upload.isPending ? "Parsing resume…" : "Upload resume for AI parsing"}
        </span>
        <span className="text-xs text-muted-foreground">{ALLOWED_LABEL}</span>
      </button>
      <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
        ⚡ AI Resume Parsing Enabled
      </p>
      {error !== null && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
