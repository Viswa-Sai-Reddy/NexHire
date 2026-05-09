# NexHire — Functionality Matrix

> **Purpose.** A single, scannable reference of every feature in the NexHire platform, grouped by user role, with the outcome of each action. Use it to confirm coverage, brief stakeholders, and locate incomplete work.
>
> **As of** 2026-05-08. **Source of truth** = code under [backend/app/modules/](../backend/app/modules/) and [frontend/src/modules/](../frontend/src/modules/). Every row cites its source.
>
> **Status legend** — ✅ wired end-to-end · ⚠ shape locked, stub/placeholder inside · ❌ not yet built.

---

## 1. Overview

NexHire is an AI-powered intern referral management platform — a modular monolith built on FastAPI (Python) and React (TypeScript). Employees refer candidates, mentors accept the assignment, HR approves and provisions, the candidate signs an NDA via OpenSign, IT issues an AD account, Admin issues a badge, and the intern completes the program with a mentor-authored, AI-generated certificate.

### Roles at a glance

| # | Role | Who they are | Primary outcome they drive |
|---|---|---|---|
| 1 | **Referrer** (Employee) | Internal employee submitting a referral | Candidate enters the pipeline |
| 2 | **Mentor** (Employee) | Internal employee guiding an intern | Mentor accept/reject + lifecycle ownership |
| 3 | **HR** | Human Resources reviewer | Approve/reject; issue ID; manage corrections; reassign mentors |
| 4 | **Candidate** | External applicant (no AAD identity) | Sign NDA, complete joining form, finish internship |
| 5 | **Admin** (Badge/Site Access) | Security/badge desk | Provision physical access |
| 6 | **IT / AD** | Active Directory team | Provision Azure AD account |
| 7 | **Program Owner** (PO) | Governance / executive | Configure thresholds, override AI, view program intelligence |
| 8 | **SYSTEM** | Reserved automation actor | Runs AI-1…AI-10 + scheduled jobs |

---

## 2. Role-by-Role Functionalities

### 2.1 Referrer (Employee)

Internal employee authorized to submit referrals. Subject to RULE-E2 (max 2 active referrals per college) and RULE-E3 (cannot be the mentor for their own referral). Sees only their own referrals.

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | Submit a new referral (5-step form) | `POST /referrals` · [ReferralFormPage](../frontend/src/modules/referral/) | Candidate details, eligibility consents, mentor selection, internship details | Referral created; AI-3/AI-4 run; mentor token email sent | ✅ |
| 2 | Upload & parse resume (AI-1) | `POST /referrals/upload-resume` · ResumeUploader | PDF/DOC | Form fields autofilled with confidence scores | ✅ |
| 3 | Real-time PAN deduplication check (AI-4) | `POST /referrals/check-pan` · PanField | Plain PAN | Verdict ACCEPTED/COOLING/FORBIDDEN + masked PAN + matched referral | ✅ |
| 4 | Check college cap | `GET /referrals/college-cap?college_id=…` | college_id | `{used, limit=2, remaining, can_submit}` | ✅ |
| 5 | View own referrals | `GET /referrals/me` | — | List of own ReferralSummary | ✅ |
| 6 | View single referral detail | `GET /referrals/{id}` | referral_id | Full ReferralDetail + AI analysis (if owner) | ✅ |
| 7 | Search & select college | `GET /colleges/search?q=…` · CollegeCombobox | query | Top-10 trigram matches | ✅ |
| 8 | List eligible mentors | `GET /mentors/eligible` · MentorPicker | — | Mentors with capacity counts (excludes full + self) | ✅ |
| 9 | Get AI mentor suggestions (AI-2) | `POST /mentors/suggest` | candidate_skills, college_id, exclusions | Top 3 with radar scores + narrative | ✅ |
| 10 | Change mentor before acceptance | implicit re-submit on `POST /referrals` | new mentor_id | Mentor swapped while in MENTOR_PENDING | ✅ |
| 11 | Initiate early termination | `POST /interns/terminate` · MyReferralsPage | intern_id, reason | Intern → TERMINATED; cooling-off applied | ✅ |
| 12 | Home redirect | `HomeRedirect` (`/`) | — | Redirected to `/referrals/new` | ✅ |

Sources: [backend/app/modules/referral/router.py](../backend/app/modules/referral/router.py), [backend/app/modules/referral/college_router.py](../backend/app/modules/referral/college_router.py), [backend/app/modules/mentor/picker_router.py](../backend/app/modules/mentor/picker_router.py), [backend/app/modules/lifecycle/router.py](../backend/app/modules/lifecycle/router.py).

---

### 2.2 Mentor (Employee)

Internal employee assigned to guide one or more interns. Receives an action-token email per assignment (preview-safe link), manages the intern lifecycle, can request extensions, and submits closure feedback.

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | Preview mentor action (no token consume) | `GET /action/mentor?token=…&action=…` · MentorActionPage | token, action | `{valid, action, referral_id, expires_at}` | ✅ |
| 2 | Accept assignment | `POST /action/mentor/confirm` (action=ACCEPT) | token | Referral → MENTOR_ACCEPTED; access tasks queued | ✅ |
| 3 | Reject assignment | `POST /action/mentor/confirm` (action=REJECT) | token, reason ≥10 chars | MENTOR_REJECTED; strike counter; reroute or terminal | ✅ |
| 4 | View my interns | `GET /interns/mine` · MentorWorkspacePage | — | List of MentorInternEntry | ✅ |
| 5 | Confirm internship start | `POST /interns/confirm-start` | intern_id | Intern → ACTIVE; actual_start_date set | ✅ |
| 6 | Request extension | `POST /interns/extend` | intern_id, new_end_date, reason | actual_end_date updated; extension_count++ | ✅ |
| 7 | Submit closure feedback | `POST /interns/confirm-completion` | intern_id, summary, skills, recommendation, contributions | CLOSURE_PENDING; AI-8 certificate queued | ✅ |
| 8 | Initiate early termination | `POST /interns/terminate` · TerminationDialog | intern_id, reason | TERMINATED; cooling-off 6m | ✅ |
| 9 | View own assigned referral detail | `GET /referrals/{id}` | referral_id | ReferralDetail (only if mentor_id == self) | ✅ |
| 10 | Set out-of-office (for AI-10 routing) | `GET\|PUT /auth/me/out-of-office` · MentorWorkspacePage panel | until (ISO datetime or null) | AI-10 skips routing during OOO | ✅ |

Sources: [backend/app/modules/mentor/router.py](../backend/app/modules/mentor/router.py), [backend/app/modules/lifecycle/router.py](../backend/app/modules/lifecycle/router.py), [backend/app/modules/auth/models.py](../backend/app/modules/auth/models.py).

---

### 2.3 HR (Human Resources)

Reviews flagged referrals, approves/rejects, requests corrections, reassigns mentors mid-flow without strike penalty (A14), recalls AI auto-approvals within the 2h window (A21), and oversees the candidate's onboarding (ID, NDA, certificate). Sees all referrals; can reveal full PAN (E19).

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | HR dashboard home | `/hr` · HrDashboardPage | — | KPIs + queue counts | ✅ |
| 2 | View HR review queue | `GET /referrals/hr/queue` | — | Top-50 flagged referrals with auto-action recommendation | ✅ |
| 3 | View full review context | `GET /referrals/hr/{id}/review` · HrReviewPage | referral_id | Detail + AI-3 risk + AI-4 dup + AI-1 resume + auto-action + recall window | ✅ |
| 4 | View recent AI auto-actions (recall window) | `GET /referrals/hr/recent-ai` | — | Items where `recall_active=true` (≤2h) | ✅ |
| 5 | Approve referral | `POST /referrals/hr/{id}/approve` | notes? | APPROVED → Intern created; offer letter email | ✅ |
| 6 | Reject referral | `POST /referrals/hr/{id}/reject` | reason ≥10 chars | HR_REJECTED; cooling-off 3m | ✅ |
| 7 | Request correction | `POST /referrals/hr/{id}/request-correction` | notes ≥10 chars | CORRECTION_NEEDED; referrer notified | ✅ |
| 8 | Reassign mentor (no strike) | `POST /referrals/hr/{id}/reassign-mentor` | new_mentor_id, reason | Mentor swapped under A14 | ✅ |
| 9 | Recall AI auto-approval | `POST /referrals/hr/{id}/recall` | reason? | Reverts to HR_REVIEW; auto_action.recalled_at set | ✅ |
| 10 | Issue Non-Worker ID | task complete via `/tasks/issue-id` | task entry | Intern.non_worker_id assigned; NDA queued | ⚠ backend ready, UI partial |
| 11 | Lock joining form | `POST /hr/onboarding/joining-form/{intern_id}/lock` (or auto on submit) | intern_id, notes? | Form → LOCKED; NDA signing link sent | ✅ |
| 12 | Generate certificate (manual override) | `POST /interns/{intern_id}/generate-certificate` | intern_id | AI-8 citation + PDF; emailed to candidate | ✅ |
| 13 | View any referral (audit) | `GET /referrals/{id}` · `GET /referrals/hr/all` | referral_id / status, college_id, q | Full visibility with REVEAL_PAN if granted; paginated list | ✅ |
| 14 | View SLA dashboard | `GET /admin/overview`, `GET /admin/sla/open` · AuditSlaReportPage | — | Open breaches + drilldown | ✅ |
| 15 | View audit trail | `GET /admin/audit/recent` | — | Recent immutable audit events | ✅ |
| 16 | Query AI chatbot (AI-9) | `POST /admin/chatbot` | question 4–400 chars | Answer + data_source + confidence | ✅ |
| 17 | Reveal PAN | E19 permission flag in HR review context | — | Full PAN visible (else masked) | ✅ |
| 18 | Submit referral on behalf | `POST /referrals` | full form | Same as Referrer flow | ✅ |

Sources: [backend/app/modules/referral/hr_router.py](../backend/app/modules/referral/hr_router.py), [backend/app/modules/admin/router.py](../backend/app/modules/admin/router.py), [backend/app/modules/access/router.py](../backend/app/modules/access/router.py), [backend/app/modules/onboarding/router.py](../backend/app/modules/onboarding/router.py), [backend/app/modules/ai/certificate.py](../backend/app/modules/ai/certificate.py).

---

### 2.4 Candidate (Intern Applicant)

External applicant with no Azure AD identity. Authenticates via a 72h magic link. JWT scope is `OWN_RECORD_ONLY`. Completes joining form, signs NDA, monitors progress, can early-terminate, and downloads the final certificate.

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | Redeem magic link | `POST /candidate/redeem` · CandidateAccessPage | token | Candidate JWT + redirect_to | ✅ |
| 2 | Status portal | `/candidate/status` · CandidateStatusPage | — | Stage, dates, NDA, certificate links | ✅ |
| 3 | Joining form: fetch draft | `GET /candidate/joining-form` · JoiningFormPage | — | Current draft + version | ✅ |
| 4 | Joining form: auto-save (60s) | `PATCH /candidate/joining-form` | partial fields + version | Draft saved (optimistic lock) | ✅ |
| 5 | Joining form: extract ID doc (AI-6) | `POST /candidate/joining-form/extract-id-doc` | ID photo | Parsed name, DOB, ID number, address | ✅ |
| 6 | Joining form: submit | `POST /candidate/joining-form/submit` | full form | AUTO_LOCK / CORRECTION_NEEDED / WAITING_HR | ✅ |
| 7 | Sign NDA (in-app click-to-accept) | `GET /candidate/nda` · `POST /candidate/nda/accept` · [CandidateNdaPage](../frontend/src/modules/candidate/components/CandidateNdaPage.tsx) | typed_name + text_sha256 | NDA → SIGNED; records typed_name, IP, UA, text_sha256; fires `NdaSigned` | ✅ |
| 8 | Decline NDA (OpenSign path only) | external `POST /webhooks/opensign` (declined event) | declined event | NDA_DECLINED_REJECTED; cooling 6m | ⚠ inert in staging — OpenSign disabled |
| 9 | View NDA status | `GET /candidate/nda` · CandidateNdaPage | — | Renders agreement + acceptance state | ✅ |
| 10 | Initiate early termination | `POST /interns/terminate` (candidate JWT) · CandidateStatusPage | intern_id, reason | TERMINATED; cooling 6m | ✅ |
| 11 | View / download certificate | `/candidate/certificate` | — | AI-8 PDF download | ✅ |
| 12 | Receive offer letter email | triggered on HR approve | — | Gmail-API email with magic link + offer | ⚠ Gmail send is stub (S1) |

Sources: [backend/app/modules/onboarding/router.py](../backend/app/modules/onboarding/router.py), [backend/app/modules/nda/webhook_router.py](../backend/app/modules/nda/webhook_router.py), [backend/app/modules/lifecycle/router.py](../backend/app/modules/lifecycle/router.py), [backend/app/modules/workflow/offer_letter.py](../backend/app/modules/workflow/offer_letter.py).

---

### 2.5 Admin (Badge / Site Access)

Security desk role. Sees only their assigned BADGE_ACCESS tasks; marks them complete with a badge reference number.

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | View task queue | `GET /tasks/mine` · TaskQueuePage | — | Open BADGE_ACCESS tasks with SLA + AI-10 routing reason | ✅ |
| 2 | Complete badge access task | `POST /tasks/badge-access/complete` | intern_id, badge_reference | Task COMPLETED; intern.badge_ref stored; workflow advances | ✅ |
| 3 | View SLA dashboard | `GET /admin/overview`, `GET /admin/sla/open` | — | Open breaches drilldown for Admin's queue | ✅ |

Sources: [backend/app/modules/access/router.py](../backend/app/modules/access/router.py), [backend/app/modules/auth/rbac.py](../backend/app/modules/auth/rbac.py).

---

### 2.6 IT / AD

Active Directory team. Sees only AD_PROVISION tasks. Real Microsoft Graph integration is S1; S0 ships the endpoint shape with a placeholder.

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | View task queue | `GET /tasks/mine` · TaskQueuePage | — | Open AD_PROVISION tasks | ✅ |
| 2 | Complete AD provisioning | `POST /tasks/ad-provision/complete` | intern_id | AD account created; user_id+azure_oid linked; task COMPLETED | ⚠ Microsoft Graph stub (S1) |

Source: [backend/app/modules/access/router.py](../backend/app/modules/access/router.py).

---

### 2.7 Program Owner (Governance)

Highest-privilege role. Has every HR permission plus governance: edits mentor capacity, cooling-off durations, can override AI decisions and cooling periods, recalls auto-approvals, and queries the AI-9 chatbot.

| # | Feature | Endpoint / UI | Input | Outcome | Status |
|---|---|---|---|---|---|
| 1 | Executive dashboard | `GET /admin/overview` · ExecutiveDashboardPage | — | Pipeline KPIs, SLA breaches, at-risk count, cooling-active count | ✅ |
| 2 | Audit & SLA report | `GET /admin/audit/recent`, `GET /admin/sla/open` · AuditSlaReportPage | — | Recent events + open breaches | ✅ |
| 3 | View config panel | `GET /admin/config/...`, `GET /admin/config/history` · ConfigPanelPage | — | Current settings + change history | ✅ |
| 4 | Set mentor capacity threshold | `POST /admin/config/mentor-threshold` | value 1–10, reason? | Threshold updated; previous archived | ✅ |
| 5 | Set cooling-off duration | `POST /admin/config/cooling-periods/{state}` | months 0–24, reason? | Duration updated; previous archived | ✅ |
| 6 | View config change history | `GET /admin/config/history` | — | All changes with actor, timestamp, reason | ✅ |
| 7 | Override cooling-off period | `POST /admin/cooling-overrides/{referral_id}` | referral_id, reason ≥50 chars | Candidate re-eligible immediately; audit row written | ✅ |
| 8 | Query AI chatbot (AI-9) | `POST /admin/chatbot` | question | Answer + data_source + confidence | ✅ |
| 9 | Approve / reject / request-correction (HR powers) | `POST /referrals/hr/{id}/approve|reject|request-correction` | — | Same as HR | ✅ |
| 10 | Override AI decision | implicit during approval (`OVERRIDE_AI_DECISION` perm) | — | PO can approve a HIGH-risk referral | ⚠ no explicit endpoint |
| 11 | Recall AI auto-approval | `POST /referrals/hr/{id}/recall` | reason? | Auto-approve reverted to HR_REVIEW | ✅ |
| 12 | Reveal PAN | E19 permission | — | Full PAN visible | ✅ |
| 13 | Submit referral on behalf | `POST /referrals` | form | Same as Referrer | ✅ |

Sources: [backend/app/modules/admin/router.py](../backend/app/modules/admin/router.py), [backend/app/modules/referral/hr_router.py](../backend/app/modules/referral/hr_router.py), [backend/app/modules/auth/rbac.py](../backend/app/modules/auth/rbac.py).

---

### 2.8 SYSTEM (AI / Automation)

Reserved system actor (UUID `00000000-0000-0000-0000-000000000001`) for all automated actions. Not a human role; no RBAC. Ten AI touchpoints power the platform.

| # | AI feature | Touchpoint | Trigger | Output | Status |
|---|---|---|---|---|---|
| 1 | **AI-1** Resume Deep Analyzer | RESUME_PARSE | Referrer uploads resume | Parsed candidate fields + skills + red flags + readiness score + mentor questions | ✅ |
| 2 | **AI-2** Mentor Match Engine | MENTOR_MATCH | Referrer requests suggestions | Top-3 mentors with 5-axis radar (skill, availability, reputation, familiarity, response speed) + narrative | ✅ |
| 3 | **AI-3** Eligibility & Risk Profiler | ELIGIBILITY_RISK | On referral submit | Risk score 0–100 + classification + factors → routes to HR_REVIEW or AUTO_APPROVE | ✅ |
| 4 | **AI-4** Duplicate Detection | DUPLICATE_DETECTION | PAN realtime check + on submit | Verdict ACCEPTED/COOLING/FORBIDDEN + similarity + matched referral | ✅ |
| 5 | **AI-5** Bottleneck Predictor | BOTTLENECK_PREDICTION | Scheduled (every 6h) | Per-referral risk + email to HR/PO | ✅ |
| 6 | **AI-6** Joining Form Assistant | FORM_ASSIST | ID upload + form submit | Field extraction + cross-validation → AUTO_LOCK or CORRECTION_NEEDED | ✅ |
| 7 | **AI-7** Pre-Start Compliance Checker | COMPLIANCE_CHECK | Scheduled T-48h | Checklist + flags missing items; emails HR/mentor | ✅ |
| 8 | **AI-8** Certificate Content Generator | CERTIFICATE_CITATION | On closure feedback submit | Personalized 2–3 sentence citation | ✅ |
| 9 | **AI-9** Program Intelligence Chatbot | PROGRAM_CHATBOT | HR/PO query | NL answer + data_source + confidence | ✅ |
| 10 | **AI-10** Workflow Auto-Router | WORKFLOW_ROUTING | On task creation | Least-loaded user assigned (skips OOO) + routing reason | ✅ |

Sources: [backend/app/modules/ai/](../backend/app/modules/ai/) (one module per AI feature).

---

## 3. Cross-Cutting Capabilities

### 3.1 Authentication & session

| Capability | Endpoint / Mechanism | Notes |
|---|---|---|
| SSO login (employees) | `POST /auth/login` (Azure AD ID token in) | Issues NexHire JWT (RS256, 8h) + refresh (24h, encrypted in Redis) |
| JWT refresh | `POST /auth/refresh` | Sliding window; rotates refresh token |
| Current user | `GET /auth/me` | Drives role-based UI |
| Logout | `POST /auth/logout` | Optional refresh_token; else all sessions |
| Public JWKS | `GET /.well-known/jwks.json` | Public RSA keys for JWT verification |
| Magic link (candidates) | `POST /candidate/redeem` | 72h expiry; idempotent; bcrypt-hashed at rest |

Source: [backend/app/modules/auth/router.py](../backend/app/modules/auth/router.py), [backend/app/modules/onboarding/router.py](../backend/app/modules/onboarding/router.py).

### 3.2 Notifications & email

- **Service:** Gmail API (domain-wide delegation).
- **Templates:** Jinja2, seeded in DB migrations (`offer_letter`, `nda_signing_link`, `mentor_action_token`, `approval_confirmation`, …).
- **Architecture:** Domain events (NdaIssued, NdaSigned, …) → notification handlers → service.
- **PII:** Only SHA-256 email hashes logged; never full bodies.
- **Status:** Shape locked in S0; `gmail_client.send()` raises `NotImplementedError` until S1.

Source: [backend/app/modules/notification/](../backend/app/modules/notification/), [backend/app/infrastructure/gmail_client.py](../backend/app/infrastructure/gmail_client.py).

### 3.3 Audit trail & SLA

- **`audit_events` table:** append-only; DB role lacks UPDATE/DELETE.
- **Triggers:** every status change, task complete, config change.
- **Reads:** HR/PO via `GET /admin/audit/recent`.
- **SLA:** per-stage deadlines; AI-5 + scheduled breach job; HR/PO see `/admin/sla/open`; email alerts on breach.

Source: [backend/app/middleware/audit.py](../backend/app/middleware/audit.py), [backend/app/modules/workflow/sla_breach_job.py](../backend/app/modules/workflow/sla_breach_job.py).

### 3.4 Rate limiting

| Tier | Limit | Applies to |
|---|---|---|
| `default` | 120 req/min/user | All authenticated endpoints |
| `ai` | 20 req/min/user | AI inference calls |
| `unauth` | 10 req/min/IP | Login, mentor action, OpenSign webhook |

Source: [backend/app/middleware/rate_limit.py](../backend/app/middleware/rate_limit.py).

### 3.5 PII / data protection

- **PAN masking** (`****2345`) everywhere except for callers with `REVEAL_PAN` (HR/PO, decision E19).
- **Per-role visibility:**

| Role | PII visible |
|---|---|
| Referrer | Own referrals + mentor names |
| Mentor | Own assigned interns (full) |
| Candidate | Own form + NDA + certificate |
| HR | All referrals; PAN if `REVEAL_PAN` |
| IT/AD | Only assigned tasks (limited) |
| Admin | Only assigned tasks (badge ref) |
| PO | All (with `REVEAL_PAN`) |

- **Encryption:** refresh + magic-link tokens bcrypt-hashed; TLS in transit; secrets in env vars.
- **NDA acceptance (staging mode):** in-app click-to-accept stored in `nda_records` (`typed_name`, `accepted_ip`, `accepted_user_agent`, `text_sha256`, `signed_at`). Audit row written with `payload.accepted_via='in_app'`. The `text_sha256` is the SHA-256 of the rendered HTML version the candidate read — any later wording change produces a different hash, so prior acceptances pin to the exact wording on file. The OpenSign code path remains in-tree but inert when `OPENSIGN_BASE_URL` is empty.

### 3.6 Workflow state machines

**Referral**

```
DRAFT → SUBMITTED → MENTOR_PENDING →
  (ACCEPTED | REJECTED | TIMED_OUT) →
  MENTOR_ACCEPTED → AI-3 →
  (HR_REVIEW | AUTO_APPROVE) →
  APPROVED → JOINING_FORM_PENDING → JOINING_FORM_SUBMITTED →
  (CORRECTION_NEEDED loop) → JOINING_FORM_LOCKED →
  ID_PENDING → ID_ISSUED → NDA_PENDING → NDA_SIGNED →
  ACCESS_PENDING → ACTIVE → (EXTENDED?) →
  CLOSURE_PENDING → CLOSED
Terminals: HR_REJECTED, CANDIDATE_REJECTED, NDA_TIMEOUT_REJECTED,
           NDA_DECLINED_REJECTED, TERMINATED
```

**Intern:** `ACCESS_PENDING → ACTIVE → (EXTENDED?) → CLOSURE_PENDING → CLOSED` · terminal `TERMINATED`.

**Mentor:** `PENDING → (ACCEPTED | REJECTED | TIMED_OUT | REASSIGNED)`.

**NDA:** `PENDING → SENT → (SIGNED | DECLINED | EXPIRED)`.

### 3.7 Configuration & governance

| Setting | Default | Editable by |
|---|---|---|
| Mentor capacity threshold | 4 active mentees | PO |
| Cooling-off: NDA_DECLINED_REJECTED | 6 months | PO |
| Cooling-off: TERMINATED | 6 months | PO |
| Cooling-off: NDA_TIMEOUT_REJECTED | 3 months | PO |
| Cooling-off: HR_REJECTED | 3 months | PO |
| Cooling-off: CANDIDATE_REJECTED | 0 months | PO |
| Cooling-off: CLOSED | 3 months | PO |

Override permission: `OVERRIDE_COOLING_PERIOD` (PO only, RULE-CP7).

Source: [backend/app/modules/admin/router.py](../backend/app/modules/admin/router.py), [backend/app/modules/referral/models.py](../backend/app/modules/referral/models.py).

### 3.8 Error responses

| Code | Class | Scenario |
|---|---|---|
| 400 | `ValidationError` | Bad shape (e.g. year_of_study not 2–4) |
| 401 | `AuthError` | Invalid/missing token |
| 403 | `InsufficientPermissionsError` | Role lacks permission |
| 409 | `BusinessRuleError` | Duplicate PAN, college cap, year restriction |
| 422 | `ValidationError` | Form validation |
| 503 | `ExternalServiceError` | Azure / OpenSign / Gmail down |

Source: [backend/app/shared/exceptions.py](../backend/app/shared/exceptions.py).

---

## 4. Incomplete / Stub Functionality

> All 15 of the original incomplete items now have functional code. Two services that this deployment doesn't use (Microsoft Graph for AD provisioning; OpenSign for NDA e-signature) have been replaced by Postgres-only modes — see [Iteration 3](#iteration-3--staging-replacements-2-items) below. The only remaining gap is the optional admin UI for editing notification templates.

| # | Feature | Status | Note |
|---|---|---|---|
| 13 | Email template editor UI | ⚠ backend done, no UI | `GET\|PATCH /admin/notification-templates` shipped — admin frontend page not built (out of scope) |

### Completed across the two recent iterations ✅

**Iteration 1 — quick wins (8 items)**

| # | Feature | What shipped |
|---|---|---|
| 5 | Candidate early-termination UI | `GET /candidate/intern` + termination button on [CandidateStatusPage](../frontend/src/modules/candidate/components/CandidateStatusPage.tsx) |
| 6 | Referrer early-termination UI | New [MyReferralsPage](../frontend/src/modules/referral/components/MyReferralsPage.tsx) at `/referrals` and `/referrals/mine`; `ReferralSummary` now carries `intern_id` + `intern_status` |
| 9 | Mentor OOO calendar UI | `GET\|PUT /auth/me/out-of-office` + `OutOfOfficePanel` on MentorWorkspacePage |
| 10 | HR-triggered joining-form lock | `POST /hr/onboarding/joining-form/{intern_id}/lock` (new `hr_onboarding_router`) |
| 11 | Manual certificate generation | `POST /interns/{intern_id}/generate-certificate` calls AI-8 `auto_send_for_intern` |
| 12 | Cooling-off override endpoint | `POST /admin/cooling-overrides/{referral_id}` with PO permission + min 50-char reason |
| 14 | Admin SLA dashboard RBAC | `VIEW_SLA_DASHBOARD` granted to ADMIN role in [rbac.py](../backend/app/modules/auth/rbac.py) |
| 15 | List-all-referrals endpoint | `GET /referrals/hr/all` with status/college/text filters + pagination |

**Iteration 2 — wiring + integrations (6 items)**

| # | Feature | What shipped |
|---|---|---|
| 1 | Gmail send wired | Removed unused `NotImplementedError` stub. [gmail_client.py](../backend/app/infrastructure/gmail_client.py) now exposes a real `send_html()` that uses `is_configured()` for dev-mode fallback. `notification/service.py` calls it directly instead of poking private internals. **Activates when Gmail creds are set.** |
| 2 | MS Graph AD provisioning | [graph_client.py](../backend/app/modules/access/graph_client.py) had a real implementation already — verified working with dev fallback. **Activates when Graph creds are set.** |
| 3 | NDA template storage | New [_load_nda_template()](../backend/app/modules/nda/service.py) loader: local path → Blob → bundled placeholder. Configured via `NDA_TEMPLATE_LOCAL_PATH` and `NDA_TEMPLATE_VERSION` env vars. |
| 4 | Offer letter Jinja2 | New [templates/offer_letter.html](../backend/app/modules/notification/templates/offer_letter.html) with proper styling, terms, candidate-portal CTA. `offer_letter._render_html()` now delegates to `template_renderer.render()`. |
| 7 | Mentor skills | New `users.skills` JSONB column (migration `0018_skills`) + `GET\|PUT /auth/me/skills` + [SkillsPanel](../frontend/src/modules/mentor/components/MentorWorkspacePage.tsx) on MentorWorkspacePage. AI-2 matcher's `_mentor_skills()` now reads the real column. |
| 8 | AI cost tracking | New `azure_openai.record_usage()` + 500-event ring buffer + auto-instrumentation inside `call_with_retry()` (latency + tokens). `GET /admin/ai-usage` returns the snapshot. App Insights remains canonical aggregator once configured. |
| 13 | Notification template management (backend) | `GET /admin/notification-templates` and `PATCH /admin/notification-templates/{template_id}` (PO only) with audit trail; new `updated_by`/`updated_at` columns. Frontend admin UI pending. |

#### Iteration 3 — staging replacements (2 items)

The user's stack (Postgres + Gmail + Azure AD + Blob + OpenAI + Doc Intelligence + Key Vault + Azure Cache for Redis) does not include OpenSign or a Microsoft Graph permission grant for Graph-based AD provisioning. Both have been swapped for Postgres-only equivalents:

| # | Feature | What shipped |
|---|---|---|
| OpenSign → in-app NDA | NDA acceptance now happens entirely in NexHire | Migration `0019_nda_inapp` adds 4 audit columns to `nda_records` (`typed_name`, `accepted_ip`, `accepted_user_agent`, `text_sha256`). New endpoints `GET /candidate/nda` + `POST /candidate/nda/accept`. New [CandidateNdaPage](../frontend/src/modules/candidate/components/CandidateNdaPage.tsx) renders the agreement, requires checkbox + typed legal name, and posts back the SHA-256 of the version read. New service helpers `nda.service.accept_inapp()`, `_by_intern_id()`, `render_nda_html()`. New Jinja template [templates/nda.html](../backend/app/modules/notification/templates/nda.html). OpenSign webhook router stays mounted but inert when `OPENSIGN_BASE_URL=""`. |
| MS Graph → Postgres-only AD | New `AD_PROVISIONING_MODE` config flag (`graph` \| `postgres`, default `postgres`) | When `postgres`, `complete_ad_provisioning` skips the Graph call and records a synthetic `intern-<short>@nexhire.local` username locally. Audit row carries `payload.provisioning_mode='postgres'`. Flip back to Graph by setting `AD_PROVISIONING_MODE=graph` and providing `GRAPH_*` creds — no code change. |

---

## 5. Endpoint Count by Module

| Module | Endpoints | Status |
|---|---|---|
| `auth` | 9 | ✅ login, refresh, logout, me, jwks, OOO get/put, skills get/put |
| `referral` | 4 + 7 (HR) + 2 (college) | ✅ submit, list, detail, college-cap; HR queue/all/recent-ai/review/approve/reject/correction/reassign/recall; college-search |
| `mentor` | 3 | ✅ picker, suggest, action confirm |
| `lifecycle` | 6 | ✅ my-interns, confirm-start, extend, completion, terminate, generate-certificate |
| `onboarding` | 7 + 1 (HR) | ✅ redeem, intern, form get/patch/submit/extract, NDA get/accept; HR lock |
| `access` | 2 | ✅ AD provision (Graph or Postgres-only), badge complete |
| `admin` | 11 | ✅ overview, audit, SLA, config get/set, history, chatbot, cooling-override, notification-templates list/patch, ai-usage |
| `nda` | 1 (webhook) | ✅ OpenSign signed/declined events |
| **Total** | **67** | **All app code paths wired; runs end-to-end on the staging stack** |

---

## 6. References

- [docs/System_Blueprint.md](System_Blueprint.md) — full system spec.
- [docs/System_Flow.md](System_Flow.md) — workflow & state machines.
- [docs/Implementation_Plan.md](Implementation_Plan.md) — binding decision log and build sequence.
- [docs/Architecture_Analysis.md](Architecture_Analysis.md) — architecture deep dive.
- Code: [backend/app/modules/](../backend/app/modules/), [frontend/src/modules/](../frontend/src/modules/).

---

## 7. Credentials & external resources checklist

The application code is now complete. To run end-to-end in production you need to obtain and configure the following. Each block lists the env-var name (set in `backend/.env`), what the service does in NexHire, and exactly how to obtain it.

### Recommended setup for the user's current stack

The user has confirmed this stack: **local Postgres, Gmail, Azure AD, Azure Blob, Azure OpenAI, Azure Document Intelligence, Azure Key Vault, Azure Cache for Redis**. With those configured plus locally-generated JWT + PAN keys, the platform runs end-to-end. NDA signing is handled in-app (Iteration 3); MS Graph AD provisioning is replaced by Postgres-only mode.

Checklist (set in `backend/.env`):

- [ ] `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/nexhire` (§ Postgres setup below)
- [ ] `REDIS_URL=rediss://:<access-key>@<cache-name>.redis.cache.windows.net:6380/0` — note `rediss://` (TLS) + port 6380
- [ ] `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET` — your AAD app registration (SSO only; no Graph perms needed)
- [ ] `AZURE_BLOB_ACCOUNT_URL` — see §C
- [ ] `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, deployment names — see §D
- [ ] `AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY` — for AI-6 ID extraction
- [ ] `AZURE_KEY_VAULT_URL` — see §G (optional but recommended for staging)
- [ ] `GMAIL_SERVICE_ACCOUNT_JSON_PATH`, `GMAIL_SENDER_EMAIL`, `GMAIL_DOMAIN_DELEGATED_USER` — see §A
- [ ] `JWT_PRIVATE_KEY_PEM`, `JWT_PUBLIC_KEY_PEM` — generate per §I
- [ ] `PAN_HMAC_PEPPER`, `PAN_AES_KEY` — generate per §H
- [ ] `AD_PROVISIONING_MODE=postgres` (default — explicit for staging)
- [ ] Leave blank: `OPENSIGN_*`, `GRAPH_*`, `APPLICATIONINSIGHTS_CONNECTION_STRING`, `NDA_TEMPLATE_LOCAL_PATH`

After populating: `cd backend && uv run alembic upgrade head && uv run fastapi dev app/main.py`. Then `cd frontend && pnpm install && pnpm dev`.

§B (Microsoft Graph) and §E (OpenSign) below are kept as reference for production but are **superseded by Postgres-only modes** in this deployment.

### A. Gmail (transactional email send)

**Used for** — Every outbound email: mentor action tokens, candidate magic links, offer letter, NDA signing reminders, certificate delivery.

**Env vars (in `backend/.env`):**
- `GMAIL_SERVICE_ACCOUNT_JSON_PATH` — absolute path to the service-account key JSON.
- `GMAIL_SENDER_EMAIL` — the From address (e.g. `nexhire-noreply@yourdomain.com`).
- `GMAIL_DOMAIN_DELEGATED_USER` — the same address (the user the service account impersonates).

**Steps to obtain:**
1. Open https://console.cloud.google.com/ and create (or pick) a project.
2. Enable the Gmail API — APIs & Services → Library → search "Gmail API" → Enable.
3. APIs & Services → Credentials → **Create Credentials → Service account**. Name it `nexhire-gmail`. No roles needed.
4. Open the service account → **Keys → Add Key → Create new key → JSON**. Download the file, put it somewhere safe on the backend host. Never commit it.
5. On the service account's detail page, copy the **Unique ID** (a long number).
6. Open Google Workspace Admin (`admin.google.com`) as a super-admin → **Security → Access and data control → API controls → Domain-wide delegation → Add new**.
7. Paste the Unique ID, set the OAuth scope to `https://www.googleapis.com/auth/gmail.send`, save.
8. In Workspace, create the alias mailbox `nexhire-noreply@yourdomain.com` (or whichever sender address you chose) so the service account has someone to impersonate.
9. Set the three env vars above and restart the backend. Logs will switch from `nexhire.gmail.dev_send` to actual Gmail message IDs.

### B. Microsoft Graph (Azure AD account provisioning) — *superseded in this deployment*

> **In staging mode:** set `AD_PROVISIONING_MODE=postgres` (the default). IT clicking "Mark AD provision complete" writes a synthetic `intern-<short>@nexhire.local` username to Postgres and skips Graph entirely. The block below is the production path; ignore it unless interns actually need to log into corporate AD.

**Used for** — IT marks an intern's AD provisioning task complete; the backend creates the Azure AD account via Graph (`POST /v1.0/users`) and stores the UPN + temporary password.

**Env vars:**
- `GRAPH_TENANT_ID` — your Azure AD tenant GUID.
- `GRAPH_CLIENT_ID` — the app registration's Application (client) ID.
- `GRAPH_CLIENT_SECRET` — a client secret you generate.

**Steps:**
1. Open https://portal.azure.com/ → Azure Active Directory → **App registrations → New registration**. Name `NexHire Graph Provisioning`, single-tenant.
2. After creation, copy **Directory (tenant) ID** and **Application (client) ID** — those are `GRAPH_TENANT_ID` and `GRAPH_CLIENT_ID`.
3. **Certificates & secrets → New client secret**. Copy the **Value** immediately (it disappears after navigation) — that's `GRAPH_CLIENT_SECRET`.
4. **API permissions → Add a permission → Microsoft Graph → Application permissions** → enable `User.ReadWrite.All` (and `Directory.ReadWrite.All` if you'll later use enable/disable). Click **Grant admin consent**.
5. Set the three env vars and restart. With creds present, `complete_ad_provisioning` actually creates accounts; without them, the existing dev fallback returns `dev-<nickname>` IDs.

### C. Azure Blob Storage (offer letters, certificates, NDA template)

**Used for** — Persisting generated PDFs (offer letter, certificate, signed NDA) and serving the NDA template to OpenSign.

**Env vars:**
- `AZURE_BLOB_ACCOUNT_URL` — e.g. `https://<storage-acct>.blob.core.windows.net`.
- `AZURE_BLOB_CONTAINER_DOCUMENTS` — defaults to `documents`. Create this container.
- `AZURE_BLOB_CONTAINER_TEMP` — defaults to `temp-uploads`.
- `NDA_TEMPLATE_VERSION` — e.g. `v1`. The loader fetches `<documents>/templates/nda-v1.pdf`.

**Steps:**
1. Azure portal → **Storage accounts → Create**. Use Standard performance, LRS redundancy is fine for v1.
2. Once created → **Containers → + Container** → name `documents`. Repeat for `temp-uploads`.
3. **Containers → documents → Upload** → upload your real NDA template as `templates/nda-v1.pdf`.
4. NexHire authenticates via `DefaultAzureCredential`. Either:
   - **Easy path**: assign the backend host's Managed Identity (or your dev account via `az login`) the **Storage Blob Data Contributor** role on this account.
   - **Alternate**: switch the code to a connection string — open an issue if you prefer that route.
5. Set the env var. The first NDA issuance will pull the real template.

**Local dev shortcut:** set `NDA_TEMPLATE_LOCAL_PATH=/some/local/file.pdf` to skip Blob entirely.

### D. Azure OpenAI (already used by AI-1..AI-9)

**Used for** — Resume parsing, mentor matching narratives, risk profiling, certificate citations, chatbot.

**Env vars:**
- `AZURE_OPENAI_ENDPOINT` — e.g. `https://<resource>.openai.azure.com/`.
- `AZURE_OPENAI_API_KEY` — the resource's primary key.
- `AZURE_OPENAI_DEPLOYMENT_GPT4O` — your GPT-4o deployment name (defaults to `gpt-4o`).
- `AZURE_OPENAI_DEPLOYMENT_EMBEDDINGS` — your embedding deployment (defaults to `text-embedding-3-large`).

**Steps:**
1. Azure portal → **Create Azure OpenAI resource** (requires approved access — apply at https://aka.ms/oai/access if you don't have it yet).
2. Once provisioned, open Azure OpenAI Studio → **Deployments → Create new deployment**. Deploy `gpt-4o` and `text-embedding-3-large`. Note the deployment names.
3. Back in the portal, **Keys and Endpoint** — copy both into env vars.
4. Without these, every AI feature degrades gracefully (rule-based fallbacks) — the platform still works, but mentor narratives, risk scoring, and chatbot will use static text.

### E. OpenSign (NDA e-signature) — *superseded in this deployment*

> **In staging mode:** leave `OPENSIGN_BASE_URL` blank. NDA acceptance happens in-app at `/candidate/nda` and is recorded in `nda_records` (typed name + IP + UA + text SHA-256). See [Iteration 3 in §4](#iteration-3--staging-replacements-2-items). The block below is the production path; ignore it unless you need a notarized PDF audit trail.

**Used for** — Sending the NDA envelope, receiving signed/declined webhooks.

**Env vars:**
- `OPENSIGN_BASE_URL` — your OpenSign deployment URL.
- `OPENSIGN_API_KEY` — generated in the OpenSign admin UI.
- `OPENSIGN_WEBHOOK_SIGNING_SECRET` — used to verify webhook authenticity.

**Steps:**
1. OpenSign can be self-hosted (https://www.opensignlabs.com) or used as SaaS. For self-host: follow their Docker compose instructions.
2. Once running → **Settings → API tokens → Generate**. Copy the token.
3. **Settings → Webhooks → Add webhook** pointing at `https://<your-backend>/api/v1/webhooks/opensign`. Copy the signing secret.
4. Configure all three env vars and restart. With them set, NDA issuance creates real envelopes; without them, the FSM uses the existing `dev-env-<intern_id>` shortcut.

### F. Application Insights (observability — optional but recommended)

**Used for** — Aggregating the structured `nexhire.openai.usage` log lines (and other logs) into queryable metrics + dashboards.

**Env var:**
- `APPLICATIONINSIGHTS_CONNECTION_STRING` — from the App Insights resource overview.

**Steps:**
1. Azure portal → **Application Insights → Create**. Workspace-based, in the same region as the backend.
2. Copy the **Connection String** from the overview blade.
3. Set the env var. The structured logs (`nexhire.openai.usage`, `nexhire.notification.*`, `nexhire.audit.*`) flow into AI Logs automatically through whatever logging shipper you choose (e.g. OpenTelemetry Python). Without this, the in-process `GET /admin/ai-usage` snapshot still gives you the last 100 calls.

### G. Azure Key Vault (production-only — secret storage)

**Used for** — Resolving every secret above from a vault rather than `.env`. The code already does this via `infrastructure/azure_keyvault.py` when `AZURE_KEY_VAULT_URL` is set.

**Env var:**
- `AZURE_KEY_VAULT_URL` — e.g. `https://<vault-name>.vault.azure.net/`.

**Steps:**
1. Azure portal → **Key vaults → Create**. RBAC permission model.
2. Grant the backend's Managed Identity the **Key Vault Secrets User** role.
3. Add secrets named exactly as the env-var keys (e.g. `gmail-service-account-json-path`).
4. Set `AZURE_KEY_VAULT_URL`. The settings loader prefers the vault over local `.env` for any secret it finds.

### H. PAN encryption (mandatory before any real candidate data)

**Env vars:**
- `PAN_HMAC_PEPPER` — 32+ random bytes (used for blind-index lookups).
- `PAN_AES_KEY` — base64-encoded 32-byte key (used for at-rest encryption of full PAN).

**Generate locally:**
```bash
python -c "import secrets, base64; print('PAN_HMAC_PEPPER=' + secrets.token_hex(32)); print('PAN_AES_KEY=' + base64.b64encode(secrets.token_bytes(32)).decode())"
```

Add the output to `backend/.env`. **In production, store both in Key Vault, not the env file.**

### I. JWT signing keys

**Env vars:**
- `JWT_PRIVATE_KEY_PEM` — RSA private key for signing.
- `JWT_PUBLIC_KEY_PEM` — matching public key for verification (also exposed via JWKS endpoint).

**Generate locally:**
```bash
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem
# Then paste the PEM contents (with newlines escaped as \n) into the env vars.
```

Or use Python:
```python
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
print('JWT_PRIVATE_KEY_PEM:'); print(priv)
print('JWT_PUBLIC_KEY_PEM:'); print(pub)
```

### Minimum viable env to actually log in

If you just want to bring up the system and click around without external integrations:

```dotenv
# Required for app to start
DATABASE_URL=postgresql+asyncpg://localhost/nexhire
REDIS_URL=redis://localhost:6379/0

# Required for auth to work (generate per §I)
JWT_PRIVATE_KEY_PEM=...
JWT_PUBLIC_KEY_PEM=...

# Required before storing any candidate (generate per §H)
PAN_HMAC_PEPPER=...
PAN_AES_KEY=...

# At least Azure AD client for SSO login (no Graph perms needed for SSO)
AZURE_AD_TENANT_ID=...
AZURE_AD_CLIENT_ID=...

# Everything else can stay empty — features degrade gracefully.
```

With just the above, you get: SSO login, full referral / mentor / HR flows, joining form, lifecycle, dashboards. AI features fall back to rules. Email goes to logs. AD provisioning skips. Cert/NDA PDFs use the bundled placeholder.
