import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  Sparkles,
} from "lucide-react";

import { ConfidenceBadge } from "@/shared/components/ConfidenceBadge";
import { CollegeCombobox } from "@/modules/referral/components/CollegeCombobox";
import { MentorPicker } from "@/modules/referral/components/MentorPicker";
import { PanField } from "@/modules/referral/components/PanField";
import { ResumeUploader } from "@/modules/referral/components/ResumeUploader";
import { Stepper } from "@/modules/referral/components/Stepper";
import { searchColleges } from "@/modules/referral/api";
import { useCollegeCap, useSubmitReferral } from "@/modules/referral/hooks";
import { NexHireApiError } from "@/lib/axios";
import type {
  CollegeSearchResult,
  PanVerdict,
  ReferralSubmitRequest,
  ResumePrefillResponse,
} from "@/modules/referral/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Textarea,
} from "@/shared/components/ui";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "candidate", label: "Candidate Details" },
  { key: "eligibility", label: "Eligibility Check" },
  { key: "mentor", label: "Mentor Selection" },
  { key: "details", label: "Internship Details" },
  { key: "review", label: "Review & Submit" },
];

const RELATIONSHIP_OPTIONS = [
  "None",
  "Family",
  "Friend",
  "Acquaintance",
  "Other",
];

type AiStatus = "idle" | "running" | "done" | "failed";

interface FormState {
  candidate_name: string;
  candidate_email: string;
  candidate_phone: string;
  candidate_pan: string;
  candidate_year_of_study: 2 | 3 | 4 | "";
  candidate_graduation_year: number | "";
  college: CollegeSearchResult | null;
  resume_document_id: string | null;
  resumePrefill: ResumePrefillResponse | null;

  unpaid_consent: boolean;
  inperson_ready: boolean;
  relationship_declaration: string;
  relationship_declaration_detail: string;

  mentor_id: string | null;

  project_title: string;
  project_overview: string;
  joining_location: string;
  internship_start_date: string;
  internship_end_date: string;
}

const INITIAL_STATE: FormState = {
  candidate_name: "",
  candidate_email: "",
  candidate_phone: "",
  candidate_pan: "",
  candidate_year_of_study: "",
  candidate_graduation_year: "",
  college: null,
  resume_document_id: null,
  resumePrefill: null,
  unpaid_consent: false,
  inperson_ready: false,
  relationship_declaration: "None",
  relationship_declaration_detail: "",
  mentor_id: null,
  project_title: "",
  project_overview: "",
  joining_location: "",
  internship_start_date: "",
  internship_end_date: "",
};

export function ReferralFormPage() {
  const [state, setState] = useState<FormState>(INITIAL_STATE);
  const [stepIndex, setStepIndex] = useState(0);
  const [panVerdict, setPanVerdict] = useState<PanVerdict | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [attemptedSteps, setAttemptedSteps] = useState<Set<number>>(new Set());
  const [aiStatus, setAiStatus] = useState<AiStatus>("idle");

  const submit = useSubmitReferral();
  const collegeCap = useCollegeCap(state.college?.id ?? null);
  const navigate = useNavigate();

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  const applyResumePrefill = (result: ResumePrefillResponse) => {
    setState((prev) => ({
      ...prev,
      resumePrefill: result,
      resume_document_id: result.document_id,
      candidate_name: result.candidate_name ?? prev.candidate_name,
      candidate_email: result.candidate_email ?? prev.candidate_email,
      candidate_phone: result.candidate_phone ?? prev.candidate_phone,
      candidate_year_of_study:
        (result.candidate_year_of_study as 2 | 3 | 4 | undefined) ??
        prev.candidate_year_of_study,
      candidate_graduation_year:
        result.candidate_graduation_year ?? prev.candidate_graduation_year,
    }));

    if (result.college_name) {
      void (async () => {
        try {
          const matches = await searchColleges(result.college_name as string, {
          skipCache: true,
        });
          const first = matches[0];
          if (first !== undefined) {
            setState((prev) =>
              prev.college === null ? { ...prev, college: first } : prev,
            );
          }
        } catch {
          // Best-effort.
        }
      })();
    }
  };

  const onResumeParsed = (result: ResumePrefillResponse) => {
    applyResumePrefill(result);
  };

  const completed = useMemo(() => {
    const set = new Set<number>();
    for (let i = 0; i < stepIndex; i++) set.add(i);
    return set;
  }, [stepIndex]);

  const stepValid = useMemo(
    () =>
      isStepValid(
        stepIndex,
        state,
        panVerdict,
        collegeCap.data?.can_submit ?? true,
      ),
    [stepIndex, state, panVerdict, collegeCap.data],
  );

  const handleSubmit = async () => {
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      const body = toSubmitRequest(state);
      const result = await submit.mutateAsync(body);
      setState(INITIAL_STATE);
      setStepIndex(0);
      setPanVerdict(null);
      navigate("/referrals/mine", {
        replace: true,
        state: {
          submittedReferralId: result.referral_id,
          flash: `Referral submitted (#${result.referral_id.slice(0, 8)}). Mentor will be notified.`,
        },
      });
    } catch (err) {
      if (err instanceof NexHireApiError) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Submission failed. Please try again.");
      }
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Submit Internship Referral
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            All referrals must be submitted through this portal. Fields marked
            <span className="text-destructive"> *</span> are mandatory.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/referrals/mine">View my referrals</Link>
        </Button>
      </header>

      <Card className="mb-6">
        <CardContent className="p-5 sm:p-6">
          <Stepper
            steps={STEPS}
            currentIndex={stepIndex}
            completedIndexes={completed}
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          {stepIndex === 0 && (
            <Step1Candidate
              state={state}
              update={update}
              onResumeParsed={onResumeParsed}
              onPanVerdict={setPanVerdict}
              panVerdict={panVerdict}
              collegeCap={collegeCap.data}
              showErrors={attemptedSteps.has(0)}
              aiStatus={aiStatus}
            />
          )}
          {stepIndex === 1 && <Step2Eligibility state={state} update={update} />}
          {stepIndex === 2 && <Step3Mentor state={state} update={update} />}
          {stepIndex === 3 && (
            <Step4Internship
              state={state}
              update={update}
              showErrors={attemptedSteps.has(3)}
            />
          )}
          {stepIndex === 4 && (
            <Step5Review
              state={state}
              onBack={() => setStepIndex(3)}
              onSubmit={() => {
                void handleSubmit();
              }}
              isSubmitting={submit.isPending}
              error={submitError}
              success={submitSuccess}
            />
          )}
        </CardContent>
      </Card>

      {stepIndex < STEPS.length - 1 && (
        <div className="mt-6 flex items-center justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={() => setStepIndex((i) => Math.max(i - 1, 0))}
            disabled={stepIndex === 0}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back
          </Button>
          <Button
            type="button"
            onClick={() => {
              if (stepValid) {
                setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
              } else {
                setAttemptedSteps((s) => {
                  if (s.has(stepIndex)) return s;
                  const next = new Set(s);
                  next.add(stepIndex);
                  return next;
                });
              }
            }}
          >
            {stepIndex === STEPS.length - 2 ? "Review" : "Next"}
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      )}
    </div>
  );
}

/* ───────────── Step 1 — Candidate Basics ───────────── */
function Step1Candidate({
  state,
  update,
  onResumeParsed,
  onPanVerdict,
  panVerdict,
  collegeCap,
  showErrors,
  aiStatus,
}: {
  state: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  onResumeParsed: (r: ResumePrefillResponse) => void;
  onPanVerdict: (v: PanVerdict | null) => void;
  panVerdict: PanVerdict | null;
  collegeCap: ReturnType<typeof useCollegeCap>["data"];
  showErrors: boolean;
  aiStatus: AiStatus;
}) {
  const p = state.resumePrefill;
  const aiBusy = aiStatus === "running";

  const yearFlash = useFillFlash(state.candidate_year_of_study, aiStatus);
  const gradYearFlash = useFillFlash(
    state.candidate_graduation_year,
    aiStatus,
  );
  const collegeFlash = useFillFlash(state.college, aiStatus);

  const nameLen = state.candidate_name.trim().length;
  const phoneLen = state.candidate_phone.trim().length;
  const rawNameError =
    nameLen === 0
      ? "Full name is required."
      : nameLen < 2
        ? "Full name must be at least 2 characters."
        : null;
  const rawEmailError =
    state.candidate_email.length === 0
      ? "Email address is required."
      : !/\S+@\S+\.\S+/.test(state.candidate_email)
        ? "Enter a valid email address."
        : null;
  const rawPhoneError =
    phoneLen === 0
      ? "Phone number is required."
      : phoneLen < 6
        ? "Phone number must be at least 6 digits."
        : null;
  const rawCollegeError =
    state.college === null ? "Select a college from the list." : null;
  const rawYearError =
    state.candidate_year_of_study === ""
      ? "Select the candidate's current year of study."
      : null;
  const rawGradYearError =
    typeof state.candidate_graduation_year !== "number"
      ? "Expected graduation year is required."
      : null;

  const rawPanError =
    state.candidate_pan.length === 0
      ? "PAN card number is required."
      : state.candidate_pan.length !== 10
        ? "PAN must be exactly 10 characters (e.g. ABCDE1234F)."
        : panVerdict === "HARD_BLOCK"
          ? "This PAN is blocked from referrals (active duplicate). Please verify with HR."
          : panVerdict === "COOLING_BLOCK"
            ? "This candidate is in a cooling-off period. A new referral can be submitted later."
            : panVerdict === null
              ? "PAN check is still running — please wait a moment."
              : null;

  const nameError = showErrors ? rawNameError : null;
  const emailError = showErrors ? rawEmailError : null;
  const phoneError = showErrors ? rawPhoneError : null;
  const collegeError = showErrors ? rawCollegeError : null;
  const yearError = showErrors ? rawYearError : null;
  const gradYearError = showErrors ? rawGradYearError : null;
  const panError = showErrors ? rawPanError : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Candidate Details
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a resume for AI-assisted prefill, or enter details manually.
        </p>
      </div>

      <ResumeUploader onParsed={onResumeParsed} />

      <AiAnalysisBanner status={aiStatus} />

      <div className="grid gap-4 md:grid-cols-2">
        <Field
          label="Full Name *"
          confidence={p?.candidate_name_confidence ?? null}
          error={nameError}
        >
          <Input
            type="text"
            value={state.candidate_name}
            onChange={(e) => update("candidate_name", e.target.value)}
            placeholder="Candidate full name"
            className={confidenceTint(p?.candidate_name_confidence)}
          />
        </Field>
        <Field
          label="Email Address *"
          confidence={p?.candidate_email_confidence ?? null}
          error={emailError}
        >
          <Input
            type="email"
            value={state.candidate_email}
            onChange={(e) => update("candidate_email", e.target.value)}
            placeholder="candidate@university.edu"
            className={confidenceTint(p?.candidate_email_confidence)}
          />
        </Field>
        <Field
          label="Phone Number *"
          confidence={p?.candidate_phone_confidence ?? null}
          error={phoneError}
        >
          <Input
            type="tel"
            value={state.candidate_phone}
            onChange={(e) => update("candidate_phone", e.target.value)}
            placeholder="+91 XXXXX XXXXX"
            className={confidenceTint(p?.candidate_phone_confidence)}
          />
        </Field>
        <Field label="University / Institution *" error={collegeError}>
          <div
            className={cn(
              "rounded-md transition-colors",
              collegeFlash && "bg-stage-active/10",
            )}
          >
            <CollegeCombobox
              value={state.college}
              onChange={(c) => update("college", c)}
              placeholder={
                aiBusy ? "AI analyzing…" : "Type college name (e.g. VIT)"
              }
            />
          </div>
          {collegeCap && state.college && (
            <CollegeCapHint
              used={collegeCap.used}
              limit={collegeCap.limit}
              warning={collegeCap.warning}
              canSubmit={collegeCap.can_submit}
            />
          )}
        </Field>
        <Field
          label="Year of Study *"
          confidence={p?.candidate_year_of_study_confidence ?? null}
          error={yearError}
        >
          <select
            value={state.candidate_year_of_study}
            onChange={(e) =>
              update(
                "candidate_year_of_study",
                e.target.value === ""
                  ? ""
                  : (Number(e.target.value) as 2 | 3 | 4),
              )
            }
            className={cn(
              selectClass,
              confidenceTint(p?.candidate_year_of_study_confidence),
              yearFlash && "bg-stage-active/10",
            )}
          >
            <option value="">
              {aiBusy ? "Select year (AI analyzing…)" : "Select year"}
            </option>
            <option value={2}>2nd Year</option>
            <option value={3}>3rd Year</option>
            <option value={4}>4th Year</option>
          </select>
        </Field>
        <Field
          label="Expected Graduation Year *"
          confidence={p?.candidate_graduation_year_confidence ?? null}
          error={gradYearError}
        >
          <Input
            type="number"
            min={2025}
            max={2035}
            value={state.candidate_graduation_year}
            onChange={(e) =>
              update(
                "candidate_graduation_year",
                e.target.value === "" ? "" : Number(e.target.value),
              )
            }
            placeholder={aiBusy ? "AI analyzing…" : "e.g. 2027"}
            className={cn(
              confidenceTint(p?.candidate_graduation_year_confidence),
              gradYearFlash && "bg-stage-active/10",
            )}
          />
        </Field>
        <div className="md:col-span-2">
          <PanField
            value={state.candidate_pan}
            onChange={(v) => update("candidate_pan", v)}
            onVerdictChange={onPanVerdict}
          />
          {panError !== null && (
            <p className="mt-1 text-xs text-destructive" role="alert">
              {panError}
            </p>
          )}
        </div>
      </div>

      {p?.skills && p.skills.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Key Skills (AI-extracted)</h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {p.skills.map((s) => (
              <Badge key={s} variant="muted">
                {s}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ───────────── Step 2 — Eligibility ───────────── */
function Step2Eligibility({
  state,
  update,
}: {
  state: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Eligibility Check
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Both consent boxes are required by NexHire policy.
        </p>
      </div>

      <CheckboxRow
        label="Candidate confirms acceptance of the unpaid internship terms."
        checked={state.unpaid_consent}
        onChange={(v) => update("unpaid_consent", v)}
      />
      <CheckboxRow
        label="Candidate confirms in-person availability at the joining location."
        checked={state.inperson_ready}
        onChange={(v) => update("inperson_ready", v)}
      />

      <Field label="Relationship to candidate">
        <select
          value={state.relationship_declaration}
          onChange={(e) => update("relationship_declaration", e.target.value)}
          className={selectClass}
        >
          {RELATIONSHIP_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </Field>
      {state.relationship_declaration === "Other" && (
        <Field label="Please describe">
          <Input
            type="text"
            value={state.relationship_declaration_detail}
            onChange={(e) =>
              update("relationship_declaration_detail", e.target.value)
            }
          />
        </Field>
      )}
    </div>
  );
}

/* ───────────── Step 3 — Mentor ───────────── */
function Step3Mentor({
  state,
  update,
}: {
  state: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
}) {
  const skills = state.resumePrefill?.skills ?? [];
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Mentor Selection
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          AI-2 ranks the top 3 mentors based on skill overlap, capacity,
          completion history, college familiarity, and response speed. Use
          "Browse all" to see every mentor.
        </p>
      </div>
      <MentorPicker
        value={state.mentor_id}
        onChange={(id) => update("mentor_id", id)}
        collegeId={state.college?.id ?? null}
        candidateSkills={skills}
      />
    </div>
  );
}

/* ───────────── Step 4 — Internship Details ───────────── */
function Step4Internship({
  state,
  update,
  showErrors,
}: {
  state: FormState;
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  showErrors: boolean;
}) {
  const titleLen = state.project_title.trim().length;
  const locationLen = state.joining_location.trim().length;

  const rawTitleError =
    titleLen === 0
      ? "Project title is required."
      : titleLen < 3
        ? "Project title must be at least 3 characters."
        : null;
  const rawLocationError =
    locationLen === 0
      ? "Joining location is required."
      : locationLen < 2
        ? "Joining location must be at least 2 characters."
        : null;
  const rawStartError = state.internship_start_date
    ? null
    : "Start date is required.";
  const rawEndError = state.internship_end_date
    ? null
    : "End date is required.";

  let rawDateRangeError: string | null = null;
  if (state.internship_start_date && state.internship_end_date) {
    const start = new Date(state.internship_start_date);
    const end = new Date(state.internship_end_date);
    const days = Math.round(
      (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24),
    );
    if (Number.isFinite(days)) {
      if (days < 28) {
        rawDateRangeError = `Duration is ${days} days — minimum is 28 days (4 weeks).`;
      } else if (days > 182) {
        rawDateRangeError = `Duration is ${days} days — maximum is 182 days (26 weeks).`;
      }
    }
  }

  const titleError = showErrors ? rawTitleError : null;
  const locationError = showErrors ? rawLocationError : null;
  const startError = showErrors ? rawStartError : null;
  const endError = showErrors ? rawEndError : null;
  const dateRangeError = showErrors ? rawDateRangeError : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Internship Details
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Duration must be between 4 and 26 weeks.
        </p>
      </div>
      <Field
        label="Project Title *"
        error={titleError}
        hint={titleError ? null : "At least 3 characters."}
      >
        <Input
          type="text"
          value={state.project_title}
          onChange={(e) => update("project_title", e.target.value)}
          maxLength={255}
          placeholder="e.g. Mobile checkout redesign"
        />
      </Field>
      <Field label="Project Overview">
        <Textarea
          value={state.project_overview}
          onChange={(e) => update("project_overview", e.target.value)}
          rows={3}
          maxLength={2000}
        />
      </Field>
      <Field label="Joining Location *" error={locationError}>
        <Input
          type="text"
          value={state.joining_location}
          onChange={(e) => update("joining_location", e.target.value)}
          placeholder="Bangalore, IN"
        />
      </Field>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Start Date *" error={startError}>
          <Input
            type="date"
            value={state.internship_start_date}
            onChange={(e) => update("internship_start_date", e.target.value)}
          />
        </Field>
        <Field label="End Date *" error={endError ?? dateRangeError}>
          <Input
            type="date"
            value={state.internship_end_date}
            onChange={(e) => update("internship_end_date", e.target.value)}
          />
        </Field>
      </div>
    </div>
  );
}

/* ───────────── Step 5 — Review ───────────── */
function Step5Review({
  state,
  onBack,
  onSubmit,
  isSubmitting,
  error,
  success,
}: {
  state: FormState;
  onBack: () => void;
  onSubmit: () => void;
  isSubmitting: boolean;
  error: string | null;
  success: string | null;
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold tracking-tight">Review & Submit</h2>

      <div className="grid gap-4 rounded-md border border-border/60 bg-secondary/30 p-4 text-sm md:grid-cols-2">
        <Pair label="Candidate" value={state.candidate_name} />
        <Pair label="Email" value={state.candidate_email} />
        <Pair label="Phone" value={state.candidate_phone} />
        <Pair label="PAN" value={maskedPan(state.candidate_pan)} />
        <Pair
          label="College"
          value={state.college?.canonical_name ?? "—"}
        />
        <Pair
          label="Year of Study"
          value={String(state.candidate_year_of_study)}
        />
        <Pair
          label="Graduation Year"
          value={String(state.candidate_graduation_year)}
        />
        <Pair
          label="Mentor selected"
          value={state.mentor_id ? "Yes" : "—"}
        />
        <Pair label="Project" value={state.project_title} />
        <Pair label="Location" value={state.joining_location} />
        <Pair
          label="Duration"
          value={`${state.internship_start_date} → ${state.internship_end_date}`}
        />
        <Pair
          label="Consents"
          value={
            state.unpaid_consent && state.inperson_ready ? "Confirmed" : "—"
          }
        />
      </div>

      {error !== null && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}
      {success !== null && (
        <p className="flex items-start gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-3 py-2 text-sm text-stage-active">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {success}
        </p>
      )}

      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="outline"
          onClick={onBack}
          disabled={isSubmitting}
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back
        </Button>
        <Button type="button" onClick={onSubmit} disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Submit Referral"}
        </Button>
      </div>
    </div>
  );
}

/* ───────────── Helpers ───────────── */
const selectClass =
  "flex h-9 w-full rounded-md border border-border bg-card px-3 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50";

function Field({
  label,
  confidence,
  error,
  hint,
  children,
}: {
  label: string;
  confidence?: number | null;
  error?: string | null;
  hint?: string | null;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <div className="mb-1.5 flex items-center gap-2 font-medium">
        {label}
        <ConfidenceBadge confidence={confidence ?? null} />
      </div>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </label>
  );
}

function CheckboxRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 h-4 w-4 rounded border-border text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      />
      <span>{label}</span>
    </label>
  );
}

function CollegeCapHint({
  used,
  limit,
  warning,
  canSubmit,
}: {
  used: number;
  limit: number;
  warning: boolean;
  canSubmit: boolean;
}) {
  if (canSubmit && !warning) {
    return (
      <p className="mt-1 text-xs text-muted-foreground">
        {used} of {limit} referrals used from this college.
      </p>
    );
  }
  if (warning) {
    return (
      <p className="mt-1 flex items-center gap-1 text-xs text-stage-review">
        <AlertCircle className="h-3 w-3" aria-hidden />
        {used} of {limit} used. One more allowed from this college.
      </p>
    );
  }
  return (
    <p
      role="alert"
      className="mt-1 flex items-center gap-1 text-xs text-destructive"
    >
      <AlertCircle className="h-3 w-3" aria-hidden />
      Limit reached for this college ({used}/{limit}).
    </p>
  );
}

function Pair({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 font-medium">{value || "—"}</p>
    </div>
  );
}

function maskedPan(pan: string): string {
  const cleaned = pan.trim().toUpperCase();
  if (cleaned.length !== 10) return cleaned || "—";
  return `${cleaned.slice(0, 5)}****${cleaned.slice(9)}`;
}

function confidenceTint(confidence: number | null | undefined): string {
  const tinted =
    confidence !== null &&
    confidence !== undefined &&
    confidence < 0.9 &&
    confidence > 0;
  return tinted ? "border-stage-review/60 bg-stage-review/5" : "";
}

function AiAnalysisBanner({ status }: { status: AiStatus }) {
  const [hideTerminal, setHideTerminal] = useState(false);

  useEffect(() => {
    if (status === "done" || status === "failed") {
      setHideTerminal(false);
      const ms = status === "done" ? 2000 : 4000;
      const t = window.setTimeout(() => setHideTerminal(true), ms);
      return () => window.clearTimeout(t);
    }
    return;
  }, [status]);

  if (status === "idle") return null;
  if ((status === "done" || status === "failed") && hideTerminal) return null;

  if (status === "running") {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2 rounded-md border border-stage-submitted/30 bg-stage-submitted/10 px-4 py-2 text-sm text-stage-submitted"
      >
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        <span>
          AI is analyzing skills, college, and graduation details — this can
          take a few seconds.
        </span>
      </div>
    );
  }
  if (status === "done") {
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-md border border-stage-active/30 bg-stage-active/10 px-4 py-2 text-sm text-stage-active"
      >
        <Sparkles className="h-4 w-4" aria-hidden />
        AI analysis complete.
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="flex items-center gap-2 rounded-md border border-stage-review/30 bg-stage-review/10 px-4 py-2 text-sm text-stage-review"
    >
      <AlertCircle className="h-4 w-4" aria-hidden />
      AI analysis didn't complete — please fill these fields manually.
    </div>
  );
}

function useFillFlash(value: unknown, aiStatus: AiStatus): boolean {
  const prevRef = useRef(value);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    const wasEmpty =
      prevRef.current === null ||
      prevRef.current === undefined ||
      prevRef.current === "";
    const isFilled = value !== null && value !== undefined && value !== "";
    if (wasEmpty && isFilled && aiStatus === "running") {
      setFlash(true);
      const t = window.setTimeout(() => setFlash(false), 700);
      prevRef.current = value;
      return () => window.clearTimeout(t);
    }
    prevRef.current = value;
    return;
  }, [value, aiStatus]);

  return flash;
}

function isStepValid(
  index: number,
  s: FormState,
  panVerdict: PanVerdict | null,
  collegeCanSubmit: boolean,
): boolean {
  switch (index) {
    case 0:
      return (
        s.candidate_name.trim().length >= 2 &&
        /\S+@\S+\.\S+/.test(s.candidate_email) &&
        s.candidate_phone.trim().length >= 6 &&
        s.candidate_pan.length === 10 &&
        (panVerdict === "CLEAR" ||
          panVerdict === "WARN" ||
          panVerdict === "SOFT_BLOCK") &&
        s.college !== null &&
        collegeCanSubmit &&
        (s.candidate_year_of_study === 2 ||
          s.candidate_year_of_study === 3 ||
          s.candidate_year_of_study === 4) &&
        typeof s.candidate_graduation_year === "number"
      );
    case 1:
      return s.unpaid_consent && s.inperson_ready;
    case 2:
      return s.mentor_id !== null;
    case 3:
      return (
        s.project_title.trim().length >= 3 &&
        s.joining_location.trim().length >= 2 &&
        Boolean(s.internship_start_date) &&
        Boolean(s.internship_end_date)
      );
    default:
      return true;
  }
}

function toSubmitRequest(s: FormState): ReferralSubmitRequest {
  if (
    s.college === null ||
    s.mentor_id === null ||
    typeof s.candidate_graduation_year !== "number" ||
    (s.candidate_year_of_study !== 2 &&
      s.candidate_year_of_study !== 3 &&
      s.candidate_year_of_study !== 4)
  ) {
    throw new Error("Form is incomplete.");
  }
  return {
    candidate_name: s.candidate_name.trim(),
    candidate_email: s.candidate_email.trim().toLowerCase(),
    candidate_phone: s.candidate_phone.trim() || null,
    candidate_pan: s.candidate_pan.trim().toUpperCase(),
    college_id: s.college.id,
    candidate_year_of_study: s.candidate_year_of_study,
    candidate_graduation_year: s.candidate_graduation_year,
    unpaid_consent: s.unpaid_consent,
    inperson_ready: s.inperson_ready,
    relationship_declaration: s.relationship_declaration || null,
    relationship_declaration_detail: s.relationship_declaration_detail || null,
    mentor_id: s.mentor_id,
    project_title: s.project_title.trim(),
    project_overview: s.project_overview.trim() || null,
    joining_location: s.joining_location.trim(),
    internship_start_date: s.internship_start_date,
    internship_end_date: s.internship_end_date,
    resume_document_id: s.resume_document_id ?? null,
  };
}
