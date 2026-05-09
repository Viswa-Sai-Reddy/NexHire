import { useRef, useState } from "react";
import { CheckCircle2, FileText, Sparkles, Upload } from "lucide-react";

import { useResumeUpload } from "@/modules/referral/hooks";
import type { ResumePrefillResponse } from "@/modules/referral/types";
import { Button } from "@/shared/components/ui";

const ALLOWED = ["application/pdf", "image/jpeg", "image/png"];
const ALLOWED_LABEL = "PDF, DOCX, JPG, PNG · 5MB max";

interface Props {
  onParsed: (result: ResumePrefillResponse) => void;
}

interface UploadedState {
  fileName: string;
  result: ResumePrefillResponse;
  filledCount: number;
}

const PREFILL_KEYS: (keyof ResumePrefillResponse)[] = [
  "candidate_name",
  "candidate_email",
  "candidate_phone",
  "candidate_year_of_study",
  "candidate_graduation_year",
  "college_name",
];

function countFilled(r: ResumePrefillResponse): number {
  let n = 0;
  for (const k of PREFILL_KEYS) {
    const v = r[k];
    if (v !== null && v !== undefined && v !== "") n += 1;
  }
  return n;
}

/**
 * AI-prefill upload card. Empty → parsing → parsed states.
 */
export function ResumeUploader({ onParsed }: Props) {
  const upload = useResumeUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<UploadedState | null>(null);
  const [pendingFileName, setPendingFileName] = useState<string | null>(null);

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
    setPendingFileName(file.name);
    try {
      const result = await upload.mutateAsync(file);
      onParsed(result);
      setUploaded({
        fileName: file.name,
        result,
        filledCount: countFilled(result),
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Upload failed. Please try again.",
      );
    } finally {
      setPendingFileName(null);
    }
  };

  const triggerPicker = () => inputRef.current?.click();

  if (uploaded !== null && !upload.isPending) {
    const { fileName, result, filledCount } = uploaded;
    const succeeded = result.succeeded !== false;
    const message = result.user_message;
    return (
      <div className="rounded-md border border-stage-active/30 bg-stage-active/10 p-5">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          className="sr-only"
          onChange={(e) => void handleFiles(e.target.files)}
        />
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <CheckCircle2
              className="mt-0.5 h-5 w-5 shrink-0 text-stage-active"
              aria-hidden
            />
            <div>
              <p className="text-sm font-medium text-stage-active">
                Resume uploaded: {fileName}
              </p>
              <p className="mt-1 text-xs text-stage-active/80">
                {succeeded
                  ? filledCount > 0
                    ? `AI auto-filled ${filledCount} field${filledCount === 1 ? "" : "s"} below — review and edit anything that's wrong.`
                    : "AI parsing returned no extractable fields. Please fill the form manually."
                  : message ||
                    "AI parsing didn't succeed. Please fill the form manually."}
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={triggerPicker}
            className="shrink-0"
          >
            Replace
          </Button>
        </div>
      </div>
    );
  }

  if (upload.isPending) {
    return (
      <div
        className="rounded-md border border-stage-submitted/30 bg-stage-submitted/10 p-6"
        role="status"
        aria-live="polite"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          className="sr-only"
          onChange={(e) => void handleFiles(e.target.files)}
        />
        <div className="flex items-start gap-3">
          <FileText
            className="mt-0.5 h-5 w-5 shrink-0 text-stage-submitted"
            aria-hidden
          />
          <div className="flex-1">
            <p className="text-sm font-medium text-stage-submitted">
              Parsing {pendingFileName ?? "resume"}…
            </p>
            <p className="mt-1 text-xs text-stage-submitted/80">
              Uploading + extracting text…
            </p>
            <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-stage-submitted/20">
              <div className="h-full w-1/3 animate-pulse bg-stage-submitted" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-dashed border-border bg-card p-8 text-center">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        className="sr-only"
        onChange={(e) => void handleFiles(e.target.files)}
      />
      <button
        type="button"
        onClick={triggerPicker}
        className="mx-auto flex flex-col items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span
          aria-hidden
          className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary"
        >
          <Upload className="h-5 w-5" />
        </span>
        <span className="text-sm font-medium">
          Upload resume for AI parsing
        </span>
        <span className="text-xs text-muted-foreground">{ALLOWED_LABEL}</span>
      </button>
      <p className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
        <Sparkles className="h-3 w-3" aria-hidden />
        AI Resume Parsing Enabled
      </p>
      {error !== null && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
