import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { NexHireApiError } from "@/lib/axios";
import {
  getJoiningForm,
  saveJoiningForm,
  submitJoiningForm,
  type JoiningFormDraft,
} from "@/modules/candidate/api";

/**
 * S9 — Candidate joining form.
 *
 * Multi-section, optimistic-locked, auto-saves every 60s. The form
 * submission triggers AI-6 cross-validation (auto-lock or route-to-HR).
 *
 * Sections in v1: Personal Details · Address · Emergency Contact ·
 * Education · Government IDs · Declaration. Document uploads land in
 * a follow-up turn.
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

  // Auto-save loop (60s) when the form is editable.
  useEffect(() => {
    if (form === null || form.status === "LOCKED") return;
    const interval = window.setInterval(() => {
      void saveSnapshot(form, lastSavedRef, setForm, setError);
    }, 60_000);
    return () => window.clearInterval(interval);
  }, [form]);

  if (error !== null && form === null) {
    return (
      <div className="container py-12">
        <p
          role="alert"
          className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      </div>
    );
  }
  if (form === null) {
    return (
      <div className="container py-12 text-sm text-muted-foreground">
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
      window.setTimeout(() => navigate(result.next_redirect, { replace: true }), 1_500);
    } catch (err) {
      setError(
        err instanceof NexHireApiError ? err.message : "Submission failed.",
      );
    }
  };

  return (
    <div className="container py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Joining Form</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Auto-saves every minute. You can return via the link in your email
          for up to 72 hours.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Status: <strong>{form.status}</strong> · version {form.version}
        </p>
      </header>

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      )}
      {submittingMessage && (
        <p className="mb-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {submittingMessage}
        </p>
      )}

      <Section title="Personal Details">
        <Input
          label="Full name *"
          value={(form.personal_details.full_name as string) ?? ""}
          onChange={(v) => updateNested("personal_details", "full_name", v)}
          disabled={!editable}
        />
        <Input
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
        <Input
          label="Current address"
          value={(form.address.current_address as string) ?? ""}
          onChange={(v) => updateNested("address", "current_address", v)}
          disabled={!editable}
        />
      </Section>

      <Section title="Emergency Contact">
        <Input
          label="Contact name"
          value={(form.emergency_contact.name as string) ?? ""}
          onChange={(v) => updateNested("emergency_contact", "name", v)}
          disabled={!editable}
        />
        <Input
          label="Contact phone"
          value={(form.emergency_contact.phone as string) ?? ""}
          onChange={(v) => updateNested("emergency_contact", "phone", v)}
          disabled={!editable}
        />
      </Section>

      <Section title="Government IDs">
        <Input
          label="PAN number"
          value={(form.govt_ids.pan_number as string) ?? ""}
          onChange={(v) =>
            updateNested("govt_ids", "pan_number", v.toUpperCase())
          }
          disabled={!editable}
        />
      </Section>

      <Section title="Declaration">
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.declaration_signed}
            onChange={(e) => update("declaration_signed", e.target.checked)}
            disabled={!editable}
            className="mt-1"
          />
          <span>
            I confirm that all information provided is accurate, and I consent
            to background verification.
          </span>
        </label>
      </Section>

      {editable && (
        <div className="mt-8 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() =>
              void saveSnapshot(form, lastSavedRef, setForm, setError)
            }
            className="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-secondary"
          >
            Save draft
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Submit form
          </button>
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
    <section className="mb-6 rounded-xl border border-border bg-card p-6 shadow-sm">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">{children}</div>
    </section>
  );
}

function Input({
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
    <label className="block text-sm">
      <span className="font-medium">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="mt-1 w-full rounded-md border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-60"
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
