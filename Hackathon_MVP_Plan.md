# NexHire — AI-Powered Intern Referral Management Platform
## System Blueprint v2.0 — Final Specification

> **Based on BRD:** Intern Flow — Internship Program Automation (Unpaid Internships)
> **Architecture:** Single Frontend (React + TypeScript) · Modular Monolith (Python FastAPI)
> **Document Status:** Final — All specs confirmed
> **Last Updated:** V2.0

---

## Confirmed Technology Stack

| Layer | Technology | Justification |
|---|---|---|
| Frontend | React 18 + TypeScript + TanStack Query | Type-safe, industry standard, excellent async state |
| UI Library | shadcn/ui + Tailwind CSS | Accessible by default, composable, WCAG 2.1 AA ready |
| Backend | Python 3.12 + FastAPI | Async-native, fast, AI/ML ecosystem fit, team scale appropriate |
| Database | Azure Database for PostgreSQL (Flexible Server) | Managed, ACID, JSONB support, row-level security |
| ORM | SQLAlchemy 2.0 + Alembic | Async ORM, typed models, migration management |
| AI/LLM | Azure OpenAI Service (GPT-4o) | Data stays within Azure boundary, unified billing, enterprise SLA |
| SSO & Identity | Microsoft Azure AD (OIDC) + MSAL | Native SSO for employees, Graph API for AD provisioning |
| Email | Google Workspace (Gmail API via OAuth2) | Organizational email, deliverability, threading support |
| E-sign | OpenSign (self-hosted Docker) | Open-source, REST API, webhook support, zero licensing cost |
| File Storage | Azure Blob Storage | Managed, SAS token access, lifecycle policies, CDN-ready |
| Deployment | Azure App Service (Linux) + Azure Container Registry | PaaS, auto-scaling, integrated with Azure AD |
| Background Jobs | APScheduler (FastAPI-native) + Azure Service Bus (dead-letter) | Lightweight scheduler; Service Bus for reliable job queuing |
| Caching | Azure Cache for Redis | Session store, AI result caching, rate limiting |
| Monitoring | Azure Monitor + Application Insights | Full observability, alert rules, query analytics |
| E-sign Infra | OpenSign on Azure Container Instance | Isolated, same Azure network, REST API accessible internally |

---

## Table of Contents

1. [Problem Framing](#1-problem-framing)
2. [Role Modeling](#2-role-modeling)
3. [Business Rules — Complete Specification](#3-business-rules--complete-specification)
4. [Workflow Reasoning](#4-workflow-reasoning)
5. [Auto-Rejection State Machines](#5-auto-rejection-state-machines)
6. [UI/UX Thinking](#6-uiux-thinking)
7. [AI System Design — 10 Touchpoints](#7-ai-system-design--10-touchpoints)
8. [System Architecture — Modular Monolith](#8-system-architecture--modular-monolith)
9. [Data Modeling](#9-data-modeling)
10. [Failure Scenarios](#10-failure-scenarios)
11. [Metrics & Feedback Loops](#11-metrics--feedback-loops)
12. [Security & Ethics](#12-security--ethics)
13. [Future Evolution](#13-future-evolution)
14. [Project Folder Structure](#14-project-folder-structure)
15. [Assumptions & Open Questions](#15-assumptions--open-questions)

---

## 1. Problem Framing

### 1.1 Core Problem

IT organizations running unpaid internship programs face a fundamental contradiction: interns are temporary and low-overhead, but their onboarding touches at least 6 departments and requires legal, identity, and physical access coordination — all currently done via email and chat.

**The result:**

| Pain Point | Business Impact |
|---|---|
| No centralized referral intake | Duplicates, lost referrals, no audit trail |
| Manual mentor assignment | Bottlenecks, no SLA, no fallback when mentor ignores |
| NDA managed via email | Compliance risk; impossible to prove pre-start signing |
| AD provisioning ad-hoc | Interns arrive on Day 1 with no system access |
| Zero visibility for leadership | Cannot track cycle time, SLA health, or program quality |

### 1.2 Why Modular Monolith (Python FastAPI)

**FastAPI chosen because:**
- Async-native (handles 500 concurrent users with minimal resources)
- First-class Azure OpenAI SDK support
- Python's NLP/ML ecosystem is best-in-class
- 3-person team can own a single codebase efficiently
- No network overhead between internal modules
- Shared PostgreSQL transaction boundaries — ACID guarantees across the entire workflow

**Monolith over microservices because:**
- Distributed transactions (NDA + ID + AD must all succeed or roll back) are trivially solved in a monolith
- 3-person team cannot operate 8+ independently deployed services
- Internal tool with 500 concurrent users does not need horizontal service scaling at launch
- Transactional Outbox pattern is pre-designed for future extraction if needed

---

## 2. Role Modeling

### 2.1 Actor Taxonomy

```
NexHire Actors
├── Internal (Azure AD SSO)
│   ├── Referrer (Employee)     → Submits referrals, selects mentor, tracks status
│   ├── Mentor (Employee)       → Accepts/rejects mentoring, guides intern lifecycle
│   └── Program Owner           → Governance, SLA oversight, configuration, reporting
│
├── External (Magic Link)
│   └── Candidate (Intern)      → Completes joining form, signs NDA
│
├── Operational (Azure AD SSO)
│   ├── HR                      → Reviews referrals, issues Non-Worker ID, manages NDA, letters, closure
│   ├── Admin / Security        → Badge and site access coordination
│   └── IT / AD Team            → AD account provisioning and deactivation via Microsoft Graph
│
└── System Actors (Automated)
    ├── AI Engine               → All 10 AI touchpoints (Azure OpenAI)
    ├── Scheduler               → APScheduler jobs for SLA clocks, reminders, auto-rejections
    ├── Notification Service    → Gmail API-based email delivery
    └── OpenSign Webhook        → NDA signing events (signed / declined / expired)
```

### 2.2 RBAC Permission Matrix

| Action | Referrer | Mentor | Candidate | HR | IT/AD | Admin | Program Owner |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Submit referral | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Select / change mentor | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Accept / reject mentoring | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View own referrals only | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| View all referrals | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Complete joining form | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Lock joining form | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Issue Non-Worker ID | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Provision AD account | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Manage badge / site access | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Approve / reject referral | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Override AI decision | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Generate certificate | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| View SLA dashboard | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| View audit trail | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| System configuration | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Query AI chatbot | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |

### 2.3 Authentication Strategy

**Employees (Referrer, Mentor, HR, IT, Admin, Program Owner):**
- Azure AD OIDC SSO via MSAL
- JWT issued by NexHire on successful SSO token exchange (RS256, 8h expiry)
- Role claims stored in NexHire DB (not in Azure AD groups) — decoupled
- Refresh token rotation: 24h, stored encrypted in Redis

**Candidates (External):**
- No password account — magic link via Gmail API to referral-submitted email
- Magic link: single-use, 72h expiry, bcrypt-hashed in DB
- Candidate JWT scoped strictly to their own intern record
- Account archived post-closure (not deleted — retention policy)

---

## 3. Business Rules — Complete Specification

### 3.1 Eligibility Rules (Hard Blocks — System Enforced)

```
RULE-E1: Year of Study Restriction
  ALLOWED:   2nd year, 3rd year, 4th year students ONLY
  BLOCKED:   1st year students
  BLOCKED:   Graduated students (graduation_year ≤ current_year)
  ENFORCEMENT: Referral form validator (backend) + UI field validation
  ERROR MSG: "Only students currently in their 2nd, 3rd, or 4th year are eligible."

RULE-E2: College Cap per Referrer
  LIMIT: Max 2 active referrals per referrer from the same college
  SCOPE: Active = any status except REJECTED, CLOSED, TERMINATED
  ENFORCEMENT: Backend pre-submission check against referral_college_count view
  ERROR MSG: "You have already referred 2 students from [College Name].
              This limit has been reached for this cycle."
  AI ASSIST: Warning shown during form fill before submission attempt

RULE-E3: Referrer ≠ Mentor
  BLOCKED: Same employee cannot be both referrer and mentor for the same intern
  ENFORCEMENT: Referral form validator (server-side hard block)

RULE-E4: Unpaid Consent Required
  BLOCKED: Submission if candidate has not confirmed unpaid internship consent
  ENFORCEMENT: Boolean field; backend blocks if false

RULE-E5: In-Person Readiness Required
  BLOCKED: Submission if candidate has not confirmed in-person availability
  ENFORCEMENT: Boolean field; backend blocks if false

RULE-E6: Mentor Capacity
  BLOCKED: Mentor selection if mentor.active_mentee_count >= 4
  ENFORCEMENT: Real-time check during mentor selection in referral form
  UI: Mentor picker shows capacity badge (e.g., "2/4 slots used", "FULL")
  AI ASSIST: Full mentors excluded from AI mentor recommendations automatically
```

### 3.2 Mentor Assignment Rules

```
RULE-M1: Mentor Must Explicitly Accept
  After referral submission → mentor receives assignment request email
  Mentor must click Accept or Reject within 3 business days
  Status held at: MENTOR_PENDING until response received

RULE-M2: Mentor No-Response Auto-Rejection (3-day rule)
  Trigger: mentor has not responded in 3 calendar days
  Action:
    1. Mentor assignment status → MENTOR_TIMED_OUT
    2. Referral status → MENTOR_PENDING (awaiting new selection)
    3. Notify referrer: "[Mentor Name] did not respond. Please select a new mentor."
    4. AI Mentor Suggestion engine runs immediately with updated recommendations
    5. Attempt counter incremented: mentor_attempt_count += 1

RULE-M3: Maximum Mentor Re-selection Attempts
  LIMIT: 3 total mentor attempts per referral
  After 3rd failure (rejection OR timeout):
    1. Referral status → CANDIDATE_REJECTED
    2. Rejection reason logged: "MAX_MENTOR_ATTEMPTS_EXCEEDED"
    3. Notify referrer: "Unable to assign a mentor after 3 attempts. Referral closed."
    4. Notify candidate: "Unfortunately, your referral could not proceed at this time."
    5. Record archived with full audit trail

RULE-M4: Mentor Rejection Handling
  Mentor rejection requires mandatory rejection_reason field
  On rejection:
    1. Referral status → MENTOR_REJECTED → MENTOR_PENDING
    2. Rejection captured: {reason, timestamp, mentor_id}
    3. Notify referrer immediately with rejection reason
    4. AI Mentor Suggestions regenerated excluding rejected mentor
    5. Attempt counter incremented

STATE MACHINE:
  MENTOR_PENDING
    → [Accept]       → MENTOR_ACCEPTED → (continue workflow)
    → [Reject]       → MENTOR_REJECTED → MENTOR_PENDING (if attempts < 3)
    → [Timeout 3d]   → MENTOR_TIMED_OUT → MENTOR_PENDING (if attempts < 3)
    → [3rd failure]  → CANDIDATE_REJECTED (terminal)
```

### 3.3 NDA Signing Rules

```
RULE-N1: NDA Must Be Signed Before Start Date (Hard Block)
  Internship ACTIVE transition blocked if nda.status ≠ SIGNED
  No exceptions; no manual override (by design)

RULE-N2: NDA Reminder Schedule
  Day 1 (T+24h): Reminder email — "Please sign your NDA to proceed"
  Day 2 (T+48h): Urgent reminder — "Action required: NDA signing deadline approaching"
  Day 3 (T+72h): Final warning — "You have 48 hours remaining. After Day 5, your referral will be closed."
  Day 5 (T+120h): AUTO-REJECT triggered

RULE-N3: NDA Auto-Rejection (Day 5)
  Trigger: nda.status ≠ SIGNED AND nda.issued_at < NOW() - 5 days
  Action:
    1. Referral status → NDA_TIMEOUT_REJECTED
    2. NDA status → EXPIRED
    3. Notify referrer: "Candidate did not sign NDA within 5 days. Referral closed."
    4. Notify candidate: "Your referral has been closed due to NDA timeout. Contact HR to appeal."
    5. Audit event logged with reason: NDA_AUTO_REJECTED
    6. Record archived (not deleted)

RULE-N4: NDA Decline Handling
  If candidate explicitly declines NDA via OpenSign:
    1. Webhook received → immediate rejection
    2. Referral status → NDA_DECLINED_REJECTED
    3. Notify referrer and HR immediately
    4. No waiting period — terminal state
```

### 3.4 SLA Rules

| Activity | SLA | Warning | Escalation |
|---|---|---|---|
| HR referral review | 2 business days | T+1 day | T+2 days → Program Owner |
| Mentor response | 3 calendar days | T+2 days | T+3 days → auto-timeout |
| Non-Worker ID creation | 1 business day | T+4 hours | T+8 hours → Program Owner |
| NDA signing | 5 calendar days | T+24h, T+48h, T+72h | T+5 days → auto-reject |
| Badge / site access | 2 business days before start | T-3 days | T-4 days → Admin Manager |
| AD account provisioning | 2 business days before start | T-3 days | T-4 days → IT Manager |
| AD deactivation post-end | 24 hours | T+12 hours | T+18 hours → Program Owner |
| Certificate issuance | 5 business days post-request | T+3 days | T+5 days → HR Manager |

---

## 4. Workflow Reasoning

### 4.1 Master Workflow (End-to-End)

```
═══════════════════════════════════════════════════════════════════
PHASE 1: REFERRAL INTAKE
═══════════════════════════════════════════════════════════════════

Step 1: Employee logs in via Azure AD SSO
        └── Role resolved from NexHire RBAC table

Step 2: Employee fills Internship Referral Form
        ├── Uploads candidate resume
        │   └── AI-1: Resume Deep Analyzer runs
        │         ├── Extracts: name, email, phone, education, skills
        │         ├── Generates: internship_readiness_score, suggested_project_tracks
        │         ├── Flags: red_flags[], recommended_mentor_questions[]
        │         └── Prefills form with confidence scores per field
        │
        ├── Employee selects year of study
        │   └── RULE-E1: 1st year / graduated → BLOCKED immediately
        │
        ├── Employee selects college
        │   └── RULE-E2: College cap check → WARNING if 1/2 used, BLOCK if 2/2 used
        │
        ├── Employee selects mentor from picker
        │   ├── RULE-E3: Referrer ≠ Mentor enforced
        │   ├── RULE-M-CAP: Full mentors (4/4) shown as FULL, unselectable
        │   └── AI-2: Mentor Match Engine suggests top 3 mentors with radar chart
        │
        ├── AI-3: Eligibility & Risk Profiler runs
        │   └── Outputs: risk_score, risk_factors[], college_cap_status
        │
        └── AI-4: Duplicate Detection runs
            ├── Multi-signal: email + phone + name fuzzy match
            └── Flags if candidate found in last 24 months

Step 3: Referral submitted → status: SUBMITTED
        ├── Timestamps, referrer_id, mentor_id logged immutably
        ├── Confirmation email → Referrer (AI-drafted)
        └── Assignment request email → Mentor (AI-drafted with candidate summary)

═══════════════════════════════════════════════════════════════════
PHASE 2: MENTOR ASSIGNMENT
═══════════════════════════════════════════════════════════════════

Step 4: Mentor receives assignment request
        ├── Email contains: candidate summary, project, internship dates
        ├── Two action buttons: [Accept Mentoring] [Reject Mentoring]
        ├── SLA clock starts: 3 calendar days
        └── Mentor capacity pre-validated (system won't allow over-assignment)

Step 4A: MENTOR ACCEPTS
        ├── Referral status → MENTOR_ACCEPTED
        ├── Mentor.active_mentee_count += 1
        ├── Notify referrer: "Mentor [Name] has accepted!"
        └── Proceed to Phase 3

Step 4B: MENTOR REJECTS
        ├── Rejection reason captured (mandatory)
        ├── Referral status → MENTOR_REJECTED → MENTOR_PENDING
        ├── attempt_count += 1
        ├── Notify referrer with rejection reason
        ├── AI-2: Re-runs mentor suggestions (excludes rejected mentor)
        └── Employee selects new mentor (if attempt_count < 3)

Step 4C: MENTOR TIMEOUT (3 days no response)
        ├── APScheduler job fires
        ├── Mentor status → MENTOR_TIMED_OUT
        ├── Referral status → MENTOR_PENDING
        ├── attempt_count += 1
        ├── Notify referrer: "[Mentor] did not respond. Please select new mentor."
        ├── AI-2: Regenerates suggestions
        └── Employee selects new mentor (if attempt_count < 3)

Step 4D: 3RD ATTEMPT FAILS (reject OR timeout)
        ├── Referral status → CANDIDATE_REJECTED
        ├── Reason: MAX_MENTOR_ATTEMPTS_EXCEEDED
        ├── Notify referrer and candidate (AI-drafted empathetic emails)
        └── Record archived → TERMINAL STATE

═══════════════════════════════════════════════════════════════════
PHASE 3: HR REVIEW & APPROVAL
═══════════════════════════════════════════════════════════════════

Step 5: HR receives referral notification
        ├── AI-10: Workflow Auto-Router assigns to least-loaded HR member
        ├── HR reviews: AI-parsed data, original resume, risk profile
        ├── AI-3 output shown: risk score, flags, recommended questions
        └── HR actions: Approve / Reject / Request Correction

Step 6: On Approval
        ├── Referral status → APPROVED
        ├── Congratulations email → Candidate (AI-drafted, personalized)
        ├── Email includes: mentor name, project title, expected start date
        └── Magic link sent to candidate for joining form access

═══════════════════════════════════════════════════════════════════
PHASE 4: CANDIDATE ONBOARDING
═══════════════════════════════════════════════════════════════════

Step 7: Candidate accesses joining form via magic link
        ├── AI-6: Joining Form Assistant active
        │   ├── Detects institution name → auto-fills affiliated codes
        │   ├── Reads uploaded ID proof → extracts DOB, ID number, name
        │   ├── Cross-validates name vs referral form → flags mismatches
        │   └── Contextual prompts per section
        ├── Auto-save every 60 seconds (save-draft)
        └── File uploads: photo, ID proof, education certificate

Step 8: Candidate submits joining form
        ├── HR notified (AI-drafted review task email)
        └── Referral status → JOINING_FORM_SUBMITTED

Step 9: HR reviews and locks joining form
        ├── Lock = data verified
        ├── Immutable lock event logged
        ├── SLA clock starts for Non-Worker ID (T+0)
        └── Referral status → JOINING_FORM_LOCKED

Step 10: HR creates Non-Worker ID
         ├── SLA: 1 business day
         ├── Warning at T+4h, escalation to Program Owner at T+8h
         └── Referral status → ID_ISSUED

Step 11: NDA issued via OpenSign
         ├── NDA PDF template pulled from Azure Blob Storage
         ├── OpenSign API: create envelope → send to candidate email
         ├── OpenSign webhook registered for: SIGNED / DECLINED / EXPIRED
         ├── NDA reminder schedule starts (Day 1, Day 2, Day 3, Day 5 auto-reject)
         └── Start date HARD BLOCKED until nda.status = SIGNED

Step 11A: Candidate signs NDA
         ├── OpenSign webhook → SIGNED event received
         ├── Signed PDF retrieved → stored in Azure Blob Storage
         ├── nda.status → SIGNED, signed_at = timestamp
         └── Referral status → NDA_SIGNED

Step 11B: NDA Day 5 Auto-Reject
         ├── APScheduler job fires at T+120h
         ├── Referral status → NDA_TIMEOUT_REJECTED
         ├── Notify referrer + candidate (AI-drafted)
         └── TERMINAL STATE

Step 12: Offer / Confirmation letter generated
         ├── AI-8 (adapted): Letter content generated from intern data
         ├── HR reviews and sends
         └── Copy archived to Azure Blob Storage

═══════════════════════════════════════════════════════════════════
PHASE 5: ACCESS PROVISIONING
═══════════════════════════════════════════════════════════════════

Step 13: Admin/Security task created (badge)
         ├── AI-10: Auto-routed to available Admin member
         ├── SLA: 2 business days before start
         └── Completion logged with badge reference

Step 14: IT/AD task created (account provisioning)
         ├── Trigger: Non-Worker ID confirmed + start date T-2 days
         ├── IT uses Microsoft Graph API to create AD account
         ├── Credentials delivered to candidate via OTP magic link
         ├── AD credentials NEVER stored in NexHire DB
         └── IT marks task complete

Step 15: Mentor receives full intern dossier
         ├── AI-7 (adapted): Dossier compiled — photo, skills, project, timeline
         ├── One secure link (SAS token, 24h expiry)
         └── Mutual connect prompt (Teams deep link)

Step 16: AI-7: Pre-Start Compliance Check fires at T-48h
         ├── Checks all blockers: NDA, ID, AD, badge, offer letter
         ├── Auto-escalates any red items immediately
         └── Report sent to HR + Program Owner

═══════════════════════════════════════════════════════════════════
PHASE 6: INTERNSHIP EXECUTION
═══════════════════════════════════════════════════════════════════

Step 17: Mentor confirms intern started (Day 1 check-in)
         ├── Referral status → ACTIVE
         └── Internship duration clock begins

Step 18: Mid-point check-in (AI-5 monitors SLA health continuously)
         ├── AI-5: Bottleneck Predictor runs every 6 hours
         └── Extension requests: Mentor + HR approval, new end date set

═══════════════════════════════════════════════════════════════════
PHASE 7: CLOSURE & CERTIFICATION
═══════════════════════════════════════════════════════════════════

Step 19: End-of-internship reminders
         ├── T-7 days: Mentor + HR reminder (AI-drafted)
         └── T-1 day: Final reminder

Step 20: Closure workflow
         ├── Mentor confirms completion (or early exit with reason)
         ├── IT/AD: Graph API account deactivation task (SLA ≤ 24h)
         ├── Admin/Security: badge deactivation task
         ├── Certificate request form sent to candidate
         └── Referral status → CLOSURE_PENDING

Step 21: Certificate generation
         ├── HR reviews certificate request
         ├── AI-8: Certificate citation content generated
         ├── PDF generated on letterhead template (Azure Blob)
         ├── HR approves → signed PDF archived
         ├── Delivery link sent to candidate
         └── Referral status → CLOSED
```

---

## 5. Auto-Rejection State Machines

### 5.1 Mentor Assignment State Machine

```
                    ┌─────────────────┐
                    │  MENTOR_PENDING  │◄──────────────────────┐
                    └────────┬────────┘                        │
                             │                                 │
              ┌──────────────┼──────────────┐                  │
              │              │              │                  │
         [Accept]       [Reject]      [Timeout 3d]             │
              │              │              │                  │
              ▼              ▼              ▼                  │
      MENTOR_ACCEPTED  MENTOR_REJECTED  MENTOR_TIMED_OUT       │
              │              │              │                  │
              │              └──────┬───────┘                  │
              │                     │                          │
              │            attempt_count += 1                  │
              │                     │                          │
              │              ┌──────▼──────┐                   │
              │              │ attempts < 3?│                   │
              │              └──────┬──────┘                   │
              │                     │                          │
              │              ┌──────┴──────┐                   │
              │              │             │                   │
              │            YES            NO                   │
              │              │             │                   │
              │              │             ▼                   │
              │              │    CANDIDATE_REJECTED           │
              │              │    (TERMINAL — audit logged)    │
              │              │                                 │
              │              └─────────────────────────────────┘
              │                  Employee selects new mentor
              │
              ▼
    Continue to HR Review Phase
```

### 5.2 NDA Signing State Machine

```
[NDA Issued via OpenSign]
         │
         ▼
    NDA_PENDING
         │
    ┌────┴──────────────────────────────────────────┐
    │                                               │
[T+24h] Day 1 Reminder                    [Candidate Signs]
[T+48h] Day 2 Urgent Reminder                      │
[T+72h] Day 3 Final Warning                        ▼
    │                                          NDA_SIGNED
[T+120h] Auto-Reject Triggered                     │
    │                                              ▼
    ▼                                   Continue to Access Provisioning
NDA_TIMEOUT_REJECTED
(TERMINAL)
    │
    ├── Notify Referrer (AI-drafted)
    ├── Notify Candidate (AI-drafted)
    ├── Audit event: NDA_AUTO_REJECTED
    └── Archive record

    OR

[Candidate Explicitly Declines via OpenSign]
    │
    ▼
NDA_DECLINED_REJECTED
(TERMINAL — immediate, no grace period)
    │
    ├── Webhook received from OpenSign
    ├── Notify Referrer + HR immediately
    └── Audit event: NDA_DECLINED
```

### 5.3 Master Referral Status Flow

```
DRAFT
  └─► SUBMITTED
        └─► MENTOR_PENDING
              ├─► MENTOR_ACCEPTED
              │     └─► HR_REVIEW
              │           ├─► APPROVED
              │           │     └─► JOINING_FORM_PENDING
              │           │           └─► JOINING_FORM_SUBMITTED
              │           │                 └─► JOINING_FORM_LOCKED
              │           │                       └─► ID_PENDING
              │           │                             └─► ID_ISSUED
              │           │                                   └─► NDA_PENDING
              │           │                                         ├─► NDA_SIGNED
              │           │                                         │     └─► ACCESS_PENDING
              │           │                                         │           └─► ACTIVE
              │           │                                         │                 ├─► EXTENDED
              │           │                                         │                 └─► CLOSURE_PENDING
              │           │                                         │                       └─► CLOSED ✅
              │           │                                         ├─► NDA_TIMEOUT_REJECTED ❌
              │           │                                         └─► NDA_DECLINED_REJECTED ❌
              │           └─► HR_REJECTED ❌
              ├─► MENTOR_REJECTED → MENTOR_PENDING (attempt < 3)
              ├─► MENTOR_TIMED_OUT → MENTOR_PENDING (attempt < 3)
              └─► CANDIDATE_REJECTED ❌ (3 failed mentor attempts)
```

---

## 6. UI/UX Thinking

### 6.1 Screen Inventory (25 Screens)

#### Auth (2)
| # | Screen | Purpose |
|---|---|---|
| S1 | Azure AD SSO Redirect | Employee login via MSAL |
| S2 | Magic Link Verification | Candidate accesses portal |

#### Referrer Screens (5)
| # | Screen | Purpose |
|---|---|---|
| S3 | My Dashboard | Referral pipeline, statuses, pending actions |
| S4 | New Referral Form | Multi-step wizard with AI prefill + mentor picker |
| S5 | Referral Detail & Timeline | Full status history, AI analysis, event log |
| S6 | Edit Referral (pre-approval) | Correct before HR reviews |
| S7 | Mentor Re-selection Panel | AI suggestions with radar chart after mentor failure |

#### Candidate Screens (3)
| # | Screen | Purpose |
|---|---|---|
| S8 | Welcome / Status Page | Current stage, "What happens next" panel |
| S9 | Joining Form | Multi-section, AI-assisted, save-draft |
| S10 | NDA Signing Page | Embedded OpenSign widget |

#### HR Screens (7)
| # | Screen | Purpose |
|---|---|---|
| S11 | HR Dashboard | All referrals, SLA breach alerts, AI bottleneck insights |
| S12 | Referral Review Panel | AI analysis vs original resume, approve/reject |
| S13 | Joining Form Review | Review submitted form, lock button |
| S14 | Non-Worker ID Management | Issue ID, track SLA countdown |
| S15 | NDA & Letters Management | NDA status, OpenSign status, offer letter generation |
| S16 | Certificate Issuance | AI-generated citation, review, approve, archive |
| S17 | AI Program Chatbot | Natural language queries on program data |

#### Mentor Screens (3)
| # | Screen | Purpose |
|---|---|---|
| S18 | Mentor Dashboard | My interns: active (n/4), upcoming, past |
| S19 | Intern Dossier View | Full profile, AI-generated summary, task checklist |
| S20 | Lifecycle Actions | Accept/reject mentoring, confirm start, request extension, confirm closure |

#### IT/AD & Admin Screens (2)
| # | Screen | Purpose |
|---|---|---|
| S21 | Task Queue (IT/AD) | Graph API provisioning tasks, SLA countdown |
| S22 | Task Queue (Admin/Security) | Badge access tasks with start/end dates |

#### Program Owner Screens (3)
| # | Screen | Purpose |
|---|---|---|
| S23 | Executive Dashboard | SLA heartbeat, stage counts, cycle time, College Map |
| S24 | SLA & Audit Report | Breach drill-down, full audit trail, export |
| S25 | Configuration Panel | Templates, escalation matrix, NDA versions, role management |

### 6.2 Key UX Design Decisions

**AI Prefill Visual Treatment:**
- Azure OpenAI-filled fields: amber tint + "AI Suggested" badge
- Confidence < 75%: warning icon + "Please verify" tooltip
- Human override tracked silently

**Mentor Picker (S4):**
```
┌──────────────────────────────────────────────────────────┐
│  Select Mentor                                           │
│                                                          │
│  🤖 AI Recommended                                       │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Arjun Mehta          Match: 94%   Slots: 2/4  ✅  │  │
│  │ ████████████████░░ Skills  ████████████░░░░ Avail  │  │
│  │ Reason: "Best skill match, fast responder"         │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Priya Nair           Match: 78%   Slots: 3/4  ✅  │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Ravi Kumar           Match: 71%   Slots: 4/4  🔴  │  │
│  │ MENTOR FULL — Cannot be selected                   │  │
│  └────────────────────────────────────────────────────┘  │
│  [Browse all mentors ▼]                                  │
└──────────────────────────────────────────────────────────┘
```

**"What Happens Next" Panel (every screen):**
Each role sees a contextual next-step panel — never left wondering what to do.

**SLA Heartbeat Cards (S23):**
Live pulsing cards per intern. Green → Amber → Red as SLA approaches breach. Visual urgency without data overload.

**College Intelligence Map (S23 — Program Owner):**
Bubble map of India with college locations. Bubble size = referral count. Color = completion rate. Completely unique visual no competing team will have.

---

## 7. AI System Design — 10 Touchpoints

### AI Coverage Summary

```
🤖 AI-Driven (fully automated):    35%
🤝 AI-Assisted (human reviews):    40%
👤 Human-Only (judgment required): 25%

Total AI Coverage: 75%
```

### AI-1: Resume Deep Analyzer

**Trigger:** Resume file uploaded in referral form
**Model:** Azure OpenAI GPT-4o (vision + text)
**Why GPT-4o:** Handles varied resume formats including scanned PDFs via vision capability

```python
# Input
{
  "file_bytes": "<base64>",
  "mime_type": "application/pdf"
}

# Azure OpenAI Prompt Strategy
SYSTEM: """
You are a resume analysis engine. Extract structured data and
provide readiness assessment. Return ONLY valid JSON.
"""
USER: """
Analyze this resume. Return:
{
  "candidate_name": {"value": "", "confidence": 0.0},
  "email": {"value": "", "confidence": 0.0},
  "phone": {"value": "", "confidence": 0.0},
  "year_of_study": {"value": "", "confidence": 0.0},
  "college": {"value": "", "confidence": 0.0},
  "graduation_year": {"value": 0, "confidence": 0.0},
  "education": [{"degree": "", "field": "", "institution": "", "year": 0}],
  "skills": [],
  "internship_readiness_score": 0,
  "technical_depth": "",
  "project_experience_quality": "",
  "suggested_project_tracks": [],
  "red_flags": [],
  "recommended_mentor_questions": []
}
"""

# Output stored in: ai_parse_results table
# Confidence < 0.75 → field highlighted for human review
# Human overrides tracked in: ai_parse_results.human_overrides JSONB
```

**Bias safeguard:** All fields extracted structurally — no merit scoring, no ranking. Override rate monitored by college type weekly.

---

### AI-2: Mentor Match Engine

**Trigger:** (1) Referral form — mentor selection step; (2) Mentor rejection/timeout event
**Model:** Azure OpenAI GPT-4o + rule-based scoring layer

```python
# Scoring Algorithm (5 dimensions, each 0–20 points = max 100)
def score_mentor(mentor, candidate):
    return {
        "skill_alignment":     compute_skill_overlap(mentor.skills, candidate.skills),
        "availability":        (4 - mentor.active_mentee_count) * 5,  # 0–20
        "reputation":          mentor.completion_rate * 20,            # 0–20
        "college_familiarity": 20 if mentor.has_guided_from(candidate.college) else 10,
        "response_latency":    score_response_speed(mentor.avg_response_hours)
    }

# GPT-4o generates plain-English recommendation reason per mentor
# Output: top 3 mentors with score, radar chart data, reason string
# Full mentors (4/4) excluded before scoring runs
```

**Radar chart dimensions:** Skill Match · Availability · Success Rate · Familiarity · Responsiveness

---

### AI-3: Eligibility & Risk Profiler

**Trigger:** Referral form — real-time as fields are filled
**Model:** Rule-based engine + Azure OpenAI for narrative generation

```python
# Rule engine checks (deterministic)
rules = [
    check_year_of_study(form.year_of_study),          # RULE-E1
    check_college_cap(referrer_id, form.college),      # RULE-E2
    check_unpaid_consent(form.unpaid_consent),         # RULE-E4
    check_inperson_readiness(form.inperson_ready),     # RULE-E5
    check_location_alignment(form.location, form.college_location)
]

# GPT-4o generates human-readable risk narrative from rule outputs
risk_narrative = gpt4o.generate(
    f"Based on these risk factors {risk_factors}, write a 2-sentence"
    f"advisory for the HR reviewer. Be specific and actionable."
)
```

---

### AI-4: Duplicate Detection

**Trigger:** Resume upload in referral form
**Model:** Deterministic fuzzy matching (no LLM needed)

```python
def detect_duplicate(email, phone, name):
    candidates = db.query(
        "SELECT * FROM candidates WHERE status NOT IN ('REJECTED','CLOSED')"
        "AND created_at > NOW() - INTERVAL '24 months'"
    )
    for existing in candidates:
        score = 0.0
        if normalize_email(email) == normalize_email(existing.email): score += 0.6
        if normalize_phone(phone) == normalize_phone(existing.phone): score += 0.4
        name_sim = jaro_winkler(unicode_normalize(name), unicode_normalize(existing.name))
        if name_sim > 0.85: score += name_sim * 0.2

        if score >= 0.6:
            return DuplicateResult(
                is_duplicate=True,
                match_id=existing.id,
                similarity_score=score,
                recommendation="BLOCK" if score >= 0.9 else "WARN"
            )
    return DuplicateResult(is_duplicate=False)
```

**Unicode normalization applied** to handle regional name variations correctly.

---

### AI-5: Bottleneck Predictor

**Trigger:** APScheduler — runs every 6 hours on all ACTIVE referrals
**Model:** Rule-based heuristics (Phase 1) → Gradient Boosting (Phase 2 after 6mo data)

```python
# Phase 1 heuristic scoring
def predict_breach_risk(referral):
    days_in_stage = (now() - referral.stage_entered_at).days
    historical_avg = get_historical_avg(referral.current_stage)
    hr_workload = count_open_tasks(assigned_hr_id)
    is_friday = now().weekday() == 4

    risk_score = (days_in_stage / historical_avg) * 0.5
    risk_score += (hr_workload / 10) * 0.3
    risk_score += 0.2 if is_friday else 0

    return BreachPrediction(
        probability=min(risk_score, 1.0),
        predicted_stage=referral.current_stage,
        recommended_action=generate_action(referral.current_stage, hr_workload)
    )
```

**Output:** Surfaced on HR Dashboard as "At Risk" cards with specific action recommendations.

---

### AI-6: Joining Form Assistant

**Trigger:** Real-time as candidate types in joining form
**Model:** Azure OpenAI GPT-4o (for document reading) + rule-based autofill

```
When candidate uploads ID proof (Aadhaar/PAN):
  → GPT-4o Vision extracts: name, DOB, ID number
  → Pre-fills corresponding form fields
  → Cross-validates: name on ID vs referral form name
  → Flags mismatch: "Name on ID (Riya Sharma) differs from
                     referral form (Riya S.). Please confirm."

When candidate types university name:
  → Fuzzy match against known institution list
  → Auto-fills: state, affiliated board, institution code
```

---

### AI-7: Pre-Start Compliance Checker

**Trigger:** APScheduler — fires exactly 48 hours before each intern's start date
**Model:** Rule-based (deterministic checklist) + GPT-4o for narrative + auto-escalation

```python
def run_compliance_check(intern_id):
    checklist = {
        "nda_signed":         check_nda_status(intern_id),
        "non_worker_id":      check_id_status(intern_id),
        "ad_provisioned":     check_ad_status(intern_id),
        "badge_configured":   check_badge_status(intern_id),
        "offer_letter_sent":  check_letter_status(intern_id)
    }

    blocking_items = [k for k, v in checklist.items() if not v]

    if blocking_items:
        # Auto-escalate each blocking item to responsible team
        for item in blocking_items:
            escalate_immediately(item, intern_id)

        # GPT-4o generates report narrative
        report = gpt4o.generate(f"Write a compliance report for HR. "
                                f"Blocking items: {blocking_items}. "
                                f"Start date: {intern.start_date}. "
                                f"Be urgent but professional.")

        send_compliance_report(intern_id, report, checklist)
```

---

### AI-8: Certificate Content Generator

**Trigger:** HR initiates certificate generation
**Model:** Azure OpenAI GPT-4o

```python
SYSTEM = """You write professional internship certificate citations.
            Be specific about the project and skills. 3-4 sentences maximum.
            Do not fabricate metrics — only use provided data."""

USER = f"""
Generate certificate citation for:
  Intern: {intern.name}
  Duration: {intern.duration_weeks} weeks
  Project: {intern.project_title}
  Project summary: {intern.project_overview}
  Skills demonstrated: {intern.skills}
  Mentor feedback: {mentor.closure_feedback}
"""

# HR reviews → approves → PDF generated on letterhead
# Azure Blob Storage → SAS delivery link to candidate
```

---

### AI-9: Program Intelligence Chatbot

**Trigger:** Program Owner / HR types query in S17 or S23
**Model:** Azure OpenAI GPT-4o with function calling against NexHire DB

```python
# Function definitions available to GPT-4o
tools = [
    get_mentor_rejection_stats(period),
    get_college_performance_report(),
    get_sla_breach_summary(stage, date_range),
    get_at_risk_referrals(),
    get_cycle_time_trends(),
    get_intern_completion_rates(mentor_id=None, college=None)
]

# Example interaction
Owner: "Which mentors have the highest rejection rates this quarter?"
GPT-4o: calls get_mentor_rejection_stats(period="Q4-2024")
Output: "Arjun Mehta (3 rejections, 60% rejection rate) and Priya Nair
         (2 rejections, 40%). Common reason: workload — both are at 4/4 capacity."
```

**No hallucination risk** on data queries — GPT-4o only synthesizes from live DB function results.

---

### AI-10: Workflow Auto-Router

**Trigger:** Every time a task is created (Non-Worker ID, badge, AD provisioning, etc.)
**Model:** Rule-based scoring (no LLM needed — deterministic)

```python
def auto_route_task(task_type, role_group):
    eligible_members = db.query(
        "SELECT u.*, COUNT(t.id) as open_tasks, "
        "AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))/3600) as avg_response_hours "
        "FROM users u LEFT JOIN tasks t ON t.assigned_to = u.id "
        "WHERE u.role = :role AND u.is_available = true "
        "GROUP BY u.id ORDER BY open_tasks ASC, avg_response_hours ASC LIMIT 1",
        role=role_group
    )

    assigned_to = eligible_members[0]
    log_routing_decision(task_type, assigned_to.id,
                        reason=f"Lowest workload ({assigned_to.open_tasks} tasks), "
                               f"fastest avg response ({assigned_to.avg_response_hours:.1f}h)")
    return assigned_to
```

---

## 8. System Architecture — Modular Monolith

### 8.1 FastAPI Module Structure & Communication

```
NexHire Backend (Single FastAPI Application)
│
├── API Layer (FastAPI Routers — HTTP boundary)
│   ├── /auth/*              → AuthRouter
│   ├── /referrals/*         → ReferralRouter
│   ├── /onboarding/*        → OnboardingRouter
│   ├── /mentors/*           → MentorRouter
│   ├── /tasks/*             → TaskRouter
│   ├── /documents/*         → DocumentRouter
│   ├── /notifications/*     → NotificationRouter
│   ├── /ai/*                → AiRouter
│   ├── /admin/*             → AdminRouter
│   └── /webhooks/*          → WebhookRouter (OpenSign, Graph API)
│
├── Application Modules (Internal — shared process, zero network)
│   │
│   ├── [auth]               Authentication & RBAC
│   ├── [referral]           Referral intake & HR review
│   ├── [mentor]             Mentor assignment, accept/reject, timeout
│   ├── [onboarding]         Joining form, Non-Worker ID, AD tasks
│   ├── [ai]                 All 10 AI touchpoints (Azure OpenAI SDK)
│   ├── [workflow]           State machine, SLA clocks, auto-rejection jobs
│   ├── [notification]       Gmail API email delivery, template rendering
│   ├── [document]           Azure Blob, OpenSign API, PDF generation
│   └── [admin]              Dashboards, audit trail, configuration
│
├── Shared Kernel (Types only — no business logic)
│   ├── domain_events.py     (Base DomainEvent, all event types)
│   ├── value_objects.py     (Email, Phone, UserId, InternId — validated types)
│   ├── exceptions.py        (BusinessRuleViolation, SlaBreachException, etc.)
│   └── constants.py         (SLA durations, status enums, role constants)
│
├── Infrastructure Layer
│   ├── database.py          (SQLAlchemy async engine, session factory)
│   ├── event_bus.py         (In-process async event bus)
│   ├── scheduler.py         (APScheduler setup — DB-backed job store)
│   ├── azure_blob.py        (Azure Blob Storage client + SAS generation)
│   ├── azure_openai.py      (Azure OpenAI client + retry logic)
│   ├── gmail_client.py      (Gmail API OAuth2 client)
│   ├── opensign_client.py   (OpenSign REST API client + webhook handler)
│   └── graph_api_client.py  (Microsoft Graph API — AD provisioning)
│
└── Cross-Cutting Concerns
    ├── middleware/audit.py   (Every request → immutable audit event)
    ├── middleware/auth.py    (JWT validation + RBAC enforcement)
    ├── middleware/rate_limit.py (Redis-backed rate limiting)
    └── middleware/logging.py (Structured JSON logging → Azure Monitor)
```

### 8.2 Module Interaction Rules (Anti-Big-Ball-of-Mud)

**Rule 1: Domain Events for Cross-Module Communication**
No module imports another module's services directly. All cross-module communication goes through the in-process async event bus.

```python
# referral/services.py
class ReferralService:
    async def approve_referral(self, referral_id: UUID):
        referral = await self.repo.get(referral_id)
        referral.status = ReferralStatus.APPROVED
        await self.repo.save(referral)
        # Publish event — does NOT call NotificationService directly
        await self.event_bus.publish(ReferralApproved(
            referral_id=referral_id,
            candidate_email=referral.candidate_email,
            mentor_id=referral.mentor_id
        ))

# notification/handlers.py
class NotificationEventHandler:
    @event_handler(ReferralApproved)
    async def on_referral_approved(self, event: ReferralApproved):
        # Notification module reacts — Referral module never knew this existed
        await self.notification_service.send_congratulations(event)
```

**Rule 2: Interface Boundaries (No Cross-Module DB Access)**
```python
# ❌ WRONG
from onboarding.repositories import JoiningFormRepository
form = await JoiningFormRepository().get_by_intern(intern_id)  # breaks encapsulation

# ✅ CORRECT
from onboarding.interfaces import OnboardingQueryPort
status = await self.onboarding_query.get_onboarding_status(intern_id)  # contract only
```

**Rule 3: Shared Kernel is Types-Only**
```python
# shared/domain_events.py — ALLOWED in shared kernel
@dataclass
class ReferralApproved(DomainEvent):
    referral_id: UUID
    candidate_email: Email  # value object from shared kernel
    mentor_id: UUID

# shared/value_objects.py — ALLOWED
class Email(str):
    def __new__(cls, value: str):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', value):
            raise ValueError(f"Invalid email: {value}")
        return super().__new__(cls, value.lower())

# ❌ NOT ALLOWED in shared kernel: business logic, DB queries, service calls
```

### 8.3 Module Specifications

#### [auth] Module
```
Responsibilities:
  - Azure AD OIDC token validation via MSAL
  - Magic link generation, storage (bcrypt hashed), validation
  - JWT issuance (RS256), refresh token rotation
  - RBAC permission enforcement (annotation-driven)
  - Session management (Redis-backed)

Inputs:  Azure AD token, magic link token, JWT
Outputs: Signed JWT + role claims, 401/403 errors
Dependencies: Shared Kernel (UserId, Email), Redis, PostgreSQL (sessions)

Key files:
  auth/service.py       → AzureADAuthService, MagicLinkService, JwtService
  auth/rbac.py          → RbacEnforcer, @require_permission decorator
  auth/router.py        → /auth/login, /auth/callback, /auth/magic-link
  auth/models.py        → Session, MagicLink SQLAlchemy models
```

#### [referral] Module
```
Responsibilities:
  - Referral form validation (all RULE-E1 through RULE-E5)
  - Referral CRUD (create, read, update status)
  - College cap enforcement
  - Year-of-study validation
  - HR approval/rejection workflow
  - Duplicate detection coordination (via AI module interface)

Inputs:  Referral form data, HR decisions, resume file reference
Outputs: Referral records, domain events (ReferralSubmitted, ReferralApproved, etc.)
Dependencies: Shared Kernel, [ai] module interface, [document] module interface

Key business rules enforced here:
  - RULE-E1: year_of_study in [2, 3, 4]
  - RULE-E2: college_referral_count(referrer_id, college) < 2
  - RULE-E3: referrer_id ≠ mentor_id
```

#### [mentor] Module
```
Responsibilities:
  - Mentor capacity tracking (max 4 mentees)
  - Assignment request lifecycle (PENDING → ACCEPTED/REJECTED/TIMED_OUT)
  - Mandatory rejection reason capture
  - Attempt counter management (max 3)
  - Auto-rejection after 3rd failure
  - Mentor reputation score calculation

Inputs:  Referral submission events, mentor accept/reject actions, scheduler ticks
Outputs: Mentor assignment records, domain events (MentorAccepted, MentorRejected,
         MentorTimedOut, CandidateRejectedMaxAttempts)

Key APScheduler jobs:
  check_mentor_timeouts()  → runs every hour
    → finds MENTOR_PENDING records where assigned_at < NOW() - 3 days
    → fires MentorTimedOut event per record
```

#### [workflow] Module
```
Responsibilities:
  - Master referral state machine (all valid transitions + guards)
  - SLA clock start/stop per stage
  - Escalation rule evaluation
  - NDA auto-rejection job (Day 5)
  - Pre-start compliance check job (T-48h)
  - Overall workflow orchestration via event reactions

Key APScheduler jobs:
  check_nda_timeouts()           → every 6 hours
  check_sla_breaches()           → every 1 hour
  run_compliance_checks()        → every 6 hours (filters start_date - 2 days)
  run_bottleneck_predictions()   → every 6 hours
  check_mentor_timeouts()        → every 1 hour
```

#### [ai] Module
```
Responsibilities:
  All 10 AI touchpoints via clean AiService interface
  Azure OpenAI client management (rate limiting, retry, cost tracking)
  AI result caching (Redis — 1h TTL for mentor suggestions)
  Human override tracking
  AI performance metrics collection

Public interface:
  ai_service.parse_resume(file_bytes, mime_type) → ParseResult
  ai_service.suggest_mentors(candidate, excluded_ids) → List[MentorRecommendation]
  ai_service.assess_risk(form_data) → RiskProfile
  ai_service.detect_duplicate(email, phone, name) → DuplicateResult
  ai_service.draft_email(template_id, context) → EmailDraft
  ai_service.predict_breach(referral) → BreachPrediction
  ai_service.assist_joining_form(field, value) → FormAssistance
  ai_service.check_compliance(intern_id) → ComplianceReport
  ai_service.generate_certificate(intern_data) → CertificateText
  ai_service.query_program(question) → ProgramInsight
```

#### [document] Module
```
Responsibilities:
  - Azure Blob Storage: upload, download, SAS token generation (15min expiry)
  - Virus scanning on upload (Azure Defender integration)
  - OpenSign API: envelope creation, signing URL generation, webhook processing
  - NDA lifecycle: issued → sent → signed/declined/expired
  - PDF generation: certificates, offer letters (reportlab / weasyprint)
  - Document metadata in PostgreSQL
  - Retention job: anonymize expired documents per policy

OpenSign Integration:
  POST /api/request-signature → creates envelope with NDA PDF
  Webhook: POST /webhooks/opensign → receives SIGNED/DECLINED/EXPIRED
  GET /api/download/{envelope_id} → retrieves signed PDF for archival
```

#### [notification] Module
```
Responsibilities:
  - Gmail API OAuth2 email delivery
  - Jinja2 template rendering (9 core templates)
  - Delivery status tracking (sent/bounced/failed)
  - Retry queue (exponential backoff: 5min, 15min, 1h, 4h)
  - All email content AI-drafted then stored in notification_queue
  - Bounce rate monitoring

Gmail API Setup:
  - Service account with domain-wide delegation
  - Send-as: nexhire-noreply@company.com
  - Rate: 100 emails/second (Gmail API limit respected)
  - All sends logged with recipient + content_sha256 (not full body — PII)
```

---

## 9. Data Modeling

### 9.1 Core Schema (PostgreSQL)

```sql
-- Users (synced from Azure AD on first login)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    azure_oid VARCHAR(255) UNIQUE NOT NULL,     -- Azure AD Object ID
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role user_role NOT NULL,                    -- ENUM: REFERRER, MENTOR, HR, IT_AD, ADMIN, PROGRAM_OWNER
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Referrals (core entity)
CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id UUID NOT NULL REFERENCES users(id),
    mentor_id UUID REFERENCES users(id),
    candidate_name VARCHAR(255) NOT NULL,
    candidate_email VARCHAR(255) NOT NULL,
    candidate_phone VARCHAR(20),
    candidate_college VARCHAR(255) NOT NULL,
    candidate_year_of_study SMALLINT NOT NULL CHECK (year_of_study BETWEEN 2 AND 4),
    candidate_graduation_year SMALLINT NOT NULL,
    project_title VARCHAR(255),
    project_overview TEXT,
    joining_location VARCHAR(255),
    internship_start_date DATE,
    internship_end_date DATE,
    relationship_declaration VARCHAR(50),
    relationship_declaration_detail TEXT,
    unpaid_consent BOOLEAN NOT NULL DEFAULT false,
    inperson_ready BOOLEAN NOT NULL DEFAULT false,
    status referral_status NOT NULL DEFAULT 'DRAFT',
    mentor_attempt_count SMALLINT DEFAULT 0 CHECK (mentor_attempt_count <= 3),
    resume_document_id UUID REFERENCES documents(id),
    submitted_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    approved_by UUID REFERENCES users(id),
    rejected_at TIMESTAMPTZ,
    rejected_by UUID REFERENCES users(id),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint: prevent duplicate active referrals
CREATE UNIQUE INDEX idx_referrals_active_candidate
    ON referrals(candidate_email)
    WHERE status NOT IN ('REJECTED', 'CLOSED', 'TERMINATED',
                         'CANDIDATE_REJECTED', 'NDA_TIMEOUT_REJECTED',
                         'NDA_DECLINED_REJECTED');

-- College cap enforcement view
CREATE VIEW referrer_college_counts AS
    SELECT referrer_id, candidate_college, COUNT(*) as count
    FROM referrals
    WHERE status NOT IN ('REJECTED', 'CLOSED', 'TERMINATED',
                         'CANDIDATE_REJECTED', 'NDA_TIMEOUT_REJECTED',
                         'NDA_DECLINED_REJECTED')
    GROUP BY referrer_id, candidate_college;

-- Mentor assignments
CREATE TABLE mentor_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id UUID NOT NULL REFERENCES referrals(id),
    mentor_id UUID NOT NULL REFERENCES users(id),
    attempt_number SMALLINT NOT NULL,
    status mentor_assignment_status NOT NULL DEFAULT 'PENDING',
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    rejection_reason TEXT,
    timeout_at TIMESTAMPTZ                      -- set at assigned_at + 3 days
);

-- Interns (created on referral approval)
CREATE TABLE interns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id UUID UNIQUE NOT NULL REFERENCES referrals(id),
    user_id UUID REFERENCES users(id),          -- candidate portal user
    non_worker_id VARCHAR(100) UNIQUE,
    ad_account_username VARCHAR(255),
    ad_account_status ad_status DEFAULT 'NOT_CREATED',
    actual_start_date DATE,
    actual_end_date DATE,
    status intern_status NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Joining forms
CREATE TABLE joining_forms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intern_id UUID UNIQUE NOT NULL REFERENCES interns(id),
    personal_details JSONB,
    address JSONB,
    emergency_contact JSONB,
    education_history JSONB,
    employment_history JSONB,
    govt_ids JSONB,
    status form_status NOT NULL DEFAULT 'DRAFT',
    version INTEGER DEFAULT 1,                  -- optimistic locking
    submitted_at TIMESTAMPTZ,
    locked_at TIMESTAMPTZ,
    locked_by UUID REFERENCES users(id),
    declaration_signed BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- NDA records
CREATE TABLE nda_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intern_id UUID UNIQUE NOT NULL REFERENCES interns(id),
    opensign_envelope_id VARCHAR(255) UNIQUE,
    template_version VARCHAR(50),
    status nda_status NOT NULL DEFAULT 'PENDING',
    issued_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    signed_at TIMESTAMPTZ,
    declined_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ,
    auto_rejected_at TIMESTAMPTZ,
    signed_document_id UUID REFERENCES documents(id),
    reminder_1_sent_at TIMESTAMPTZ,
    reminder_2_sent_at TIMESTAMPTZ,
    reminder_3_sent_at TIMESTAMPTZ
);

-- Tasks
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intern_id UUID NOT NULL REFERENCES interns(id),
    task_type task_type NOT NULL,               -- ENUM: NON_WORKER_ID, NDA_SIGN,
                                                --       AD_PROVISION, BADGE_ACCESS,
                                                --       AD_DEACTIVATE, CERT_REQUEST
    assigned_to UUID NOT NULL REFERENCES users(id),
    assigned_by_ai BOOLEAN DEFAULT false,
    ai_routing_reason TEXT,
    status task_status NOT NULL DEFAULT 'PENDING',
    sla_deadline TIMESTAMPTZ NOT NULL,
    warned_at TIMESTAMPTZ,
    escalated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    completion_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type doc_type NOT NULL,
    azure_blob_container VARCHAR(255) NOT NULL,
    azure_blob_key VARCHAR(500) NOT NULL,       -- UUID-based, unpredictable
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    is_archived BOOLEAN DEFAULT false,
    retention_delete_at DATE                    -- computed from retention policy
);

-- AI parse results
CREATE TABLE ai_parse_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id UUID REFERENCES referrals(id),
    ai_touchpoint VARCHAR(50) NOT NULL,         -- RESUME_PARSE, MENTOR_MATCH, etc.
    model_version VARCHAR(100) NOT NULL,
    azure_openai_request_id VARCHAR(255),
    parsed_at TIMESTAMPTZ DEFAULT NOW(),
    raw_output JSONB NOT NULL,
    confidence_scores JSONB,
    human_overrides JSONB DEFAULT '[]',         -- [{field, original, override, by, at}]
    tokens_used INTEGER,
    latency_ms INTEGER
);

-- Audit events (APPEND-ONLY — no UPDATE or DELETE ever)
CREATE TABLE audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    actor_user_id UUID,
    actor_role VARCHAR(50),
    ip_address INET,
    user_agent TEXT,
    event_timestamp TIMESTAMPTZ DEFAULT NOW(),
    payload JSONB NOT NULL,
    prev_checksum VARCHAR(64),
    checksum VARCHAR(64) NOT NULL               -- SHA256(prev_checksum || payload::text)
);

-- Revoke UPDATE and DELETE on audit_events
REVOKE UPDATE, DELETE ON audit_events FROM nexhire_app;

-- Notifications
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intern_id UUID REFERENCES interns(id),
    template_id VARCHAR(100) NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    body_sha256 VARCHAR(64) NOT NULL,           -- hash only, not full body (PII)
    gmail_message_id VARCHAR(255),
    status notification_status NOT NULL DEFAULT 'QUEUED',
    queued_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    delivery_status VARCHAR(50),
    bounce_reason TEXT,
    retry_count SMALLINT DEFAULT 0
);
```

---

## 10. Failure Scenarios

### 10.1 Auto-Rejection Edge Cases

| Scenario | Handling |
|---|---|
| APScheduler crashes before NDA auto-reject fires | Job is DB-backed (persisted) — resumes on restart; idempotency key prevents double execution |
| Candidate signs NDA at Day 4 23:59 | Signing event from OpenSign webhook updates nda.status = SIGNED; scheduler job checks status before firing — auto-reject aborted |
| Mentor responds at exactly 72h mark | Race condition handled by DB transaction: mentor response wins if committed before scheduler job starts; idempotent event processing |
| Third mentor attempt fails but event bus is down | Synchronous fallback: workflow state written to DB first, event published after; at-least-once delivery with deduplication |
| OpenSign webhook not received (network issue) | Polling job runs every 15 minutes to check pending NDA status via OpenSign API as fallback |

### 10.2 Azure OpenAI Failures

| Failure | Response |
|---|---|
| Rate limit hit | Exponential backoff (1s, 2s, 4s, 8s); cached results served if available |
| Timeout > 10s | Fallback: show "AI unavailable" with manual fields; user proceeds without prefill |
| Malformed JSON output | Retry with corrected prompt (max 2 retries); fall back to empty prefill |
| Azure OpenAI quota exceeded | Alert ops team via Azure Monitor; all AI touchpoints degrade gracefully to manual mode |

### 10.3 OpenSign Integration Failures

| Failure | Response |
|---|---|
| OpenSign container down | NDA issuance queued in notifications table; retry every 1h; HR alerted |
| Webhook signature invalid | Reject and log; poll OpenSign API as backup within 15 minutes |
| Envelope ID not found | Log error; HR manually triggered to re-issue; audit event recorded |

### 10.4 Microsoft Graph API Failures

| Failure | Response |
|---|---|
| Graph API returns 503 | Task remains PENDING; IT alerted; retry every 30 minutes |
| AD account creation fails | Detailed error logged; IT task shows error reason; manual intervention with system update |
| Deactivation fails at end | Escalation to Program Owner and IT Manager within 2 hours |

---

## 11. Metrics & Feedback Loops

### 11.1 AI Performance Dashboard (Program Owner — S23)

| Metric | Target | Alert Threshold |
|---|---|---|
| Resume parse success rate | ≥ 95% | < 90% |
| Average parse confidence (name/email) | ≥ 0.85 | < 0.75 |
| Human override rate (any field) | ≤ 15% | > 20% |
| Mentor match acceptance rate (top suggestion) | ≥ 60% | < 40% |
| Email draft send-without-edit rate | ≥ 70% | < 50% |
| Duplicate detection false positive rate | ≤ 5% | > 10% |
| Azure OpenAI latency (p95) | ≤ 8s | > 15s |
| Azure OpenAI cost per referral | Tracked | +50% spike |

### 11.2 AI Continuous Improvement Loop

```
[AI Output] → [Human Reviews] → [Override Captured]
                                        │
                              Weekly Analysis Job
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              Override rate        False positive      Cost per
              by field > 20%       rate > 10%          referral spike
                    │                   │                   │
            Prompt engineering    Threshold tune      Model version
            review + update       in config           review
                    │
              Canary deploy (10% traffic)
                    │
              Compare override rates
                    │
              Full rollout if improved
```

---

## 12. Security & Ethics

### 12.1 Azure Security Posture

| Control | Implementation |
|---|---|
| Data at rest | Azure Database for PostgreSQL — encryption enabled (AES-256) |
| Blob encryption | Azure Blob Storage — Microsoft-managed keys (phase 1); CMK (phase 2) |
| Data in transit | TLS 1.3 minimum; internal OpenSign on same Azure VNet |
| Identity | Azure AD — MFA enforced for all internal users via Conditional Access |
| Secrets management | Azure Key Vault — all API keys, connection strings, JWT private keys |
| Network | Azure App Service VNet Integration; PostgreSQL on private endpoint |
| Monitoring | Azure Application Insights + Azure Monitor alerts |
| Vulnerability scanning | Azure Defender for App Service + Container Registry |
| File upload safety | Azure Defender for Storage — malware scanning on blob upload |

### 12.2 PII Minimization by Role

| Role | PII Accessible |
|---|---|
| IT/AD | Name, Non-Worker ID, AD username, start/end date ONLY |
| Admin/Security | Name, photo, start/end date, location ONLY |
| Mentor | Full dossier (name, skills, project) — no govt IDs |
| Referrer | Own referrals only; candidate contact details masked after approval |
| HR | Full record |
| Program Owner | Aggregated data; individual records on drill-down |

### 12.3 AI Ethics

- **No merit ranking:** AI never scores candidates for suitability — only parses structure and detects duplicates
- **Transparency:** Every AI-filled field is visually marked; confidence shown on hover
- **Human override always available:** No AI decision is final without human confirmation
- **Override audit:** Every override logged with actor, field, original value, new value, timestamp
- **Bias monitoring:** Override rates tracked by college tier, state, resume language — investigated if > 20% disparity
- **Data residency:** All Azure OpenAI calls route through Azure region within India/organization boundary

---

## 13. Future Evolution

### 13.1 Scaling the Monolith

**Immediate (launch):**
- FastAPI async + uvicorn with 4 workers handles 500 concurrent users comfortably
- Azure Database for PostgreSQL Flexible Server auto-scales storage
- Azure App Service — scale up vertically before scaling out

**Medium-term:**
- Redis caching for AI results (mentor suggestions, risk profiles)
- PostgreSQL read replica for all Admin/Reporting module queries
- Azure CDN for static frontend assets (React build)
- APScheduler → Azure Service Bus for reliable job queuing (no job loss on restart)

### 13.2 Microservice Extraction Path (When Needed)

```
Step 1: Replace in-process event bus with Transactional Outbox
        (events written to outbox table within same DB transaction)

Step 2: Add relay process: outbox table → Azure Service Bus

Step 3: Extract AI Module to separate FastAPI service
        (First candidate: different resource needs — GPU for LLM inference)
        Module's public interface contract remains identical

Step 4: Extract Notification Module
        (Second candidate: high-frequency, independent scaling)

Clean extraction guaranteed because:
  - No cross-module DB access (interface boundaries enforced from day 1)
  - Domain events already define the API contract
  - Module internals are fully encapsulated
```

---

## 14. Project Folder Structure

```
nexhire/
│
├── frontend/                          # React + TypeScript SPA
│   ├── src/
│   │   ├── app/
│   │   │   ├── routes/                # Role-based route definitions
│   │   │   ├── providers/             # QueryClient, AuthProvider, ThemeProvider
│   │   │   └── App.tsx
│   │   ├── modules/
│   │   │   ├── auth/
│   │   │   │   ├── components/        # Login, MagicLinkEntry
│   │   │   │   ├── hooks/             # useAuth, useMsal
│   │   │   │   └── api.ts
│   │   │   ├── referral/
│   │   │   │   ├── components/        # ReferralForm, ReferralCard, ReferralTimeline
│   │   │   │   ├── hooks/             # useReferralForm, useAiPrefill
│   │   │   │   └── api.ts
│   │   │   ├── mentor/
│   │   │   │   ├── components/        # MentorPicker, MentorRadarChart, ReselectionPanel
│   │   │   │   └── api.ts
│   │   │   ├── onboarding/
│   │   │   │   ├── components/        # JoiningForm, NdaViewer, FormAssistant
│   │   │   │   └── api.ts
│   │   │   ├── dashboard/
│   │   │   │   ├── components/        # SlaHeartbeat, CollegeMap, BottleneckCard
│   │   │   │   └── api.ts
│   │   │   └── admin/
│   │   │       ├── components/        # AuditTrail, ConfigPanel, AiChatbot
│   │   │       └── api.ts
│   │   ├── shared/
│   │   │   ├── components/            # WhatHappensNext, ConfidenceBadge, SlaCountdown
│   │   │   ├── hooks/                 # usePermission, useSlaCountdown
│   │   │   └── types.ts
│   │   └── lib/
│   │       ├── axios.ts               # Axios instance + JWT interceptor
│   │       ├── msal.ts                # MSAL Azure AD config
│   │       └── utils.ts
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── backend/                           # Python FastAPI Modular Monolith
│   ├── app/
│   │   ├── main.py                    # FastAPI app init, router registration, middleware
│   │   ├── config.py                  # Settings (Azure Key Vault + env vars via pydantic-settings)
│   │   │
│   │   ├── shared/                    # Shared Kernel — types only
│   │   │   ├── domain_events.py       # Base DomainEvent + all event dataclasses
│   │   │   ├── value_objects.py       # Email, PhoneNumber, UserId, InternId
│   │   │   ├── exceptions.py          # BusinessRuleViolation, SlaBreachException
│   │   │   └── constants.py           # Enums, SLA durations, role constants
│   │   │
│   │   ├── modules/
│   │   │   ├── auth/
│   │   │   │   ├── router.py          # /auth/* endpoints
│   │   │   │   ├── service.py         # AzureADAuthService, MagicLinkService, JwtService
│   │   │   │   ├── rbac.py            # RbacEnforcer, require_permission decorator
│   │   │   │   ├── models.py          # Session, MagicLink SQLAlchemy models
│   │   │   │   └── schemas.py         # Pydantic request/response schemas
│   │   │   │
│   │   │   ├── referral/
│   │   │   │   ├── router.py          # /referrals/* endpoints
│   │   │   │   ├── service.py         # ReferralService (submit, approve, reject)
│   │   │   │   ├── validator.py       # All RULE-E1 through RULE-E5 enforcement
│   │   │   │   ├── repository.py      # ReferralRepository (SQLAlchemy async)
│   │   │   │   ├── query_service.py   # Read-side: list, filter, search
│   │   │   │   ├── models.py          # Referral SQLAlchemy model
│   │   │   │   └── schemas.py
│   │   │   │
│   │   │   ├── mentor/
│   │   │   │   ├── router.py          # /mentors/* endpoints
│   │   │   │   ├── service.py         # MentorAssignmentService, ReputationService
│   │   │   │   ├── timeout_job.py     # APScheduler: check_mentor_timeouts()
│   │   │   │   ├── repository.py      # MentorAssignmentRepository
│   │   │   │   ├── models.py          # MentorAssignment SQLAlchemy model
│   │   │   │   └── schemas.py
│   │   │   │
│   │   │   ├── onboarding/
│   │   │   │   ├── router.py          # /onboarding/* endpoints
│   │   │   │   ├── service.py         # JoiningFormService, NonWorkerIdService
│   │   │   │   ├── ad_service.py      # Microsoft Graph API provisioning
│   │   │   │   ├── validator.py       # Joining form field validations
│   │   │   │   ├── repository.py
│   │   │   │   ├── models.py          # Intern, JoiningForm SQLAlchemy models
│   │   │   │   └── schemas.py
│   │   │   │
│   │   │   ├── ai/
│   │   │   │   ├── router.py          # /ai/* endpoints (chatbot, suggestions)
│   │   │   │   ├── service.py         # AiService — public interface (10 touchpoints)
│   │   │   │   ├── resume_parser.py   # AI-1: Resume Deep Analyzer
│   │   │   │   ├── mentor_matcher.py  # AI-2: Mentor Match Engine
│   │   │   │   ├── risk_profiler.py   # AI-3: Eligibility & Risk Profiler
│   │   │   │   ├── duplicate_detector.py # AI-4: Duplicate Detection
│   │   │   │   ├── bottleneck_predictor.py # AI-5
│   │   │   │   ├── form_assistant.py  # AI-6: Joining Form Assistant
│   │   │   │   ├── compliance_checker.py # AI-7: Pre-Start Compliance
│   │   │   │   ├── cert_generator.py  # AI-8: Certificate Content
│   │   │   │   ├── program_chatbot.py # AI-9: Program Intelligence
│   │   │   │   ├── auto_router.py     # AI-10: Workflow Auto-Router
│   │   │   │   ├── models.py          # AiParseResult SQLAlchemy model
│   │   │   │   └── schemas.py
│   │   │   │
│   │   │   ├── workflow/
│   │   │   │   ├── state_machine.py   # Master FSM — all valid transitions + guards
│   │   │   │   ├── sla_service.py     # SLA clock start/stop/breach detection
│   │   │   │   ├── escalation_service.py # Escalation rules + triggers
│   │   │   │   ├── nda_timeout_job.py # APScheduler: check_nda_timeouts()
│   │   │   │   ├── compliance_job.py  # APScheduler: run_compliance_checks() T-48h
│   │   │   │   ├── sla_breach_job.py  # APScheduler: check_sla_breaches() hourly
│   │   │   │   └── event_handlers.py  # All @event_handler registrations
│   │   │   │
│   │   │   ├── notification/
│   │   │   │   ├── router.py
│   │   │   │   ├── service.py         # NotificationService + GmailApiClient
│   │   │   │   ├── template_renderer.py # Jinja2 template rendering
│   │   │   │   ├── retry_job.py       # APScheduler: retry failed sends
│   │   │   │   ├── event_handlers.py  # Listens to all publishable events
│   │   │   │   ├── models.py          # Notification SQLAlchemy model
│   │   │   │   ├── schemas.py
│   │   │   │   └── templates/         # Jinja2 .html email templates
│   │   │   │       ├── congratulations.html
│   │   │   │       ├── mentor_assignment.html
│   │   │   │       ├── mentor_rejection.html
│   │   │   │       ├── nda_reminder.html
│   │   │   │       ├── nda_final_warning.html
│   │   │   │       ├── auto_reject_candidate.html
│   │   │   │       ├── offer_letter.html
│   │   │   │       ├── closure_reminder.html
│   │   │   │       └── certificate_delivery.html
│   │   │   │
│   │   │   ├── document/
│   │   │   │   ├── router.py          # /documents/* endpoints
│   │   │   │   ├── service.py         # DocumentService, AzureBlobService
│   │   │   │   ├── opensign_client.py # OpenSign REST API client
│   │   │   │   ├── nda_service.py     # NDA lifecycle management
│   │   │   │   ├── pdf_generator.py   # Certificate + offer letter PDF (reportlab)
│   │   │   │   ├── webhook_handler.py # /webhooks/opensign → processes events
│   │   │   │   ├── retention_job.py   # APScheduler: anonymize expired docs
│   │   │   │   ├── models.py          # Document, NdaRecord SQLAlchemy models
│   │   │   │   └── schemas.py
│   │   │   │
│   │   │   └── admin/
│   │   │       ├── router.py          # /admin/* endpoints
│   │   │       ├── dashboard_service.py # Aggregation queries (read replica)
│   │   │       ├── audit_service.py   # Audit trail query + export
│   │   │       ├── sla_report_service.py
│   │   │       ├── config_service.py  # Template + escalation config management
│   │   │       ├── metrics_service.py # AI performance metrics
│   │   │       └── schemas.py
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── database.py            # SQLAlchemy async engine + session factory
│   │   │   ├── event_bus.py           # In-process async event bus implementation
│   │   │   ├── scheduler.py           # APScheduler setup + job registration
│   │   │   ├── redis_client.py        # Azure Cache for Redis client
│   │   │   ├── azure_blob.py          # Blob Storage client + SAS token generation
│   │   │   ├── azure_openai.py        # Azure OpenAI client + retry logic + cost tracking
│   │   │   ├── azure_keyvault.py      # Key Vault secret resolution
│   │   │   ├── gmail_client.py        # Gmail API OAuth2 client
│   │   │   ├── opensign_client.py     # OpenSign REST API base client
│   │   │   └── graph_api_client.py    # Microsoft Graph API AD client
│   │   │
│   │   └── middleware/
│   │       ├── audit.py               # Immutable audit event on every request
│   │       ├── auth.py                # JWT validation + RBAC enforcement
│   │       ├── rate_limit.py          # Redis-backed rate limiting
│   │       ├── error_handler.py       # Global exception → structured error response
│   │       └── logging.py             # Structured JSON → Azure Application Insights
│   │
│   ├── migrations/                    # Alembic migration files
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   │   ├── unit/                      # Per-module unit tests (pytest + pytest-asyncio)
│   │   │   ├── test_referral_validator.py
│   │   │   ├── test_mentor_state_machine.py
│   │   │   ├── test_nda_timeout_logic.py
│   │   │   └── test_ai_duplicate_detection.py
│   │   ├── integration/               # Testcontainers (PostgreSQL + Redis)
│   │   │   ├── test_referral_workflow.py
│   │   │   ├── test_mentor_assignment_flow.py
│   │   │   └── test_nda_auto_rejection.py
│   │   └── conftest.py
│   ├── pyproject.toml                 # Dependencies (uv / poetry)
│   ├── Dockerfile
│   └── alembic.ini
│
├── infrastructure/                    # Azure Infrastructure as Code
│   ├── bicep/
│   │   ├── main.bicep                 # App Service, PostgreSQL, Redis, Blob, OpenAI
│   │   ├── keyvault.bicep
│   │   └── networking.bicep
│   └── scripts/
│       ├── opensign_deploy.sh         # Azure Container Instance for OpenSign
│       └── seed_data.sql              # Initial roles, templates, config
│
├── .github/
│   └── workflows/
│       ├── backend_ci.yml             # pytest + ruff + mypy
│       └── frontend_ci.yml            # vitest + eslint + tsc
│
└── README.md
```

---

## 15. Assumptions & Open Questions

### Confirmed Assumptions

| # | Assumption | Source |
|---|---|---|
| A1 | Organization uses Microsoft Azure AD — SSO via OIDC | Confirmed by user |
| A2 | AD provisioning via Microsoft Graph API (cloud AD) | Inferred from Azure AD SSO choice |
| A3 | Single company deployment — no multi-tenancy | Confirmed by user |
| A4 | 3-person development team | Confirmed by user |
| A5 | Year of study: 2nd, 3rd, 4th only (not 1st, not graduated) | Confirmed by user (RULE-E1) |
| A6 | Max 2 referrals per employee per college | Confirmed by user (RULE-E2) |
| A7 | Mentor max 4 active mentees | Confirmed by user |
| A8 | Mentor timeout: 3 calendar days → auto-reassign (not reject candidate) | Confirmed by user (Option A2) |
| A9 | NDA timeout: Day 5 auto-reject with Day 1/2/3 reminders | Confirmed by user (Option B2) |
| A10 | Azure OpenAI for all AI (GPT-4o) | Confirmed by user ("Azure AI") |
| A11 | OpenSign self-hosted on Azure Container Instance | Confirmed by user |
| A12 | Gmail API (Google Workspace) for email delivery | Confirmed by user |
| A13 | Azure Blob Storage for all file storage | Confirmed by user |

### Open Questions (Require Stakeholder Input Before Build)

| # | Question | Impact |
|---|---|---|
| OQ1 | Who gets notified on auto-rejection — referrer only, or also candidate? | Notification template scope |
| OQ2 | Can a rejected referral be re-submitted by the same referrer in the same cycle? | Duplicate detection logic |
| OQ3 | What defines "business days" for SLA — Mon–Fri only? Are holidays excluded? | SLA calculation accuracy |
| OQ4 | What is the maximum and minimum internship duration allowed? | Date validation rules |
| OQ5 | Can a mentor reassignment happen after MENTOR_ACCEPTED (e.g., mentor falls ill)? | Post-acceptance state machine |
| OQ6 | What is the approved NDA template — does Legal need to upload it before go-live? | OpenSign setup dependency |
| OQ7 | Should the candidate be told WHY their referral was auto-rejected, or only that it was closed? | Notification content policy |
| OQ8 | Can an intern have their end date extended more than once? | Extension state machine |

---

*NexHire System Blueprint v2.0 — Final*
*Stack: React + TypeScript · Python FastAPI · PostgreSQL · Azure OpenAI · Azure AD · Gmail API · OpenSign · Azure Blob*
*Architecture: Modular Monolith · AI Coverage: 75% · Team: 3 engineers*
