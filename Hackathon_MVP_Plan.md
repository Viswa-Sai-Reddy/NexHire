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

## 16. Email Response Capture Architecture

### 16.1 Three-Mechanism Design

| Interaction | Mechanism | Who Owns It |
|---|---|---|
| Mentor Accept / Reject | Email Action Token (button in email → tokenized URL) | NexHire backend |
| Candidate Joining Form | Magic Link → Candidate JWT → Portal | NexHire backend |
| NDA Signing | OpenSign email → OpenSign UI → Webhook back to NexHire | OpenSign |
| Certificate Request | Magic Link → Candidate JWT → Portal | NexHire backend |
| Mentor Confirm Start/End | Email reminder → SSO Portal → S20 Lifecycle Actions | NexHire portal |

### 16.2 Email Action Token — Mentor Accept/Reject

```
Mentor receives assignment email:
┌──────────────────────────────────────────────────────────────────┐
│  You've been assigned as Mentor for Riya Sharma                  │
│  Project: ML Pipeline Optimization · Duration: 8 weeks           │
│                                                                  │
│  [✅ Accept Mentoring]          [❌ Decline Mentoring]           │
│                                                                  │
│  These links expire in 3 days.                                   │
└──────────────────────────────────────────────────────────────────┘

Each button = a unique tokenized URL:
  ACCEPT: https://nexhire.company.com/action/mentor?token=<UUID>&a=ACCEPT
  REJECT: https://nexhire.company.com/action/mentor?token=<UUID>&a=REJECT

Token stored in action_tokens table:
  {
    token_hash:    bcrypt(UUID),     ← stored hashed, raw token only in email
    action_type:   MENTOR_RESPONSE,
    referral_id:   <uuid>,
    actor_user_id: <mentor_user_id>,
    expires_at:    NOW() + 3 days,
    used:          false
  }

ACCEPT flow:
  Mentor clicks Accept → browser opens confirmation page
  GET /action/mentor?token=X&a=ACCEPT
  → Token validated → one-click confirmation → MentorAccepted event published
  → Token marked used = true (replay-proof)
  → Confirmation page: "You have accepted mentoring for Riya Sharma."

REJECT flow:
  Mentor clicks Reject → browser opens mini-form
  GET /action/mentor?token=X&a=REJECT
  → Shows: rejection reason textarea (mandatory) + Submit button
  POST /action/mentor/confirm { token, action: REJECT, reason: "..." }
  → Reason validated not empty → MentorRejected event published
  → Confirmation page: "Your response has been recorded."
```

### 16.3 Magic Link — Candidate Portal Access

```
GET /candidate/access?token=<UUID>

Flow:
  1. Hash raw token (SHA-256) → look up in action_tokens
  2. Validate: not expired, correct action_type
  3. Issue candidate JWT (8h, scoped strictly to their intern_id)
  4. Log: token used_at + ip_address
  5. Redirect based on intern.status:
       APPROVED              → /candidate/joining-form    (S9)
       JOINING_FORM_LOCKED   → /candidate/nda             (S10)
       NDA_SIGNED            → /candidate/status          (S8 — waiting)
       CLOSED                → /candidate/certificate     (cert request)

  Magic link policy: new link per major lifecycle stage
    (joining form, NDA reminder, certificate request each get a fresh link)
```

### 16.4 action_tokens Table

```sql
CREATE TABLE action_tokens (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash   VARCHAR(255) NOT NULL UNIQUE,    -- SHA-256 of raw token
    action_type  VARCHAR(50)  NOT NULL,           -- MENTOR_RESPONSE | CANDIDATE_ACCESS
    referral_id  UUID REFERENCES referrals(id),
    intern_id    UUID REFERENCES interns(id),
    actor_user_id UUID REFERENCES users(id),
    expires_at   TIMESTAMPTZ NOT NULL,
    used         BOOLEAN DEFAULT false,
    used_at      TIMESTAMPTZ,
    ip_address   INET,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Cleanup job: delete expired tokens older than 30 days
```

### 16.5 OpenSign Webhook — NDA Capture

```python
# POST /webhooks/opensign
# Called by OpenSign when candidate signs, declines, or envelope expires

async def handle_opensign_webhook(payload: OpenSignWebhookPayload):
    # Step 1: Verify webhook signature (HMAC-SHA256 shared secret)
    verify_opensign_signature(request.headers, payload)

    # Step 2: Find NDA record by envelope_id
    nda = await nda_repo.get_by_envelope_id(payload.envelope_id)

    match payload.event:
        case "document_signed":
            # Download signed PDF from OpenSign
            signed_pdf = await opensign_client.download_signed(payload.envelope_id)
            # Archive to Azure Blob Storage
            blob_key = await blob_service.upload(signed_pdf, doc_type=DocType.SIGNED_NDA)
            # Update record
            await nda_repo.mark_signed(nda.id, signed_at=payload.signed_at,
                                        document_key=blob_key)
            # Publish event → workflow unblocks
            await event_bus.publish(NdaSigned(intern_id=nda.intern_id))

        case "document_declined":
            await nda_repo.mark_declined(nda.id)
            await event_bus.publish(NdaDeclined(intern_id=nda.intern_id))

        case "envelope_expired":
            # Only if OpenSign expires before our Day-5 job fires
            await nda_repo.mark_expired(nda.id)
            await event_bus.publish(NdaExpired(intern_id=nda.intern_id))
```

---

## 17. Error Handling — Complete System Design

### 17.1 Error Handling Philosophy

NexHire follows four principles for error handling:

```
1. FAIL LOUDLY TO DEVELOPERS    → structured logs + Azure Monitor alerts
2. FAIL GRACEFULLY TO USERS     → friendly messages, never raw stack traces
3. NEVER LOSE STATE             → every operation is recoverable or audited
4. DEGRADE GRACEFULLY           → AI failures don't block core HR workflows
```

Every error in the system falls into one of five categories:

```
┌─────────────────────────────────────────────────────────────────┐
│  ERROR TAXONOMY                                                 │
├──────────────────────┬──────────────────────────────────────────┤
│  VALIDATION_ERROR    │ Input doesn't meet business rules        │
│                      │ HTTP 400 · User fixes input              │
├──────────────────────┼──────────────────────────────────────────┤
│  AUTH_ERROR          │ Identity / permission failure            │
│                      │ HTTP 401/403 · Redirect to login         │
├──────────────────────┼──────────────────────────────────────────┤
│  BUSINESS_RULE_ERROR │ Valid input, but violates a workflow rule │
│                      │ HTTP 422 · User shown specific reason    │
├──────────────────────┼──────────────────────────────────────────┤
│  INTEGRATION_ERROR   │ External service failed (OpenSign, Azure)│
│                      │ HTTP 502/503 · Retry + ops alert         │
├──────────────────────┼──────────────────────────────────────────┤
│  SYSTEM_ERROR        │ Unexpected crash / DB failure            │
│                      │ HTTP 500 · Logged + ops alerted          │
└──────────────────────┴──────────────────────────────────────────┘
```

### 17.2 Standard Error Response Format

Every error from the NexHire API returns the same structured envelope — never a raw Python traceback:

```json
{
  "error": {
    "code": "COLLEGE_CAP_EXCEEDED",
    "category": "BUSINESS_RULE_ERROR",
    "message": "You have already referred 2 students from VIT Vellore. The maximum limit per referrer per college is 2.",
    "details": {
      "college": "VIT Vellore",
      "current_count": 2,
      "max_allowed": 2,
      "referrer_id": "usr_abc123"
    },
    "request_id": "req_7f3a91bc",
    "timestamp": "2025-08-01T10:23:45Z",
    "docs_url": "https://nexhire.internal/docs/errors#COLLEGE_CAP_EXCEEDED"
  }
}
```

**Key fields:**
- `code` — machine-readable, unique error identifier (frontend maps this to UI messages)
- `category` — error type (frontend decides behavior: toast vs modal vs redirect)
- `message` — human-readable, safe to display directly to the user
- `details` — structured context (never includes PII beyond what user already knows)
- `request_id` — correlates with Azure Application Insights trace for debugging
- `docs_url` — internal error reference (helps 3-person dev team debug quickly)

### 17.3 Complete Error Code Registry

#### Validation Errors (HTTP 400)

| Code | Trigger | User Message |
|---|---|---|
| `INVALID_YEAR_OF_STUDY` | year_of_study not in [2,3,4] | "Only 2nd, 3rd, and 4th year students are eligible for this program." |
| `GRADUATED_STUDENT_INELIGIBLE` | graduation_year ≤ current year | "Graduated students are not eligible. This program is for current students only." |
| `MISSING_MANDATORY_FIELD` | Required field empty | "Please complete all required fields before submitting." |
| `INVALID_DATE_RANGE` | start_date ≥ end_date | "Internship end date must be after the start date." |
| `INVALID_START_DATE_PAST` | start_date < today | "Internship start date cannot be in the past." |
| `INVALID_FILE_TYPE` | Upload is not PDF/DOCX/JPG/PNG | "Only PDF, DOCX, JPG, and PNG files are accepted." |
| `FILE_TOO_LARGE` | File > 5MB | "File size exceeds the 5MB limit. Please compress and retry." |
| `INVALID_PHONE_FORMAT` | Phone doesn't match E.164 | "Please enter a valid phone number including country code." |
| `INVALID_EMAIL_FORMAT` | Email format invalid | "Please enter a valid email address." |
| `INVALID_GOVT_ID_FORMAT` | Aadhaar/PAN pattern mismatch | "The government ID format is invalid. Please check and re-enter." |
| `UNPAID_CONSENT_REQUIRED` | unpaid_consent = false | "Candidate must confirm acceptance of unpaid internship terms." |
| `INPERSON_READY_REQUIRED` | inperson_ready = false | "Candidate must confirm in-person availability." |
| `JOINING_FORM_VERSION_CONFLICT` | Optimistic lock version mismatch | "This form was updated elsewhere. Please refresh and re-enter your changes." |

#### Auth Errors (HTTP 401 / 403)

| Code | Trigger | User Message |
|---|---|---|
| `JWT_EXPIRED` | JWT past 8h expiry | "Your session has expired. Please log in again." |
| `JWT_INVALID` | Tampered or malformed token | "Authentication failed. Please log in again." |
| `SSO_TOKEN_INVALID` | Azure AD OIDC token rejected | "Login failed. Please try again or contact IT." |
| `MAGIC_LINK_EXPIRED` | Token past expires_at | "This link has expired. Please request a new access link from HR." |
| `MAGIC_LINK_USED` | Token already used (used = true) | "This link has already been used. Please request a new link." |
| `MAGIC_LINK_INVALID` | Token hash not found in DB | "This link is invalid or has been tampered with." |
| `INSUFFICIENT_PERMISSIONS` | Role lacks required permission | "You don't have permission to perform this action." |
| `ACTION_TOKEN_EXPIRED` | Mentor action link past 3 days | "This response link has expired. A new one has been sent to your email." |
| `ACTION_TOKEN_USED` | Mentor clicked link twice | "You have already submitted your response for this mentoring request." |
| `CANDIDATE_RECORD_MISMATCH` | Candidate JWT internId doesn't match route | "Access denied. This record does not belong to your account." |

#### Business Rule Errors (HTTP 422)

| Code | Trigger | User Message |
|---|---|---|
| `COLLEGE_CAP_EXCEEDED` | Referrer has 2 active referrals from same college | "You've reached the maximum of 2 referrals from [College]. Select a different college." |
| `REFERRER_IS_MENTOR` | referrer_id = mentor_id | "The referrer and mentor cannot be the same person." |
| `MENTOR_AT_CAPACITY` | mentor.active_mentee_count = 4 | "[Mentor Name] currently has 4 active mentees and cannot accept new assignments." |
| `DUPLICATE_CANDIDATE_BLOCKED` | Duplicate score ≥ 0.9 | "A referral for this candidate already exists (Referral #XXXX). Please check existing records." |
| `DUPLICATE_CANDIDATE_WARNING` | Duplicate score 0.6–0.89 | Advisory warning shown — not blocked, HR must confirm |
| `NDA_NOT_SIGNED_BLOCK` | Attempt to mark intern ACTIVE before NDA signed | "Internship cannot begin. The NDA has not been signed yet." |
| `JOINING_FORM_NOT_LOCKED` | Non-Worker ID attempted before form lock | "The joining form must be reviewed and locked by HR before ID creation." |
| `MAX_MENTOR_ATTEMPTS_REACHED` | mentor_attempt_count = 3 and new attempt requested | "Maximum mentor assignment attempts (3) reached. This referral cannot proceed." |
| `REFERRAL_NOT_IN_VALID_STATE` | State machine transition guard fails | "This action cannot be performed. The referral is currently in [STATUS] state." |
| `MENTOR_REJECTION_REASON_MISSING` | Mentor submits rejection without reason | "A reason is required when declining a mentoring assignment." |
| `JOINING_FORM_ALREADY_LOCKED` | Edit attempted after HR lock | "This form has been locked by HR and can no longer be modified." |
| `EXTENSION_AFTER_END_DATE` | Extension requested after actual_end_date | "Extensions must be requested before the internship end date." |
| `NON_WORKER_ID_ALREADY_ISSUED` | Duplicate ID issuance attempt | "A Non-Worker ID has already been issued for this intern." |
| `INTERNSHIP_NOT_ACTIVE` | Closure attempted on non-ACTIVE record | "Only active internships can be closed. Current status: [STATUS]." |

#### Integration Errors (HTTP 502 / 503)

| Code | Service | Behavior |
|---|---|---|
| `AZURE_OPENAI_UNAVAILABLE` | Azure OpenAI | AI features degrade gracefully; form works without prefill |
| `AZURE_OPENAI_RATE_LIMITED` | Azure OpenAI | Exponential backoff (1s, 2s, 4s, 8s); cached result served if available |
| `AZURE_OPENAI_QUOTA_EXCEEDED` | Azure OpenAI | All AI touchpoints switch to manual mode; ops alerted via Azure Monitor |
| `OPENSIGN_UNAVAILABLE` | OpenSign Docker | NDA issuance queued; HR alerted; retry every 1 hour |
| `OPENSIGN_WEBHOOK_INVALID` | OpenSign webhook | Signature validation failed; request rejected; polling fallback activates |
| `GMAIL_API_UNAVAILABLE` | Gmail API | Email queued in notifications table; retry every 15 min; dead-letter at 24h |
| `GMAIL_RATE_LIMITED` | Gmail API | Exponential backoff; queue drains when limit resets |
| `GRAPH_API_UNAVAILABLE` | Microsoft Graph | AD task remains PENDING; IT alerted; retry every 30 min |
| `GRAPH_API_AUTH_FAILED` | Microsoft Graph | App credential refresh attempted; ops alerted if refresh fails |
| `AZURE_BLOB_UNAVAILABLE` | Azure Blob Storage | Upload queued; non-blocking for form submission; retry every 5 min |
| `AZURE_BLOB_UPLOAD_FAILED` | Azure Blob Storage | Upload retried 3x; if all fail, user shown re-upload prompt |
| `REDIS_UNAVAILABLE` | Azure Redis | Rate limiting falls back to in-memory (restart-unsafe); AI cache bypassed |
| `DATABASE_UNAVAILABLE` | PostgreSQL | 503 returned; connection pool retries 3x with 2s backoff |

#### System Errors (HTTP 500)

| Code | Trigger | Behavior |
|---|---|---|
| `UNEXPECTED_ERROR` | Any unhandled exception | Generic user message; full stack trace logged to Application Insights; ops alerted |
| `STATE_MACHINE_VIOLATION` | Code attempted an invalid FSM transition | Full audit log entry; ops alerted; referral status unchanged |
| `AUDIT_LOG_FAILURE` | Audit event could not be written | Request aborted entirely (audit integrity > operation success) |
| `SCHEDULER_JOB_FAILED` | APScheduler job crashed | Job retry after 5 min; max 3 retries; dead-letter logged to Azure Service Bus |
| `EVENT_BUS_FAILURE` | In-process event could not be delivered | Operation rolled back; event logged to outbox for retry |

### 17.4 FastAPI Global Error Handler

```python
# app/middleware/error_handler.py

from fastapi import Request
from fastapi.responses import JSONResponse
from app.shared.exceptions import (
    ValidationError, AuthError, BusinessRuleError,
    IntegrationError, SystemError
)
import uuid
import structlog

logger = structlog.get_logger()

def register_error_handlers(app: FastAPI):

    @app.exception_handler(ValidationError)
    async def handle_validation_error(request: Request, exc: ValidationError):
        request_id = str(uuid.uuid4())
        logger.warning("validation_error",
                        code=exc.code, path=request.url.path,
                        request_id=request_id)
        return JSONResponse(status_code=400, content={
            "error": {
                "code": exc.code,
                "category": "VALIDATION_ERROR",
                "message": exc.user_message,
                "details": exc.details or {},
                "request_id": request_id,
                "timestamp": utcnow().isoformat()
            }
        })

    @app.exception_handler(BusinessRuleError)
    async def handle_business_rule_error(request: Request, exc: BusinessRuleError):
        request_id = str(uuid.uuid4())
        logger.warning("business_rule_violation",
                        code=exc.code, rule=exc.rule_id,
                        entity_id=exc.entity_id, request_id=request_id)
        # Every business rule violation is also an audit event
        await audit_publisher.publish(AuditEvent(
            event_type="BUSINESS_RULE_VIOLATED",
            entity_id=exc.entity_id,
            payload={"code": exc.code, "rule": exc.rule_id}
        ))
        return JSONResponse(status_code=422, content={
            "error": {
                "code": exc.code,
                "category": "BUSINESS_RULE_ERROR",
                "message": exc.user_message,
                "details": exc.details or {},
                "request_id": request_id,
                "timestamp": utcnow().isoformat()
            }
        })

    @app.exception_handler(IntegrationError)
    async def handle_integration_error(request: Request, exc: IntegrationError):
        request_id = str(uuid.uuid4())
        logger.error("integration_error",
                      code=exc.code, service=exc.service,
                      status_code=exc.upstream_status,
                      request_id=request_id, exc_info=exc)
        # Alert ops team via Azure Monitor custom metric
        await metrics.increment("integration_error", tags={"service": exc.service})
        return JSONResponse(status_code=502, content={
            "error": {
                "code": exc.code,
                "category": "INTEGRATION_ERROR",
                "message": f"A third-party service is temporarily unavailable. "
                           f"Your action has been queued and will be retried automatically.",
                "request_id": request_id,
                "timestamp": utcnow().isoformat()
            }
        })

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = str(uuid.uuid4())
        # Full stack trace — NEVER sent to client, only to Application Insights
        logger.exception("unexpected_error",
                          path=request.url.path,
                          method=request.method,
                          request_id=request_id,
                          exc_info=exc)
        await metrics.increment("system_error")
        return JSONResponse(status_code=500, content={
            "error": {
                "code": "UNEXPECTED_ERROR",
                "category": "SYSTEM_ERROR",
                "message": "Something went wrong on our end. "
                           "Our team has been notified. Please try again in a moment.",
                "request_id": request_id,
                "timestamp": utcnow().isoformat()
            }
        })
```

### 17.5 Business Rule Exception Hierarchy

```python
# app/shared/exceptions.py

class NexHireBaseException(Exception):
    """Base for all NexHire exceptions."""
    code: str
    user_message: str
    details: dict = {}

# ── Validation ──────────────────────────────────────────────────────
class ValidationError(NexHireBaseException):
    """Input data violates format or type constraints."""
    pass

class InvalidYearOfStudyError(ValidationError):
    code = "INVALID_YEAR_OF_STUDY"
    user_message = "Only 2nd, 3rd, and 4th year students are eligible."

class InvalidFiletypeError(ValidationError):
    code = "INVALID_FILE_TYPE"
    user_message = "Only PDF, DOCX, JPG, and PNG files are accepted."

# ── Auth ─────────────────────────────────────────────────────────────
class AuthError(NexHireBaseException):
    """Identity or permission failure."""
    pass

class JwtExpiredError(AuthError):
    code = "JWT_EXPIRED"
    user_message = "Your session has expired. Please log in again."

class MagicLinkExpiredError(AuthError):
    code = "MAGIC_LINK_EXPIRED"
    user_message = "This link has expired. Please request a new one from HR."

class InsufficientPermissionsError(AuthError):
    code = "INSUFFICIENT_PERMISSIONS"
    user_message = "You don't have permission to perform this action."

# ── Business Rules ───────────────────────────────────────────────────
class BusinessRuleError(NexHireBaseException):
    """Valid input violates a workflow or domain rule."""
    rule_id: str
    entity_id: str = None

class CollegeCapExceededError(BusinessRuleError):
    code = "COLLEGE_CAP_EXCEEDED"
    rule_id = "RULE-E2"
    def __init__(self, college: str):
        self.user_message = (f"You've reached the maximum of 2 referrals "
                             f"from {college}.")
        self.details = {"college": college, "max_allowed": 2}

class MentorAtCapacityError(BusinessRuleError):
    code = "MENTOR_AT_CAPACITY"
    rule_id = "RULE-M-CAP"
    def __init__(self, mentor_name: str):
        self.user_message = (f"{mentor_name} currently has 4 active mentees "
                             f"and cannot accept new assignments.")
        self.details = {"mentor_name": mentor_name, "max_mentees": 4}

class NdaNotSignedBlockError(BusinessRuleError):
    code = "NDA_NOT_SIGNED_BLOCK"
    rule_id = "RULE-N1"
    user_message = "Internship cannot begin. The NDA has not been signed yet."

class InvalidStateTransitionError(BusinessRuleError):
    code = "REFERRAL_NOT_IN_VALID_STATE"
    rule_id = "FSM-GUARD"
    def __init__(self, current_status: str, attempted_action: str):
        self.user_message = (f"This action cannot be performed. "
                             f"The referral is currently in {current_status} state.")
        self.details = {"current_status": current_status,
                        "attempted_action": attempted_action}

class MaxMentorAttemptsReachedError(BusinessRuleError):
    code = "MAX_MENTOR_ATTEMPTS_REACHED"
    rule_id = "RULE-M3"
    user_message = ("Maximum mentor assignment attempts (3) reached. "
                    "This referral cannot proceed further.")

# ── Integration ──────────────────────────────────────────────────────
class IntegrationError(NexHireBaseException):
    """External service failure."""
    service: str
    upstream_status: int = None
    retryable: bool = True

class AzureOpenAiError(IntegrationError):
    code = "AZURE_OPENAI_UNAVAILABLE"
    service = "azure_openai"
    user_message = "AI features are temporarily unavailable. You can continue manually."

class OpenSignError(IntegrationError):
    code = "OPENSIGN_UNAVAILABLE"
    service = "opensign"
    user_message = "Document signing is temporarily unavailable. It will be sent automatically when restored."

class GmailApiError(IntegrationError):
    code = "GMAIL_API_UNAVAILABLE"
    service = "gmail"
    user_message = "Email delivery is delayed. Your action was saved and notifications will be sent shortly."

class GraphApiError(IntegrationError):
    code = "GRAPH_API_UNAVAILABLE"
    service = "microsoft_graph"
    user_message = "Account provisioning is temporarily unavailable. IT has been notified."

class AzureBlobError(IntegrationError):
    code = "AZURE_BLOB_UNAVAILABLE"
    service = "azure_blob"
    user_message = "File storage is temporarily unavailable. Please retry the upload."
```

### 17.6 AI-Specific Error Handling & Graceful Degradation

```python
# app/modules/ai/service.py

class AiService:
    """
    All AI operations degrade gracefully — AI failure never blocks
    a core HR workflow. Every failure is logged for model monitoring.
    """

    async def parse_resume(self, file_bytes: bytes,
                            mime_type: str) -> ParseResult:
        try:
            result = await self._call_azure_openai_with_retry(
                prompt=RESUME_PARSE_PROMPT,
                file_bytes=file_bytes,
                timeout=15.0
            )
            return ParseResult(success=True, data=result,
                               confidence_scores=result.confidences)

        except asyncio.TimeoutError:
            logger.warning("ai_parse_timeout", touchpoint="RESUME_PARSE")
            await metrics.increment("ai_timeout", tags={"touchpoint": "resume_parse"})
            # Graceful degradation: return empty prefill, form works normally
            return ParseResult(
                success=False,
                degradation_reason="AI_TIMEOUT",
                user_message="Auto-fill is temporarily unavailable. Please fill in the details manually.",
                data={}
            )

        except AzureOpenAiError as e:
            logger.error("ai_unavailable", touchpoint="RESUME_PARSE", exc_info=e)
            return ParseResult(
                success=False,
                degradation_reason="AI_UNAVAILABLE",
                user_message="Auto-fill is temporarily unavailable. Please fill in the details manually.",
                data={}
            )

        except json.JSONDecodeError as e:
            # Model returned malformed JSON
            logger.warning("ai_malformed_output", touchpoint="RESUME_PARSE",
                           raw_output=e.doc[:200])
            await metrics.increment("ai_malformed_output")
            # Retry once with corrected prompt
            return await self._retry_parse_with_correction(file_bytes, mime_type)

    async def _call_azure_openai_with_retry(self, **kwargs) -> dict:
        """Exponential backoff retry for rate limits."""
        delays = [1, 2, 4, 8]
        last_error = None
        for delay in delays:
            try:
                return await self.openai_client.complete(**kwargs)
            except RateLimitError as e:
                last_error = e
                logger.warning("azure_openai_rate_limited", retry_in=delay)
                await asyncio.sleep(delay)
            except QuotaExceededError:
                await metrics.increment("azure_openai_quota_exceeded")
                raise AzureOpenAiError(code="AZURE_OPENAI_QUOTA_EXCEEDED",
                                        service="azure_openai")
        raise last_error

    async def suggest_mentors(self, candidate: Candidate,
                               excluded_ids: list[UUID]) -> list[MentorRecommendation]:
        """
        Mentor suggestions: cached for 1 hour.
        If AI fails, return rule-based suggestions (availability + capacity only).
        """
        cache_key = f"mentor_suggestions:{candidate.id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        try:
            suggestions = await self._generate_mentor_suggestions(
                candidate, excluded_ids)
            await redis.set(cache_key, json.dumps(suggestions), ex=3600)
            return suggestions

        except (AzureOpenAiError, asyncio.TimeoutError):
            logger.warning("ai_mentor_match_fallback", candidate_id=candidate.id)
            # Fallback: rule-based only (no AI narrative, just score)
            return self._rule_based_mentor_ranking(candidate, excluded_ids)
```

### 17.7 Database Error Handling

```python
# app/infrastructure/database.py

class DatabaseErrorHandler:
    """
    Wraps all DB operations with consistent error handling.
    Distinguishes between transient (retry) and permanent (fail-fast) errors.
    """

    RETRYABLE_ERRORS = (
        OperationalError,       # connection issues
        TimeoutError,
        DeadlockDetectedError
    )

    PERMANENT_ERRORS = (
        IntegrityError,         # constraint violations
        DataError,              # bad data type
        UniqueViolation
    )

    async def execute_with_retry(self, operation, max_retries=3):
        for attempt in range(max_retries):
            try:
                async with self.session() as session:
                    async with session.begin():
                        return await operation(session)

            except self.PERMANENT_ERRORS as e:
                # Never retry — map to business error
                raise self._map_integrity_error(e)

            except self.RETRYABLE_ERRORS as e:
                if attempt == max_retries - 1:
                    logger.exception("db_permanent_failure", exc_info=e)
                    raise SystemError(code="DATABASE_UNAVAILABLE",
                                      user_message="A database error occurred. Please try again.")
                wait = 2 ** attempt
                logger.warning("db_transient_error_retry",
                               attempt=attempt + 1, retry_in=wait)
                await asyncio.sleep(wait)

    def _map_integrity_error(self, e: IntegrityError) -> BusinessRuleError:
        """Maps PostgreSQL constraint violations to domain errors."""
        msg = str(e.orig)
        if "idx_referrals_active_candidate" in msg:
            return BusinessRuleError(
                code="DUPLICATE_CANDIDATE_BLOCKED",
                user_message="An active referral already exists for this candidate."
            )
        if "unique constraint" in msg and "non_worker_id" in msg:
            return BusinessRuleError(
                code="NON_WORKER_ID_ALREADY_ISSUED",
                user_message="A Non-Worker ID has already been issued for this intern."
            )
        # Unknown constraint — treat as system error
        logger.error("unmapped_integrity_error", detail=msg)
        raise SystemError(code="UNEXPECTED_ERROR",
                          user_message="A data conflict occurred. Please contact support.")
```

### 17.8 Scheduler Job Error Handling

```python
# app/infrastructure/scheduler.py

class NexHireScheduler:
    """
    All APScheduler jobs wrapped with:
      - Idempotency keys (prevent double execution)
      - Structured error logging
      - Dead-letter to Azure Service Bus after max retries
      - Audit event on every job failure
    """

    def wrap_job(self, job_fn, job_name: str, max_retries: int = 3):
        async def wrapped():
            idempotency_key = f"{job_name}:{utcnow().date()}"

            # Prevent double execution (e.g., after restart)
            if await redis.get(f"job_lock:{idempotency_key}"):
                logger.info("job_skipped_idempotent", job=job_name)
                return

            await redis.set(f"job_lock:{idempotency_key}", "1", ex=3600)

            for attempt in range(max_retries):
                try:
                    await job_fn()
                    logger.info("job_completed", job=job_name, attempt=attempt + 1)
                    return

                except Exception as e:
                    logger.error("job_failed",
                                  job=job_name,
                                  attempt=attempt + 1,
                                  exc_info=e)
                    if attempt == max_retries - 1:
                        # Dead-letter: send to Azure Service Bus for manual review
                        await service_bus.send_dead_letter(
                            queue="scheduler-dead-letter",
                            message={
                                "job": job_name,
                                "failed_at": utcnow().isoformat(),
                                "error": str(e),
                                "attempts": max_retries
                            }
                        )
                        # Audit event for compliance
                        await audit_publisher.publish(AuditEvent(
                            event_type="SCHEDULER_JOB_DEAD_LETTERED",
                            payload={"job": job_name, "error": str(e)}
                        ))
                        # Ops alert
                        await metrics.increment("scheduler_dead_letter",
                                                tags={"job": job_name})
                    else:
                        await asyncio.sleep(5 * (attempt + 1))
        return wrapped

# Job registrations
scheduler.add_job(
    wrap_job(check_mentor_timeouts, "check_mentor_timeouts"),
    trigger="interval", hours=1, id="mentor_timeout"
)
scheduler.add_job(
    wrap_job(check_nda_timeouts, "check_nda_timeouts"),
    trigger="interval", hours=6, id="nda_timeout"
)
scheduler.add_job(
    wrap_job(check_sla_breaches, "check_sla_breaches"),
    trigger="interval", hours=1, id="sla_breach"
)
scheduler.add_job(
    wrap_job(run_compliance_checks, "run_compliance_checks"),
    trigger="interval", hours=6, id="compliance_check"
)
```

### 17.9 Event Bus Error Handling

```python
# app/infrastructure/event_bus.py

class InProcessEventBus:
    """
    In-process async event bus with:
      - Guaranteed delivery within the same request transaction
      - Failed handler isolation (one handler failure doesn't affect others)
      - Outbox pattern for cross-transaction events
    """

    async def publish(self, event: DomainEvent):
        handlers = self._handlers.get(type(event), [])
        errors = []

        for handler in handlers:
            try:
                await handler.handle(event)
            except Exception as e:
                # One handler failing does NOT stop other handlers
                logger.error("event_handler_failed",
                              event_type=type(event).__name__,
                              handler=type(handler).__name__,
                              exc_info=e)
                errors.append((handler, e))
                # Store in outbox for retry
                await self.outbox.store(event, handler, str(e))

        if errors:
            await metrics.increment("event_handler_failures",
                                    count=len(errors))
            # Non-fatal: operation succeeded, handlers will retry via outbox

    async def process_outbox(self):
        """Runs every 2 minutes — retries failed event deliveries."""
        failed_events = await self.outbox.get_pending(limit=50)
        for item in failed_events:
            try:
                handler = self._resolve_handler(item.handler_class)
                await handler.handle(item.event)
                await self.outbox.mark_processed(item.id)
            except Exception as e:
                await self.outbox.increment_retry(item.id)
                if item.retry_count >= 5:
                    await self.outbox.dead_letter(item.id, str(e))
                    logger.error("event_dead_lettered",
                                  event=item.event_type,
                                  handler=item.handler_class)
```

### 17.10 Frontend Error Handling Strategy

```typescript
// frontend/src/lib/axios.ts

// Global Axios interceptor — handles all API error responses consistently

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<NexHireErrorResponse>) => {
    const err = error.response?.data?.error;

    if (!err) {
      // Network error — no response received
      toast.error("Connection lost. Please check your network and retry.");
      return Promise.reject(error);
    }

    switch (err.category) {

      case "AUTH_ERROR":
        if (err.code === "JWT_EXPIRED") {
          // Attempt silent token refresh
          const refreshed = await attemptTokenRefresh();
          if (refreshed) return api.request(error.config!);
          // Refresh failed → redirect to login
          window.location.href = "/auth/login";
        } else if (err.code === "MAGIC_LINK_EXPIRED") {
          // Show full-page error (not toast) with request-new-link CTA
          navigate("/candidate/link-expired");
        } else if (err.code === "INSUFFICIENT_PERMISSIONS") {
          toast.error("You don't have permission to do this.");
        }
        break;

      case "VALIDATION_ERROR":
        // These are typically caught at form level before API call
        // But if they reach here, show inline
        toast.error(err.message);
        break;

      case "BUSINESS_RULE_ERROR":
        // Show in a modal with full context (not just a toast)
        showBusinessRuleModal({
          code: err.code,
          message: err.message,
          details: err.details
        });
        break;

      case "INTEGRATION_ERROR":
        // Reassuring message — action was saved, will retry
        toast.warning(err.message, { duration: 6000 });
        break;

      case "SYSTEM_ERROR":
        // Show request_id so user can report to IT
        showSystemErrorModal({
          message: err.message,
          requestId: err.request_id
        });
        break;
    }

    return Promise.reject(error);
  }
);
```

### 17.11 React Error Boundary (Catches Render Crashes)

```tsx
// frontend/src/app/ErrorBoundary.tsx

class NexHireErrorBoundary extends React.Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Report to Azure Application Insights
    appInsights.trackException({
      exception: error,
      properties: { componentStack: info.componentStack }
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen gap-4">
          <h1 className="text-2xl font-semibold text-gray-800">
            Something went wrong
          </h1>
          <p className="text-gray-500">
            This page encountered an error. Our team has been notified.
          </p>
          <Button onClick={() => window.location.reload()}>
            Reload Page
          </Button>
          <Button variant="ghost" onClick={() => window.location.href = "/"}>
            Go to Dashboard
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Wrap every route
<NexHireErrorBoundary>
  <RouterProvider router={router} />
</NexHireErrorBoundary>
```

### 17.12 Audit Integrity Error Handling

```python
# The audit log is the most critical subsystem.
# If an audit event cannot be written, the operation itself is aborted.

class AuditPublisher:
    async def publish(self, event: AuditEvent):
        try:
            # Compute checksum chain
            last = await self.repo.get_last_checksum()
            checksum = sha256(f"{last.checksum}{event.payload_json}".encode()).hexdigest()

            await self.repo.insert(event, checksum=checksum)

        except Exception as e:
            # Audit failure is FATAL — we cannot let operations proceed
            # without an audit trail (legal and compliance requirement)
            logger.critical("AUDIT_LOG_FAILURE",
                             event_type=event.event_type,
                             exc_info=e)
            await metrics.increment("audit_log_failure")
            # Ops paged immediately via Azure Monitor alert
            raise SystemError(
                code="AUDIT_LOG_FAILURE",
                user_message="A critical system error occurred. "
                             "Your action could not be completed. "
                             "Please contact the system administrator immediately."
            )
```

### 17.13 Error Monitoring & Alerting (Azure Monitor Rules)

| Alert | Condition | Severity | Notification |
|---|---|---|---|
| Audit log failure | `audit_log_failure` count > 0 | Critical (P0) | Page on-call immediately |
| Scheduler dead letter | `scheduler_dead_letter` count > 0 | High (P1) | Email ops team |
| Azure OpenAI quota exceeded | `azure_openai_quota_exceeded` count > 0 | High (P1) | Email + Slack ops |
| Integration error spike | Any integration error > 10 in 5 min | Medium (P2) | Email ops team |
| System error rate > 1% | `system_error` / total_requests > 0.01 | High (P1) | Email ops team |
| AI override rate > 20% | Weekly batch metric | Medium (P2) | Email Program Owner |
| Email bounce rate > 1% | `email_bounce` / `email_sent` > 0.01 | Low (P3) | Weekly report |
| SLA breach | Any task past `sla_deadline` | Medium (P2) | Auto-escalation (in-app + email) |
| Magic link abuse | >5 invalid token attempts from same IP | High (P1) | Block IP + alert security |

### 17.14 Error Handling Coverage Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│  ERROR HANDLING COVERAGE MAP                                        │
├──────────────────────────────────────┬──────────────────────────────┤
│  Layer                               │  Mechanism                   │
├──────────────────────────────────────┼──────────────────────────────┤
│  Frontend form validation            │ React Hook Form + Zod schemas│
│  API input validation                │ Pydantic v2 models           │
│  Business rule enforcement           │ Service layer + exception    │
│  State machine violations            │ FSM guard + exception        │
│  Database constraint violations      │ Mapped to domain exceptions  │
│  AI failures                         │ Graceful degradation + retry │
│  Integration failures                │ Circuit breaker + queue      │
│  Scheduler job failures              │ Retry + dead-letter + alert  │
│  Event bus failures                  │ Outbox pattern + retry       │
│  Audit log failures                  │ Fatal abort + P0 alert       │
│  Token replay attacks                │ Single-use + hash validation │
│  React render crashes                │ Error boundary + AI insights │
│  Unhandled exceptions                │ Global handler + P1 alert    │
│  Network errors (frontend)           │ Axios interceptor + toast    │
└──────────────────────────────────────┴──────────────────────────────┘
```

---

*NexHire System Blueprint v2.1 — Error Handling & Email Capture Added*
*Stack: React + TypeScript · Python FastAPI · PostgreSQL · Azure OpenAI · Azure AD · Gmail API · OpenSign · Azure Blob*
*Architecture: Modular Monolith · AI Coverage: 75% · Team: 3 engineers*

---

## 18. AI Automation Upgrades — HR Work Reduction

> **Design Principle:** AI handles detection, validation, and execution for clean cases.
> HR handles authorization only for borderline or flagged cases.
> Every AI auto-decision is logged, auditable, and HR-recallable within a defined window.

### 18.1 Revised Human vs AI Split

```
┌─────────────────────────────────────────────────────────────────────┐
│  NEXHIRE AI COVERAGE — REVISED                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  AI-Driven (fully automated, no human needed)     ████████  52%    │
│  • Eligibility checks                                               │
│  • PAN-based duplicate detection (hard block)                       │
│  • Fuzzy duplicate detection (soft block)                           │
│  • Referral auto-approval (clean cases)                             │
│  • Joining form auto-lock (clean cases)                             │
│  • Non-Worker ID auto-generation (from PAN)                         │
│  • SLA breach prediction + auto-escalation                          │
│  • Pre-start compliance check + auto-escalation                     │
│  • Offer letter auto-send (standard template)                       │
│  • Certificate auto-generate + auto-send                            │
│  • Workflow auto-routing                                             │
│  • College cap enforcement                                           │
│                                                                     │
│  AI-Assisted (AI decides, human reviews borderline) ██████  33%    │
│  • Resume deep analysis (HR sees flagged referrals only)            │
│  • Joining form validation (HR sees flagged forms only)             │
│  • Mentor matching (AI suggests, human picks)                       │
│  • All communication drafts                                          │
│  • Risk profiling                                                    │
│  • Certificate citation generation                                   │
│                                                                     │
│  Human-Only (genuine judgment, accountability)     ████    15%     │
│  • Borderline referral approval (flagged cases)                     │
│  • Borderline joining form lock (flagged cases)                     │
│  • Mentor accept/reject (personal responsibility)                   │
│  • Non-Worker ID: HR still confirms in external system              │
│    (NexHire generates ID; HR submits to HR identity system)         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  🤖 Total AI Coverage:   85%  (up from 75%)                        │
│  👤 Total Human Work:    15%  (down from 25%)                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 18.2 PAN Card — System-Wide Integration

#### 18.2.1 Where PAN is Captured

```
REFERRAL FORM — Step 1: Candidate Basics (NEW FIELD)
  Field: PAN Card Number
  Format validation: regex [A-Z]{5}[0-9]{4}[A-Z]{1}
  Example: ABCDE1234F
  Mandatory: YES
  Stored: referrals.candidate_pan (encrypted at rest — AES-256)
  Display: masked after save — "ABCDE****F" (first 5 + last 1 only)

JOINING FORM — Section 4: Government IDs (EXISTING FIELD — now linked)
  Same PAN field
  Cross-validated against referral form PAN
  IF mismatch → HIGH SEVERITY flag → HR review required
  Upload: PAN card photo/scan (Azure Document Intelligence reads it)
```

#### 18.2.2 PAN-Based Duplicate Detection

```python
# app/modules/ai/duplicate_detector.py

async def detect_duplicate_pan(pan_number: str) -> DuplicateResult:
    """
    PAN is a government-issued unique identifier.
    Any PAN match is a certain duplicate — no fuzzy logic needed.
    """
    normalized_pan = pan_number.strip().upper()

    # Validate PAN format first
    if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', normalized_pan):
        raise ValidationError(
            code="INVALID_PAN_FORMAT",
            user_message="PAN card number format is invalid. "
                         "Expected format: ABCDE1234F"
        )

    # Query all non-terminal referrals
    existing = await db.query("""
        SELECT id, candidate_name, candidate_pan,
               status, created_at, submitted_at
        FROM referrals
        WHERE candidate_pan = :pan
        AND status NOT IN ('HR_REJECTED', 'CANDIDATE_REJECTED',
                           'NDA_TIMEOUT_REJECTED', 'NDA_DECLINED_REJECTED')
    """, pan=encrypt(normalized_pan))

    if existing:
        return DuplicateResult(
            is_duplicate=True,
            match_id=existing.id,
            match_type="PAN_EXACT",
            similarity_score=1.0,           # 100% certain
            match_reason="PAN card number exact match",
            recommendation="HARD_BLOCK",    # No override allowed
            existing_status=existing.status,
            existing_referral_ref=existing.id
        )

    # No PAN match — run fuzzy fallback
    return await detect_duplicate_fuzzy(pan_number=pan_number)


async def detect_duplicate_fuzzy(pan_number: str, ...) -> DuplicateResult:
    """Existing fuzzy matching — email + phone + name."""
    # ... existing algorithm unchanged
    # Only runs if PAN check passes (no PAN match found)
```

**UI Behavior on PAN match:**
```
┌──────────────────────────────────────────────────────────────────────┐
│  ⛔ HARD BLOCK — Duplicate PAN Detected                             │
│                                                                      │
│  PAN ABCDE1234F is already linked to an active referral:            │
│  Riya Sharma — Referral #2025-0142 (Status: ACTIVE)                │
│                                                                      │
│  PAN cards are unique government identifiers.                       │
│  This candidate cannot be referred again while the previous         │
│  referral is active.                                                 │
│                                                                      │
│  [View Existing Referral]    [Cancel This Submission]               │
│                                                                      │
│  Note: Override is not available for PAN duplicates.                │
└──────────────────────────────────────────────────────────────────────┘
```

#### 18.2.3 PAN-Based Non-Worker ID Generation

```python
# app/modules/ai/non_worker_id_generator.py

class NonWorkerIdGenerator:
    """
    Generates deterministic, unique Non-Worker IDs from PAN number.
    No LLM needed — pure deterministic function.
    """

    ID_PREFIX = "NW"

    def generate(self, pan_number: str, joining_year: int) -> str:
        """
        Format: NW-{PAN}-{YEAR}
        Example: NW-ABCDE1234F-2025

        Properties:
          - Globally unique (PAN is unique per person in India)
          - Year-scoped (same person, different year = different ID)
          - Traceable (PAN embedded, HR can reverse-lookup)
          - Deterministic (same input = same output always)
        """
        pan_normalized = pan_number.strip().upper()

        # Validate PAN format
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan_normalized):
            raise ValidationError(
                code="INVALID_PAN_FORMAT",
                user_message="Cannot generate Non-Worker ID: PAN format is invalid."
            )

        non_worker_id = f"{self.ID_PREFIX}-{pan_normalized}-{joining_year}"

        # Uniqueness check (edge case: same person, same year, different referral)
        existing = db.query(
            "SELECT id FROM interns WHERE non_worker_id = :id",
            id=non_worker_id
        )
        if existing:
            # Append sequence suffix: NW-ABCDE1234F-2025-2
            sequence = db.query(
                "SELECT COUNT(*) FROM interns WHERE non_worker_id LIKE :pattern",
                pattern=f"{non_worker_id}%"
            )
            non_worker_id = f"{non_worker_id}-{sequence + 1}"

        return non_worker_id

    async def generate_and_assign(self, intern_id: UUID,
                                   pan_number: str,
                                   joining_year: int) -> str:
        """
        Full flow: generate ID → validate uniqueness → store → publish event.
        Triggered automatically on JoiningFormLocked event.
        """
        non_worker_id = self.generate(pan_number, joining_year)

        # Store
        await intern_repo.update(intern_id, non_worker_id=non_worker_id)

        # Audit log
        await audit_publisher.publish(AuditEvent(
            event_type="NON_WORKER_ID_AUTO_GENERATED",
            entity_type="INTERN",
            entity_id=intern_id,
            payload={
                "non_worker_id": non_worker_id,
                "generated_from": "PAN_NUMBER",
                "pan_masked": f"{pan_number[:5]}****{pan_number[-1]}",
                "joining_year": joining_year,
                "generated_at": utcnow().isoformat()
            }
        ))

        # Publish event → workflow continues
        await event_bus.publish(NonWorkerIdAutoGenerated(
            intern_id=intern_id,
            non_worker_id=non_worker_id
        ))

        return non_worker_id
```

**Trigger point:**
```python
# app/modules/workflow/event_handlers.py

@event_handler(JoiningFormLocked)
async def on_joining_form_locked(event: JoiningFormLocked):
    """
    BEFORE: Created task for HR to manually create Non-Worker ID
    AFTER:  AI generates it immediately — no HR task needed
    """
    intern = await intern_repo.get_by_referral(event.referral_id)
    pan    = await referral_repo.get_pan(event.referral_id)  # decrypted

    # Auto-generate Non-Worker ID immediately
    non_worker_id = await non_worker_id_generator.generate_and_assign(
        intern_id=intern.id,
        pan_number=pan,
        joining_year=intern.actual_start_date.year
    )

    # No HR task created — workflow continues automatically
    logger.info("non_worker_id_auto_generated",
                intern_id=intern.id,
                non_worker_id=non_worker_id)
```

### 18.3 AI Auto-Approval Engine (Referral Review)

```python
# app/modules/ai/auto_approval_engine.py

class ReferralAutoApprovalEngine:
    """
    Evaluates referrals against clean-case criteria.
    Clean cases: auto-approved, no HR involvement.
    Borderline cases: routed to HR with AI recommendation pre-filled.
    """

    # Thresholds for auto-approval
    THRESHOLDS = {
        "max_duplicate_score":         0.0,    # PAN must be clear (0 = no fuzzy match)
        "max_risk_score":              25,     # Low risk only
        "min_ai_parse_confidence":     0.82,   # High confidence parse
        "required_field_completeness": 1.0,    # All mandatory fields present
        "max_fuzzy_duplicate_score":   0.59,   # Below warn threshold
    }

    async def evaluate(self, referral_id: UUID) -> AutoApprovalResult:
        referral    = await referral_repo.get(referral_id)
        ai_parse    = await ai_parse_repo.get_by_referral(referral_id)
        risk        = await risk_repo.get_by_referral(referral_id)
        dup_check   = ai_parse.duplicate_check

        flags = []

        # CHECK 1: PAN duplicate (hard block — cannot auto-approve)
        if dup_check.get("match_type") == "PAN_EXACT":
            return AutoApprovalResult(
                decision="HARD_BLOCK",
                reason="PAN_DUPLICATE",
                route_to_hr=True,
                hr_recommendation="REJECT",
                flags=["Definite duplicate — same PAN card"]
            )

        # CHECK 2: Fuzzy duplicate score
        if dup_check.get("similarity_score", 0) > self.THRESHOLDS["max_fuzzy_duplicate_score"]:
            flags.append(f"Possible duplicate (score: {dup_check['similarity_score']:.0%})")

        # CHECK 3: Risk score
        if risk.risk_score > self.THRESHOLDS["max_risk_score"]:
            flags.append(f"Risk score {risk.risk_score} exceeds threshold (25)")

        # CHECK 4: AI parse confidence
        low_confidence_fields = [
            field for field, score
            in ai_parse.confidence_scores.items()
            if score < self.THRESHOLDS["min_ai_parse_confidence"]
        ]
        if low_confidence_fields:
            flags.append(f"Low confidence on: {', '.join(low_confidence_fields)}")

        # CHECK 5: Field completeness
        missing = referral_validator.get_missing_mandatory_fields(referral)
        if missing:
            flags.append(f"Missing fields: {', '.join(missing)}")

        # CHECK 6: Red flags from AI resume analysis
        if ai_parse.raw_output.get("red_flags"):
            flags.extend(ai_parse.raw_output["red_flags"])

        # DECISION
        if not flags:
            # ✅ CLEAN CASE — Auto-approve
            return AutoApprovalResult(
                decision="AUTO_APPROVE",
                route_to_hr=False,
                auto_approved_at=utcnow(),
                conditions_met=[
                    "No duplicate detected",
                    "Risk score within threshold",
                    "High confidence parse",
                    "All mandatory fields present",
                    "No red flags"
                ]
            )
        else:
            # ⚠️ BORDERLINE — Route to HR with recommendation
            hr_recommendation = self._compute_hr_recommendation(flags, risk, dup_check)
            return AutoApprovalResult(
                decision="ROUTE_TO_HR",
                route_to_hr=True,
                flags=flags,
                hr_recommendation=hr_recommendation,
                ai_summary=await self._generate_hr_summary(referral, flags,
                                                             hr_recommendation)
            )

    def _compute_hr_recommendation(self, flags, risk, dup_check) -> str:
        """AI pre-fills what it would recommend HR to do."""
        if dup_check.get("similarity_score", 0) > 0.85:
            return "LIKELY_REJECT"
        if risk.risk_score > 40:
            return "REVIEW_CAREFULLY"
        if len(flags) == 1 and "Low confidence" in flags[0]:
            return "LIKELY_APPROVE"
        return "REQUIRES_REVIEW"
```

**HR Dashboard experience (borderline only):**
```
┌──────────────────────────────────────────────────────────────────────┐
│  📋 Referrals Requiring Your Review  (3 of 18 total)                │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  ✅ 15 referrals auto-approved by AI — no action needed             │
│                                                                      │
│  ⚠️  Riya Sharma         AI Recommendation: LIKELY_APPROVE          │
│      Flag: Low confidence on phone field (74%)                      │
│      [Review]                                                        │
│                                                                      │
│  ⚠️  Karan Patel         AI Recommendation: REVIEW_CAREFULLY        │
│      Flags: Risk score 38, college 280km from office                │
│      [Review]                                                        │
│                                                                      │
│  🚨 Priya Nair           AI Recommendation: LIKELY_REJECT           │
│      Flag: Possible duplicate — 87% match with #2024-0142           │
│      [Review]                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 18.4 AI Auto-Lock Engine (Joining Form)

```python
# app/modules/ai/form_auto_lock_engine.py

class JoiningFormAutoLockEngine:
    """
    Validates joining form cross-field consistency using AI document verification.
    Clean forms: auto-locked immediately.
    Flagged forms: routed to HR with specific issues highlighted.
    """

    async def evaluate(self, intern_id: UUID) -> FormLockResult:
        form       = await joining_form_repo.get_by_intern(intern_id)
        referral   = await referral_repo.get_by_intern(intern_id)
        documents  = await document_repo.get_by_intern(intern_id)

        flags = []
        severity = "NONE"

        # VALIDATION 1: Name consistency
        name_on_referral = normalize_name(referral.candidate_name)
        name_on_form     = normalize_name(form.personal_details["full_name"])
        name_on_id       = await self._extract_name_from_id(documents)

        name_sim_referral = jaro_winkler(name_on_referral, name_on_form)
        name_sim_id       = jaro_winkler(name_on_form, name_on_id) if name_on_id else 1.0

        if name_sim_referral < 0.85 or name_sim_id < 0.85:
            flags.append(FormFlag(
                field="full_name",
                severity="HIGH",
                message=f"Name mismatch: referral='{referral.candidate_name}', "
                        f"form='{form.personal_details['full_name']}', "
                        f"ID='{name_on_id}'"
            ))

        # VALIDATION 2: PAN consistency
        pan_on_referral = referral.candidate_pan
        pan_on_form     = form.govt_ids.get("pan_number", "")
        pan_on_id       = await self._extract_pan_from_id_doc(documents)

        if pan_on_referral != pan_on_form:
            flags.append(FormFlag(
                field="pan_number",
                severity="HIGH",
                message="PAN number in joining form differs from referral form."
            ))

        if pan_on_id and pan_on_id != pan_on_form:
            flags.append(FormFlag(
                field="pan_number",
                severity="HIGH",
                message="PAN number on uploaded ID card differs from entered PAN."
            ))

        # VALIDATION 3: DOB consistency
        dob_form = form.personal_details.get("date_of_birth")
        dob_id   = await self._extract_dob_from_id(documents)
        if dob_id and dob_form != dob_id:
            flags.append(FormFlag(
                field="date_of_birth",
                severity="HIGH",
                message=f"DOB mismatch: form={dob_form}, ID document={dob_id}"
            ))

        # VALIDATION 4: Completeness
        missing = self._check_mandatory_fields(form)
        for field in missing:
            flags.append(FormFlag(field=field, severity="HIGH",
                                   message=f"Mandatory field missing: {field}"))

        # VALIDATION 5: Education certificate vs form
        cert_institution = await self._extract_institution_from_cert(documents)
        form_institution = form.education_history[0].get("institution", "") \
                           if form.education_history else ""
        if cert_institution:
            sim = jaro_winkler(normalize(cert_institution),
                               normalize(form_institution))
            if sim < 0.75:
                flags.append(FormFlag(
                    field="education_history",
                    severity="LOW",
                    message=f"Institution name slightly differs: "
                            f"form='{form_institution}', cert='{cert_institution}'"
                ))

        # DECISION
        high_flags = [f for f in flags if f.severity == "HIGH"]
        low_flags  = [f for f in flags if f.severity == "LOW"]

        if not high_flags:
            if not low_flags:
                # ✅ CLEAN — Auto-lock
                return FormLockResult(
                    decision="AUTO_LOCK",
                    route_to_hr=False,
                    locked_by="AI_AUTO_LOCK",
                    locked_at=utcnow()
                )
            else:
                # Minor issues only — auto-lock with notes
                return FormLockResult(
                    decision="AUTO_LOCK_WITH_NOTES",
                    route_to_hr=False,
                    low_flags=low_flags,
                    locked_by="AI_AUTO_LOCK",
                    locked_at=utcnow(),
                    note="Minor inconsistencies noted but not blocking."
                )
        else:
            # ❌ HIGH severity — route to HR
            return FormLockResult(
                decision="ROUTE_TO_HR",
                route_to_hr=True,
                high_flags=high_flags,
                low_flags=low_flags,
                hr_summary=await self._generate_hr_summary(high_flags)
            )
```

### 18.5 AI Auto-Send: Offer Letter & Certificate

```python
# app/modules/ai/auto_send_engine.py

class OfferLetterAutoSendEngine:
    """Auto-sends offer letter if standard template applies."""

    RECALL_WINDOW_MINUTES = 30

    async def evaluate_and_send(self, intern_id: UUID):
        intern   = await intern_repo.get(intern_id)
        letter   = await document_repo.get_offer_letter(intern_id)
        referral = await referral_repo.get_by_intern(intern_id)

        # Check: is this a standard case?
        is_standard = (
            letter.generated_from_template == True and
            letter.custom_edits_count == 0 and
            all([
                intern.non_worker_id,
                intern.actual_start_date,
                referral.mentor_id,
                referral.project_title
            ])
        )

        if is_standard:
            # Auto-send
            await notification_service.send(
                template_id="NOTIF_010_OFFER_LETTER",
                recipient=referral.candidate_email,
                attachments=[letter.blob_key]
            )

            # HR gets FYI (not action required)
            await notification_service.send(
                template_id="NOTIF_011_OFFER_LETTER_FYI_HR",
                recipient=assigned_hr.email,
                context={
                    "candidate_name": referral.candidate_name,
                    "sent_at": utcnow(),
                    "recall_until": utcnow() + timedelta(minutes=self.RECALL_WINDOW_MINUTES),
                    "recall_link": generate_recall_token(intern_id, "OFFER_LETTER")
                }
            )

            await audit_publisher.publish(AuditEvent(
                event_type="OFFER_LETTER_AUTO_SENT",
                payload={"intern_id": intern_id, "sent_by": "AI_AUTO_SEND"}
            ))
        else:
            # Non-standard → route to HR
            await self._route_to_hr(intern_id, reason="custom_template_used")


class CertificateAutoSendEngine:
    """Auto-generates and sends certificate for clean closures."""

    RECALL_WINDOW_HOURS = 48

    async def evaluate_and_send(self, intern_id: UUID):
        intern   = await intern_repo.get(intern_id)
        referral = await referral_repo.get_by_intern(intern_id)

        is_clean_closure = (
            intern.status == InternStatus.CLOSURE_PENDING and
            referral.status != ReferralStatus.TERMINATED and
            intern.mentor_confirmed_completion == True
        )

        if is_clean_closure:
            # AI-8 generates certificate content
            citation = await ai_service.generate_certificate(intern_id)

            if citation.confidence >= 0.85:
                # Generate PDF on letterhead
                pdf_key = await certificate_generator.generate(intern_id, citation)

                # Send to candidate
                await notification_service.send(
                    template_id="NOTIF_007_CERTIFICATE_DELIVERY",
                    recipient=referral.candidate_email,
                    attachments=[pdf_key]
                )

                # HR gets FYI + recall option
                await notification_service.send(
                    template_id="NOTIF_012_CERT_AUTO_SENT_FYI",
                    recipient=assigned_hr.email,
                    context={
                        "recall_until": utcnow() + timedelta(hours=self.RECALL_WINDOW_HOURS),
                        "recall_link": generate_recall_token(intern_id, "CERTIFICATE")
                    }
                )

                await audit_publisher.publish(AuditEvent(
                    event_type="CERTIFICATE_AUTO_SENT",
                    payload={"intern_id": intern_id, "sent_by": "AI_AUTO_SEND",
                             "citation_confidence": citation.confidence}
                ))
            else:
                # Low confidence citation → HR reviews
                await self._route_to_hr(intern_id, reason="low_citation_confidence")
        else:
            # Terminated or disputed → HR handles
            await self._route_to_hr(intern_id, reason="non_standard_closure")
```

### 18.6 Recall Mechanism (HR Safety Net)

Every auto-action has a recall window where HR can undo it:

```
AUTO-APPROVE recall:   2 hours     → HR can revert to PENDING_REVIEW
AUTO-LOCK recall:      1 hour      → HR can unlock and flag for review
OFFER LETTER recall:   30 minutes  → HR can retract (candidate gets "disregard" email)
CERTIFICATE recall:    48 hours    → HR can invalidate (candidate notified)

Recall is available via:
  1. Email link in HR's FYI notification
  2. S11 HR Dashboard → "Recent AI Actions" panel → [Recall] button

After recall window closes:
  Action is permanent
  Audit event: AI_ACTION_RECALL_WINDOW_CLOSED logged
```

### 18.7 Updated Data Schema — PAN Card

```sql
-- Add PAN to referrals table
ALTER TABLE referrals
  ADD COLUMN candidate_pan VARCHAR(255),     -- encrypted AES-256
  ADD COLUMN candidate_pan_masked VARCHAR(20); -- "ABCDE****F" for display

-- Unique constraint on PAN for active referrals
CREATE UNIQUE INDEX idx_referrals_active_pan
  ON referrals(candidate_pan)
  WHERE status NOT IN (
    'HR_REJECTED', 'CANDIDATE_REJECTED',
    'NDA_TIMEOUT_REJECTED', 'NDA_DECLINED_REJECTED', 'TERMINATED'
  );

-- AI auto-action log
CREATE TABLE ai_auto_actions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  intern_id        UUID REFERENCES interns(id),
  referral_id      UUID REFERENCES referrals(id),
  action_type      VARCHAR(50) NOT NULL,  -- AUTO_APPROVE, AUTO_LOCK,
                                          --   AUTO_SEND_OFFER, AUTO_SEND_CERT,
                                          --   AUTO_GENERATE_NW_ID
  decision         VARCHAR(50) NOT NULL,  -- EXECUTED, ROUTED_TO_HR
  conditions_met   JSONB,                 -- what passed
  flags            JSONB,                 -- what was flagged (if routed)
  hr_recommendation VARCHAR(50),          -- LIKELY_APPROVE, LIKELY_REJECT, etc.
  executed_at      TIMESTAMPTZ DEFAULT NOW(),
  recalled_at      TIMESTAMPTZ,           -- if HR recalled
  recalled_by      UUID REFERENCES users(id),
  recall_reason    TEXT
);
```

### 18.8 Updated Referral Form — PAN Field

```
REFERRAL FORM — Step 1: Candidate Basics (UPDATED)

Fields:
  1. Upload Resume (existing — AI-1 fires)
  2. Candidate Full Name (AI prefilled)
  3. Candidate Email (AI prefilled)
  4. Candidate Phone (AI prefilled)
  5. [NEW] PAN Card Number
       - Input: text field with mask (shows as typed, stored encrypted)
       - Validation: real-time regex [A-Z]{5}[0-9]{4}[A-Z]{1}
       - On valid PAN entered: duplicate check fires immediately (not on submit)
         Response within 1 second:
           CLEAR  → green tick shown
           MATCH  → red banner: "HARD BLOCK — PAN already in system"
       - Stored as: encrypted (AES-256), displayed masked after save
  6. Year of Study (existing — RULE-E1 fires)
  7. College Name (existing — RULE-E2 fires)
  8. Graduation Year (existing)
```

### 18.9 Revised Master Workflow — AI-Automated Steps

```
OLD STEP → NEW STEP

Step 5  (HR reviews referral)
  OLD: HR reviews ALL referrals → approve/reject
  NEW: AI evaluates ALL referrals
       Clean (no flags) → AUTO-APPROVED instantly
       Flagged → routed to HR with pre-filled recommendation
       HR sees only ~15–20% of referrals

Step 7  (Joining form — HR locks)
  OLD: HR reviews ALL forms → clicks Lock
  NEW: AI validates ALL forms (name, PAN, DOB, docs cross-check)
       Clean → AUTO-LOCKED instantly
       Flagged (HIGH severity) → routed to HR
       HR sees only ~20–25% of forms

Step 8  (Non-Worker ID creation — HR manually creates)
  OLD: HR creates ID manually in external system → SLA 1 business day
  NEW: AI generates NW-{PAN}-{YEAR} automatically on JoiningFormLocked event
       Generated in < 1 second
       SLA: near-instant (no more 1-day wait)
       HR notified as FYI (not action)

Step 10 (Offer letter — HR reviews and sends)
  OLD: HR reviews ALL letters → sends
  NEW: Standard template → AUTO-SENT (30-min recall window for HR)
       Custom cases → HR reviews

Step 21 (Certificate — HR reviews and approves)
  OLD: HR reviews ALL certificates → approves → sends
  NEW: Clean closure → AUTO-GENERATED + AUTO-SENT (48h recall window)
       Terminated / disputed → HR handles
```

---

*NexHire System Blueprint v2.2 — AI Automation Upgrades + PAN Card Integration*
*AI Coverage: 85% · HR Work: 15% · PAN-based deduplication + Non-Worker ID generation*

---

## 19. Variable Cooling Period System

> **Design Principle:** Cooling periods are proportional to the candidate's responsibility
> for the terminal outcome. Where the candidate had no control (mentor unavailability),
> no penalty is applied. Where the candidate actively disengaged, a longer period applies.
> All durations are hardcoded via DB seed migration — intentional, version-controlled,
> requires a code review to change.

### 19.1 Cooling Period Matrix (Final — All Specs Confirmed)

| Terminal State | Duration | Responsibility | Reasoning |
|---|---|---|---|
| `NDA_DECLINED_REJECTED` | **6 months** | Candidate | Explicitly refused a legal document — strong disengagement signal |
| `TERMINATED` | **6 months** | Candidate | Left mid-internship — reliability and commitment concern |
| `NDA_TIMEOUT_REJECTED` | **3 months** | Candidate | Did not respond for 5 days — moderate disengagement |
| `HR_REJECTED` | **3 months** | Shared | HR found profile unfit — time for profile improvement |
| `CANDIDATE_REJECTED` | **0 months** | System | 3 mentors unavailable — not candidate's fault, no penalty |
| `CLOSED` (re-join) | **3 months** | None | Healthy spacing between internship cycles |

### 19.2 Cooling Period Configuration (DB-Seeded — Not UI-Editable)

```sql
-- Seeded via Alembic migration — NOT editable via UI
-- To change: write new migration, code review required, version-controlled

CREATE TABLE cooling_period_config (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    terminal_state   VARCHAR(50) NOT NULL UNIQUE,
    duration_months  SMALLINT NOT NULL,    -- 0 = no cooling period
    description      TEXT NOT NULL,        -- human-readable reason
    is_active        BOOLEAN DEFAULT true,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Seed data (inserted via Alembic migration: 0005_seed_cooling_periods.py)
INSERT INTO cooling_period_config
  (terminal_state, duration_months, description) VALUES
  ('NDA_DECLINED_REJECTED', 6,
   'Candidate explicitly declined NDA — 6-month cooling period.'),
  ('TERMINATED',            6,
   'Candidate left mid-internship — 6-month cooling period.'),
  ('NDA_TIMEOUT_REJECTED',  3,
   'Candidate did not sign NDA within 5 days — 3-month cooling period.'),
  ('HR_REJECTED',           3,
   'HR found candidate unfit — 3-month cooling period.'),
  ('CANDIDATE_REJECTED',    0,
   'Mentor unavailability — no cooling period applied.'),
  ('CLOSED',                3,
   'Successful completion — 3-month spacing before re-joining.');

-- Application role: SELECT only
-- To update durations: write new Alembic migration
--   → code review required → git history preserved → deliberate change
REVOKE INSERT, UPDATE, DELETE ON cooling_period_config FROM nexhire_app;
GRANT SELECT ON cooling_period_config TO nexhire_app;
```

**Why DB-seeded and not UI-configurable:**
- Changes to cooling periods are policy decisions — not operational ones
- Require deliberate code review + migration (prevents accidental changes)
- Full version history preserved in git (every change traceable to a PR)
- `is_active` flag allows disabling a rule without deletion (migration can toggle)

### 19.3 Cooling Period DB Schema

```sql
-- Cooling period tracking on referrals
ALTER TABLE referrals
  ADD COLUMN cooling_period_months    SMALLINT,
  ADD COLUMN cooling_period_start_at  TIMESTAMPTZ,
  ADD COLUMN cooling_period_end_at    TIMESTAMPTZ,
  ADD COLUMN cooling_triggered_by     VARCHAR(50),  -- terminal state name
  ADD COLUMN cooling_override_at      TIMESTAMPTZ,
  ADD COLUMN cooling_override_by      UUID REFERENCES users(id),
  ADD COLUMN cooling_override_reason  TEXT;

-- Index for fast PAN + cooling period lookups
CREATE INDEX idx_referrals_pan_cooling
  ON referrals(candidate_pan, cooling_period_end_at)
  WHERE cooling_period_end_at IS NOT NULL;

-- Cooling period override audit (separate table for clean querying)
CREATE TABLE cooling_period_overrides (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_id         UUID NOT NULL REFERENCES referrals(id),
    new_referral_id     UUID REFERENCES referrals(id),  -- referral that bypassed
    candidate_pan_masked VARCHAR(20) NOT NULL,
    original_end_date   DATE NOT NULL,
    overridden_at       TIMESTAMPTZ DEFAULT NOW(),
    overridden_by       UUID NOT NULL REFERENCES users(id),
    override_reason     TEXT NOT NULL,
    CHECK (length(override_reason) >= 50)  -- minimum 50 chars — must be meaningful
);
```

### 19.4 Cooling Period Business Rules (RULE-CP Series)

```
RULE-CP1: NDA Declined — 6 Month Cooling Period
  Trigger:  referral.status transitions to NDA_DECLINED_REJECTED
  Action:   Set cooling_period_months = 6
            cooling_period_start_at = NOW()
            cooling_period_end_at = NOW() + INTERVAL '6 months'
            cooling_triggered_by = 'NDA_DECLINED_REJECTED'
  Block:    Any new referral for same PAN before cooling_period_end_at

RULE-CP2: Terminated — 6 Month Cooling Period
  Trigger:  referral.status transitions to TERMINATED
  Action:   Same as CP1 with duration = 6 months

RULE-CP3: NDA Timeout — 3 Month Cooling Period
  Trigger:  referral.status transitions to NDA_TIMEOUT_REJECTED
  Action:   Same as CP1 with duration = 3 months

RULE-CP4: HR Rejected — 3 Month Cooling Period
  Trigger:  referral.status transitions to HR_REJECTED
  Action:   Same as CP1 with duration = 3 months

RULE-CP5: Candidate Rejected (Mentor Unavailability) — No Cooling Period
  Trigger:  referral.status transitions to CANDIDATE_REJECTED
  Action:   cooling_period_months = 0
            No block on new referral — can be re-referred immediately
            cooling_triggered_by = 'CANDIDATE_REJECTED'
            (recorded for history, not enforcement)

RULE-CP6: Closed (Re-join) — 3 Month Cooling Period
  Trigger:  referral.status transitions to CLOSED
  Action:   Same as CP1 with duration = 3 months
            Cooling starts from actual_end_date (not closure processing date)

RULE-CP7: Program Owner Override
  Trigger:  Program Owner initiates override for specific referral
  Guard:    override_reason.length >= 50 characters (enforced by DB constraint)
  Action:   cooling_period_end_at → NOW() (effectively ends cooling immediately)
            cooling_override_at → NOW()
            cooling_override_by → program_owner.id
            cooling_override_reason → reason text
            Record inserted to cooling_period_overrides table
            Audit event: COOLING_PERIOD_OVERRIDDEN (immutable)
            HR notified of override
  Limit:    Program Owner role only — HR cannot override
```

### 19.5 Cooling Period Service

```python
# app/modules/referral/cooling_period_service.py

from dataclasses import dataclass
from datetime import date
from uuid import UUID

@dataclass
class CoolingPeriodStatus:
    is_in_cooling: bool
    terminal_state: str | None       = None
    cooling_start:  date | None      = None
    cooling_end:    date | None      = None
    days_remaining: int | None       = None
    months_duration: int | None      = None
    can_override:   bool             = False
    override_applied: bool           = False


class CoolingPeriodService:

    async def get_status(self, pan_number: str) -> CoolingPeriodStatus:
        """
        Primary check: called whenever a PAN is entered in referral form.
        Returns full cooling period status for a candidate identified by PAN.
        """
        # Find most recent terminal referral for this PAN
        record = await db.query("""
            SELECT r.status,
                   r.cooling_period_months,
                   r.cooling_period_start_at,
                   r.cooling_period_end_at,
                   r.cooling_triggered_by,
                   r.cooling_override_at,
                   r.actual_end_date
            FROM referrals r
            WHERE r.candidate_pan = :pan_encrypted
            AND r.cooling_period_end_at IS NOT NULL
            ORDER BY r.cooling_period_start_at DESC
            LIMIT 1
        """, pan_encrypted=encrypt(pan_number))

        if not record:
            return CoolingPeriodStatus(is_in_cooling=False)

        # No cooling period for CANDIDATE_REJECTED
        if record.cooling_period_months == 0:
            return CoolingPeriodStatus(is_in_cooling=False)

        # Override already applied — cooling ended early
        if record.cooling_override_at:
            return CoolingPeriodStatus(
                is_in_cooling=False,
                override_applied=True,
                terminal_state=record.cooling_triggered_by
            )

        today = date.today()
        cooling_end = record.cooling_period_end_at.date()

        if today >= cooling_end:
            # Cooling period naturally elapsed
            return CoolingPeriodStatus(is_in_cooling=False)

        days_remaining = (cooling_end - today).days

        return CoolingPeriodStatus(
            is_in_cooling=True,
            terminal_state=record.cooling_triggered_by,
            cooling_start=record.cooling_period_start_at.date(),
            cooling_end=cooling_end,
            days_remaining=days_remaining,
            months_duration=record.cooling_period_months,
            can_override=True  # Program Owner can override
        )

    async def apply_cooling_period(self,
                                    referral_id: UUID,
                                    terminal_state: str) -> None:
        """
        Called by WorkflowEngine when any terminal state is reached.
        Looks up duration from cooling_period_config, sets dates.
        """
        config = await db.query("""
            SELECT duration_months FROM cooling_period_config
            WHERE terminal_state = :state AND is_active = true
        """, state=terminal_state)

        if not config:
            # Unknown terminal state — log warning, no cooling applied
            logger.warning("cooling_config_not_found",
                           terminal_state=terminal_state)
            return

        duration_months = config.duration_months

        if duration_months == 0:
            # No cooling period — record for history only
            await referral_repo.update(referral_id, {
                "cooling_period_months": 0,
                "cooling_period_start_at": utcnow(),
                "cooling_period_end_at": utcnow(),  # immediately expired
                "cooling_triggered_by": terminal_state
            })
            return

        start = utcnow()
        end   = add_months(start, duration_months)

        await referral_repo.update(referral_id, {
            "cooling_period_months":   duration_months,
            "cooling_period_start_at": start,
            "cooling_period_end_at":   end,
            "cooling_triggered_by":    terminal_state
        })

        await audit_publisher.publish(AuditEvent(
            event_type="COOLING_PERIOD_APPLIED",
            entity_type="REFERRAL",
            entity_id=referral_id,
            payload={
                "terminal_state":    terminal_state,
                "duration_months":   duration_months,
                "cooling_start":     start.isoformat(),
                "cooling_end":       end.isoformat(),
                "pan_masked":        get_masked_pan(referral_id)
            }
        ))

    async def apply_override(self,
                              original_referral_id: UUID,
                              program_owner_id: UUID,
                              reason: str,
                              new_referral_id: UUID | None = None) -> None:
        """
        Program Owner overrides cooling period for exceptional cases.
        Reason must be at least 50 characters (DB constraint enforced).
        """
        if len(reason.strip()) < 50:
            raise ValidationError(
                code="OVERRIDE_REASON_TOO_SHORT",
                user_message="Override reason must be at least 50 characters. "
                             "Please provide a detailed justification."
            )

        # Verify actor is Program Owner
        actor = await user_repo.get(program_owner_id)
        if actor.role != UserRole.PROGRAM_OWNER:
            raise InsufficientPermissionsError()

        # Apply override — cooling ends immediately
        await referral_repo.update(original_referral_id, {
            "cooling_period_end_at":     utcnow(),  # ends now
            "cooling_override_at":       utcnow(),
            "cooling_override_by":       program_owner_id,
            "cooling_override_reason":   reason
        })

        # Record in override audit table
        await cooling_override_repo.insert(CoolingPeriodOverride(
            referral_id=original_referral_id,
            new_referral_id=new_referral_id,
            candidate_pan_masked=get_masked_pan(original_referral_id),
            original_end_date=get_original_end_date(original_referral_id),
            overridden_by=program_owner_id,
            override_reason=reason
        ))

        # Immutable audit event
        await audit_publisher.publish(AuditEvent(
            event_type="COOLING_PERIOD_OVERRIDDEN",
            actor_user_id=program_owner_id,
            actor_role="PROGRAM_OWNER",
            payload={
                "original_referral_id":  str(original_referral_id),
                "original_cooling_end":  get_original_end_date(original_referral_id),
                "override_reason":       reason,
                "pan_masked":            get_masked_pan(original_referral_id),
                "overridden_at":         utcnow().isoformat()
            }
        ))

        # Notify HR of override
        await notification_service.send(
            template_id="NOTIF_013_COOLING_OVERRIDE_HR",
            recipient=hr_team_email,
            context={
                "overridden_by":    actor.full_name,
                "reason":           reason,
                "pan_masked":       get_masked_pan(original_referral_id),
                "overridden_at":    utcnow()
            }
        )
```

### 19.6 Updated PAN Check — Full Decision Tree

```python
# app/modules/ai/duplicate_detector.py (updated)

async def check_pan_full(pan_number: str,
                          referrer_id: UUID) -> PanCheckResult:
    """
    Complete PAN check: active duplicate + cooling period.
    Called in real-time as employee types PAN in referral form.
    """

    # STEP 1: Active duplicate check (highest priority)
    active = await db.query("""
        SELECT id, candidate_name, status
        FROM referrals
        WHERE candidate_pan = :pan
        AND status NOT IN (
          'HR_REJECTED','CANDIDATE_REJECTED',
          'NDA_TIMEOUT_REJECTED','NDA_DECLINED_REJECTED',
          'TERMINATED','CLOSED'
        )
        LIMIT 1
    """, pan=encrypt(pan_number))

    if active:
        return PanCheckResult(
            verdict="HARD_BLOCK",
            block_type="ACTIVE_DUPLICATE",
            message=f"An active referral already exists for this candidate "
                    f"(Referral #{active.id[:8].upper()}, "
                    f"Status: {active.status}).",
            allow_override=False,
            existing_referral_id=active.id
        )

    # STEP 2: Cooling period check
    cooling = await cooling_period_service.get_status(pan_number)

    if cooling.is_in_cooling:
        terminal_labels = {
            "NDA_DECLINED_REJECTED": "explicitly declined the NDA",
            "TERMINATED":            "left mid-internship",
            "NDA_TIMEOUT_REJECTED":  "did not sign NDA within the deadline",
            "HR_REJECTED":           "was found unfit by HR review",
            "CLOSED":                "completed a previous internship"
        }
        reason_text = terminal_labels.get(
            cooling.terminal_state, "a previous referral was closed"
        )

        return PanCheckResult(
            verdict="COOLING_BLOCK",
            block_type="COOLING_PERIOD_ACTIVE",
            terminal_state=cooling.terminal_state,
            cooling_start=cooling.cooling_start,
            cooling_end=cooling.cooling_end,
            days_remaining=cooling.days_remaining,
            months_duration=cooling.months_duration,
            message=f"This candidate {reason_text}. "
                    f"A {cooling.months_duration}-month cooling period applies.",
            allow_override=True,   # Program Owner can override
            override_role_required="PROGRAM_OWNER"
        )

    # STEP 3: Fuzzy duplicate check (existing candidates, no cooling period)
    fuzzy = await detect_duplicate_fuzzy(pan_number=pan_number)

    if fuzzy.is_duplicate:
        return PanCheckResult(
            verdict="WARN" if fuzzy.similarity_score < 0.9 else "SOFT_BLOCK",
            block_type="FUZZY_DUPLICATE",
            similarity_score=fuzzy.similarity_score,
            match_reasons=fuzzy.match_reasons,
            message="A possible duplicate candidate was found. HR will verify.",
            allow_override=True
        )

    # STEP 4: All clear
    return PanCheckResult(
        verdict="CLEAR",
        message="PAN verified — no existing referral or cooling period found."
    )
```

### 19.7 UI — Cooling Period Blocks (Referral Form)

```
COOLING PERIOD ACTIVE — 6 months (NDA_DECLINED_REJECTED):
┌──────────────────────────────────────────────────────────────────────┐
│  ⏳ COOLING PERIOD ACTIVE — Cannot Refer                            │
│                                                                      │
│  Riya Sharma (PAN: ABCDE****F)                                      │
│  Reason:          Candidate explicitly declined the NDA             │
│  Period:          6 months                                           │
│  Started:         12 Jan 2025                                        │
│  Ends:            12 Jul 2025                                        │
│  Days remaining:  47 days                                            │
│                                                                      │
│  You can submit a new referral after 12 Jul 2025.                   │
│  [🔔 Remind me on 12 Jul 2025]                                      │
│                                                                      │
│  ── Program Owner only ────────────────────────────────────────     │
│  [Request Cooling Period Override]  (requires justification)        │
└──────────────────────────────────────────────────────────────────────┘

COOLING PERIOD ACTIVE — 3 months (CLOSED re-join):
┌──────────────────────────────────────────────────────────────────────┐
│  ⏳ COOLING PERIOD ACTIVE — Re-join Not Yet Available               │
│                                                                      │
│  Riya Sharma (PAN: ABCDE****F)                                      │
│  Reason:          Completed previous internship (re-join period)    │
│  Period:          3 months                                           │
│  Started:         15 Mar 2025                                        │
│  Ends:            15 Jun 2025                                        │
│  Days remaining:  18 days                                            │
│                                                                      │
│  Riya completed her previous internship successfully.               │
│  She can re-join after the standard 3-month spacing period.         │
│  [🔔 Remind me on 15 Jun 2025]                                      │
└──────────────────────────────────────────────────────────────────────┘

NO COOLING PERIOD (CANDIDATE_REJECTED):
┌──────────────────────────────────────────────────────────────────────┐
│  ✅ PAN Verified — Eligible for Re-referral                         │
│                                                                      │
│  Riya Sharma (PAN: ABCDE****F)                                      │
│  Note: A previous referral was closed due to mentor unavailability. │
│  No cooling period applies — this was not the candidate's fault.    │
│  You may submit a new referral immediately.                         │
└──────────────────────────────────────────────────────────────────────┘
```

### 19.8 Program Owner Override Flow (UI)

```
Program Owner visits S23 (Executive Dashboard) or S24 (Audit Report)
  ↓
Sees referral with COOLING_BLOCK status
  ↓
Clicks [Override Cooling Period]
  ↓
┌──────────────────────────────────────────────────────────────────────┐
│  Override Cooling Period                                             │
│  ─────────────────────────────────────────────────────────────────  │
│  Candidate:       Riya Sharma (PAN: ABCDE****F)                    │
│  Terminal state:  NDA_DECLINED_REJECTED                             │
│  Cooling ends:    12 Jul 2025 (47 days remaining)                   │
│                                                                      │
│  ⚠️  This action is irreversible and will be permanently            │
│      logged in the audit trail with your name and reason.           │
│                                                                      │
│  Justification (minimum 50 characters): *                           │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Candidate had a medical emergency during NDA period.         │  │
│  │ HR verified hospital documentation. Exceptional case        │  │
│  │ approved by department head.                                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  Characters: 142 / minimum 50 ✅                                    │
│                                                                      │
│  [Cancel]                    [Confirm Override — Log Permanently]   │
└──────────────────────────────────────────────────────────────────────┘
  ↓
On confirm:
  cooling_period_end_at → NOW()
  cooling_override_at, cooling_override_by, cooling_override_reason set
  cooling_period_overrides record inserted
  Audit event: COOLING_PERIOD_OVERRIDDEN (immutable)
  HR notified via email
  New referral can now be submitted immediately
```

### 19.9 Updated Auto-Approval Engine — Condition #7

```python
# Cooling period check added as condition 7 in ReferralAutoApprovalEngine

# CHECK 7: Cooling period (should never reach here if UI blocks correctly,
#           but server-side guard is essential — never trust client)
cooling = await cooling_period_service.get_status(referral.candidate_pan)
if cooling.is_in_cooling:
    return AutoApprovalResult(
        decision="HARD_BLOCK",
        reason="COOLING_PERIOD_ACTIVE",
        route_to_hr=False,  # Not an HR decision — system-enforced block
        flags=[f"Candidate in {cooling.months_duration}-month cooling period. "
               f"Ends: {cooling.cooling_end}. "
               f"Triggered by: {cooling.terminal_state}"]
    )
```

### 19.10 Cooling Period Notification Templates

```
NOTIF_014: Cooling Period Applied (to Referrer)
  Trigger:  Any terminal state with cooling_period_months > 0
  Content:  "The referral for [Candidate Name] has been closed.
             A [N]-month cooling period has been applied starting [date].
             You may submit a new referral for this candidate after [end_date]."
  Action:   [Set Reminder] button → creates calendar reminder

NOTIF_015: Cooling Period Ending Soon (to Referrer)
  Trigger:  APScheduler — 7 days before cooling_period_end_at
  Content:  "[Candidate Name]'s cooling period ends in 7 days ([date]).
             You will be able to submit a new referral from [date]."

NOTIF_016: Cooling Period Expired — Re-referral Available (to Referrer)
  Trigger:  APScheduler — on cooling_period_end_at date
  Content:  "[Candidate Name]'s cooling period has ended.
             You may now submit a new referral."

NOTIF_013: Cooling Period Overridden (to HR)
  Trigger:  Program Owner override confirmed
  Content:  "Program Owner [Name] has overridden the cooling period
             for [Candidate PAN masked]. Reason: [reason].
             A new referral may now be submitted immediately."
```

### 19.11 Cooling Period Report (S24 — Audit & SLA Report)

```
Program Owner sees on S24:

COOLING PERIOD ANALYTICS
─────────────────────────────────────────────────────────────────────
Currently in cooling period:     12 candidates
  → 6-month periods:              4  (NDA declined: 2, Terminated: 2)
  → 3-month periods:              8  (Timeout: 3, HR rejected: 4, Re-join: 1)

Cooling periods ending this month: 5
  → Referrers notified:            5 ✅

Historical override count:         2
  → Last override:                 23 Mar 2025 by [Program Owner Name]

CANDIDATE COOLING STATUS TABLE (filterable, exportable)
  Candidate PAN    Terminal State          Started      Ends         Days Left
  ABCDE****F       NDA_DECLINED_REJECTED   12 Jan 2025  12 Jul 2025  47
  FGHIJ****K       HR_REJECTED             01 Mar 2025  01 Jun 2025  8
  LMNOP****Q       CLOSED (re-join)        15 Mar 2025  15 Jun 2025  22
  ...
```

---

*NexHire System Blueprint v2.3 — Variable Cooling Period System Added*
*AI Coverage: 85% · HR Work: 15% · 6 cooling period rules · Program Owner override*
