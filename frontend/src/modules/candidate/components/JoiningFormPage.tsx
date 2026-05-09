import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { NexHireApiError } from "@/lib/axios";
import {
  getJoiningForm,
  saveJoiningForm,
  submitJoiningForm,
  type JoiningFormDraft,
} from "@/modules/candidate/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input as UiInput,
} from "@/shared/components/ui";

/**
 * S9 — Candidate joining form (multi-section, auto-saving).
 */
export function JoiningFormPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<JoiningFormDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submittingMessage, setSubmittingMessage] = useState<string | null>(
    null,
  );
  const lastSavedRef = useRef<string>("");

  useEffect(() => {
    void getJoiningForm()
      .then((data) => setForm(data))
      .catch((err) =>
        setError(
          err instanceof NexHireApiError ? err.message : "Could not load form.",
        ),
      );
  }, []);

  useEffect(() => {
    if (form === null || form.status === "LOCKED") return;
    const interval = window.setInterval(() => {
      void saveSnapshot(form, lastSavedRef, setForm, setError);
    }, 60_000);
    return () => window.clearInterval(interval);
  }, [form]);

  if (error !== null && form === null) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6">
        <p
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {error}
        </p>
      </div>
    );
  }
  if (form === null) {
    return (
      <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-12 text-sm text-muted-foreground sm:px-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading…
      </div>
    );
  }

  const editable = form.status !== "LOCKED";

  const update = <K extends keyof JoiningFormDraft>(
    key: K,
    value: JoiningFormDraft[K],
  ) => setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  const updateNested = (
    key: "personal_details" | "address" | "emergency_contact" | "govt_ids",
    field: string,
    value: string,
  ) => {
    setForm((prev) =>
      prev ? { ...prev, [key]: { ...prev[key], [field]: value } } : prev,
    );
  };

  const handleSubmit = async () => {
    if (!form.declaration_signed) {
      setError("Please tick the declaration before submitting.");
      return;
    }
    setError(null);
    try {
      await saveSnapshot(form, lastSavedRef, setForm, setError);
      const result = await submitJoiningForm();
      setSubmittingMessage(
        result.decision === "AUTO_LOCK"
          ? "Form auto-locked by AI. Proceeding to NDA…"
          : "Form submitted. HR is reviewing — you'll receive an email shortly.",
      );
      window.setTimeout(
        () => navigate(result.next_redirect, { replace: true }),
        1_500,
      );
    } catch (err) {
      setError(
        err instanceof NexHireApiError ? err.message : "Submission failed.",
      );
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Joining Form</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Auto-saves every minute. You can return via the link in your email
          for up to 72 hours.
        </p>
        <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          Status: <Badge variant="muted">{form.status}</Badge>
          <span>· version {form.version}</span>
        </p>
      </header>

      {error && (
        <p
          role="alert"
          className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}
      {submittingMessage && (
        <p className="mb-4 flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-3 py-2 text-sm text-stage-active">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {submittingMessage}
        </p>
      )}

      <Section title="Personal Details">
        <FieldInput
          label="Full name *"
          value={(form.personal_details.full_name as string) ?? ""}
          onChange={(v) => updateNested("personal_details", "full_name", v)}
          disabled={!editable}
        />
        <FieldInput
          label="Date of birth *"
          type="date"
          value={(form.personal_details.date_of_birth as string) ?? ""}
          onChange={(v) =>
            updateNested("personal_details", "date_of_birth", v)
          }
          disabled={!editable}
        />
      </Section>

      <Section title="Address">
        <FieldInput
          label="Current address"
          value={(form.address.current_address as string) ?? ""}
          onChange={(v) => updateNested("address", "current_address", v)}
          disabled={!editable}
        />
      </Section>

      <Section title="Emergency Contact">
        <FieldInput
          label="Contact name"
          value={(form.emergency_contact.name as string) ?? ""}
          onChange={(v) => updateNested("emergency_contact", "name", v)}
          disabled={!editable}
        />
        <FieldInput
          label="Contact phone"
          value={(form.emergency_contact.phone as string) ?? ""}
          onChange={(v) => updateNested("emergency_contact", "phone", v)}
          disabled={!editable}
        />
      </Section>

      <Section title="Government IDs">
        <FieldInput
          label="PAN number"
          value={(form.govt_ids.pan_number as string) ?? ""}
          onChange={(v) =>
            updateNested("govt_ids", "pan_number", v.toUpperCase())
          }
          disabled={!editable}
        />
      </Section>

      <Section title="Declaration">
        <label className="flex items-start gap-2 text-sm md:col-span-2">
          <input
            type="checkbox"
            checked={form.declaration_signed}
            onChange={(e) => update("declaration_signed", e.target.checked)}
            disabled={!editable}
            className="mt-1 h-4 w-4 rounded border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          />
          <span>
            I confirm that all information provided is accurate, and I consent
            to background verification.
          </span>
        </label>
      </Section>

      {editable && (
        <div className="mt-8 flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              void saveSnapshot(form, lastSavedRef, setForm, setError)
            }
          >
            Save draft
          </Button>
          <Button
            type="button"
            onClick={() => {
              void handleSubmit();
            }}
          >
            Submit form
          </Button>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">{children}</CardContent>
    </Card>
  );
}

function FieldInput({
  label,
  value,
  onChange,
  type = "text",
  disabled,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium">{label}</span>
      <UiInput
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    </label>
  );
}

async function saveSnapshot(
  form: JoiningFormDraft,
  lastSavedRef: React.MutableRefObject<string>,
  setForm: (f: JoiningFormDraft) => void,
  setError: (msg: string | null) => void,
) {
  if (form.status === "LOCKED") return;
  const snapshot = JSON.stringify({
    p: form.personal_details,
    a: form.address,
    e: form.emergency_contact,
    g: form.govt_ids,
    d: form.declaration_signed,
  });
  if (snapshot === lastSavedRef.current) return;
  try {
    const updated = await saveJoiningForm({
      expected_version: form.version,
      personal_details: form.personal_details,
      address: form.address,
      emergency_contact: form.emergency_contact,
      govt_ids: form.govt_ids,
      declaration_signed: form.declaration_signed,
    });
    setForm(updated);
    lastSavedRef.current = snapshot;
  } catch (err) {
    setError(
      err instanceof NexHireApiError ? err.message : "Auto-save failed.",
    );
  }
}
