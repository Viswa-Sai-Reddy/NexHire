# NexHire — System Flow Document
## Version 2.1 | All Flows · All Actors · All Edge Cases

> **Platform:** AI-Powered Intern Referral Management
> **Architecture:** React + TypeScript · Python FastAPI · Modular Monolith
> **Document Type:** System Flow Reference
> **Companion Document:** NexHire System Blueprint v2.1

---

## Document Overview

This document describes every system flow in NexHire — from the moment an employee logs in to the moment an intern's record is closed and certified. Each flow includes:

- Actor responsible for each step
- System actions (automated)
- AI touchpoints
- Decision gates and guards
- Error paths and recovery
- State changes

---

## Table of Contents

| # | Flow | Category |
|---|---|---|
| F-01 | [Master End-to-End Lifecycle Flow](#f-01-master-end-to-end-lifecycle-flow) | Master |
| F-02 | [Employee Authentication Flow](#f-02-employee-authentication-flow) | Auth |
| F-03 | [Candidate Magic Link Access Flow](#f-03-candidate-magic-link-access-flow) | Auth |
| F-04 | [Referral Submission Flow](#f-04-referral-submission-flow) | Referral |
| F-05 | [AI Resume Analysis Flow](#f-05-ai-resume-analysis-flow) | AI |
| F-06 | [Duplicate Detection Flow](#f-06-duplicate-detection-flow) | AI |
| F-07 | [Eligibility & Risk Profiling Flow](#f-07-eligibility--risk-profiling-flow) | AI |
| F-08 | [Mentor Assignment Flow](#f-08-mentor-assignment-flow) | Mentor |
| F-09 | [Mentor Accept Flow](#f-09-mentor-accept-flow) | Mentor |
| F-10 | [Mentor Reject Flow](#f-10-mentor-reject-flow) | Mentor |
| F-11 | [Mentor Timeout & Auto-Reassignment Flow](#f-11-mentor-timeout--auto-reassignment-flow) | Mentor |
| F-12 | [Candidate Rejection — Max Attempts Flow](#f-12-candidate-rejection--max-attempts-flow) | Mentor |
| F-13 | [HR Review & Approval Flow](#f-13-hr-review--approval-flow) | HR |
| F-14 | [Candidate Joining Form Flow](#f-14-candidate-joining-form-flow) | Onboarding |
| F-15 | [Joining Form Lock & Non-Worker ID Flow](#f-15-joining-form-lock--non-worker-id-flow) | HR |
| F-16 | [NDA Issuance & Signing Flow](#f-16-nda-issuance--signing-flow) | Document |
| F-17 | [NDA Auto-Rejection Flow](#f-17-nda-auto-rejection-flow) | Document |
| F-18 | [Access Provisioning Flow](#f-18-access-provisioning-flow) | IT/Admin |
| F-19 | [Pre-Start Compliance Check Flow](#f-19-pre-start-compliance-check-flow) | AI |
| F-20 | [Internship Active & Execution Flow](#f-20-internship-active--execution-flow) | Lifecycle |
| F-21 | [Internship Extension Flow](#f-21-internship-extension-flow) | Lifecycle |
| F-22 | [Closure & Certificate Flow](#f-22-closure--certificate-flow) | Closure |
| F-23 | [Email Action Token Flow](#f-23-email-action-token-flow) | Email |
| F-24 | [OpenSign Webhook Flow](#f-24-opensign-webhook-flow) | Integration |
| F-25 | [AI Mentor Match Engine Flow](#f-25-ai-mentor-match-engine-flow) | AI |
| F-26 | [SLA Breach & Escalation Flow](#f-26-sla-breach--escalation-flow) | Workflow |
| F-27 | [AI Bottleneck Prediction Flow](#f-27-ai-bottleneck-prediction-flow) | AI |
| F-28 | [Program Intelligence Chatbot Flow](#f-28-program-intelligence-chatbot-flow) | AI |
| F-29 | [Workflow Auto-Router Flow](#f-29-workflow-auto-router-flow) | AI |
| F-30 | [Error Handling Flows](#f-30-error-handling-flows) | Error |
| F-31 | [Master State Machine](#f-31-master-state-machine) | State |
| F-32 | [Audit Trail Flow](#f-32-audit-trail-flow) | Compliance |

---

## F-01: Master End-to-End Lifecycle Flow

This is the complete happy-path flow from referral submission to internship closure. All sub-flows are detailed individually in subsequent sections.

```
ACTOR          ACTION / EVENT                           SYSTEM RESPONSE                 STATUS CHANGE
─────────────────────────────────────────────────────────────────────────────────────────────────────────

REFERRER       Logs in via Azure AD SSO               JWT issued, role resolved        —
               ↓
REFERRER       Opens New Referral Form (S4)            Form initialized, AI ready      —
               Uploads candidate resume                AI-1: Resume Deep Analyzer      —
               ↓                                       Prefill form fields
               Selects year of study                   RULE-E1: year check             BLOCKED if 1st/grad
               Selects college                         RULE-E2: college cap check      BLOCKED if 2/2 used
               Selects mentor from picker              AI-2: Mentor suggestions shown  BLOCKED if mentor full
               Submits referral form                   AI-3: Risk profile generated    DRAFT → SUBMITTED
               ↓                                       AI-4: Duplicate check run
                                                       Emails: Referrer (confirm)
                                                               Mentor (assignment)

MENTOR         Receives assignment email               Action token created (3d expiry) MENTOR_PENDING
               Clicks [Accept] or [Reject]             Token validated                 —
               ↓
               IF ACCEPT ──────────────────────────────────────────────────────────────MENTOR_ACCEPTED
               IF REJECT → selects reason ─────────────────────────────────────────────MENTOR_REJECTED
               IF TIMEOUT (3 days) ────────────────────────────────────────────────────MENTOR_TIMED_OUT
               ↓ (on reject or timeout, attempts < 3)
REFERRER       Receives notification                   AI-2: New suggestions           MENTOR_PENDING
               Selects new mentor                      New action token sent           MENTOR_PENDING
               ↓ (on 3rd failure)
SYSTEM         Auto-rejects candidate                  Emails: Referrer + Candidate    CANDIDATE_REJECTED ❌

               ↓ (on accept)
HR             Receives review notification            AI-10: Task auto-routed         HR_REVIEW
               Reviews referral + AI analysis          Risk profile, duplicate flags   —
               Approves referral                       Email: Candidate (congrats)     APPROVED
               ↓                                       Magic link sent to candidate

CANDIDATE      Receives congratulations email          —                               —
               Clicks magic link                       Token validated, JWT issued     —
               Fills Joining Form (S9)                 AI-6: Form Assistant active     —
               Uploads ID proof                        AI-6: Extracts DOB, ID fields   —
               Submits joining form                    Email: HR (review task)         JOINING_FORM_SUBMITTED
               ↓

HR             Reviews joining form                    AI-10: Task auto-routed         —
               Locks joining form                      SLA clock starts (1 business day) JOINING_FORM_LOCKED
               Creates Non-Worker ID                   SLA tracked (T+4h warn, T+8h esc) ID_ISSUED
               ↓

SYSTEM         Issues NDA via OpenSign                 OpenSign API: envelope created  NDA_PENDING
               ↓
CANDIDATE      Receives NDA email from OpenSign        Day 1,2,3 reminders if no sign  —
               Signs NDA digitally                     OpenSign webhook → NDA_SIGNED   NDA_SIGNED
               ↓ (if no sign by Day 5)
SYSTEM         Auto-rejects referral                   Emails: Referrer + Candidate    NDA_TIMEOUT_REJECTED ❌

               ↓ (on NDA signed)
HR             Generates offer/confirmation letter     AI-8 (adapted): letter drafted  —
               Reviews and sends                       Archived to Azure Blob          —
               ↓

ADMIN          Receives badge setup task               AI-10: Auto-routed              —
               Configures site access                  Task completed + logged         —
               ↓

IT/AD          Receives provisioning task              Microsoft Graph API: AD created —
               Credentials delivered to candidate      OTP magic link (not stored)     ACCESS_PENDING
               ↓

MENTOR         Receives intern dossier link            AI-7 (pre-start check at T-48h) —
               ↓
SYSTEM         Pre-start compliance check fires (T-48h) AI-7: All blockers evaluated   —
               Auto-escalates any red items            Emails: HR + Program Owner      —
               ↓

MENTOR         Confirms intern started (Day 1)         Start clock begins              ACTIVE
               ↓

SYSTEM         AI-5 Bottleneck Predictor runs (6-hrly) Risk scores per active intern   —
               SLA breach checks run (hourly)          Escalations fired if breached   —
               ↓

MENTOR         Confirms internship completion          Closure workflow triggered      CLOSURE_PENDING
               ↓

IT/AD          Deactivates AD account                  Graph API: account disabled     —
               (SLA: ≤24h)
               ↓

ADMIN          Deactivates badge                       Task completed                  —
               ↓

CANDIDATE      Receives certificate request link       Magic link → cert form          —
               Submits request                         HR notified                     —
               ↓

HR             Reviews certificate request             AI-8: Citation generated        —
               Approves certificate                    PDF on letterhead generated     —
               Delivers to candidate                   Azure Blob SAS link             CLOSED ✅
```

---

## F-02: Employee Authentication Flow

```
ACTOR       STEP                                    SYSTEM ACTION                   OUTCOME
──────────────────────────────────────────────────────────────────────────────────────────────

EMPLOYEE    Navigates to NexHire portal             MSAL redirect to Azure AD       —
            ↓
AZURE AD    Authenticates employee                  OIDC token issued               —
            ↓
BACKEND     Receives OIDC token                     Validates token signature        —
            ↓
            Checks if user exists in DB             If new: create user record       —
            ↓
            Reads role from nexhire users table     Role NOT read from Azure AD      —
            (Role is NexHire-managed, not IdP-managed)
            ↓
            Issues NexHire JWT (RS256, 8h)          Claims: {userId, role, email}    —
            Stores refresh token in Redis           Encrypted, 24h TTL              —
            ↓
FRONTEND    Receives JWT                            Stored in memory (not localStorage) —
            Redirects to role-based home screen:
              REFERRER      → S3 My Dashboard
              MENTOR        → S18 Mentor Dashboard
              HR            → S11 HR Dashboard
              IT_AD         → S21 Task Queue
              ADMIN         → S22 Task Queue
              PROGRAM_OWNER → S23 Executive Dashboard

ERROR PATHS:
  Azure AD unreachable    → Show: "Login service is temporarily unavailable."
                            Retry button shown
  User not in Azure AD   → 401 from Azure AD → redirect to IT contact page
  Role not assigned       → User record created with NULL role
                            Show: "Your account is pending role assignment. Contact HR."
  JWT issuance fails      → 500 → global error handler → user shown request_id
```

---

## F-03: Candidate Magic Link Access Flow

```
ACTOR       STEP                                    SYSTEM ACTION                   OUTCOME
──────────────────────────────────────────────────────────────────────────────────────────────

SYSTEM      Referral approved by HR                 Magic link generated:           —
            ↓                                         raw_token = UUID v4
                                                      token_hash = SHA-256(token)
                                                      stored in action_tokens table
                                                      expires_at = NOW() + 72h
                                                    Gmail API: email sent to candidate
                                                    with link:
                                                    /candidate/access?token=<raw_token>

CANDIDATE   Clicks link in email                    GET /candidate/access?token=X   —
            ↓
BACKEND     Hashes incoming token                   SHA-256(X)                      —
            Looks up token_hash in action_tokens    —                               —
            ↓
            VALIDATION CHECKS:
            ┌─ token not found?     → 401 MAGIC_LINK_INVALID
            ├─ token expired?       → 401 MAGIC_LINK_EXPIRED
            │   └─ Show: "This link has expired. Contact HR for a new link."
            └─ token valid ─────────────────────────────────────────────────────► continue

            Issues candidate JWT:
              claims: { userId, role: CANDIDATE, internId, scope: OWN_RECORD_ONLY }
              expiry: 8 hours
            ↓
            Reads intern.status → determines redirect:
              APPROVED              → /candidate/joining-form
              JOINING_FORM_LOCKED   → /candidate/nda
              NDA_SIGNED            → /candidate/status (waiting for start)
              CLOSED                → /candidate/certificate

CANDIDATE   Lands on correct screen automatically   No navigation needed            —

SESSION MANAGEMENT:
  Candidate JWT expires in 8 hours
  No refresh token for candidates (security: limited scope session)
  New magic link request: candidate emails HR or clicks "Resend link"
    → HR generates fresh link via S15 (NDA & Letters Management)
    → Previous unused tokens for same intern invalidated
```

---

## F-04: Referral Submission Flow

```
ACTOR       STEP                                    SYSTEM ACTION / VALIDATION      STATE
──────────────────────────────────────────────────────────────────────────────────────────────

REFERRER    Opens S4 New Referral Form              Multi-step wizard initialized   —
            ↓
            ┌─────────────────────────────────────────────────────────────────────┐
            │ STEP 1: CANDIDATE BASICS                                            │
            │                                                                     │
            │  Upload Resume ──────────────────────────► AI-1 fires (async)       │
            │    └─ Prefill: name, email, phone,          Confidence scores shown   │
            │              education, skills              Amber tint on AI fields   │
            │                                                                     │
            │  Enter year of study                        RULE-E1 check:           │
            │    └─ 1st year selected?  ─────────────────► BLOCK immediately       │
            │    └─ Graduated?         ─────────────────► BLOCK immediately        │
            │    └─ 2nd/3rd/4th year   ─────────────────► continue                 │
            │                                                                     │
            │  Enter college name                         RULE-E2 check:           │
            │    └─ count = 1/2        ─────────────────► warning badge shown      │
            │    └─ count = 2/2        ─────────────────► BLOCK: cannot proceed    │
            │    └─ count < 1          ─────────────────► continue                 │
            └─────────────────────────────────────────────────────────────────────┘
            ↓ [Next]
            ┌─────────────────────────────────────────────────────────────────────┐
            │ STEP 2: ELIGIBILITY CONFIRMATIONS                                   │
            │                                                                     │
            │  ☐ Candidate confirms unpaid internship    RULE-E4: must be checked  │
            │  ☐ Candidate confirms in-person readiness  RULE-E5: must be checked  │
            │  ☐ Relationship declaration (dropdown)     Free-text if "Other"      │
            │                                                                     │
            │  AI-3: Risk Profiler runs on form data     Risk score + narrative    │
            │    shown to referrer as advisory info                               │
            └─────────────────────────────────────────────────────────────────────┘
            ↓ [Next]
            ┌─────────────────────────────────────────────────────────────────────┐
            │ STEP 3: MENTOR SELECTION                                            │
            │                                                                     │
            │  AI-2: Mentor suggestions load (top 3)     Radar chart per mentor    │
            │    Shows: Match %, slots (n/4), reason                              │
            │    Full mentors (4/4) shown as FULL ─────────► unselectable         │
            │                                                                     │
            │  Referrer selects mentor                   RULE-E3: referrer ≠       │
            │    └─ Same as referrer? ──────────────────► BLOCK immediately        │
            │    └─ Mentor at 4/4?   ──────────────────► BLOCK (UI prevents this) │
            │    └─ Valid mentor     ──────────────────► continue                  │
            └─────────────────────────────────────────────────────────────────────┘
            ↓ [Next]
            ┌─────────────────────────────────────────────────────────────────────┐
            │ STEP 4: INTERNSHIP DETAILS                                          │
            │                                                                     │
            │  Project title, overview                   500 char limit           │
            │  Start date (must be future)               VALIDATION: not past      │
            │  End date (must be after start)            VALIDATION: end > start   │
            │  Joining location                          Must match org locations  │
            └─────────────────────────────────────────────────────────────────────┘
            ↓ [Review & Submit]
            ┌─────────────────────────────────────────────────────────────────────┐
            │ STEP 5: REVIEW                                                      │
            │                                                                     │
            │  AI-4: Duplicate check runs                Result shown:            │
            │    score ≥ 0.9 ──────────────────────────► BLOCK with match details │
            │    score 0.6–0.89 ───────────────────────► WARNING: confirm to      │
            │                                             proceed (HR must verify) │
            │    no duplicate ─────────────────────────► proceed                  │
            │                                                                     │
            │  Summary of all entered data               Referrer confirms        │
            └─────────────────────────────────────────────────────────────────────┘
            ↓ [Submit]

BACKEND     Validates all fields (server-side)      Re-runs all RULE-E1 to RULE-E5 —
            (Never trust client-only validation)    Re-runs RULE-E2, RULE-E3
            ↓
            Creates Referral record                 status = SUBMITTED              SUBMITTED
            Logs: submitted_at, referrer_id,        Immutable audit event           —
                  mentor_id, ai_parse_result_id
            ↓
            Publishes: ReferralSubmitted event      —                               —
            ↓
NOTIFICATION  Email → Referrer (confirmation)       AI-drafted, template rendered   —
              Email → Mentor (assignment request)   Action tokens created           —
              Action token: 3-day expiry             MENTOR_PENDING state           MENTOR_PENDING
```

---

## F-05: AI Resume Analysis Flow

```
TRIGGER: Resume file uploaded in Step 1 of Referral Form (async, non-blocking)

INPUT → PIPELINE → OUTPUT
─────────────────────────────────────────────────────────────────────────────────────

UPLOAD
  Referrer uploads file
  ↓
  Validation:
    MIME type check       → reject if not PDF/DOCX/JPG/PNG
    File size check       → reject if > 5MB
    Azure Defender scan   → reject if malware detected
  ↓
  File stored temporarily in Azure Blob (temp container, 24h TTL)
  File reference passed to AI pipeline

EXTRACTION
  ↓
  File type routing:
    PDF  → Azure Document Intelligence (text extraction)
    DOCX → python-docx (text extraction)
    JPG/PNG → Azure OpenAI GPT-4o Vision
  ↓
  Raw text extracted

NLP ANALYSIS (Azure OpenAI GPT-4o)
  ↓
  Structured prompt sent:
    Extract: name, email, phone, year_of_study, college, graduation_year,
             education[], skills[], internship_readiness_score,
             technical_depth, project_experience_quality,
             suggested_project_tracks[], red_flags[],
             recommended_mentor_questions[]
  ↓
  Raw JSON response received
  ↓
  JSON validation (Pydantic model)
    Invalid JSON → retry prompt with correction instruction (max 2 retries)
    Still invalid → return empty parse result (graceful degradation)

CONFIDENCE SCORING
  ↓
  Per-field confidence assigned:
    ≥ 0.90 → HIGH   → prefill, no highlight
    0.75–0.89 → MEDIUM → prefill + amber tint + "AI Suggested" badge
    < 0.75  → LOW   → prefill + warning icon + "Please verify"
                       mandatory human review before submit
  ↓
  Result stored: ai_parse_results table
    {referral_id, model_version, parsed_at, raw_output JSONB,
     confidence_scores JSONB, tokens_used, latency_ms}

FRONTEND RENDERING
  ↓
  Fields populated in form with visual indicators
  Low-confidence fields: pulsing amber border + tooltip: "87% confident"
  Red flags section: shown to referrer as advisory
  Recommended mentor questions: shown on mentor selection step

OVERRIDE TRACKING
  ↓
  Any field edited by referrer after prefill:
    Captured as: {field, original_value, override_value, by, at}
    Stored in: ai_parse_results.human_overrides JSONB

ERROR PATHS:
  Azure OpenAI timeout (>15s)     → empty prefill, manual entry, warning toast
  Azure OpenAI rate limited       → exponential backoff (1,2,4,8s), then empty prefill
  Azure OpenAI quota exceeded     → all AI disabled, ops alerted, manual mode
  Empty extraction (blank resume) → show: "Could not extract data. Please fill manually."
  Non-resume file uploaded        → AI detects: "This does not appear to be a resume."
                                    Prompt shown to re-upload correct file
```

---

## F-06: Duplicate Detection Flow

```
TRIGGER: Referral form review step (Step 5) — runs before final submission

INPUT: candidate.email, candidate.phone, candidate.name

ALGORITHM:
  ─────────────────────────────────────────────────────────────────────────────

  1. QUERY SCOPE
     SELECT * FROM referrals
     WHERE status NOT IN ('REJECTED','CLOSED','TERMINATED',
                           'CANDIDATE_REJECTED','NDA_TIMEOUT_REJECTED',
                           'NDA_DECLINED_REJECTED')
     AND created_at > NOW() - INTERVAL '24 months'

  2. PER-CANDIDATE SCORING
     For each existing record:

       EMAIL MATCH (weight: 0.6)
         normalize: lowercase, strip whitespace, strip dots in local part
         if normalized_email matches → score += 0.6
         reason added: "email_exact_match"

       PHONE MATCH (weight: 0.4)
         normalize: E.164 format (strip spaces, dashes, country code variants)
         if normalized_phone matches → score += 0.4
         reason added: "phone_exact_match"

       NAME SIMILARITY (weight: 0.2 × similarity)
         Unicode normalize both names (NFKC)
         Jaro-Winkler similarity computed
         if similarity > 0.85 → score += similarity × 0.2
         reason added: "name_similar:{score}"

  3. DECISION THRESHOLDS
     score ≥ 0.9  → BLOCK    (near-certain duplicate)
     score 0.6–0.89 → WARN   (likely duplicate, HR must confirm)
     score < 0.6  → PASS     (no significant match)

OUTPUT SHOWN TO REFERRER:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  ⛔ Duplicate Detected (Score: 94%)                                 │
  │  Matched with: Riya Sharma — Referral #2024-0142                   │
  │  Reasons: Email exact match, Phone exact match                     │
  │  Last status: CLOSED (Internship completed June 2023)              │
  │                                                                    │
  │  [Cancel Submission]                                               │
  └──────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────────┐
  │  ⚠️ Possible Duplicate (Score: 74%)                                │
  │  Matched with: Riya S. — Referral #2024-0098                      │
  │  Reasons: Phone exact match, Name similar (88%)                   │
  │  Last status: REJECTED (HR rejection, June 2023)                  │
  │                                                                    │
  │  This may be a different candidate. HR will verify on review.     │
  │  [Proceed with Warning]    [Cancel]                               │
  └──────────────────────────────────────────────────────────────────────┘

RESULT STORED: ai_parse_results.duplicate_check JSONB
  {is_duplicate, match_id, similarity_score, match_reasons, recommendation}
```

---

## F-07: Eligibility & Risk Profiling Flow

```
TRIGGER: Real-time as referral form fields are completed (Step 2)

RULE ENGINE (Deterministic — runs first):
  ─────────────────────────────────────────────────────────────────────────
  RULE-E1: year_of_study check
    Input:  candidate.year_of_study
    Logic:  if year_of_study == 1 → BLOCK
            if graduation_year ≤ current_year → BLOCK (graduated)
            if year_of_study in [2,3,4] → PASS

  RULE-E2: College cap check
    Input:  referrer_id + candidate.college
    Query:  SELECT count FROM referrer_college_counts
            WHERE referrer_id = :id AND candidate_college = :college
    Logic:  count == 0 → PASS (first referral from this college)
            count == 1 → WARN: "1 of 2 slots used from [College]"
            count >= 2 → BLOCK: "2/2 slots used. Cannot refer more from [College]"

  RULE-E3: Referrer ≠ Mentor
    Input:  referrer_id + selected_mentor_id
    Logic:  if referrer_id == mentor_id → BLOCK

  RULE-E4: Unpaid consent
    Input:  form.unpaid_consent (boolean)
    Logic:  if false → BLOCK (cannot submit)

  RULE-E5: In-person readiness
    Input:  form.inperson_ready (boolean)
    Logic:  if false → BLOCK (cannot submit)

AI RISK NARRATIVE (Azure OpenAI — runs after rule engine):
  ─────────────────────────────────────────────────────────────────────────
  Input: all rule check results + form data
  Prompt: "Given these eligibility results and candidate details,
           write a 2-sentence advisory for the HR reviewer.
           Be specific about any risk factors."
  Output example:
    "Candidate's college (Chennai, 380km) may pose commute challenges
     given the Bangalore in-person requirement. Confirm transportation
     arrangement before approval."

RISK SCORE COMPUTED:
  Base score: 0
  +10 per risk factor identified
  +15 if college location > 200km from office
  +20 if internship overlaps exam period (academic calendar check)
  +5  per unaccounted gap in education history

  0–20:  LOW RISK   (green badge)
  21–40: MED RISK   (amber badge)
  41+:   HIGH RISK  (red badge — HR must acknowledge before approving)

OUTPUT DISPLAYED IN HR REVIEW PANEL (S12):
  Risk score badge
  Risk factors list (bullet points)
  AI narrative paragraph
  Recommended questions for mentor
```

---

## F-08: Mentor Assignment Flow

```
TRIGGER: Referral status transitions to SUBMITTED

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. SYSTEM creates mentor_assignments record
       {
         referral_id:    <uuid>,
         mentor_id:      referral.mentor_id,
         attempt_number: 1,
         status:         PENDING,
         assigned_at:    NOW(),
         timeout_at:     NOW() + 3 days
       }

  2. SYSTEM generates two action tokens
       ACCEPT token: {action_type: MENTOR_RESPONSE, action: ACCEPT, expires: +3d}
       REJECT token: {action_type: MENTOR_RESPONSE, action: REJECT, expires: +3d}

  3. NOTIFICATION sends mentor assignment email
       Template: NOTIF_002_MENTOR_ASSIGNMENT
       Content (AI-drafted):
         - Candidate name + brief summary (from AI parse)
         - Project title + overview
         - Internship dates + location
         - Mentor's current mentee count (e.g., "You currently mentor 2 interns")
         - [✅ Accept Mentoring] button → ACCEPT token URL
         - [❌ Decline Mentoring] button → REJECT token URL
         - "These links expire in 3 days"

  4. APScheduler registers timeout job:
       run_at: assigned_at + 3 days
       job_id: mentor_timeout:{assignment_id}
       (idempotent — job deleted if mentor responds before timeout)

  5. Referral status: MENTOR_PENDING
     SLA clock starts (3 calendar days)
     SLA warning at T+2 days: reminder email to mentor
```

---

## F-09: Mentor Accept Flow

```
TRIGGER: Mentor clicks [Accept Mentoring] button in email

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Browser: GET /action/mentor?token=<raw_token>&action=ACCEPT

  2. BACKEND validates token:
       hash = SHA-256(raw_token)
       lookup action_tokens WHERE token_hash = hash
       ├─ Not found          → 401 MAGIC_LINK_INVALID
       ├─ Expired            → 401 ACTION_TOKEN_EXPIRED
       │   └─ System auto-sends new token if timeout not yet reached
       └─ Used               → 401 ACTION_TOKEN_USED
           └─ Show: "You have already responded to this request."

  3. BACKEND processes acceptance:
       mentor_assignments.status → ACCEPTED
       mentor_assignments.responded_at → NOW()
       mentor.active_mentee_count += 1
       referral.status → MENTOR_ACCEPTED
       action_tokens.used → true (both ACCEPT and REJECT tokens invalidated)

  4. APScheduler cancels timeout job:
       delete job: mentor_timeout:{assignment_id}

  5. Events published:
       MentorAccepted { referral_id, mentor_id, candidate_name }
       ↓
       Notification handler reacts:
         Email → Referrer: "[Mentor Name] has accepted mentoring for [Candidate]!"
         (AI-drafted, warm tone)

  6. Workflow engine reacts to MentorAccepted:
       Next stage: HR_REVIEW
       AI-10: Auto-route HR review task to least-loaded HR member

  7. Browser shows mentor:
       ✅ "Thank you! You have accepted mentoring for [Candidate Name].
          You will receive their full dossier once onboarding is complete."
```

---

## F-10: Mentor Reject Flow

```
TRIGGER: Mentor clicks [Decline Mentoring] button in email

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Browser: GET /action/mentor?token=<raw_token>&action=REJECT

  2. Token validation (same as F-09 steps 1–2)

  3. Browser renders rejection reason form:
       ┌────────────────────────────────────────────────────────────┐
       │  Decline Mentoring Request                                │
       │                                                          │
       │  Candidate: Riya Sharma                                  │
       │  Project: ML Pipeline Optimization                       │
       │                                                          │
       │  Please provide a reason for declining: *               │
       │  ┌────────────────────────────────────────────────────┐ │
       │  │                                                    │ │
       │  └────────────────────────────────────────────────────┘ │
       │  (Required — minimum 10 characters)                     │
       │                                                          │
       │  [Submit Decline]                                        │
       └────────────────────────────────────────────────────────────┘

  4. Mentor submits:
       POST /action/mentor/confirm
         { token: <raw_token>, action: REJECT, reason: "Too busy this quarter..." }

  5. BACKEND validates:
       reason empty or < 10 chars → 400 MENTOR_REJECTION_REASON_MISSING

  6. BACKEND processes rejection:
       mentor_assignments.status → REJECTED
       mentor_assignments.rejection_reason → captured
       mentor_assignments.responded_at → NOW()
       referral.mentor_attempt_count += 1

  7. CHECK: mentor_attempt_count >= 3?
       YES → F-12: Candidate Rejection — Max Attempts
       NO  → continue:
               referral.status → MENTOR_PENDING
               AI-2: Mentor match engine runs (excludes rejected mentor)

  8. Events published:
       MentorRejected { referral_id, mentor_id, reason, attempt_count }
       ↓
       Notification handler:
         Email → Referrer (AI-drafted, empathetic):
           "Unfortunately [Mentor Name] declined the mentoring request.
            Reason: [reason]
            Please log in to select a new mentor. [AI has suggested alternatives]"

  9. Referrer logs in → S7: Mentor Re-selection Panel
       AI-2 suggestions refresh (excluding rejected mentor)
       New mentor selected → F-08 restarts

  10. Browser shows mentor:
        "Your response has been recorded. Thank you for letting us know."
```

---

## F-11: Mentor Timeout & Auto-Reassignment Flow

```
TRIGGER: APScheduler job fires when mentor has not responded in 3 calendar days

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. APScheduler: check_mentor_timeouts() runs every 1 hour

  2. QUERY:
       SELECT ma.* FROM mentor_assignments ma
       WHERE ma.status = 'PENDING'
       AND ma.timeout_at <= NOW()
       AND ma.attempt_number = referral.mentor_attempt_count

  3. For each timed-out assignment:

     a. Idempotency check:
          IF assignment already processed → skip (prevents double-timeout)

     b. Update records:
          mentor_assignments.status → TIMED_OUT
          referral.mentor_attempt_count += 1

     c. CHECK: mentor_attempt_count >= 3?
          YES → F-12: Candidate Rejection — Max Attempts
          NO  → continue:
                  referral.status → MENTOR_PENDING
                  AI-2: Mentor suggestions regenerated
                  Invalidate old action tokens

     d. Publish event:
          MentorTimedOut { referral_id, mentor_id, attempt_count }

     e. Notification:
          Email → Referrer (AI-drafted):
            "[Mentor Name] did not respond within 3 days.
             Your referral has been paused.
             Please log in to select a new mentor.
             [AI has prepared new suggestions for you]"

          Email → Timed-out Mentor (informational only):
            "The mentoring request for [Candidate Name] has been reassigned
             as no response was received within 3 days."

  4. Audit events logged:
       MENTOR_TIMED_OUT: {mentor_id, referral_id, attempt_count, timeout_at}

  5. Referrer logs in → S7: Mentor Re-selection Panel
       Updated AI suggestions shown (radar chart, excluding timed-out mentor)
       Fresh action tokens generated on new selection
```

---

## F-12: Candidate Rejection — Max Attempts Flow

```
TRIGGER: mentor_attempt_count reaches 3 (after 3rd rejection OR timeout)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. CHECK GUARD:
       IF referral.mentor_attempt_count >= 3
         AND (mentor_assignments.status = REJECTED OR TIMED_OUT)
       THEN: execute terminal rejection

  2. Update referral:
       referral.status → CANDIDATE_REJECTED
       referral.rejection_reason → MAX_MENTOR_ATTEMPTS_EXCEEDED
       referral.rejected_at → NOW()

  3. Mentor capacity cleanup:
       No mentor accepted → no mentee count to decrement

  4. Events published:
       CandidateRejectedMaxAttempts { referral_id, candidate_email,
                                       referrer_id, attempt_history[] }

  5. Notifications (AI-drafted, empathetic tone):

     Email → Referrer:
       "Unfortunately, we were unable to assign a mentor for [Candidate Name]
        after 3 attempts. The referral has been closed.
        You may submit a new referral for this candidate in the next cycle
        if a suitable mentor becomes available."

     Email → Candidate:
       "We regret that your internship application could not proceed at this time
        due to mentor unavailability. This is not a reflection of your profile.
        Please contact [Referrer Name] if you have questions."

  6. Audit log:
       CANDIDATE_REJECTED_MAX_ATTEMPTS:
         { referral_id, attempt_1: {mentor, reason/timeout},
           attempt_2: {mentor, reason/timeout},
           attempt_3: {mentor, reason/timeout} }

  7. Record archived (not deleted):
       Retained for 2 years (duplicate detection window)
       Status: CANDIDATE_REJECTED (TERMINAL STATE)
```

---

## F-13: HR Review & Approval Flow

```
TRIGGER: MentorAccepted event → HR task auto-created via AI-10

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. AI-10: Workflow Auto-Router selects least-loaded HR member
       Assigns review task → hr_member.id
       SLA: 2 business days
       Email notification → assigned HR member

  2. HR opens Referral Review Panel (S12):

     INFORMATION SHOWN:
     ┌──────────────────────────────────────────────────────────────────────┐
     │  Referral #2025-0187 — Riya Sharma                                 │
     │  ─────────────────────────────────────────────────────────────────  │
     │  📄 Original Resume        🤖 AI Analysis                          │
     │  [View PDF]                Readiness Score: 82/100                 │
     │                            Technical Depth: Intermediate           │
     │                            Red Flags: Gap Jun–Aug 2024             │
     │                                                                    │
     │  AI-Prefilled Data:        ⚠️ Risk Profile                        │
     │  Name:  Riya Sharma ✅     Risk Score: 28 (Medium)                │
     │  Email: riya@g... ✅       "College 180km from office.             │
     │  Year:  3rd Year ✅         Confirm commute plan."                 │
     │  College: VIT ✅                                                   │
     │                            Duplicate Check: ✅ No duplicate        │
     │                                                                    │
     │  Referrer: Arjun Mehta     Mentor: Priya Nair (2/4 slots)         │
     │  Project: ML Pipeline      Duration: 8 weeks                      │
     │  Start: Aug 1, 2025        Location: Bangalore                    │
     └──────────────────────────────────────────────────────────────────────┘

  3. HR decision:

     APPROVE:
       referral.status → APPROVED
       referral.approved_at → NOW()
       referral.approved_by → hr_user.id
       Event: ReferralApproved
       ↓
       Notification: congratulations email → Candidate (AI-drafted)
       Magic link generated → sent with congratulations email
       → F-14: Candidate Joining Form Flow begins

     REJECT:
       HR enters rejection reason (mandatory)
       referral.status → HR_REJECTED
       referral.rejection_reason → captured
       Event: ReferralRejected
       ↓
       Notification: rejection email → Referrer (AI-drafted, respectful)
       Candidate NOT notified at this stage (referral not yet disclosed to candidate)

     REQUEST CORRECTION:
       HR adds comment on specific fields
       Referral status → CORRECTION_NEEDED
       Notification → Referrer with specific items to fix
       Referrer updates and re-submits → HR reviews again

  4. All HR actions logged:
       REFERRAL_APPROVED / REFERRAL_REJECTED / CORRECTION_REQUESTED
       actor_user_id, timestamp, reason, payload
```

---

## F-14: Candidate Joining Form Flow

```
TRIGGER: Candidate receives congratulations email with magic link

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Candidate clicks magic link → F-03: Magic Link Access Flow
     Lands on S9: Joining Form

  2. FORM SECTIONS (wizard pattern, save-draft every 60 seconds):

     SECTION 1: Personal Details
       Full name (pre-filled from referral — read-only)
       Date of birth
       Gender
       Nationality
       Profile photo upload

     SECTION 2: Contact & Address
       Personal email (pre-filled — read-only)
       Alternate phone
       Current address (street, city, state, pincode)
       Permanent address (checkbox: same as current)
       Emergency contact (name, phone, relationship)

     SECTION 3: Education
       Degree, field, institution, year
       AI-6 assists: institution name → auto-fills state, board, code
       Upload: education certificate(s)

     SECTION 4: Government IDs
       ID type (Aadhaar / PAN / Passport)
       ID number (pattern validated per type)
       Upload: ID proof document
       AI-6: reads uploaded ID → extracts DOB, ID number
             cross-validates name vs referral form → flags mismatches

     SECTION 5: Employment History (optional)
       Previous internships / part-time work (if any)

     SECTION 6: Declaration & Signature
       ☐ I confirm all information is accurate
       ☐ I consent to background verification
       Digital signature capture (canvas pad or typed name)

  3. SAVE DRAFT:
       Auto-save every 60 seconds
       Manual save button on every section
       Candidate can return via magic link (same token, 72h validity)
       Draft status stored: joining_forms.status = DRAFT

  4. SUBMIT:
       All mandatory fields validated (Pydantic + frontend Zod)
       joining_forms.status → SUBMITTED
       joining_forms.submitted_at → NOW()
       Event: JoiningFormSubmitted
       ↓
       Notification: email → assigned HR member
       Show candidate: "Your joining form has been submitted. HR will review it shortly."

  ERROR PATHS:
    Network drops during save-draft → local state preserved in React state
                                      retry on reconnect (TanStack Query mutation)
    File upload fails (Azure Blob)  → retry 3x with backoff
                                      if all fail: "Upload failed. Please retry."
    Version conflict on submit      → optimistic lock conflict detected
                                      show: "Form was updated elsewhere. Please refresh."
    Session expires mid-form        → soft warning at T-30min: "Your session expires soon"
                                      form data auto-saved → new magic link requested
```

---

## F-15: Joining Form Lock & Non-Worker ID Flow

```
TRIGGER: Candidate submits joining form

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  PART A: FORM REVIEW & LOCK

  1. HR opens S13: Joining Form Review
     Sees submitted form data + uploaded documents

  2. HR verifies data (manual check):
       Name consistency across ID, resume, referral form
       Government ID validity
       Education certificates
       Emergency contact completeness

  3. HR clicks [Lock Form]:
       VALIDATION: joining_forms.status must be SUBMITTED
       GUARD: cannot lock if status = LOCKED (idempotent protection)
       ↓
       joining_forms.status → LOCKED
       joining_forms.locked_at → NOW()
       joining_forms.locked_by → hr_user.id
       joining_forms.version += 1
       ↓
       Candidate's edit access revoked (JWT scope update)
       SLA clock starts for Non-Worker ID: T+0 = locked_at
       Event: JoiningFormLocked
       ↓
       Task created: NON_WORKER_ID (assigned to HR via AI-10)
         sla_deadline = locked_at + 1 business day

  PART B: NON-WORKER ID CREATION

  4. HR opens S14: Non-Worker ID Management
     Sees: task card with SLA countdown

     SLA timeline:
       T+0:    Task created (locked_at)
       T+4h:   Warning email → assigned HR member
       T+8h:   Escalation → Program Owner
       T+1bd:  SLA breach logged + escalation
       (bd = business day, Mon–Fri)

  5. HR creates Non-Worker ID:
       Enters ID in NexHire system
       Links to intern record
       ↓
       interns.non_worker_id → assigned
       tasks[NON_WORKER_ID].status → COMPLETED
       tasks[NON_WORKER_ID].completed_at → NOW()
       Event: NonWorkerIdIssued
       ↓
       Workflow engine reacts:
         referral.status → ID_ISSUED
         Next task auto-created: NDA issuance

  ERROR PATHS:
    HR tries to lock already-locked form  → 422 JOINING_FORM_ALREADY_LOCKED
    Non-Worker ID already exists          → 422 NON_WORKER_ID_ALREADY_ISSUED
    SLA breach (T+8h no action)           → auto-escalation to Program Owner
```

---

## F-16: NDA Issuance & Signing Flow

```
TRIGGER: NonWorkerIdIssued event

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. SYSTEM fetches NDA template:
       Azure Blob Storage → approved NDA template PDF
       (Compliance-approved version, version-controlled)

  2. SYSTEM calls OpenSign API:
       POST https://opensign.internal/api/request-signature
       {
         document: <base64 NDA PDF>,
         signers: [{ name: candidate.name, email: candidate.email }],
         metadata: { referral_id, intern_id, template_version },
         webhook_url: "https://nexhire.internal/webhooks/opensign",
         expiry_days: 5
       }
       ↓
       OpenSign returns: { envelope_id: "env_abc123", signing_url: "..." }

  3. SYSTEM stores NDA record:
       nda_records.opensign_envelope_id → env_abc123
       nda_records.template_version → current version
       nda_records.status → SENT
       nda_records.issued_at → NOW()
       nda_records.sent_at → NOW()

  4. NOTIFICATION sends NDA email to candidate:
       (Sent by NexHire notification module, not OpenSign directly)
       Template: NOTIF_003_NDA_ISSUANCE
       Content (AI-drafted):
         Explains what the NDA is and why it's required
         Direct OpenSign signing URL embedded
         Deadline: NOW() + 5 days
         "Your internship cannot begin until this is signed."

  5. REMINDER SCHEDULE starts (APScheduler):
       Day 1 (T+24h): Reminder email → candidate
       Day 2 (T+48h): Urgent reminder → candidate
       Day 3 (T+72h): Final warning → candidate + HR notified
       Day 5 (T+120h): AUTO-REJECTION triggered → F-17

  6. CANDIDATE signs NDA:
       Candidate clicks OpenSign URL (from email or S10 in portal)
       OpenSign renders signing UI
       Candidate reviews and signs digitally
       OpenSign processes signature
       OpenSign sends webhook → F-24: OpenSign Webhook Flow

  AFTER SUCCESSFUL SIGNING:
       nda_records.status → SIGNED
       nda_records.signed_at → webhook timestamp
       Signed PDF downloaded from OpenSign → archived to Azure Blob
       Event: NdaSigned { intern_id }
       ↓
       Workflow engine: referral.status → NDA_SIGNED
       All NDA reminder jobs cancelled (APScheduler)
       Next: Offer letter generation + Access provisioning
```

---

## F-17: NDA Auto-Rejection Flow

```
TRIGGER: APScheduler job check_nda_timeouts() — runs every 6 hours
         Fires when nda_records.sent_at < NOW() - 5 days
         AND nda_records.status NOT IN (SIGNED, DECLINED)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. QUERY:
       SELECT nda.*, i.id as intern_id, r.id as referral_id
       FROM nda_records nda
       JOIN interns i ON nda.intern_id = i.id
       JOIN referrals r ON i.referral_id = r.id
       WHERE nda.status = 'SENT'
       AND nda.sent_at < NOW() - INTERVAL '5 days'

  2. For each expired NDA:

     a. IDEMPOTENCY CHECK:
          IF nda.status already = EXPIRED → skip (job already ran)

     b. UPDATE:
          nda_records.status → EXPIRED
          nda_records.expired_at → NOW()
          nda_records.auto_rejected_at → NOW()
          referral.status → NDA_TIMEOUT_REJECTED
          referral.rejected_at → NOW()
          referral.rejection_reason → NDA_AUTO_REJECTED

     c. Cancel OpenSign envelope (if still open):
          DELETE /api/envelopes/{envelope_id}

     d. Events published:
          NdaAutoRejected { intern_id, referral_id, reason: NDA_TIMEOUT }

     e. NOTIFICATIONS (AI-drafted):
          Email → Referrer:
            "[Candidate Name]'s referral has been automatically closed
             because the NDA was not signed within 5 days.
             If you believe this is an error, please contact HR."

          Email → Candidate:
            "Your internship application has been closed as the required
             NDA was not completed within the specified timeframe.
             If you wish to appeal, please contact [HR email] within 5 business days."

          Email → HR (informational):
            "NDA auto-rejection triggered for [Candidate Name]. Referral #XXXX closed."

     f. AUDIT LOG:
          NDA_AUTO_REJECTED: { intern_id, referral_id, sent_at, expired_at,
                                reminder_1_sent, reminder_2_sent, reminder_3_sent }

  3. TERMINAL STATE — record archived, not deleted
     Retained for 2 years (duplicate detection window)

  NDA DECLINE PATH (OpenSign webhook — immediate):
     If candidate explicitly clicks "Decline" in OpenSign UI:
       Webhook received → F-24
       nda_records.status → DECLINED
       nda_records.declined_at → NOW()
       referral.status → NDA_DECLINED_REJECTED
       No grace period — immediate terminal rejection
       Notifications: same as above but reason = "NDA declined"
```

---

## F-18: Access Provisioning Flow

```
TRIGGER: NdaSigned event + start_date approaching (T-2 business days)

TWO PARALLEL TRACKS (run concurrently):

TRACK A: BADGE / SITE ACCESS (Admin/Security)
  ─────────────────────────────────────────────────────────────────────────────

  1. Task created: BADGE_ACCESS
       assigned_to: AI-10 auto-routes to available Admin member
       sla_deadline: start_date - 2 business days

  2. Admin opens S22: Task Queue
       Sees: intern name, photo, start date, joining location
       SLA countdown visible

  3. Admin configures badge:
       Physical badge + site access system updated
       Badge reference number logged in task

  4. Admin marks task complete:
       tasks[BADGE_ACCESS].status → COMPLETED
       tasks[BADGE_ACCESS].completed_at → NOW()
       Event: BadgeAccessConfigured

TRACK B: AD ACCOUNT PROVISIONING (IT/AD)
  ─────────────────────────────────────────────────────────────────────────────

  1. Task created: AD_PROVISION
       assigned_to: AI-10 auto-routes to available IT member
       sla_deadline: start_date - 2 business days
       Triggered: NonWorkerIdIssued confirmed + start_date T-2 days

  2. IT opens S21: Task Queue
       Sees: intern name, Non-Worker ID, start date, project details

  3. IT provisions AD account via Microsoft Graph API:
       POST https://graph.microsoft.com/v1.0/users
       {
         displayName: intern.name,
         userPrincipalName: "intern.name@company.com",
         mailNickname: intern.non_worker_id,
         accountEnabled: false,    ← enabled on start date only
         passwordProfile: { forceChangePasswordNextSignIn: true }
       }

  4. Credentials delivered to candidate:
       OTP one-time magic link: /candidate/credentials?token=<UUID>
       Token: single-use, 48h expiry
       Candidate sees: AD username + temporary password (once, then link expires)
       Credentials NEVER stored in NexHire DB

  5. IT enables AD account (on start date):
       PATCH /v1.0/users/{id} { accountEnabled: true }
       ↓
       interns.ad_account_username → assigned
       interns.ad_account_status → ACTIVE
       tasks[AD_PROVISION].status → COMPLETED
       Event: AdAccountProvisioned

  6. Mentor receives intern dossier:
       Secure link (S19 Intern Dossier View)
       SAS token: 24h expiry
       Content: photo, name, skills, project, timeline, AD username
       Teams deep link for mutual connect

ERROR PATHS:
  Graph API unavailable     → task PENDING, IT alerted, retry every 30 min
  AD account creation fails → detailed error logged, IT task shows error
  Badge system offline      → Admin notified, manual backup process documented
  Both tracks complete → F-19: Pre-Start Compliance Check fires at T-48h
```

---

## F-19: Pre-Start Compliance Check Flow

```
TRIGGER: APScheduler run_compliance_checks() — every 6 hours
         Fires for interns WHERE start_date = TODAY + 2 days

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. QUERY:
       SELECT i.* FROM interns i
       WHERE i.actual_start_date = CURRENT_DATE + INTERVAL '2 days'
       AND i.status NOT IN ('ACTIVE', 'CLOSED', 'TERMINATED')

  2. For each intern — run compliance checklist:

     CHECK 1: NDA signed
       nda_records.status = SIGNED?

     CHECK 2: Non-Worker ID issued
       interns.non_worker_id IS NOT NULL?

     CHECK 3: AD account provisioned
       interns.ad_account_status = ACTIVE?

     CHECK 4: Badge configured
       tasks[BADGE_ACCESS].status = COMPLETED?

     CHECK 5: Offer letter sent
       documents[OFFER_LETTER].sent_at IS NOT NULL?

  3. RESULT CLASSIFICATION:
       All ✅ → READY — no action, log only
       Any ⚠️ → WARNING — escalate non-blocking items
       Any ❌ → NOT READY — immediate escalation

  4. AI-7 generates compliance report narrative:
       Input: checklist results + intern details + start date
       Output: professional 3-5 sentence report
       "Intern Riya Sharma is scheduled to start in 48 hours.
        AD account provisioning is pending — this will block system access
        on Day 1. Badge access is also unconfirmed. Immediate action required
        from IT (AD) and Admin/Security teams."

  5. AUTO-ESCALATION per blocking item:
       NDA not signed    → Email: Candidate (urgent reminder) + HR
       No ID issued      → Email: HR (SLA breach)
       No AD account     → Email: IT/AD + Program Owner
       No badge          → Email: Admin/Security + Program Owner
       No offer letter   → Email: HR

  6. Report sent to HR + Program Owner:
       Visual checklist (✅/⚠️/❌ per item)
       AI narrative
       Predicted resolution time per item
       Direct action links

  7. All escalations logged:
       COMPLIANCE_CHECK_FAILED: { intern_id, start_date,
                                   blocking_items[], report_sent_at }
```

---

## F-20: Internship Active & Execution Flow

```
TRIGGER: All compliance items ✅ + start_date = TODAY + Mentor confirms

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  DAY 1 — START CONFIRMATION

  1. Mentor logs into portal (S20: Lifecycle Actions)
     Sees: [Confirm Intern Has Started] button
     Mentor clicks confirm

  2. SYSTEM:
       interns.actual_start_date → TODAY
       interns.status → ACTIVE
       referral.status → ACTIVE
       Event: InternshipStarted { intern_id, start_date }
       ↓
       Notification: start confirmation email → Mentor + Candidate (AI-drafted)

  DURING INTERNSHIP — CONTINUOUS MONITORING

  3. AI-5: Bottleneck Predictor runs every 6 hours:
       Evaluates all ACTIVE interns
       Predicts SLA risks (extension deadlines, closure approach)
       High-risk interns surfaced on HR Dashboard (S11) and
         Program Owner Dashboard (S23) as "At Risk" cards

  4. Mid-point check-in (at 50% of duration):
       APScheduler: fires at start_date + (duration / 2)
       Email → Mentor: "Riya is halfway through her internship.
                        How is the project progressing?"
       Email → Program Owner: mid-point status summary (AI-generated)

  5. SLA breach checks (every hour):
       Evaluates all open tasks for active interns
       Any task past sla_deadline → F-26: SLA Breach & Escalation Flow

  APPROACH TO END DATE

  6. T-7 days: closure reminder → Mentor + HR (AI-drafted)
       "Riya's internship ends in 7 days. Confirm completion or request extension."

  7. T-1 day: final reminder → Mentor
       "Riya's internship ends tomorrow. Please confirm completion in the portal."

  8. DECISION POINT:
       Mentor requests extension  → F-21: Extension Flow
       Mentor confirms closure    → F-22: Closure & Certificate Flow
       No response (T+2 days)    → SLA breach → Program Owner escalation
```

---

## F-21: Internship Extension Flow

```
TRIGGER: Mentor requests extension before end_date

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Mentor opens S20: Lifecycle Actions
     Clicks [Request Extension]

  2. GUARD CHECK:
       IF TODAY > interns.actual_end_date → BLOCK
         Show: "Extensions must be requested before the internship end date."

  3. Mentor fills extension request:
       New end date (must be > current end_date)
       Reason for extension (mandatory)
       Updated project scope (optional)

  4. SYSTEM validates new end date:
       Must be in future
       Duration still within program limits

  5. HR receives extension approval task:
       AI-10: auto-routed to least-loaded HR member
       Email notification (AI-drafted)

  6. HR reviews and decides:

     APPROVE:
       interns.actual_end_date → new_end_date
       referral.status → EXTENDED
       mentor.active_mentee_count remains same (not incremented again)
       Event: InternshipExtended
       ↓
       Notifications: Mentor + Candidate (AI-drafted)
       New closure reminder scheduled

     REJECT:
       Extension rejected with reason
       Original end date stands
       Notification → Mentor with reason

  7. Audit log:
       EXTENSION_REQUESTED + EXTENSION_APPROVED/REJECTED
       Full history preserved
```

---

## F-22: Closure & Certificate Flow

```
TRIGGER: Mentor confirms internship completion (S20: Lifecycle Actions)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  PART A: CLOSURE

  1. Mentor confirms completion:
       Optional: closure feedback text (used by AI-8 for certificate)
       referral.status → CLOSURE_PENDING

  2. PARALLEL closure tasks auto-created (AI-10 routes all):

     TASK A: AD Account Deactivation (IT/AD)
       SLA: ≤ 24 hours from end_date
       IT: Microsoft Graph API PATCH { accountEnabled: false }
       Warn at T+12h, escalate at T+18h
       On complete:
         interns.ad_account_status → DISABLED
         Event: AdAccountDeactivated

     TASK B: Badge Deactivation (Admin/Security)
       SLA: ≤ 24 hours from end_date
       Admin: badge system update
       On complete: Event: BadgeDeactivated

  3. Notifications (AI-drafted):
       Email → Candidate: farewell + what to expect for certificate
       Email → Referrer: "Your referral [Name]'s internship has concluded."

  PART B: CERTIFICATE REQUEST

  4. Candidate receives certificate request link:
       Magic link → /candidate/certificate?token=<UUID>

  5. Candidate fills simple form:
       Preferred name for certificate (pre-filled, editable)
       Confirm internship period (read-only)
       Any additional notes for HR (optional)

  6. HR receives certificate generation task:
       Opens S16: Certificate Issuance

  PART C: AI CERTIFICATE GENERATION

  7. AI-8: Certificate Content Generator runs:
       Input: intern.name, duration, project_title,
              project_overview, skills, mentor.closure_feedback
       Azure OpenAI GPT-4o generates citation (3-4 sentences)
       HR sees draft certificate text + preview

  8. HR reviews + approves:
       Edit AI draft if needed (override tracked)
       Click [Generate Certificate]

  9. PDF generation:
       Letterhead template loaded from Azure Blob
       Certificate data merged into template
       PDF generated (reportlab/WeasyPrint)
       Digital signature / seal applied (if configured)

  10. Certificate archived + delivered:
        Stored: Azure Blob Storage (permanent archive)
        SAS link (7-day expiry) sent to candidate
        Email → Candidate: "Your internship certificate is ready!" (AI-drafted)
        Copy sent to Referrer

  11. FINAL STATUS UPDATE:
        referral.status → CLOSED
        interns.status → CLOSED
        interns.actual_end_date confirmed
        Event: InternshipClosed
        All open tasks verified closed
        Mentor.active_mentee_count -= 1

  AUDIT LOG:
    INTERNSHIP_CLOSED: { intern_id, start_date, end_date, duration_days,
                          certificate_document_id, closed_by, closed_at }
```

---

## F-23: Email Action Token Flow

```
COVERS: All tokenized-link interactions (Mentor Accept/Reject, Candidate access)

TOKEN LIFECYCLE:
  ─────────────────────────────────────────────────────────────────────────────

  GENERATION:
    raw_token  = secrets.token_urlsafe(32)   ← cryptographically random
    token_hash = sha256(raw_token.encode()).hexdigest()
    stored:    token_hash (NEVER raw_token in DB)
    embedded:  raw_token in email URL only
    expiry:    action-specific (3 days for mentor, 72h for candidate)

  VALIDATION (every token use):
    Step 1: hash incoming raw_token
    Step 2: lookup token_hash in action_tokens table
    Step 3: check: found? not expired? not used?
    Step 4: verify: actor_user_id matches current session (if applicable)
    Step 5: mark: used = true, used_at = NOW(), ip_address = request.ip
    Step 6: execute action

  SECURITY PROPERTIES:
    Single-use:        cannot be clicked twice (replay attack prevention)
    Hash-stored:       DB breach doesn't expose valid tokens
    Time-limited:      tokens auto-expire
    IP-logged:         all token uses record IP for audit
    Actor-scoped:      mentor tokens reject if wrong user attempts use

  CLEANUP JOB (daily):
    DELETE FROM action_tokens
    WHERE expires_at < NOW() - INTERVAL '30 days'
    (Expired tokens retained 30 days for audit, then purged)

  ERROR SCENARIOS:
    Email client pre-fetches URL (triggers token):
      Detection: if request has no user-agent or is a bot
      Handling: mark token as "pre-fetched", don't execute action,
                log event, allow manual confirmation page
    Mentor forwards email to wrong person:
      Detection: token used from unexpected IP/location
      Handling: action executes (token is valid) + audit log flags unusual IP
    Token expired before mentor responds:
      On use of expired token: 401 ACTION_TOKEN_EXPIRED
      System auto-generates new token and emails mentor
      (Only if mentor_attempt timeout hasn't been reached)
```

---

## F-24: OpenSign Webhook Flow

```
TRIGGER: OpenSign sends webhook to POST /webhooks/opensign

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. OpenSign sends webhook:
       Headers: X-OpenSign-Signature: HMAC-SHA256(shared_secret, payload)
       Body: { event, envelope_id, signer_email, timestamp, document_url }

  2. BACKEND receives webhook:
       Step 1: Verify HMAC signature
         IF invalid → 401 OPENSIGN_WEBHOOK_INVALID
                    → Log attempt + IP
                    → Do NOT process
       Step 2: Lookup nda_records by envelope_id
         IF not found → 404, log orphaned webhook
       Step 3: Idempotency check
         IF nda already in terminal state → 200 OK (already processed)

  3. ROUTE BY EVENT TYPE:

     "document_signed":
       ↓
       Download signed PDF: GET OpenSign /api/download/{envelope_id}
       Upload to Azure Blob: container=signed-ndas, key=UUID
       Update:
         nda_records.status → SIGNED
         nda_records.signed_at → webhook.timestamp
         nda_records.signed_document_id → blob_document_id
       Cancel all NDA reminder jobs (APScheduler)
       Publish: NdaSigned { intern_id }
       Return: 200 OK to OpenSign

     "document_declined":
       ↓
       Update:
         nda_records.status → DECLINED
         nda_records.declined_at → NOW()
         referral.status → NDA_DECLINED_REJECTED
       Publish: NdaDeclined { intern_id }
       Notifications: referrer + HR (immediate)
       Return: 200 OK

     "envelope_expired":
       ↓
       (Usually system auto-rejects at Day 5 before this fires)
       IF not already expired:
         Same flow as F-17 NDA auto-rejection
       Return: 200 OK

  4. ALL webhook receipts logged:
       OPENSIGN_WEBHOOK_RECEIVED: { event, envelope_id, received_at,
                                     signature_valid, processed }

  FALLBACK — If webhook not received:
    OpenSign polling job (every 15 min):
      GET /api/envelopes/{envelope_id}/status
      If status changed → process same as webhook
      (Ensures no signing event is ever missed)
```

---

## F-25: AI Mentor Match Engine Flow

```
TRIGGER: (1) Referral form Step 3 (initial mentor selection)
         (2) MentorRejected event
         (3) MentorTimedOut event

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. CHECK CACHE:
       Redis key: mentor_suggestions:{referral_id}:{attempt_count}
       TTL: 1 hour
       HIT → return cached suggestions (fast path)
       MISS → continue to scoring

  2. LOAD ELIGIBLE MENTORS:
       SELECT u.id, u.full_name, u.skills,
              COUNT(a.id) FILTER (WHERE a.status = 'ACTIVE') as active_mentees,
              AVG(completion.rate) as historical_completion_rate,
              AVG(response.hours) as avg_response_hours
       FROM users u
       LEFT JOIN interns a ON a.mentor_id = u.id AND a.status = 'ACTIVE'
       LEFT JOIN mentor_stats ms ON ms.user_id = u.id
       WHERE u.role IN ('MENTOR', 'REFERRER')
       AND u.is_active = true
       AND u.id NOT IN (:excluded_mentor_ids)   ← already rejected/timed out
       AND COUNT(active_mentees) < 4             ← capacity filter
       GROUP BY u.id

  3. SCORE EACH MENTOR (0–100 points, 5 dimensions × 20 points each):

     Skill Alignment (0–20):
       Compare candidate.skills[] vs mentor.skills[]
       Jaccard similarity × 20
       e.g., 60% overlap → 12 points

     Availability (0–20):
       (4 - active_mentee_count) × 5
       0 mentees = 20pts, 1 = 15pts, 2 = 10pts, 3 = 5pts

     Reputation / Success Rate (0–20):
       historical_completion_rate × 20
       100% completion = 20pts, 80% = 16pts

     College Familiarity (0–20):
       Has mentored intern from same college → 20pts
       Same state/region college → 10pts
       No match → 5pts

     Response Speed (0–20):
       avg_response_hours:
         < 2h  → 20pts
         2–6h  → 15pts
         6–12h → 10pts
         12–24h → 5pts
         > 24h → 0pts

  4. SORT by total score DESC → take top 3

  5. GPT-4o generates recommendation reason per mentor (1 sentence each):
       "Best skill match for ML work with 1 open slot and 100% completion rate."

  6. BUILD OUTPUT:
       [
         {
           mentor_id, full_name, match_score: 94,
           slots_available: 2, slots_total: 4,
           radar: { skill: 18, availability: 10, reputation: 20,
                    familiarity: 20, responsiveness: 16 },
           reason: "Best skill match for ML work with 1 open slot..."
         },
         ...
       ]

  7. CACHE in Redis (1h TTL)
     RETURN to frontend → renders mentor picker with radar charts

  FALLBACK (if Azure OpenAI unavailable):
    Return rule-based scores only (no reason text)
    Frontend shows: "Based on availability and skills" (no AI explanation)
    Core functionality unaffected
```

---

## F-26: SLA Breach & Escalation Flow

```
TRIGGER: APScheduler check_sla_breaches() — runs every 1 hour

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. QUERY overdue tasks:
       SELECT t.*, i.*, r.*
       FROM tasks t
       JOIN interns i ON t.intern_id = i.id
       JOIN referrals r ON i.referral_id = r.id
       WHERE t.status NOT IN ('COMPLETED', 'CANCELLED')
       AND t.sla_deadline <= NOW()

  2. FOR EACH OVERDUE TASK:

     DETERMINE ESCALATION LEVEL:
       hours_overdue = (NOW() - sla_deadline).hours
       
       NON_WORKER_ID:
         T+4h overdue  → WARNING → email assigned HR
         T+8h overdue  → ESCALATION → email Program Owner
         T+24h overdue → CRITICAL → email Program Owner + HR Manager
       
       AD_PROVISION / BADGE_ACCESS:
         T+4h overdue  → WARNING → email assigned IT/Admin
         T+8h overdue  → ESCALATION → email IT Manager / Admin Manager
       
       AD_DEACTIVATION:
         T+12h overdue → WARNING → email assigned IT
         T+18h overdue → ESCALATION → email Program Owner (security risk)
         T+24h overdue → CRITICAL → security incident logged
       
       CERTIFICATE_ISSUANCE:
         T+3d overdue  → WARNING → email assigned HR
         T+5d overdue  → ESCALATION → HR Manager

  3. SEND ESCALATION EMAIL (AI-drafted):
       Context-aware content based on task type and overdue duration
       Include: intern name, task type, hours overdue, action required
       Include: direct link to relevant screen in NexHire

  4. UPDATE TASK RECORD:
       tasks.warned_at → NOW() (if first warning)
       tasks.escalated_at → NOW() (if escalation)

  5. AUDIT EVENT:
       SLA_BREACH: { task_id, task_type, sla_deadline,
                      hours_overdue, escalation_level, escalated_to }

  6. DASHBOARD UPDATE:
       SLA breach counters updated on S11 (HR Dashboard) and S23 (Exec Dashboard)
       At-risk cards shown with red urgency indicator
```

---

## F-27: AI Bottleneck Prediction Flow

```
TRIGGER: APScheduler — runs every 6 hours on all ACTIVE + PENDING referrals

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. QUERY all non-terminal referrals:
       SELECT r.*, i.*, current stage, stage_entered_at
       FROM referrals r
       LEFT JOIN interns i ON i.referral_id = r.id
       WHERE r.status NOT IN (terminal statuses)

  2. FOR EACH REFERRAL — compute breach risk:

     FEATURES:
       days_in_current_stage      = (NOW() - stage_entered_at).days
       historical_avg_stage_days  = lookup from stage_duration_stats table
       stage_ratio                = days_in_current_stage / historical_avg_stage_days
       assigned_user_workload     = COUNT(open tasks for assigned user)
       is_friday                  = NOW().weekday() == 4   (weekend delay risk)
       upcoming_holiday           = check holiday calendar next 3 days

     RISK SCORE (0–1.0):
       risk = (stage_ratio × 0.5)
             + (min(workload/10, 1.0) × 0.3)
             + (0.15 if is_friday else 0)
             + (0.10 if upcoming_holiday else 0)
       risk = min(risk, 1.0)

     CLASSIFICATION:
       risk < 0.4  → ON_TRACK   (no alert)
       risk 0.4–0.7 → AT_RISK   (amber card on dashboard)
       risk > 0.7  → HIGH_RISK  (red card + email escalation)

  3. AI-GENERATED RECOMMENDATION:
       For AT_RISK and HIGH_RISK referrals:
       GPT-4o prompt: "Given stage={stage}, days_overdue={d},
                        assigned_user_workload={w}, generate a
                        1-sentence action recommendation."
       Output: "Escalate Non-Worker ID creation — HR has 7 open tasks
                and this referral has been in ID_PENDING for 6 days."

  4. UPDATE DASHBOARD:
       AI bottleneck predictions stored in:
         ai_parse_results (touchpoint=BOTTLENECK_PREDICTION)
       HR Dashboard (S11): shows "3 referrals at risk" summary
       Exec Dashboard (S23): risk distribution chart updated
       High-risk referrals: email sent to HR + Program Owner

  5. HISTORICAL LEARNING:
       After referral closes: actual stage durations logged
       stage_duration_stats table updated (rolling average)
       Prediction model improves with each cycle
```

---

## F-28: Program Intelligence Chatbot Flow

```
TRIGGER: Program Owner or HR types query in S17 or S23 chatbot interface

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. User types natural language question:
       "Which mentors have the highest rejection rates this quarter?"
       "Are we on track to close all internships this month?"
       "What is our average cycle time from referral to start?"

  2. FRONTEND sends to backend:
       POST /ai/chatbot
       { question: "...", context: { user_role, filters: {} } }

  3. BACKEND routes to AI-9: Program Intelligence Chatbot

  4. GPT-4o receives question + available function definitions:

     AVAILABLE FUNCTIONS (GPT-4o can call any):
       get_mentor_stats(period, metric)
       get_college_performance(college_name)
       get_sla_breach_summary(stage, date_range)
       get_at_risk_referrals(threshold)
       get_cycle_time_stats(start_date, end_date)
       get_intern_completion_rates(filters)
       get_referral_pipeline_counts(status_breakdown)
       get_ai_performance_metrics()

  5. GPT-4o decides which function(s) to call:
       Calls: get_mentor_stats(period="Q1-2025", metric="rejection_rate")
       NexHire executes DB query → returns structured data
       GPT-4o synthesizes natural language answer from data

  6. RESPONSE returned to frontend:
       {
         answer: "Arjun Mehta has the highest rejection rate at 60%
                  (3 rejections out of 5 assignments) in Q1 2025.
                  He currently has 4/4 mentees. Consider having HR
                  speak with him about capacity.",
         data_source: "mentor_assignments table, Q1 2025",
         confidence: "HIGH",
         suggested_followups: [
           "Show me all of Arjun's rejections with reasons",
           "Which mentors have available slots right now?",
           "What is the average mentor rejection rate this quarter?"
         ]
       }

  7. SAFETY GUARDRAILS:
       Chatbot CANNOT: update any data, trigger actions, access PII beyond
                        what user's role permits (HR vs Program Owner scopes enforced)
       All chatbot queries logged to audit trail
       If question is ambiguous → chatbot asks for clarification
       If no data available → "I don't have enough data to answer this yet.
                               Minimum 3 months of data needed for this metric."
```

---

## F-29: Workflow Auto-Router Flow

```
TRIGGER: Any task creation event (Non-Worker ID, badge, AD provision, etc.)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Task creation request received:
       task_type = NON_WORKER_ID
       role_group = HR

  2. QUERY eligible team members:
       SELECT u.id, u.full_name,
              COUNT(t.id) FILTER (WHERE t.status NOT IN ('COMPLETED','CANCELLED'))
                as open_task_count,
              AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))/3600)
                as avg_response_hours,
              CASE WHEN u.out_of_office_until > NOW() THEN false ELSE true END
                as is_available
       FROM users u
       LEFT JOIN tasks t ON t.assigned_to = u.id
       WHERE u.role = :role_group
       AND u.is_active = true
       GROUP BY u.id
       HAVING is_available = true
       ORDER BY open_task_count ASC, avg_response_hours ASC

  3. SELECT top candidate (lowest workload + fastest historical response)

  4. IF no available members (all OOO or all overloaded):
       Fallback: assign to role group lead (configured in admin settings)
       Alert: Program Owner notified of resource constraint

  5. TASK RECORD CREATED:
       tasks.assigned_to → selected_user.id
       tasks.assigned_by_ai → true
       tasks.ai_routing_reason → "Lowest workload (2 tasks), fastest response (1.8h avg)"
       tasks.sla_deadline → computed per task type

  6. ROUTING DECISION LOGGED:
       AI_TASK_ROUTED: { task_type, assigned_to, workload_at_assignment,
                          routing_reason, alternative_candidates[] }

  7. NOTIFICATION:
       Email → assigned user (AI-drafted, task-specific content)
       In-app notification on their task queue screen
```

---

## F-30: Error Handling Flows

### F-30a: Validation Error Flow
```
User submits form with invalid data
  ↓
Frontend (Zod schema) catches error → inline field error shown
  ↓ (if frontend missed it)
Backend (Pydantic model) catches error
  ↓
HTTP 400 returned:
  { error: { code: "INVALID_YEAR_OF_STUDY", message: "...", category: "VALIDATION_ERROR" } }
  ↓
Axios interceptor: shows toast notification
Field highlighted in red with specific message
User corrects input → resubmits
```

### F-30b: Business Rule Violation Flow
```
User submits valid data that breaks a business rule
(e.g., COLLEGE_CAP_EXCEEDED)
  ↓
Backend service layer raises BusinessRuleError
  ↓
HTTP 422 returned:
  { error: { code: "COLLEGE_CAP_EXCEEDED", message: "...", details: { college, count } } }
  ↓
Every business rule violation → ALSO logged to audit_events table
  ↓
Axios interceptor: shows modal (not just toast — needs acknowledgment)
Modal shows: clear reason + what user can do instead
```

### F-30c: AI Degradation Flow
```
Azure OpenAI times out or returns error
  ↓
AiService catches exception → returns ParseResult(success=False)
  ↓
Backend response still HTTP 200 (workflow not blocked):
  { ai_available: false, prefill: {}, degradation_reason: "AI_TIMEOUT",
    user_message: "Auto-fill unavailable. Please fill manually." }
  ↓
Frontend: shows info banner "AI assist temporarily unavailable"
Form fields empty but editable — user proceeds normally
  ↓
AI failure logged → ai_parse_results (success=false, latency_ms)
Azure Monitor: ai_timeout counter incremented
If rate > threshold → ops alerted
```

### F-30d: Integration Failure Flow
```
OpenSign / Gmail / Graph API returns error
  ↓
Integration client raises IntegrationError
  ↓
Error handler: HTTP 502 returned
  { error: { code: "OPENSIGN_UNAVAILABLE",
             message: "Document signing temporarily unavailable.
                       It will be sent automatically when restored." } }
  ↓
Action queued in notifications / tasks table for retry
APScheduler retry job picks up within 15 min (OpenSign) / 15 min (Gmail)
  ↓
Azure Monitor: integration_error counter incremented
If count > 10 in 5 min → ops team alerted
```

### F-30e: Critical System Error Flow
```
Unexpected exception in backend
  ↓
Global exception handler catches it
Full stack trace → Azure Application Insights (NEVER sent to client)
  ↓
HTTP 500 returned:
  { error: { code: "UNEXPECTED_ERROR",
             message: "Something went wrong. Our team has been notified.",
             request_id: "req_7f3a91bc" } }
  ↓
Azure Monitor: system_error counter incremented
Alert fires if error_rate > 1% of requests
Ops team receives alert with Application Insights trace link
  ↓
User sees: generic error + request_id they can share with IT support
```

### F-30f: Audit Log Failure Flow
```
Audit event cannot be written to DB
  ↓
AuditPublisher raises SystemError
  ↓
CRITICAL: the entire operation is ABORTED (not just the audit)
  ↓
HTTP 500 with code: AUDIT_LOG_FAILURE
  { error: { message: "A critical system error occurred.
                        Please contact the system administrator immediately." } }
  ↓
Azure Monitor: P0 alert fires IMMEDIATELY
On-call engineer paged
DB connection + audit table health checked
  ↓
Reason: audit integrity is a legal compliance requirement.
        An unaudited operation is worse than a failed operation.
```

---

## F-31: Master State Machine

```
All valid referral status transitions:

DRAFT
  └─[submit]──────────────────────────────────────────────► SUBMITTED

SUBMITTED
  └─[mentor_assigned]─────────────────────────────────────► MENTOR_PENDING

MENTOR_PENDING
  ├─[mentor_accepts]──────────────────────────────────────► MENTOR_ACCEPTED
  ├─[mentor_rejects, attempt < 3]────► MENTOR_REJECTED ──► MENTOR_PENDING (loop)
  ├─[mentor_times_out, attempt < 3]──► MENTOR_TIMED_OUT ─► MENTOR_PENDING (loop)
  └─[any failure, attempt = 3]────────────────────────────► CANDIDATE_REJECTED ❌

MENTOR_ACCEPTED
  └─[hr_receives_task]────────────────────────────────────► HR_REVIEW

HR_REVIEW
  ├─[hr_approves]─────────────────────────────────────────► APPROVED
  ├─[hr_rejects]──────────────────────────────────────────► HR_REJECTED ❌
  └─[hr_requests_correction]──────────────────────────────► CORRECTION_NEEDED
       └─[referrer_resubmits]────────────────────────────► HR_REVIEW

APPROVED
  └─[candidate_receives_link]─────────────────────────────► JOINING_FORM_PENDING

JOINING_FORM_PENDING
  └─[candidate_submits]───────────────────────────────────► JOINING_FORM_SUBMITTED

JOINING_FORM_SUBMITTED
  └─[hr_locks]────────────────────────────────────────────► JOINING_FORM_LOCKED

JOINING_FORM_LOCKED
  └─[hr_issues_id]────────────────────────────────────────► ID_ISSUED

ID_ISSUED
  └─[nda_sent]────────────────────────────────────────────► NDA_PENDING

NDA_PENDING
  ├─[candidate_signs]─────────────────────────────────────► NDA_SIGNED
  ├─[day_5_no_sign]───────────────────────────────────────► NDA_TIMEOUT_REJECTED ❌
  └─[candidate_declines]──────────────────────────────────► NDA_DECLINED_REJECTED ❌

NDA_SIGNED
  └─[all_access_provisioned]──────────────────────────────► ACCESS_PENDING

ACCESS_PENDING
  └─[mentor_confirms_start]───────────────────────────────► ACTIVE

ACTIVE
  ├─[mentor_requests_extension, before_end_date]──────────► EXTENDED
  │    └─[hr_approves]──────────────────────────────────► ACTIVE (new end_date)
  └─[mentor_confirms_completion]──────────────────────────► CLOSURE_PENDING

EXTENDED
  └─[mentor_confirms_completion]──────────────────────────► CLOSURE_PENDING

CLOSURE_PENDING
  ├─[all_tasks_complete + cert_issued]────────────────────► CLOSED ✅
  └─[early_exit_with_reason]──────────────────────────────► TERMINATED ❌ (not CLOSED)

TERMINAL STATES (no further transitions):
  CLOSED                 ✅ Successfully completed
  CANDIDATE_REJECTED     ❌ Max mentor attempts exceeded
  HR_REJECTED            ❌ HR rejected the referral
  NDA_TIMEOUT_REJECTED   ❌ NDA not signed by Day 5
  NDA_DECLINED_REJECTED  ❌ Candidate explicitly declined NDA
  TERMINATED             ❌ Early exit during active internship

STATE MACHINE GUARDS (transitions blocked if not met):
  JOINING_FORM_LOCKED → ID_ISSUED:
    ✅ joining_form.status = LOCKED

  NDA_SIGNED → ACCESS_PENDING:
    ✅ interns.non_worker_id IS NOT NULL
    ✅ nda_records.status = SIGNED

  ACCESS_PENDING → ACTIVE:
    ✅ nda_records.status = SIGNED              ← HARD BLOCK (BRD requirement)
    ✅ interns.non_worker_id IS NOT NULL
    ✅ interns.ad_account_status = ACTIVE
    ✅ tasks[BADGE_ACCESS].status = COMPLETED
    ✅ date = internship.start_date

  ACTIVE → EXTENDED:
    ✅ TODAY < interns.actual_end_date          ← cannot extend after end
```

---

## F-32: Audit Trail Flow

```
TRIGGER: Every state-changing operation in the system

EVERY AUDIT EVENT CONTAINS:
  ─────────────────────────────────────────────────────────────────────────────
  id              BIGSERIAL (append-only, monotonic)
  event_type      e.g., REFERRAL_APPROVED, MENTOR_REJECTED, NDA_SIGNED
  entity_type     e.g., REFERRAL, INTERN, TASK
  entity_id       UUID of the affected record
  actor_user_id   Who performed the action (NULL for system actions)
  actor_role      Their role at time of action
  ip_address      Request origin IP (for human actions)
  event_timestamp Immutable, server-side
  payload         Full context as JSONB (what changed, from/to values)
  prev_checksum   SHA-256 of previous event's checksum
  checksum        SHA-256(prev_checksum + payload::text) ← tamper-evident chain

CHECKSUM CHAIN:
  Event 1: checksum = SHA-256("GENESIS" + payload_1)
  Event 2: checksum = SHA-256(event_1.checksum + payload_2)
  Event 3: checksum = SHA-256(event_2.checksum + payload_3)
  ...
  Any tampering with a historical event breaks the entire chain forward
  Chain validation runs nightly as a health check

COMPLETE AUDIT EVENT CATALOG:
  Authentication:   LOGIN, LOGOUT, TOKEN_REFRESH, MAGIC_LINK_USED
  Referral:         REFERRAL_SUBMITTED, REFERRAL_APPROVED, REFERRAL_REJECTED,
                    CORRECTION_REQUESTED, DUPLICATE_WARNING_OVERRIDDEN
  AI:               AI_PARSE_COMPLETED, AI_FIELD_OVERRIDDEN, AI_MENTOR_SUGGESTED,
                    AI_BOTTLENECK_PREDICTED, AI_DEGRADED_GRACEFULLY
  Mentor:           MENTOR_ASSIGNED, MENTOR_ACCEPTED, MENTOR_REJECTED,
                    MENTOR_TIMED_OUT, CANDIDATE_REJECTED_MAX_ATTEMPTS
  Onboarding:       JOINING_FORM_SUBMITTED, JOINING_FORM_LOCKED,
                    NON_WORKER_ID_ISSUED
  NDA:              NDA_ISSUED, NDA_SIGNED, NDA_DECLINED, NDA_AUTO_REJECTED,
                    OPENSIGN_WEBHOOK_RECEIVED
  Access:           AD_ACCOUNT_CREATED, AD_ACCOUNT_ACTIVATED, BADGE_CONFIGURED,
                    CREDENTIALS_DELIVERED, AD_ACCOUNT_DEACTIVATED, BADGE_DEACTIVATED
  Lifecycle:        INTERNSHIP_STARTED, INTERNSHIP_EXTENDED, INTERNSHIP_CLOSED,
                    INTERNSHIP_TERMINATED
  Certification:    CERTIFICATE_REQUESTED, CERTIFICATE_GENERATED,
                    CERTIFICATE_APPROVED, CERTIFICATE_DELIVERED
  SLA:              SLA_WARNING_SENT, SLA_BREACH_ESCALATED, SLA_BREACH_LOGGED
  Errors:           BUSINESS_RULE_VIOLATED, STATE_MACHINE_GUARD_FAILED,
                    AUDIT_LOG_FAILURE, SCHEDULER_JOB_DEAD_LETTERED

IMMUTABILITY ENFORCEMENT:
  DB permission: REVOKE UPDATE, DELETE ON audit_events FROM nexhire_app;
  Only INSERT granted to application DB role
  Separate read-only role for audit queries (Program Owner / HR)
  Nightly chain integrity check: validates checksum chain end-to-end
  Alert fires if chain broken → immediate P0 incident

QUERYING THE AUDIT TRAIL (S24):
  Program Owner can filter by:
    entity_type + entity_id   → full history of one referral
    actor_user_id             → everything a specific HR person did
    event_type                → all NDA_AUTO_REJECTED events
    date_range                → weekly/monthly compliance report
  Export: CSV or PDF report (with chain integrity status noted)
```

---

## Flow Summary Reference

| Flow | Trigger | Terminal Outcomes | AI Involved |
|---|---|---|---|
| F-02 Auth | SSO login | JWT issued / error | No |
| F-03 Magic Link | Email click | Candidate portal access | No |
| F-04 Referral Submit | Employee fills form | SUBMITTED / BLOCKED | AI-1, 2, 3, 4 |
| F-05 Resume Analysis | File upload | Prefill + risk data | AI-1 |
| F-06 Duplicate Check | Form review | PASS / WARN / BLOCK | AI-4 |
| F-07 Eligibility Check | Form fill | PASS / WARN / BLOCK | AI-3 |
| F-08 Mentor Assignment | Referral submitted | MENTOR_PENDING | AI-2, 10 |
| F-09 Mentor Accept | Email button click | MENTOR_ACCEPTED | No |
| F-10 Mentor Reject | Email button click | MENTOR_PENDING (retry) | AI-2 |
| F-11 Mentor Timeout | 3-day scheduler | MENTOR_PENDING (retry) | AI-2 |
| F-12 Max Attempts | 3rd failure | CANDIDATE_REJECTED ❌ | No |
| F-13 HR Review | Mentor accepted | APPROVED / HR_REJECTED | AI-10 |
| F-14 Joining Form | Magic link access | JOINING_FORM_SUBMITTED | AI-6 |
| F-15 Form Lock + ID | HR action | ID_ISSUED | AI-10 |
| F-16 NDA Flow | ID issued | NDA_SIGNED / expired | No |
| F-17 NDA Auto-Reject | Day 5 scheduler | NDA_TIMEOUT_REJECTED ❌ | No |
| F-18 Access Provision | NDA signed | ACCESS_PENDING | AI-10 |
| F-19 Compliance Check | T-48h scheduler | READY / escalations | AI-7 |
| F-20 Active Execution | Mentor confirms start | ACTIVE | AI-5 |
| F-21 Extension | Mentor requests | EXTENDED / rejected | No |
| F-22 Closure + Cert | Mentor confirms end | CLOSED ✅ | AI-8 |
| F-23 Action Tokens | Email button clicks | Action processed | No |
| F-24 OpenSign Webhook | OpenSign callback | NDA status updated | No |
| F-25 Mentor Match | Form / rejection | Top 3 suggestions | AI-2 |
| F-26 SLA Breach | Hourly scheduler | Escalations fired | No |
| F-27 Bottleneck Pred | 6-hour scheduler | At-risk dashboard cards | AI-5 |
| F-28 Chatbot | Owner/HR query | Natural language answer | AI-9 |
| F-29 Auto-Router | Task creation | Task assigned | AI-10 |
| F-30 Error Handling | Various failures | Graceful degradation | — |
| F-31 State Machine | Every transition | Valid state change | — |
| F-32 Audit Trail | Every operation | Immutable log entry | — |

---

*NexHire System Flow Document v2.1*
*32 flows · 7 lifecycle phases · 10 AI touchpoints · All error paths documented*
*Companion: NexHire System Blueprint v2.1*

---

## F-33: PAN Card Duplicate Detection Flow

```
TRIGGER: PAN number entered in Referral Form Step 1 (real-time, on valid format)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. EMPLOYEE types PAN number in referral form field
     Real-time format validation fires on each keystroke:
       Regex: [A-Z]{5}[0-9]{4}[A-Z]{1}
       Invalid → red border + "Invalid PAN format (e.g. ABCDE1234F)"
       Valid   → green tick → API call fires immediately

  2. BACKEND: POST /ai/check-pan-duplicate
       Input: { pan_number: "ABCDE1234F" }
       Encrypt PAN → query referrals table

  3. QUERY:
       SELECT id, candidate_name, status, submitted_at
       FROM referrals
       WHERE candidate_pan = encrypt(:pan)
       AND status NOT IN (terminal statuses)

  4. RESULT ROUTING:

     PAN MATCH FOUND (certain duplicate):
       ┌──────────────────────────────────────────────────────────────┐
       │  ⛔ HARD BLOCK — Duplicate PAN Detected                     │
       │  PAN ABCDE1234F is already linked to:                       │
       │  Riya Sharma — Referral #2025-0142 (Status: ACTIVE)        │
       │  This is a government-verified unique identifier.           │
       │  Override is not permitted.                                  │
       │  [View Existing Referral]  [Cancel Submission]              │
       └──────────────────────────────────────────────────────────────┘
       Form submission BLOCKED — no further steps possible

     NO PAN MATCH:
       Green tick shown: "PAN verified — no existing referral found"
       Fuzzy duplicate check (F-06) still runs at form review step
       Form continues normally

  5. PAN stored encrypted (AES-256) in referrals.candidate_pan
     Displayed masked: "ABCDE****F" after save
     Raw PAN never logged — only masked version in audit events

  AUDIT EVENT:
    PAN_DUPLICATE_CHECK: { masked_pan, result: CLEAR/MATCH,
                            match_referral_id (if match), checked_at }
```

---

## F-34: Non-Worker ID Auto-Generation Flow

```
TRIGGER: JoiningFormLocked event (previously triggered HR manual task)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. JoiningFormLocked event published
     WorkflowEngine event handler receives it
     BEFORE: Created task → HR creates ID manually (SLA: 1 business day)
     NOW:    AI generates ID immediately (< 1 second)

  2. SYSTEM retrieves PAN from referral:
       pan_encrypted = referral.candidate_pan
       pan_decrypted = decrypt(pan_encrypted)  ← in-memory only, not logged

  3. NonWorkerIdGenerator.generate():
       Format: NW-{PAN}-{JOINING_YEAR}
       Example: NW-ABCDE1234F-2025

       Uniqueness check:
         EXISTS? → append sequence: NW-ABCDE1234F-2025-2
         Not exists? → use as-is

  4. STORE:
       interns.non_worker_id → "NW-ABCDE1234F-2025"

  5. NOTIFICATIONS:
       Email → HR (FYI, not action required):
         "Non-Worker ID auto-generated for Riya Sharma: NW-ABCDE1234F-2025"
       Email → Candidate:
         "Your Non-Worker ID has been assigned: NW-ABCDE1234F-2025
          Please use this ID for all official correspondence."

  6. AUDIT EVENT:
       NON_WORKER_ID_AUTO_GENERATED:
         { intern_id, non_worker_id, generated_from: "PAN_NUMBER",
           pan_masked: "ABCDE****F", joining_year: 2025,
           generated_at, latency_ms }

  7. EVENT PUBLISHED: NonWorkerIdAutoGenerated
     WorkflowEngine transitions: ID_ISSUED
     Next: NDA issuance triggers automatically

  TIMELINE COMPARISON:
    BEFORE: JoiningFormLocked → HR task created → HR acts (0–24h) → ID issued
    AFTER:  JoiningFormLocked → AI generates → ID issued (< 1 second)
    Improvement: Up to 24 business hours saved per intern
```

---

## F-35: AI Auto-Approval Flow (Referral Review)

```
TRIGGER: MentorAccepted event → replaces HR review task creation

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. MentorAccepted event received
     ReferralAutoApprovalEngine.evaluate(referral_id) runs

  2. ENGINE checks 6 conditions:

     CHECK 1: PAN duplicate
       referral.ai_parse.duplicate_check.match_type ≠ "PAN_EXACT"
       FAIL → HARD_BLOCK → route to HR (recommendation: REJECT)

     CHECK 2: Fuzzy duplicate score
       dup_check.similarity_score < 0.6
       FAIL → flag added ("Possible duplicate {score}%")

     CHECK 3: Risk score
       risk.risk_score ≤ 25
       FAIL → flag added ("Risk score {n} exceeds threshold")

     CHECK 4: AI parse confidence
       ALL field confidence scores ≥ 0.82
       FAIL → flag added ("Low confidence: {fields}")

     CHECK 5: Field completeness
       No mandatory fields missing
       FAIL → flag added ("Missing: {fields}")

     CHECK 6: Resume red flags
       ai_parse.red_flags is empty
       FAIL → flag added per red flag

  3. DECISION:

     ZERO FLAGS → AUTO-APPROVE:
       referral.status → APPROVED
       referral.approved_by → "AI_AUTO_APPROVAL"
       referral.approved_at → NOW()
       ai_auto_actions record created (decision: EXECUTED)
       ↓
       Magic link generated → sent to candidate (congratulations email)
       HR notified: FYI email (not action required)
         "Referral #2025-0187 auto-approved. 2-hour recall available."
         [Recall This Approval] button in email (2h window)

     ANY FLAG → ROUTE TO HR:
       Task created for HR review (AI-10 auto-routed)
       HR sees: flag summary + AI recommendation
         LIKELY_APPROVE  → "AI suggests approval — 1 minor flag"
         LIKELY_REJECT   → "AI suggests rejection — possible duplicate"
         REQUIRES_REVIEW → "Please review carefully — multiple flags"
       HR makes final decision

  4. AUTO-APPROVE AUDIT:
       REFERRAL_AUTO_APPROVED:
         { referral_id, conditions_met[], approved_by: "AI",
           approved_at, recall_window_until }

  STATISTICS TARGET:
    ~80% of referrals → AUTO-APPROVED (clean cases)
    ~20% of referrals → HR review (flagged cases)
    HR workload reduction: ~80%
```

---

## F-36: AI Auto-Lock Flow (Joining Form)

```
TRIGGER: JoiningFormSubmitted event

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. JoiningFormSubmitted event received
     JoiningFormAutoLockEngine.evaluate(intern_id) runs (async)

  2. ENGINE reads all uploaded documents:
       ID proof → Azure Document Intelligence extracts:
         name, DOB, ID number, PAN number
       Education certificate → extracts:
         institution name, degree, year
       Photo → validates: is a face photo (basic check)

  3. CROSS-VALIDATION CHECKS:

     CHECK 1: Name consistency (HIGH severity if fail)
       Compare: referral_name vs form_name vs id_name
       Jaro-Winkler similarity < 0.85 on any pair → HIGH FLAG

     CHECK 2: PAN consistency (HIGH severity if fail)
       referral.candidate_pan vs form.govt_ids.pan_number
       vs pan_extracted_from_id_doc
       Any mismatch → HIGH FLAG

     CHECK 3: DOB consistency (HIGH severity if fail)
       form.personal_details.dob vs dob_from_id_doc
       Mismatch → HIGH FLAG

     CHECK 4: Field completeness (HIGH severity if fail)
       All mandatory sections filled
       Missing any → HIGH FLAG

     CHECK 5: Education institution (LOW severity if fail)
       form_institution vs cert_institution
       Similarity < 0.75 → LOW FLAG (minor inconsistency)

     CHECK 6: Emergency contact (LOW severity if fail)
       Name + phone + relationship all present
       Missing → LOW FLAG

  4. DECISION:

     NO HIGH FLAGS:
       AUTO-LOCK:
         joining_forms.status → LOCKED
         joining_forms.locked_at → NOW()
         joining_forms.locked_by → "AI_AUTO_LOCK"
         joining_forms.version += 1
         ai_auto_actions record created
         ↓
         SLA clock starts for Non-Worker ID
         (Which is now also auto-generated — F-34)
         ↓
         HR notified: FYI + recall option (1 hour)

     ANY HIGH FLAG:
       ROUTE TO HR:
         Specific flags shown on S13 (Joining Form Review)
         HR sees: which fields failed + extracted values
         e.g., "Name on Aadhaar: 'Riya S Sharma' differs from
                form entry: 'Riya Sharma' (87% similar)"
         HR verifies and locks manually

  5. AUDIT EVENT:
       JOINING_FORM_AUTO_LOCKED:
         { intern_id, checks_run[], flags[], decision,
           locked_by: "AI_AUTO_LOCK", locked_at }

  STATISTICS TARGET:
    ~75% of forms → AUTO-LOCKED (clean cases)
    ~25% of forms → HR review (flagged)
```

---

## F-37: Offer Letter Auto-Send Flow

```
TRIGGER: NonWorkerIdAutoGenerated event (or NonWorkerIdIssued if manual)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. OfferLetterAutoSendEngine.evaluate_and_send(intern_id)

  2. AI-8 (adapted): Letter content generated:
       Uses approved letterhead template
       Merge fields: candidate_name, non_worker_id, mentor_name,
                     project_title, start_date, end_date, location
       All fields validated present

  3. IS_STANDARD CHECK:
       ✅ Generated from approved template (no custom edits)
       ✅ All merge fields populated
       ✅ Start date is future date
       ✅ Mentor confirmed (MENTOR_ACCEPTED status)

  4. IF STANDARD → AUTO-SEND:
       PDF generated → stored in Azure Blob
       Gmail API: email to candidate with PDF attachment
       HR FYI notification:
         "Offer letter auto-sent to Riya Sharma at 10:23 AM.
          Recall available until 10:53 AM (30 minutes).
          [Recall Offer Letter]"
       Audit event: OFFER_LETTER_AUTO_SENT

  5. IF NON-STANDARD → ROUTE TO HR:
       (e.g., custom project terms, special clauses)
       HR reviews on S15 (NDA & Letters Management)

  RECALL FLOW (if HR clicks recall within 30 min):
    System sends follow-up email to candidate:
      "Please disregard the previous email. An updated version will be sent shortly."
    Original letter marked: RECALLED
    HR reviews and re-sends correct version
    Audit event: OFFER_LETTER_RECALLED
```

---

## F-38: Certificate Auto-Generate & Send Flow

```
TRIGGER: InternshipClosed event (after mentor confirms completion)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Candidate receives certificate request magic link
     Fills simple form (name confirmation, notes)
     Submits → CertificateAutoSendEngine.evaluate_and_send(intern_id)

  2. IS_CLEAN_CLOSURE CHECK:
       ✅ intern.status = CLOSURE_PENDING
       ✅ referral.status ≠ TERMINATED
       ✅ mentor_confirmed_completion = true
       ✅ AD account deactivated
       ✅ Badge deactivated

  3. AI-8: Certificate content generation:
       Input: name, duration, project, skills, mentor_feedback
       GPT-4o generates 3-4 sentence citation
       Confidence score computed

  4. IF confidence ≥ 0.85 AND clean closure:
       PDF generated on letterhead (reportlab)
       Digital seal applied (if configured)
       Stored in Azure Blob (permanent archive)
       Gmail API: delivery email to candidate
       Copy sent to referrer (FYI)
       HR FYI notification:
         "Certificate auto-sent to Riya Sharma.
          48-hour recall window active until [datetime].
          [View Certificate] [Recall Certificate]"
       Audit event: CERTIFICATE_AUTO_SENT

  5. IF confidence < 0.85 OR terminated:
       HR review required (S16: Certificate Issuance)
       AI draft shown but HR must approve before send

  RECALL FLOW (48h window):
    HR clicks [Recall Certificate] in FYI email or S16
    System sends candidate:
      "Your certificate is being reviewed and will be reissued shortly."
    Certificate marked: RECALLED (not deleted — archived)
    New certificate issued after HR review
    Audit event: CERTIFICATE_RECALLED, CERTIFICATE_REISSUED
```

---

## Updated Flow Summary — AI Automation Added

| Flow | What Changed | AI Level |
|---|---|---|
| F-04 Referral Submit | PAN field added, real-time PAN duplicate check | AI-4 (upgraded) |
| F-13 HR Review | 80% auto-approved, 20% routed to HR | AI (new engine) |
| F-15 Form Lock + ID | 75% auto-locked, ID auto-generated from PAN | AI (new engines) |
| F-16 NDA Flow | Unchanged — NDA still requires human signing | — |
| F-22 Closure + Cert | Certificate auto-generated and auto-sent | AI-8 (upgraded) |
| F-33 PAN Duplicate | NEW — real-time PAN check, hard block | AI-4 (new) |
| F-34 NW ID Auto-Gen | NEW — PAN → NW-PAN-YEAR in < 1 second | AI (new) |
| F-35 Auto-Approval | NEW — 6-condition engine, recall window | AI (new) |
| F-36 Auto-Lock | NEW — doc cross-validation, recall window | AI (new) |
| F-37 Offer Auto-Send | NEW — standard template auto-sent, 30min recall | AI (new) |
| F-38 Cert Auto-Send | NEW — clean closure auto-cert, 48h recall | AI-8 (new) |

---

## Revised Human vs AI Work Distribution

```
PROCESS               BEFORE          AFTER
─────────────────────────────────────────────────────────
Referral Review       100% HR         ~20% HR (flagged only)
Duplicate Check       AI fuzzy only   AI: PAN (certain) + fuzzy
Form Lock             100% HR         ~25% HR (flagged only)
Non-Worker ID         100% HR (1 day) 0% HR (AI, <1 second)
Offer Letter Send     100% HR         ~10% HR (non-standard only)
Certificate Send      100% HR         ~15% HR (terminated/disputed)

OVERALL:
  Before: 25% AI · 75% HR
  After:  85% AI · 15% HR
```

---

*NexHire System Flow Document v2.2*
*38 flows · 7 lifecycle phases · 10+ AI touchpoints · PAN-based deduplication*
*AI Coverage: 85% | HR Work: 15% | Non-Worker ID: Auto-generated in <1 second*
*Companion: NexHire System Blueprint v2.2*

---

## F-39: Cooling Period Application Flow

```
TRIGGER: Any referral reaches a terminal state

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. WorkflowEngine detects terminal state transition
     Calls: CoolingPeriodService.apply_cooling_period(referral_id, terminal_state)

  2. SERVICE looks up duration from cooling_period_config table:

     terminal_state              duration_months
     ─────────────────────────────────────────────
     NDA_DECLINED_REJECTED   →  6 months
     TERMINATED              →  6 months
     NDA_TIMEOUT_REJECTED    →  3 months
     HR_REJECTED             →  3 months
     CANDIDATE_REJECTED      →  0 months  (no cooling)
     CLOSED                  →  3 months

  3. IF duration_months = 0 (CANDIDATE_REJECTED):
       Record for history only (cooling_period_months = 0)
       No block applied
       Notify referrer:
         "Referral closed due to mentor unavailability.
          No cooling period applies — you may re-refer immediately."
       → DONE

  4. IF duration_months > 0:
       cooling_period_start_at = NOW()
       cooling_period_end_at   = NOW() + N months
       cooling_triggered_by    = terminal_state
       ↓
       Audit event: COOLING_PERIOD_APPLIED
       ↓
       Notify referrer (NOTIF_014):
         "[Candidate] cooling period: [N] months
          Starts: [today] · Ends: [end_date]"
         [Set Reminder] button

  5. APScheduler registers two future jobs:
       Job 1: T-7 days before end → NOTIF_015 (ending soon reminder)
       Job 2: On end_date         → NOTIF_016 (cooling expired, can re-refer)
```

---

## F-40: PAN Check — Full Decision Tree Flow

```
TRIGGER: Employee enters PAN number in referral form Step 1
         Fires in real-time on valid PAN format (debounced 500ms)

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  Employee types PAN → frontend validates format
    Invalid format → red border: "Invalid format. Expected: ABCDE1234F"
    Valid format   → API call fires: POST /ai/check-pan

  BACKEND DECISION TREE:
  ─────────────────────────────────────────────────────────────────────────────

  STEP 1: ACTIVE DUPLICATE CHECK
    Is there an active (non-terminal) referral with this PAN?
    ├─ YES → HARD BLOCK (no override)
    │         Show: "Active referral exists for this candidate.
    │                Status: [status]. Referral: #XXXX"
    │         [View Existing Referral] button
    │         STOP — cannot proceed
    └─ NO  → continue to Step 2

  STEP 2: COOLING PERIOD CHECK
    Is there a terminal referral with active cooling period?
    ├─ YES (duration > 0, today < cooling_end_at, no override):
    │
    │   ROUTE BY TERMINAL STATE:
    │
    │   NDA_DECLINED_REJECTED (6 months):
    │     "Candidate explicitly declined the NDA.
    │      6-month cooling period active.
    │      Ends: [date] · [N] days remaining."
    │     [🔔 Set Reminder]  [Request Override — Program Owner only]
    │
    │   TERMINATED (6 months):
    │     "Candidate left mid-internship.
    │      6-month cooling period active.
    │      Ends: [date] · [N] days remaining."
    │     [🔔 Set Reminder]  [Request Override — Program Owner only]
    │
    │   NDA_TIMEOUT_REJECTED (3 months):
    │     "Candidate did not sign NDA within the deadline.
    │      3-month cooling period active.
    │      Ends: [date] · [N] days remaining."
    │     [🔔 Set Reminder]  [Request Override — Program Owner only]
    │
    │   HR_REJECTED (3 months):
    │     "Candidate was found unfit during HR review.
    │      3-month cooling period active.
    │      Ends: [date] · [N] days remaining."
    │     [🔔 Set Reminder]  [Request Override — Program Owner only]
    │
    │   CLOSED (3 months):
    │     "Candidate completed a previous internship.
    │      3-month re-join spacing period active.
    │      Ends: [date] · [N] days remaining."
    │     [🔔 Set Reminder]
    │     (No override option for CLOSED — policy spacing)
    │
    │   STOP — cannot proceed until cooling ends or override applied
    │
    ├─ YES (duration = 0 — CANDIDATE_REJECTED, no cooling):
    │     Green tick: "Previous referral closed due to mentor unavailability.
    │                  No cooling period applies.
    │                  You may submit a new referral immediately."
    │     → continue to Step 3
    │
    ├─ YES (override applied by Program Owner):
    │     Green tick: "Cooling period waived by Program Owner.
    │                  You may proceed with this referral."
    │     → continue to Step 3
    │
    └─ NO (cooling naturally elapsed):
          Green tick: "Previous referral closed. Cooling period complete."
          → continue to Step 3

  STEP 3: FUZZY DUPLICATE CHECK
    Does name/email/phone fuzzy match any existing candidate?
    ├─ score ≥ 0.90 → SOFT BLOCK (warn, HR confirms)
    │                  "Possible duplicate detected (90% match).
    │                   HR will verify during review."
    │                  [Proceed with Warning]
    ├─ score 0.6–0.89 → ADVISORY WARNING
    │                    "Possible match found. HR will verify."
    │                    Form continues, HR sees flag
    └─ score < 0.6   → CLEAR

  STEP 4: ALL CLEAR
    Green tick: "PAN verified — eligible for referral."
    Form continues normally
```

---

## F-41: Cooling Period Override Flow (Program Owner)

```
TRIGGER: Program Owner initiates override for a specific candidate

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  1. Program Owner accesses override via:
     Option A: Referral form → employee sees COOLING_BLOCK →
               [Request Override] → Program Owner receives request notification
     Option B: S23 Executive Dashboard → Cooling Period Analytics panel →
               finds candidate → clicks [Override Cooling Period]
     Option C: S24 Audit & SLA Report → cooling period table → [Override]

  2. Program Owner sees override confirmation modal:
       Candidate PAN (masked)
       Terminal state + reason for cooling
       Original cooling end date
       Days remaining
       ⚠️ Warning: "This action is irreversible and permanently logged"

  3. Program Owner enters justification:
       Minimum 50 characters (DB constraint)
       Free text — must be specific and meaningful
       e.g., "Candidate had a verified medical emergency during NDA signing
               period. Hospital documentation provided to HR on 15 Mar 2025.
               Approved by Department Head Rajesh Kumar."

  4. IF reason < 50 chars:
       BLOCK: "Override reason must be at least 50 characters.
                Please provide a detailed justification."

  5. IF reason ≥ 50 chars → confirm:
       cooling_period_end_at   → NOW()       (ends immediately)
       cooling_override_at     → NOW()
       cooling_override_by     → program_owner.id
       cooling_override_reason → reason text
       ↓
       cooling_period_overrides record inserted
       ↓
       Audit event: COOLING_PERIOD_OVERRIDDEN (immutable, permanent)
         { pan_masked, terminal_state, original_cooling_end,
           days_waived, overridden_by, override_reason, overridden_at }
       ↓
       HR notified: NOTIF_013
         "[Program Owner] waived cooling period for [PAN masked].
          Reason: [reason]. A new referral may now be submitted."
       ↓
       Original referrer notified (if applicable):
         "The cooling period for your candidate has been waived.
          You may now submit a new referral."

  6. New referral can be submitted immediately
     PAN check now returns: CLEAR (override applied)
     Override flag visible in all PAN check responses for audit purposes

  WHAT PROGRAM OWNER CANNOT DO:
    ✗ Override an ACTIVE DUPLICATE block (different rule — not cooling)
    ✗ Override cooling for CLOSED candidates (policy spacing, not overridable)
    ✗ Retroactively change cooling period duration in UI
      (requires DB migration → code review → deliberate change)
```

---

## F-42: Cooling Period Notification Scheduler Flow

```
TRIGGER: APScheduler — runs daily at 08:00 AM

SEQUENCE:
  ─────────────────────────────────────────────────────────────────────────────

  JOB: check_cooling_period_notifications()

  1. QUERY — cooling periods ending in exactly 7 days:
       SELECT r.*, u.email as referrer_email, u.full_name as referrer_name
       FROM referrals r
       JOIN users u ON u.id = r.referrer_id
       WHERE r.cooling_period_end_at::date = CURRENT_DATE + INTERVAL '7 days'
       AND r.cooling_period_months > 0
       AND r.cooling_override_at IS NULL
       AND r.reminder_7d_sent_at IS NULL    ← idempotency

     FOR EACH:
       Send NOTIF_015 → referrer
       Mark: r.reminder_7d_sent_at = NOW()

  2. QUERY — cooling periods expiring today:
       WHERE r.cooling_period_end_at::date = CURRENT_DATE
       AND r.cooling_period_months > 0
       AND r.cooling_override_at IS NULL
       AND r.reminder_expiry_sent_at IS NULL

     FOR EACH:
       Send NOTIF_016 → referrer
         "Cooling period for [Candidate] has ended.
          You can now submit a new referral."
       Mark: r.reminder_expiry_sent_at = NOW()
       Audit event: COOLING_PERIOD_NATURALLY_EXPIRED

  3. IDEMPOTENCY PROTECTION:
       All reminder jobs use sent_at columns to prevent duplicate sends
       Daily job runs are safe to re-run after crash/restart
```

---

## Updated Flow Summary — Cooling Period Flows Added

| Flow | Description |
|---|---|
| F-39 | Cooling period applied on terminal state — variable duration by state |
| F-40 | Full PAN check decision tree — active dup → cooling → fuzzy → clear |
| F-41 | Program Owner override — 50-char reason, immutable audit, HR notified |
| F-42 | Daily scheduler — 7-day reminder + expiry notification to referrer |

## Cooling Period Quick Reference

```
TERMINAL STATE          COOLING    CANDIDATE FAULT?   OVERRIDABLE?
──────────────────────────────────────────────────────────────────────
NDA_DECLINED_REJECTED   6 months   Yes (explicit)      Yes (PO only)
TERMINATED              6 months   Yes (commitment)    Yes (PO only)
NDA_TIMEOUT_REJECTED    3 months   Yes (unresponsive)  Yes (PO only)
HR_REJECTED             3 months   Shared              Yes (PO only)
CANDIDATE_REJECTED      0 months   No (mentor issue)   N/A
CLOSED (re-join)        3 months   N/A (completed)     No (policy)
──────────────────────────────────────────────────────────────────────
Override: Program Owner only · Mandatory 50-char reason · Audit logged
Config:   DB-seeded · Hardcoded · Requires migration to change
```

---

*NexHire System Flow Document v2.3*
*42 flows · Variable cooling period system · 6 rules · Program Owner override*
*Companion: NexHire System Blueprint v2.3*
