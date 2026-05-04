# NexHire — Implementation Plan & Decision Log

> **Purpose:** Authoritative record of every architectural and process decision made during the pre-build question pass for NexHire. Companion to [System_Blueprint.md](System_Blueprint.md) and [System_Flow.md](System_Flow.md). Supersedes any conflicting default in those documents (those docs remain the spec; this doc captures binding choices made on top of them).
>
> **Status:** STEP 3 (build-sequence proposal) complete. Awaiting user approval to start STEP 4 (build).

---

## Context

NexHire is an AI-powered intern referral management platform with two large authoritative spec docs:

- [System_Blueprint.md](System_Blueprint.md) — 4,680 lines, Sections 1–20: tech stack, RBAC, business rules (RULE-E1…CP7), workflows, FSMs, AI touchpoints (AI-1…AI-10), modular monolith architecture, full Postgres schema, error taxonomy, PAN integration, variable cooling periods, Program-Owner config management.
- [System_Flow.md](System_Flow.md) — 3,180 lines, F-01 through F-45: every actor flow + edge case, state machine, audit trail, AI auto-approval/lock/send engines, cooling-period override.

Tech stack (confirmed): React 18 + TS + TanStack Query + shadcn/ui · Python 3.12 FastAPI + SQLAlchemy 2.0 async + Alembic · Azure Postgres Flexible Server · Azure OpenAI (GPT-4o) · Azure AD/MSAL · Gmail API · OpenSign (self-hosted on ACI) · Azure Blob · Azure Redis · APScheduler · Azure App Service · Application Insights. Team size 3, single tenant.

---

## STEP 2 — Question Pass (~85 questions across 5 categories)

The full categorized question list is preserved below for traceability. **Answers** are captured in the "Decisions Locked" section that follows.

### A. Spec Ambiguities

| # | Question | Why it matters |
|---|---|---|
| A1 | **Auto-approval timing.** F-35 says clean referrals go MentorAccepted → AutoApprovalEngine → APPROVED, "replaces HR review task creation". But §4.1 still shows HR receiving a review notification. For the 80% clean path, do we (a) skip HR_REVIEW state entirely and jump MentorAccepted → APPROVED, or (b) transit through HR_REVIEW with `approved_by = AI_AUTO_APPROVAL` for audit symmetry? | Determines FSM transitions and `referral_status` enum. |
| A2 | **Sentinel actor for AI auto-actions.** What is `approved_by` / `locked_by` when AI is the actor? Options: a reserved `users` row (e.g., `AI_SYSTEM` UUID), `NULL` + a separate `auto_approved_by_ai` boolean, or a string sentinel? | Affects users table seeding, audit format, FK constraints. |
| A3 | **PAN encryption + searchability.** §18.2.1 says PAN is "encrypted at rest (AES-256)", but the unique index `idx_referrals_active_pan` and queries `WHERE candidate_pan = encrypt(:pan)` require **deterministic** encryption. Pick: (a) deterministic `pgp_sym_encrypt` with fixed IV via pgcrypto; (b) plaintext PAN column + separate `pan_hash` column (SHA-256 with pepper) for lookups, encrypted column for display; (c) AES-SIV via app layer? | This is load-bearing for duplicate detection. |
| A4 | **Mentor pool vs Role enum.** F-25 queries `WHERE u.role IN ('MENTOR','REFERRER')`, but §2 treats them as distinct roles. Can one employee hold multiple roles, or is "every employee with the right skill flag is a mentor candidate"? | Drives users table schema (single role vs role-set, eligibility flag). |
| A5 | **Candidate as `users` row.** §9.1 has `interns.user_id REFERENCES users(id)` but candidates have no Azure AD account. Do they get a `users` row with `role=CANDIDATE`, or is `interns.user_id` only set when AD is provisioned? | Auth model + RBAC scope. |
| A6 | **`referral_status` canonical enum.** Inferred from the FSM but never listed exhaustively. | Single source of truth. |
| A7 | **College name normalization.** RULE-E2 caps at 2 referrals per referrer per college, but college name is free-text. Master college list in DB? Fuzzy match? | Cap enforcement correctness. |
| A8 | **OpenSign reminder ownership.** F-16 says NexHire sends Day 1/2/3 reminders. OpenSign sends its own by default. Disable OpenSign reminders entirely? | Avoid double notifications. |
| A9 | **AI-7 timing precision.** §7 says T-48h. F-19 runs every 6 hours filtering `start_date = TODAY+2`. Net effect: check fires at "between T-48h and T-42h". Acceptable, or do we need a per-intern scheduler? | Trade-off — bulk job is simpler. |
| A10 | **OQ1: Auto-rejection notification.** Notify candidate too, or referrer only? |
| A11 | **OQ2: Re-submit after rejection.** Same referrer can resubmit same candidate? Cross-referrer reusable? |
| A12 | **OQ3: Business days definition.** Mon–Fri only? Indian National Holidays? Org-specific holidays? Where is the holiday source? |
| A13 | **OQ4: Internship duration.** Min and max weeks? |
| A14 | **OQ5: Mentor change after MENTOR_ACCEPTED.** If accepted mentor falls ill mid-flow, is reassignment supported? |
| A15 | **OQ7: Tell candidate the rejection reason?** Current templates say "could not proceed" without specifics. |
| A16 | **OQ8: Multiple extensions.** Cap on # of extensions per intern? |
| A17 | **HR_REJECTED candidate awareness.** §F-13 says "Candidate NOT notified at HR rejection". But RULE-CP4 puts a 3-month cooling on the PAN. Is the candidate aware their PAN is now blocked? |
| A18 | **CORRECTION_NEEDED workflow.** Referrer edits in place (same record, status reverts) or creates a new version? |
| A19 | **Closure feedback structure.** Mentor's closure_feedback (consumed by AI-8) — free text or structured? |
| A20 | **TERMINATED trigger.** Who initiates "early exit with reason → TERMINATED"? |
| A21 | **Recall enforcement model.** Auto-actions have recall windows. Are recalls (a) compensating actions executed when HR clicks the button, or (b) deferred until window closes? |

### B. Missing Technical Details (HOW)

| # | Question |
|---|---|
| B1 | **Frontend tooling.** Vite? Package manager: npm / pnpm / yarn? Node version? |
| B2 | **Python package manager.** `uv` or `poetry`? |
| B3 | **PDF library.** §8 mentions both `reportlab` and `weasyprint`. Pick one? |
| B4 | **Azure SDK choices.** Confirm `azure-identity`, `azure-storage-blob`, `azure-keyvault-secrets`, `openai` (Azure variant), `msgraph-sdk`. |
| B5 | **Routing library.** React Router v6/v7 or TanStack Router? |
| B6 | **Form library.** React Hook Form + Zod — confirm. |
| B7 | **In-process event bus.** Custom asyncio or library? |
| B8 | **APScheduler job store.** Same Postgres DB? |
| B9 | **Audit checksum chain concurrency.** How to handle race on concurrent inserts? |
| B10 | **Outbox table schema.** §17.9 references it but no DDL. |
| B11 | **Dead letter queue.** Service Bus mandatory at v1, or Postgres table? |
| B12 | **CSRF on action token GET endpoints.** State-changing GET — mitigation? |
| B13 | **CORS / origin model.** Same-origin or split? |
| B14 | **Azure Document Intelligence.** Provision separately, or use GPT-4o Vision? |
| B15 | **Timezones.** SLA hours = clock or business? |
| B16 | **Holiday calendar source.** Static seeded table, API, or per-org? |
| B17 | **Email DKIM/SPF/DMARC.** Sender domain confirmation. |
| B18 | **JWT key management.** RS256 — JWKS endpoint? `kid` rotation? |
| B19 | **PAN encryption key.** Single key with rotation, or per-environment? |
| B20 | **API versioning.** `/api/v1/...` from day 1? |
| B21 | **Rate limit numbers.** Per-role per-endpoint? |
| B22 | **File upload constraints.** 5MB; max files per joining form? |
| B23 | **AI cost tracking.** Per-touchpoint INR ceiling? Kill-switch threshold? |
| B24 | **Bottleneck Predictor cold start.** Phase-1 fallback? |
| B25 | **Magic-link flow.** SPA-loads-then-validates vs backend 302? |

### C. Environment & Infrastructure

| # | Question |
|---|---|
| C1 | Azure subscription/resource group/region — already provisioned? |
| C2 | PostgreSQL Flexible Server — created? Version? SKU? Networking? |
| C3 | Azure OpenAI — resource created? GPT-4o deployment name? Endpoint? Region? |
| C4 | Azure AD app registration — tenant ID, client ID, client secret? Graph API permission? |
| C5 | Gmail Workspace — service account JSON, domain-wide delegation, send-as alias? |
| C6 | OpenSign — ACI deployed? Webhook signing secret? Approved NDA template (OQ6)? |
| C7 | Local dev environment — docker-compose vs Azure-direct? |
| C8 | Repo & CI — GitHub repo URL? Monorepo? GitHub Actions enabled? |
| C9 | Application Insights — connection string? |
| C10 | Domain & TLS — public hostname? App Service Managed Cert? |
| C11 | Bootstrap users — first Program Owner email? |
| C12 | Backup/DR targets — RTO / RPO? |

### D. Development Preferences

| # | Question |
|---|---|
| D1 | Python lint/format. `ruff`? mypy strict? Line length? |
| D2 | TypeScript strictness. Strict mode? noUncheckedIndexedAccess? |
| D3 | Tests. Coverage target? Playwright at all? |
| D4 | Branch strategy. Trunk-based with feature branches? |
| D5 | Commit conventions. Conventional Commits? |
| D6 | Pydantic vs dataclasses. |
| D7 | Internationalization. English-only at launch? |
| D8 | Accessibility. WCAG 2.1 AA — automated testing? |
| D9 | Architecture Decision Records. Maintain `docs/adr/`? |
| D10 | Folder structure. Strict adherence to §14 layout, or open to refinements? |

### E. Spec Gaps

| # | Question |
|---|---|
| E1 | Reminder timestamp columns. F-42 references them but they're not in §9 or §19.3 schema. |
| E2 | Stage transition tracking. F-27 reads `current_stage` and `stage_entered_at` from referrals — schema doesn't define them. |
| E3 | Mentor stats / completion rate. AI-2 reads `mentor.completion_rate`, `avg_response_hours` — no `mentor_stats` table defined. |
| E4 | Stage duration stats. AI-5 reads `stage_duration_stats` — define table? |
| E5 | Joining-form-lock SLA. Spec gives SLA for ID issuance but not for HR locking the submitted form. |
| E6 | Out-of-office for users. F-29 reads `users.out_of_office_until`. No UI to set it. |
| E7 | HR assigned to a referral. F-27 references `assigned_hr_id`. Tracked how? |
| E8 | `document_type` enum values. Need explicit list. |
| E9 | Risk profile storage. §18.3 references `risk_repo` — no `risk_profiles` table in schema. |
| E10 | Duplicate check storage. §18.3 reads `ai_parse.duplicate_check` — column not defined. |
| E11 | `assigned_hr_id` for auto-routing. When a task is auto-routed, is the chosen user "owner" for downstream notifications too? |
| E12 | Action token table — referrer-side actions. Currently only MENTOR_RESPONSE and CANDIDATE_ACCESS. |
| E13 | Multiple gov IDs. Joining form lists Aadhaar/PAN/Passport. PAN is mandatory at referral. |
| E14 | Seed data. What gets seeded by Alembic on first migration? |
| E15 | `current_user` for system-acting flows. When schedulers fire, what `actor_user_id` is recorded? |
| E16 | Resume retention policy. When a candidate is rejected, does the resume PDF stay? |
| E17 | Recall window — locked-in compensating actions. |
| E18 | Mentor screen for closure feedback. S20 mentions "confirm closure" but no UI for the feedback. |
| E19 | HR PAN visibility. PII matrix says HR sees full record. Does that include unmasked PAN? |
| E20 | First-superuser bootstrap. Need first PO email. |

---

## Decisions Locked

### Round 1 — Framing

| # | Decision | Implication |
|---|---|---|
| **D-1** | **Azure: fully provisioned.** | Skip docker-compose for stateful services. We'll use real Azure dev resources directly. |
| **D-2** | **Python package manager: `uv`.** | `pyproject.toml` + `uv.lock`. `uv sync` for setup, `uv run` for entry points. `Dockerfile` uses `uv`. |
| **D-3** | **Build strategy: vertical slice.** | First slice = referral submission end-to-end. All later slices reuse this proven path. |
| **D-4** | **Q-handling: A-category + C-category answered in writing now; B/D/E defaulted with call-outs.** | A and C answered explicitly; B/D/E use proposed defaults below. |

### Round 2 — A1–A4

| # | Decision | Implication |
|---|---|---|
| **A1** | **Auto-approval skips HR_REVIEW for clean cases.** Borderline/flagged cases route through HR_REVIEW. | FSM has two valid edges from MENTOR_ACCEPTED: `→ APPROVED` (clean, AI-actor) and `→ HR_REVIEW` (flagged, human actor). Audit event `REFERRAL_AUTO_APPROVED` distinguishes the AI path. |
| **A2** | **AI sentinel = reserved `users` row.** UUID fixed in seed migration; `email='ai-system@nexhire.internal'`, `role='SYSTEM'`, `full_name='NexHire AI'`. | All FK columns stay enforceable. Audit queries that filter by actor work uniformly. The `users.role` enum gains a `SYSTEM` value not granted any RBAC permission. |
| **A3** | **PAN: hash-for-lookup + encrypted-for-display.** Two columns: `candidate_pan_hash VARCHAR(64)` (HMAC-SHA256 with peppered key from Key Vault) + `candidate_pan_encrypted BYTEA` (AES-256-GCM). Display column `candidate_pan_masked VARCHAR(20)` cached on write. | Strongest security posture. Pepper rotation = re-hash sweep migration in Phase 2. |
| **A4** | **Mentor pool: single role + `can_mentor` flag.** `users.role` enum is one of `{REFERRER, MENTOR, HR, IT_AD, ADMIN, PROGRAM_OWNER, SYSTEM, CANDIDATE}`. `users.can_mentor BOOLEAN DEFAULT false` gates inclusion in the mentor picker. | F-25 query updates to `WHERE u.can_mentor = true AND u.is_active = true`. Permission checks remain role-based. |

### Round 3 — A5, A7, A11, A18

| # | Decision | Implication |
|---|---|---|
| **A5** | **Candidates get a `users` row with `role=CANDIDATE`.** Created on referral approval. `interns.user_id` always populated. | Audit queries uniform — every actor in `audit_events.actor_user_id` resolves via `users` join. Candidate JWT subject = `users.id`. RBAC scope `OWN_RECORD_ONLY` enforced via `interns.user_id == jwt.sub`. |
| **A7** | **Master college list seeded; referrer picks via autocomplete.** Table `colleges(id, canonical_name, aliases jsonb, location, type, created_at)`. Seeded with top ~200 Indian engineering colleges. Add-as-you-go for unknown ones. RULE-E2 cap counted by `college_id`. | Reliable cap enforcement, clean College Map on S23. |
| **A11** | **PAN cooling blocks all referrers (candidate-scoped).** Cooling period is per-PAN, not per-(referrer, PAN). Anyone trying to refer a PAN under cooling gets `COOLING_BLOCK`. Override remains Program-Owner-only. | Prevents "shopping" for an HR who'll approve. |
| **A18** | **CORRECTION_NEEDED = edit-in-place.** Same referral row mutable while in `CORRECTION_NEEDED`. Resubmit returns to `HR_REVIEW` (not `SUBMITTED` — mentor already accepted). Each edit logged in `referral_stage_history`. | Preserves mentor's prior acceptance; no state-fork. |

### Round 4 — A8, A14, A19, A20

| # | Decision | Implication |
|---|---|---|
| **A8** | **Disable OpenSign's reminders; NexHire sends all NDA reminders.** Envelope creation passes `disable_reminders: true` flag. NexHire's APScheduler job owns Day 1/2/3 reminders + Day 5 auto-reject. | One source of truth for content/voice. |
| **A14** | **Mid-flow mentor reassignment supported, HR-only action, doesn't increment `mentor_attempt_count`.** New FSM edge: any state from `MENTOR_ACCEPTED` through `ACTIVE` → `MENTOR_PENDING` (HR-initiated). Original mentor's `active_mentee_count` decremented. Audit event `MENTOR_REASSIGNED { reason, original_mentor_id, new_mentor_id, hr_actor_id }`. | Doesn't reset the 3-strike rule. Candidate keeps NDA/ID/AD progress. |
| **A19** | **Closure feedback is structured.** Form on mentor's S20 closure step: `project_summary` (TEXT, 200 chars), `skills_demonstrated` (jsonb tag list, multi-select), `recommendation_strength` (SMALLINT 1–5), `notable_contributions` (TEXT, 500 chars). Stored on `interns.mentor_closure_feedback JSONB`. | AI-8 gets clean structured inputs → consistent certificate citations. |
| **A20** | **TERMINATED can be initiated by candidate, HR, or mentor (any of the three), with mandatory reason.** All three see a "Request Early Termination" / "Initiate Closure" action while internship is ACTIVE. Candidate's path: portal screen with magic link. Audit captures `actor_role`. | More flexible than HR-only. Candidate-initiated path needs a new candidate-portal screen. |

### Round 5 — A12, A15/A17, A21, A16

| # | Decision | Implication |
|---|---|---|
| **A12** | **Business days = Mon–Fri minus India national holidays + Program-Owner-managed company holidays.** Table `holidays(date PK, name, type, source, created_by, created_at)`. Alembic seeds India national holidays for the current and next 2 calendar years. PO can add/remove on S25. | Business-day SLA calculator (`business_days_after(start_ts, n)`) consults the table. |
| **A15/A17** | **Candidate notification on rejection: specific reason for unavoidable terminal states; soft language for HR judgment rejections.** NDA timeout / NDA decline / max-mentor-attempts → specific reason. HR_REJECTED → generic "could not proceed at this time". Cooling period status communicated to referrer (not candidate). | Six notification templates: `NOTIF_018_NDA_TIMEOUT_CANDIDATE`, `NOTIF_019_NDA_DECLINED_CANDIDATE`, `NOTIF_020_MAX_MENTOR_CANDIDATE`, `NOTIF_021_HR_REJECTED_CANDIDATE` (soft), plus referrer-side variants. |
| **A21** | **Recall = compensating action at click time.** Recall button writes a recall record + sends "please disregard" / "being reviewed" follow-up. Original `*_sent_at` timestamps preserved (audit truth). After window expires, button disappears from UI. | One additional notification template per recall type. `documents.is_recalled BOOLEAN`, `documents.recalled_at`, `documents.recalled_by` columns. |
| **A16** | **Max 2 extensions per intern, each ≤ 4 weeks.** `interns.extension_count SMALLINT DEFAULT 0 CHECK (<= 2)`. Per-extension validator: `new_end_date - prev_end_date <= 28 days`. | Prevents unbounded creep. |

### Round 6 — A9, A13, region, OQ1

| # | Decision | Implication |
|---|---|---|
| **A9** | **AI-7 = bulk job every 6 hours.** Filters `start_date = CURRENT_DATE + INTERVAL '2 days'`. T-48h to T-42h window acceptable per spec. | Simple APScheduler `interval` job, idempotency key `compliance_check:{intern_id}:{date}`. |
| **A13** | **Internship duration: 4–26 weeks (28–182 days).** Hard backend validator: `end_date - start_date BETWEEN 28 AND 182`. Frontend Zod schema mirrors. | Covers short summer + full semester engagements. |
| **D-5** | **Azure region: South India (Chennai).** All resources (App Service, Postgres, Blob, Redis, Key Vault, App Insights) in South India. | ⚠️ Azure OpenAI GPT-4o **availability in South India must be verified** — historically Central India had it; if South India lacks GPT-4o, OpenAI resource will be in a different region (e.g., East US 2 or Sweden Central) and called cross-region. Will confirm during C3 setup. |
| **OQ1** | **Both referrer and candidate notified on auto-rejection.** Differentiated templates per A15/A17 above. HR receives FYI on auto-rejections. | Spec-aligned. |

### Round 7 — A6 + C placeholders

| # | Decision | Implication |
|---|---|---|
| **A6** | **`referral_status` enum locked.** Values: `DRAFT, SUBMITTED, MENTOR_PENDING, MENTOR_ACCEPTED, MENTOR_REJECTED, MENTOR_TIMED_OUT, HR_REVIEW, CORRECTION_NEEDED, APPROVED, JOINING_FORM_PENDING, JOINING_FORM_SUBMITTED, JOINING_FORM_LOCKED, ID_PENDING, ID_ISSUED, NDA_PENDING, NDA_SIGNED, ACCESS_PENDING, ACTIVE, EXTENDED, CLOSURE_PENDING, CLOSED, HR_REJECTED, CANDIDATE_REJECTED, NDA_TIMEOUT_REJECTED, NDA_DECLINED_REJECTED, TERMINATED`. | Single source: `app/shared/constants.py` ENUM mirrored to Postgres `referral_status` enum via Alembic. |
| **C1–C12** | **Credentials gathered at the start of STEP 4** (not now). All `TBD` for planning. The first commit creates `.env.example` listing every required variable. | Before each module that needs a real credential boots, request value from PO. |

---

## Defaults adopted (B / D / E categories)

### B. Technical defaults

| # | Default |
|---|---|
| B1 | Vite + pnpm + Node 20 LTS. |
| B2 | uv (locked). |
| B3 | **WeasyPrint** for offer letters & certificates (HTML+CSS templates → PDF). reportlab kept available. |
| B4 | `azure-identity` (DefaultAzureCredential), `azure-storage-blob`, `azure-keyvault-secrets`, `openai` (Azure-mode), `msgraph-sdk`. Gmail via `google-api-python-client` + `google-auth`. |
| B5 | React Router v6. |
| B6 | React Hook Form + Zod. |
| B7 | Custom asyncio event bus (~150 lines). |
| B8 | APScheduler `SQLAlchemyJobStore` against the same Postgres. |
| B9 | **Audit checksum chain** uses `pg_advisory_xact_lock(audit_lock_id)` inside the insert transaction. |
| B10 | `outbox_events(id, event_type, handler_class, payload jsonb, status, retry_count, last_error, created_at, processed_at)`. Worker job every 2 min. |
| B11 | Postgres `dead_letter_jobs` table for v1; Service Bus added in Phase 2. |
| B12 | **Action token GET = confirmation page only; POST executes.** Defeats email pre-fetchers + drive-by token leak. |
| B13 | Same-origin: serve `dist/` static + `/api/*` from one App Service. |
| B14 | **Azure Document Intelligence** for ID/cert reading. GPT-4o Vision only for resumes. |
| B15 | All TIMESTAMPTZ stored UTC. Display = IST. SLAs in **clock hours** by default; "business days" SLAs use the holiday-aware calculator. |
| B16 | `holidays(date, name, source)` table seeded with India national holidays via Alembic; PO can add org-specific. |
| B17 | DKIM/SPF/DMARC handled by Workspace admin. Sender domain confirmed in C5. |
| B18 | RS256 JWT keys generated once, stored in Key Vault. JWKS endpoint at `/.well-known/jwks.json` with `kid` rotation. |
| B19 | Single PAN encryption key in Key Vault; rotation = re-encrypt sweep migration in Phase 2. |
| B20 | `/api/v1/...` from day 1. |
| B21 | Per-role rate limits — defaults: 120 req/min general, 20/min for AI endpoints, 10/min for unauth. |
| B22 | 5 MB per file (per spec); max 8 files per joining form submission. |
| B23 | AI cost tracked per request via Application Insights custom metrics. Daily kill-switch threshold = ₹2,000/day (placeholder). |
| B24 | Bottleneck Predictor v1 = pure heuristic (no historical stats needed). `stage_duration_stats` populated as referrals close. |
| B25 | Magic-link `/candidate/access?token=…` hits backend → validates → sets HttpOnly session cookie + 302 to React SPA. |

### D. Development defaults

| # | Default |
|---|---|
| D1 | `ruff` (lint+format, line length 100), `mypy --strict` for app code. |
| D2 | TS `strict: true`, `noUncheckedIndexedAccess: true`, `noImplicitOverride: true`. |
| D3 | Backend coverage target 80%; frontend 70%. Playwright deferred to Phase 2. |
| D4 | Trunk-based; short-lived feature branches; PR + 1 reviewer required; CI green required. |
| D5 | Conventional Commits (`feat(referral):`, `fix(mentor):`). |
| D6 | **Domain entities = dataclasses + invariants in `__post_init__`. Pydantic v2 only at HTTP I/O boundary.** |
| D7 | English-only at launch. |
| D8 | WCAG 2.1 AA target; `eslint-plugin-jsx-a11y` + `axe-core/react` in dev. |
| D9 | `docs/adr/` maintained; one ADR per non-obvious choice. |
| D10 | Folder structure follows §14 with minor refinements as we go. |

### E. Spec-gap defaults

| # | Default |
|---|---|
| E1 | Add `referrals.reminder_7d_sent_at`, `reminder_expiry_sent_at` columns. |
| E2 | Add to `referrals`: `current_stage VARCHAR`, `stage_entered_at TIMESTAMPTZ`. New table `referral_stage_history(id, referral_id, from_status, to_status, entered_at, actor_id, reason, payload jsonb)`. |
| E3 | `mentor_stats` = a `pg_view` over `interns` + `mentor_assignments`. |
| E4 | `stage_duration_stats(stage VARCHAR PRIMARY KEY, sample_count INT, avg_hours DOUBLE, p95_hours DOUBLE, last_updated TIMESTAMPTZ)`. Updated nightly. |
| E5 | Joining-form-lock SLA = part of the ID SLA (clock starts at form submit). |
| E6 | Add `users.out_of_office_until TIMESTAMPTZ NULL`. UI on profile preference page. |
| E7 | `assigned_hr_id` is **derived** from the latest active HR-type task. |
| E8 | `document_type` enum: `RESUME, ID_PROOF, EDUCATION_CERT, NDA_TEMPLATE, SIGNED_NDA, OFFER_LETTER, CERTIFICATE, PHOTO, PAN_CARD, OTHER`. |
| E9 | `risk_profiles(id, referral_id UNIQUE, risk_score INT, factors jsonb, narrative TEXT, computed_at)` — separate table. |
| E10 | `duplicate_check_results(id, referral_id, match_type, similarity_score, match_reasons jsonb, recommendation, checked_at)` — separate table. |
| E11 | Each task is independently routed (F-29 runs per task). |
| E12 | Action token `action_type` enum: `MENTOR_RESPONSE, CANDIDATE_ACCESS, RECALL_AUTO_ACTION, EXTENSION_RESPONSE`. |
| E13 | `joining_forms.govt_ids` JSONB shape: `{pan_number: str (mandatory), aadhaar_last4: str (optional, last-4 only), passport_number: str (optional)}`. |
| E14 | Seed migration: `cooling_period_config` (6 rows), `mentor_threshold_config` (1 row, value 4), `holidays`, `notification_templates`, 1 system user (`AI_SYSTEM` UUID), 1 first PO. |
| E15 | All scheduler-triggered audit events use `actor_user_id = AI_SYSTEM`. |
| E16 | Resumes retained for 24 months from upload, then auto-anonymized. |
| E17 | Recall = compensating action executed at click time. `OfferLetterRecalled` event → notification template; `documents.is_recalled = true`; original `sent_at` preserved. |
| E18 | Add closure-feedback textarea on S20 mentor closure confirmation. |
| E19 | HR sees PAN masked by default; "Reveal PAN" button writes audit event `PAN_REVEALED_BY_HR`. |
| E20 | Need first PO email — see C11. |

---

# STEP 3 — Build Sequence

## Module dependency graph

```
Foundation (S0) ──► Slice 1 ──► Slice 2 ──► Slice 3 ──► Slice 4 ──► Slice 5 ──► Slice 6
                                    │
                                    └──► Notification + Email Action Token (used by S2+)

Cross-cutting modules grow with each slice:
  - shared/ (kernel)         starts in S0,  expands every slice
  - audit_events             starts in S0,  every slice writes events
  - workflow/state_machine   starts in S1,  expands every slice
  - infrastructure/          starts in S0,  expands as integrations land
```

## Complexity estimates (3 devs)

| Slice | Scope | Complexity | Wall time |
|-------|-------|------------|-----------|
| **S0** | Foundation: repo scaffold, FastAPI, SQLAlchemy/Alembic, structlog, error handler, JWT issuance, Azure AD MSAL frontend, shadcn/ui shell, audit table + checksum chain, in-process event bus, APScheduler boot, Key Vault wiring, CI | M | ~1 week |
| **S1** | Referral submission end-to-end: users + colleges + referrals tables, PAN encryption, AI-1 resume parser, AI-3 risk profiler, AI-4 fuzzy + PAN duplicate detect (F-06, F-33), all RULE-E1..E5 validators, S3+S4 referrer screens, mentor email + action tokens (F-08), notification module + Gmail | **L** | ~2 weeks |
| **S2** | Mentor lifecycle + HR auto-approval: mentor accept/reject/timeout (F-09, F-10, F-11), max-attempts terminal (F-12), AI-2 mentor matcher with cache, auto-approval engine (F-35) + recall, HR_REVIEW path for flagged (S11, S12), AI-10 task auto-router, mentor reassignment edge (A14) | L | ~2 weeks |
| **S3** | Candidate onboarding: candidate users row creation, magic link service (F-03), S8/S9 candidate screens, joining form + AI-6 form assistant + Document Intelligence, auto-lock engine (F-36), Non-Worker ID auto-gen (F-34), S13/S14 HR review screens for flagged forms only | M | ~1.5 weeks |
| **S4** | NDA + access provisioning: OpenSign integration (envelope create + webhook handler F-24), S10 candidate NDA screen, NDA reminder scheduler + auto-reject (F-17), Microsoft Graph AD provisioning, S21/S22 IT and Admin task queues, AI-7 pre-start compliance (F-19), offer letter auto-send (F-37) | L | ~2 weeks |
| **S5** | Active execution + closure: S18/S19/S20 mentor screens, structured closure feedback (A19), AD/badge deactivation (F-22), AI-8 certificate generator + auto-send (F-38), extension flow (F-21, A16 caps), TERMINATED flow with 3-actor support (A20), cooling period system (F-39..F-42, S23 cooling analytics), variable cooling-period config (S25 tab 2) | L | ~2 weeks |
| **S6** | Intelligence + admin: AI-5 bottleneck predictor (F-27), AI-9 program chatbot (F-28), S23 executive dashboard (SLA heartbeat, college map), S24 audit & SLA report, S25 config panel (mentor threshold + cooling, F-43..F-45), AI performance dashboard, holiday calendar mgmt | M | ~1.5 weeks |

**Total: ~12 weeks** for a 3-dev team. Some intra-slice parallelization is possible but inter-slice dependencies are mostly serial.

## What each slice delivers (acceptance criteria)

### S0: Foundation

- ✅ `uv sync` boots; `uv run fastapi dev` serves `/health`.
- ✅ Alembic migration creates `users`, `audit_events` tables.
- ✅ Frontend `pnpm dev` boots; Azure AD login redirects.
- ✅ JWT issuance returns valid RS256 token; JWKS endpoint serves public key.
- ✅ Audit checksum chain validated by an integration test that inserts 100 events concurrently.
- ✅ Event bus publishes a `Heartbeat` event handled by a noop subscriber in a test.

### S1: Referral submission (THE FIRST VERTICAL SLICE)

**Demo path:** A referrer logs in → fills a referral form (with AI-prefilled resume data) → submits → sees confirmation → mentor receives email with action-token links.

- ✅ Referrer can SSO log in; their `users` row reflects role + can_mentor flag.
- ✅ College autocomplete works against seeded list.
- ✅ Resume upload → AI-1 prefills with confidence scores; amber-tinted fields shown.
- ✅ All 5 eligibility rules enforced server-side (test: bypass UI, hit API, get 422).
- ✅ PAN duplicate check returns CLEAR / HARD_BLOCK / COOLING_BLOCK correctly.
- ✅ Referral submit creates `referrals` row, `mentor_assignments` row, `action_tokens` (ACCEPT + REJECT), publishes `ReferralSubmitted` event.
- ✅ Mentor receives email; token validation works (single-use, expiring, hash-stored).
- ✅ All actions logged in `audit_events` with valid checksum chain.

### S2–S6 acceptance criteria

Detailed criteria captured per-slice in their respective branches before start. Every slice ends with: **(a) demo against acceptance criteria, (b) integration tests green in CI, (c) updated ADR if any non-obvious decision was made.**

## First-slice critical files (S0 + S1)

```
backend/
├─ app/
│  ├─ main.py                          (S0)
│  ├─ config.py                        (S0)
│  ├─ shared/
│  │  ├─ constants.py                  (S0 — referral_status enum, role enum, SLA constants)
│  │  ├─ value_objects.py              (S0 — Email, PhoneNumber, Pan, UserId)
│  │  ├─ exceptions.py                 (S0 — full hierarchy from §17.5)
│  │  └─ domain_events.py              (S0 — DomainEvent base + first events)
│  ├─ infrastructure/
│  │  ├─ database.py                   (S0 — async engine, session, error handler)
│  │  ├─ event_bus.py                  (S0 — InProcessEventBus + outbox)
│  │  ├─ scheduler.py                  (S0 — APScheduler with SQLAlchemyJobStore)
│  │  ├─ azure_keyvault.py             (S0)
│  │  ├─ azure_blob.py                 (S1)
│  │  ├─ azure_openai.py               (S1 — client + retry + cost tracking)
│  │  ├─ azure_doc_intelligence.py     (S3 — but sketch in S1 for shared client patterns)
│  │  └─ gmail_client.py               (S1)
│  ├─ middleware/
│  │  ├─ audit.py                      (S0 — AuditPublisher with advisory-lock chain)
│  │  ├─ auth.py                       (S0 — JWT validation, RBAC decorator)
│  │  ├─ error_handler.py              (S0)
│  │  ├─ logging.py                    (S0 — structlog → App Insights)
│  │  └─ rate_limit.py                 (S0 — Redis-backed)
│  ├─ modules/
│  │  ├─ auth/                         (S0)
│  │  │  ├─ router.py, service.py, rbac.py, models.py, schemas.py
│  │  ├─ referral/                     (S1)
│  │  │  ├─ router.py, service.py, validator.py, repository.py, models.py, schemas.py
│  │  │  ├─ pan_encryption.py          (S1 — hash + GCM helpers)
│  │  ├─ ai/                           (S1)
│  │  │  ├─ service.py                 (S1 — public AiService interface)
│  │  │  ├─ resume_parser.py           (AI-1)
│  │  │  ├─ duplicate_detector.py      (AI-4 + PAN check)
│  │  │  ├─ risk_profiler.py           (AI-3)
│  │  │  └─ models.py                  (ai_parse_results, risk_profiles, duplicate_check_results)
│  │  ├─ notification/                 (S1)
│  │  │  ├─ service.py, template_renderer.py, event_handlers.py
│  │  │  └─ templates/ (jinja2: confirmation.html, mentor_assignment.html)
│  │  └─ workflow/                     (S1 — minimal: just ReferralSubmitted handler)
│  └─ migrations/
│     ├─ 0001_create_audit_events.py            (S0)
│     ├─ 0002_create_users_and_seed_system.py   (S0 — system user, first PO)
│     ├─ 0003_create_colleges_and_seed.py       (S1 — top 200 colleges)
│     ├─ 0004_create_referrals_and_indexes.py   (S1 — including PAN hash unique idx)
│     ├─ 0005_create_action_tokens.py           (S1)
│     ├─ 0006_create_ai_tables.py               (S1)
│     └─ 0007_create_outbox_events.py           (S1)

frontend/
├─ src/
│  ├─ app/App.tsx, providers/, routes/   (S0)
│  ├─ lib/axios.ts, msal.ts, utils.ts    (S0)
│  ├─ shared/components/                 (S0 — ConfidenceBadge, WhatHappensNext)
│  └─ modules/
│     ├─ auth/                           (S0)
│     └─ referral/                       (S1 — ReferralForm, ReferralCard, MentorPicker, AiPrefill hook)
```

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| GPT-4o not available in South India region | Verify before starting S1; fall back to East US 2 / Sweden Central with cross-region call (data residency caveat). |
| OpenSign NDA template not legal-approved by S4 start | Stub the OpenSign client in S1–S3 with a test envelope; block only the NDA signing portion of S4 if the template isn't ready. |
| Audit checksum chain locking causing write contention | Phase 1 acceptable since write volume is low. If contention shows, switch to per-entity-id chains. |
| Azure OpenAI cost overrun | Daily kill-switch metric (B23). Cache mentor suggestions 1h. Use GPT-4o-mini for low-stakes touchpoints if budget pressure. |
| Microsoft Graph permission grant lag | AD provisioning is S4 work; tenant admin needs to grant `User.ReadWrite.All` before then. Surface this as a dependency in S0 demo. |

## Verification plan (full-system, after S6)

1. End-to-end happy path: referrer submits referral → mentor accepts → AI auto-approves → candidate magic-link → joining form → auto-lock → NW-ID auto-gen → NDA signs → access provisioned → mentor confirms start → 8-week internship simulated → mentor confirms closure → cert auto-sent → CLOSED.
2. Each terminal state path: NDA decline, NDA timeout, max-mentor-attempts, HR rejection, mid-flow termination — verify cooling period applied correctly.
3. Cooling-period override flow: PO overrides a 6-month NDA_DECLINED, audit verified.
4. AI degradation: Azure OpenAI quota exhausted simulated → all flows degrade gracefully, manual paths work.
5. Audit chain integrity: nightly check job validates 1000+ events end-to-end.
6. Load: 100 concurrent referral submissions → no deadlocks, audit chain intact.
7. RBAC: role-permission matrix exhaustively tested via parameterized integration test.

---

## Open items still to resolve (don't block STEP 3 approval)

- **C1–C12 credentials** — gathered at start of S0.
- **OQ6 NDA template** — needed by start of S4. If not ready, S4 is partially blocked.
- **Verify GPT-4o availability in South India** — needed before S1 starts.
- **Initial set of HR / IT / Admin / Mentor users** — needed for S2 demo. A simple admin script seeds them from a CSV.

---

## UI Design Reference

User provided a visual sample at [Gmail - Re_ nexhire ui.pdf](Gmail%20-%20Re_%20nexhire%20ui.pdf) (rendered as "InternFlow" — product brand stays **NexHire**, only the visual language is adopted).

### Visual language locked from the sample

| Element | Pattern |
|---|---|
| **Brand mark** | Text mark "NexHire" + small accent icon (color: primary blue). Logo file TBD; use text-only treatment for v1. |
| **Top navigation** | Left: brand. Center: Home / Dashboard / Submit Referral. Right: primary CTA button ("Get Started" or role-specific). |
| **Hero (landing/login)** | Dark navy gradient background, white text, single accent color highlight on key noun ("reimagined"-style), one primary + one ghost button below the H1. Eyebrow tag chip above ("AI-Powered Internship Automation Platform"). |
| **Card workspace** | Light gray background, white cards with `rounded-xl` (~12px), subtle shadow `shadow-sm`, generous padding (24–32px). |
| **Form wizard (S4 — Submit Referral)** | 4-step horizontal stepper at top with circular icons + labels. Steps for our flow: **Candidate Details → Eligibility Check → Internship Details → Review & Submit**. Active step accented; completed steps get a checkmark. |
| **AI prefill upload zone** | Dotted-border upload card, centered upload icon, "Upload resume for AI parsing" headline, accepted formats line, "AI Resume Parsing Enabled" pill at the bottom of the card. |
| **KPI cards** | 4-up grid. Each: small icon top-left, big metric (3xl font, semibold), label below, optional delta line ("+8 this month", "-82% vs last quarter"). |
| **Pipeline bar chart** | Single horizontal bar split by stage with stage-specific colors + count labels. Stage colors lock the status palette (see below). |
| **Pending Tasks list** | Each row: small icon, title, "Assigned to ___" subline, priority pill (`High`/`Medium`/`Low`), due-date text, kebab menu. |
| **All Interns table** | Columns: Intern (avatar+name) · Role · Mentor · Stage (pill) · Duration · NDA (checkmark) · Non-Worker ID. Avatar = colored circle with initials. |
| **Status pills** | Rounded-full, small caps where appropriate. Active = green, Onboarding = blue, Under Review = amber, Closure = purple, Terminal-rejected = red, Completed = emerald. |
| **Stat strip** | Dark band with 4 large stat columns (e.g., "80% Reduction in cycle time", "<1 Day Non-Worker ID SLA"). |
| **Capabilities/feature grid** | 3-up cards with icon-on-tile-top-left, bold heading, 2-line description. |
| **End-to-end automation flow** | Numbered circles (01–07) connected, each with a stage label + 1-line description. Useful pattern for: landing page (marketing of the 7 phases) and the per-referral timeline view (S5). |

### Color & typography defaults

| Token | Value (initial — refinable) |
|---|---|
| `--bg` | `#F8FAFC` (slate-50) |
| `--surface` | `#FFFFFF` |
| `--hero-bg` | `#0B1220` → `#1E293B` linear-gradient |
| `--primary` | `#2563EB` (blue-600) |
| `--primary-foreground` | `#FFFFFF` |
| `--accent` | `#06B6D4` (cyan-500, used for the "reimagined"-style highlight) |
| `--success` | `#10B981` |
| `--warning` | `#F59E0B` |
| `--danger` | `#EF4444` |
| `--muted` | `#64748B` |
| Font (sans) | `Inter`, fallback `system-ui` |
| Heading scale | h1 48/56, h2 32/40, h3 24/32 |
| Body | 15/24 (slightly larger than default for readability) |

These tokens are wired into `tailwind.config.ts` + shadcn/ui theme in S0. Refinement during S1 if real screens demand adjustment.

### Stage palette (locked)

Aligns the bar chart, status pills, and the 7-phase automation graphic everywhere they appear:

```
01 Referral Submitted   → blue-500
02 Under Review         → amber-500
03 Onboarding           → indigo-500
04 NDA Pending          → violet-500
05 Active               → emerald-500
06 Extended             → teal-500
07 Closure / Closed     → slate-500
Terminal-rejected       → rose-500
```

### Screens that use this language

All 25 screens (S1–S25 from §6.1) inherit the language above. Marketing/landing surfaces (hero, capabilities, automation flow, stat strip) appear on:

- Landing/login splash (pre-auth)
- Program Owner Executive Dashboard (S23) — KPI grid + pipeline + weekly chart at the top
- HR Dashboard (S11) — KPI grid + Pending Tasks + All Interns table

Workspace surfaces (forms, review panels, task queues) use the white-card-on-slate-50 layout consistently.

### Authoritative UI source going forward

The PDF is the v1 visual reference. Any pixel disagreement during build → defer to the PDF. If a screen isn't in the PDF, derive it from the patterns above. Major deviations require a flagged ADR.

---

## Conventions cheatsheet (quick reference for STEP 4)

| Topic | Choice |
|---|---|
| Backend pkg manager | `uv` |
| Frontend pkg manager | `pnpm` |
| Lint/format (Python) | `ruff` (lint + format) |
| Type-check (Python) | `mypy --strict` |
| Lint/format (TS) | `eslint` + `prettier` |
| Type-check (TS) | `tsc --strict` |
| Domain entities | dataclasses, invariants in `__post_init__` |
| HTTP I/O schemas | Pydantic v2 |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Logging | structlog → App Insights |
| Test frameworks | pytest + pytest-asyncio + testcontainers; vitest + RTL |
| API prefix | `/api/v1/...` |
| Commit style | Conventional Commits |
| Branch model | Trunk-based; short-lived feature branches |
| Time storage | UTC TIMESTAMPTZ; display IST |
| PII (PAN) | `_hash` (HMAC-SHA256) + `_encrypted` (AES-256-GCM) + `_masked` (display) |
| AI sentinel actor | reserved `users` row, role=`SYSTEM`, fixed UUID |
| Recall windows | compensating action at click time |
| Cooling period scope | per-PAN (not per-referrer) |
| Mentor pool gate | `users.can_mentor BOOLEAN` |
