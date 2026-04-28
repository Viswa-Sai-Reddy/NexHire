# Intern Flow — Hackathon MVP Plan

## Context

The BRD describes "Intern Flow" — an enterprise-scale unpaid internship automation platform with multi-region HA, immutable audit, microservices-friendly bounded contexts, etc. (see [Architecture_Analysis.md](./Architecture_Analysis.md) for the full enterprise design).

**This plan is different.** The user is building a hackathon submission that will demonstrate the full happy path of the BRD to ~200 users in a 2–4 week build window, using a **single deployable** built with **FastAPI + React + Postgres on Azure**. The intent is to ship a credible, demoable end-to-end product covering referral → onboarding → access → closure → certificate, with **real integrations** (Gmail, Google Gemini API, DocuSign sandbox, Microsoft Graph for AD), and to drop every enterprise concern (multi-region, read replicas, Service Bus, etc.) that adds setup time without demo value.

The outcome should be a single repo, a single container, and a single Azure App Service running the whole product — and a 5-minute demo flow that walks judges from a referrer's first click to a candidate's signed certificate.

---

## Locked decisions (from clarification)

| Decision | Choice |
|---|---|
| Timeline | **2–4 weeks** |
| Deployment shape | **FastAPI (API) + React SPA bundled into one container, one Azure App Service** |
| Cloud | **Azure** for app infra (App Service for Containers + Azure DB for PostgreSQL Flexible Server + Blob + Key Vault) |
| AI vendor | **Google Gemini API** via Google AI Studio (cross-cloud — independent of Azure infra) |
| Resume parsing | **Real** — Google Gemini (`gemini-2.0-flash`) — native multimodal, reads PDFs directly |
| Email | **Real** — Gmail API (OAuth2) |
| E-sign | **Real** — DocuSign developer sandbox |
| AD provisioning | **Real** — Microsoft Graph API against a test Entra tenant |
| AI ambition | **AI is the primary interaction modality, not a sprinkle** — target ≥ 70% of user-facing capabilities have AI in the loop |

---

## AI footprint (target ≥ 70%)

The app exposes ~26 user-facing capabilities. **20 of them have AI in the loop = ~77%.** AI is the *interaction modality* for most of them, not a hidden helper. Capabilities are listed in the "How AI is in the loop" column; "—" means pure CRUD/integration.

| # | Capability | How AI is in the loop | Model |
|---|---|---|---|
| 1 | Login | — | — |
| 2 | **Referral via classic form** | Resume parse → prefill, with confidence + override | `gemini-2.0-flash` (JSON mode) |
| 3 | **Referral via conversational intake** | Multi-turn chat (optional voice via Web Speech API) gathers fields, calls `submit_referral` tool | `gemini-2.0-flash` + tools |
| 4 | **Eligibility & readiness validator** | Cross-reads referrer narrative + parsed fields, flags concerns ("declared in-person but candidate based abroad") | `gemini-2.0-flash` |
| 5 | **Smart form validator** (referral + joining) | Holistic semantic checks — phone country code vs. address, gov-ID format vs. nationality, cross-field consistency | `gemini-2.0-flash` |
| 6 | **Hybrid duplicate detection** | Deterministic rules (email/phone/name fuzzy) + cosine similarity over candidate fingerprint embeddings | `text-embedding-004` + `rapidfuzz` |
| 7 | HR review queue (inbox CRUD) | — | — |
| 8 | **Personalized communications** (every outbound email except legal) | LLM drafts contextual body using template skeleton + role-specific tone; HR approves drafts > sensitive | `gemini-2.0-flash` |
| 9 | **Project scope analyzer** | Analyzes mentor's project overview vs. candidate skills + duration; suggests learning objectives; warns on scope-vs-duration mismatch | `gemini-2.0-flash` |
| 10 | Joining form draft + magic-link auth | — | — |
| 11 | **Attachment intelligence** | Extracts & cross-validates gov-ID and transcript fields from uploaded docs vs. declared values — Gemini reads PDFs/images natively, no separate OCR service | `gemini-2.0-flash` (native multimodal) |
| 12 | NDA via DocuSign | — | — |
| 13 | **NDA plain-language summary** | LLM produces candidate-friendly summary of NDA obligations, shown alongside legal doc | `gemini-2.0-flash` |
| 14 | AD provisioning | — | — |
| 15 | **Mentor dossier with personalized welcome brief** | LLM drafts a 1-paragraph mentor brief from candidate background + project | `gemini-2.0-flash` |
| 16 | Lifecycle events (start/extend/close) | — | — |
| 17 | **SLA risk prediction with rationale** | Heuristic baseline filters at-risk items; LLM produces risk score, predicted breach time, root-cause narrative, recommended action | Heuristic + `gemini-2.0-flash` |
| 18 | **Anomaly detection on audit stream** | Periodic LLM pass over recent audit events flags unusual patterns ("8 referrals from one referrer in a week") | `gemini-2.0-flash` |
| 19 | **Weekly executive digest agent** | Autonomous job composes Program Owner narrative report (volume, breaches, root causes, recommendations) | `gemini-2.0-flash` |
| 20 | **Personalized certificate text** | LLM-drafted achievements paragraph baked into certificate PDF; mentor reviews before issuance | `gemini-2.0-flash` |
| 21 | **Agentic FAQ chatbot** (RAG + tools) | RAG citations + function-calling tools to take actions: `get_my_pending_tasks`, `get_referral_status`, `extend_internship`, `request_nda_resend`, `escalate_sla_breach`, `submit_referral` | `gemini-2.0-flash` + `text-embedding-004` + tools |
| 22 | Audit log viewer / email-template admin | — | — |
| 23 | **Mentor-candidate matchmaking** | LLM scores available mentors against candidate skills + project + mentor workload, returns ranked top-3 with rationale | `gemini-2.0-flash` |
| 24 | **Multilingual interaction** (chatbot, intake, drafts, summaries) | Detect input language; respond in same language; UI strings AI-translated at build time for 8 locales | `gemini-2.0-flash` |
| 25 | **AI alt-text + WCAG audit** | Caption uploaded images; LLM scans rendered HTML for accessibility issues, returns fixes | `gemini-2.0-flash` (native vision — no Document Intelligence needed) |
| 26 | Audit log / template admin (already counted as #22) | — | — |

**Net AI ratio: 20 / 26 = ~77%** of user-facing capabilities. Of those, **6 are agentic** (LLM chooses actions or tools, not just generates text): conversational intake, agentic chatbot, SLA prediction with action recommendation, anomaly detection, weekly digest, attachment intelligence. The existing #6 dedup is enhanced by continuous re-embedding, and #21 chatbot is enhanced by an LLM reranker (top-20 → top-5).

---

## Hackathon scope

### IN — must demo
1. **Auth & roles** — JWT login with seeded users for the 6 roles (Referrer, Candidate, Mentor, HR, IT, Program Owner).
2. **Referral intake** — Referrer uploads resume → AI parses → form prefilled → eligibility flags → submit.
3. **HR review queue** — HR sees inbox, approves, kicks off Non-Worker ID + Joining Form invite (Gmail).
4. **Joining form** — Candidate completes via magic-link, attachments to Blob, HR locks it.
5. **NDA** — DocuSign sandbox envelope, candidate signs, webhook flips status.
6. **AD provisioning** — Microsoft Graph creates user in test Entra tenant, credentials emailed.
7. **Mentor dossier** — Mentor sees intern profile + project once NDA signed.
8. **Lifecycle** — Start confirmation, optional extension, closure trigger.
9. **Closure** — Auto AD-disable via Graph; certificate generated as PDF (WeasyPrint), emailed.
10. **Dashboard** — Program Owner view: stage counts, SLA breaches, average cycle time.
11. **Audit log** — append-only table, viewable per entity.
12. **Notification engine** — event-driven Gmail sends with templated bodies + 3-strike reminders via APScheduler.
13. **Agentic FAQ chatbot** — RAG over a curated FAQ corpus stored in Postgres via **pgvector**, plus **function-calling tools** so the bot can take actions on behalf of the user (status lookups, internship extension, NDA resend, SLA escalation, full referral submission). Role-aware retrieval and tool-permission gates. Floating drawer widget on every page.
14. **Full duplicate-detection ML** — hybrid: deterministic rules (email exact, phone E.164, name fuzzy via `rapidfuzz`) **plus** semantic similarity via `text-embedding-004` over a candidate fingerprint. Stored in pgvector; produces `dedup_score` + band (LIKELY / POSSIBLE / UNIQUE) + HR review screen.
15. **Conversational referral intake (alt. flow)** — instead of the form, referrer can click "Talk to AI" → multi-turn chat (text or voice via browser-native Web Speech API) → LLM gathers required fields → calls `submit_referral` tool. Same validation pipeline runs on submit.
16. **Eligibility & readiness validator** — LLM checks unpaid consent, in-person readiness, location alignment against the narrative + parsed resume; flags concerns before HR review.
17. **Smart form validator** — semantic cross-field checks on referral + joining forms (phone country vs. address, gov-ID format vs. nationality, education dates internally consistent).
18. **Project scope analyzer** — analyzes mentor's project text vs. candidate skills + planned duration; suggests measurable learning objectives; warns on scope-vs-duration mismatch.
19. **NDA plain-language summary** — LLM renders a candidate-friendly summary alongside the legal NDA so candidates actually read it.
20. **Mentor dossier brief** — LLM drafts a 1-paragraph welcome brief for the mentor based on candidate background + project on dossier load.
21. **Personalized certificate text** — LLM drafts an achievements paragraph embedded in the certificate PDF; mentor reviews before issuance.
22. **Attachment intelligence** — Gemini's native multimodal vision extracts fields from uploaded transcripts/IDs (PDF or image) and cross-validates against declared values — no separate OCR/Document Intelligence service needed.
23. **SLA risk prediction with rationale** — see expanded design below.
24. **Anomaly detection** — periodic LLM pass on the audit stream flags unusual patterns (e.g., one referrer spiking, repeat extensions by same mentor).
25. **Weekly executive digest agent** — autonomous Sunday-night job composes a Program Owner narrative report and emails it.
26. **Personalized communications** — every outbound email (except the legal NDA itself) gets LLM-personalized body using a template skeleton; sensitive sends require HR approval before going out.
27. **Mentor-candidate matchmaking** — when referrer leaves mentor blank (or asks for help), AI scores available mentors and recommends top-3.
28. **Multilingual interaction** — chatbot, conversational intake, validators, drafts, NDA summary all auto-detect language and respond in kind; UI strings AI-translated for 8 locales (en, hi, ta, te, kn, ml, es, fr).
29. **AI alt-text + WCAG audit** — caption uploaded images; CI + admin panel run an LLM accessibility audit on key pages.
30. **Reranker on RAG retrieval** — pgvector top-20 → LLM rerank to top-5 (chatbot quality boost).
31. **Continuous candidate re-embedding** — on candidate row update, refresh fingerprint embedding so dedup stays current.

### OUT — explicitly cut for hackathon
- Multi-region / HA / DR / read replicas
- Service Bus / Kafka — replaced by in-process APScheduler + FastAPI `BackgroundTasks`
- Always-Encrypted PII columns — TLS + bcrypt only
- Full WCAG 2.1 AA audit (hit basic semantic HTML + keyboard nav)
- AKS / Container Apps / blue-green slots — App Service single slot is fine

---

## Architecture (single deployable)

```
┌───────────────────────────────────────────────┐
│         Azure App Service (1 container)       │
│  ┌──────────────────────────────────────┐     │
│  │  FastAPI (uvicorn)                   │     │
│  │   ├─ /api/*    JSON endpoints        │     │
│  │   ├─ /static   React build (Vite)    │     │
│  │   └─ /         index.html (SPA)      │     │
│  │  APScheduler runs in same process    │     │
│  └──────────────────────────────────────┘     │
└──────┬──────────────┬────────────────┬────────┘
       │              │                │
   Postgres      Google Gemini    Gmail/DocuSign/Graph
   Flex Server   (gemini-2.0-flash    (external APIs)
                  + text-embedding-004)
       │
   Blob Storage (resumes, NDAs, certs)
```

App infrastructure is on Azure; AI is on Google Cloud (AI Studio API). Cross-cloud is a non-issue here — Gemini is just an HTTPS API call from the FastAPI container.

**Key simplifications vs. enterprise design:**
- Workflow orchestration = a `WorkflowService` class with a state-machine table (no Service Bus).
- SLA timers = APScheduler in-process job that wakes every 5 minutes and scans `scheduled_jobs` table.
- Async fan-out (e.g., "submit referral → email + audit + queue HR task") = `BackgroundTasks` in the request handler.

---

## Repository layout (single repo, single deploy)

```
/intern-flow
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers per module
│   │   │   ├── referrals.py
│   │   │   ├── joining_forms.py
│   │   │   ├── nda.py
│   │   │   ├── access.py
│   │   │   ├── internships.py
│   │   │   ├── certificates.py
│   │   │   ├── dashboards.py
│   │   │   ├── audit.py
│   │   │   ├── auth.py
│   │   │   └── webhooks.py   # docusign callbacks
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── schemas/          # Pydantic DTOs
│   │   ├── services/         # business logic
│   │   │   ├── workflow.py   # state machine
│   │   │   ├── referral_service.py
│   │   │   ├── notification_service.py
│   │   │   ├── audit_service.py
│   │   │   └── certificate_service.py
│   │   ├── integrations/
│   │   │   ├── gemini.py         # LLM, embeddings, vision (PDF/image), tools
│   │   │   ├── gmail.py          # OAuth2 + send
│   │   │   ├── docusign.py       # envelope create + webhook verify
│   │   │   ├── ms_graph.py       # AD user create/disable
│   │   │   └── blob.py           # azure-storage-blob
│   │   ├── core/
│   │   │   ├── config.py         # pydantic-settings
│   │   │   ├── security.py       # JWT + bcrypt
│   │   │   ├── deps.py           # FastAPI dependencies
│   │   │   ├── scheduler.py      # APScheduler bootstrap
│   │   │   └── rbac.py           # role policy decorators
│   │   ├── db.py                 # SQLAlchemy engine + session
│   │   └── main.py               # FastAPI app, mounts /static
│   ├── alembic/                  # migrations
│   ├── tests/
│   ├── pyproject.toml            # Poetry or uv
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ReferralNew.tsx
│   │   │   ├── ReferralList.tsx
│   │   │   ├── JoiningForm.tsx
│   │   │   ├── HrInbox.tsx
│   │   │   ├── MentorDossier.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   └── Login.tsx
│   │   ├── components/           # shared UI
│   │   ├── hooks/                # useApi, useAuth
│   │   ├── api/client.ts         # axios + JWT
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml            # local: api + postgres + adminer
├── .github/workflows/deploy.yml  # build → ACR → App Service
├── seed.py                       # seed roles, templates, demo users
└── README.md                     # demo script + setup
```

**Single-container build:** `Dockerfile` does a multi-stage build — stage 1 builds React (`npm run build`), stage 2 builds Python wheel and copies the React `dist/` into `/app/static`. FastAPI mounts `StaticFiles(directory="static", html=True)` and falls through to `index.html` for client-routed paths.

---

## Tech stack (final, hackathon-tuned)

| Layer | Choice | Notes |
|---|---|---|
| Backend | **Python 3.12 + FastAPI 0.115 + uvicorn** | Async, auto OpenAPI docs (great for demo at `/docs`) |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | |
| Validation | **Pydantic v2** | |
| Frontend | **React 18 + TypeScript + Vite** | Vite = fast dev + tiny prod bundle |
| UI kit | **Mantine** | Accessible primitives out of the box; Drawer ideal for chat widget |
| HTTP client | **axios** with JWT interceptor | |
| State | **Zustand** for auth/UI state, **TanStack Query** for server state | Avoid Redux for this size |
| Database | **Azure Database for PostgreSQL — Flexible Server (B1ms)** | ~$15/mo |
| Auth | **JWT** (`python-jose`) + **bcrypt** (`passlib`) seeded users | No Entra ID SSO for app login — keeps demo simple. Entra used only as the *target* tenant for AD provisioning |
| AI (LLM) | **Google Gemini `gemini-2.0-flash`** via Google AI Studio API | One API key shared by all AI surfaces; JSON mode (`responseSchema`) + function-calling; 1M-token context window helps the digest/anomaly agents |
| AI (embeddings) | **Google `text-embedding-004`** (768-dim) | Shared by FAQ RAG and candidate dedup; free tier covers hackathon volume |
| AI (tool-calling) | Gemini `function_declarations` on `gemini-2.0-flash` | Powers agentic chatbot + conversational intake |
| AI (multimodal vision) | **`gemini-2.0-flash` native vision** (PDF + image input directly) | Replaces Azure AI Document Intelligence — handles resumes, transcripts, gov-IDs, profile pics in a single API call. One less integration to wire |
| Voice input | **Browser-native Web Speech API** | Free, zero infra; adequate for hackathon demo |
| Vector store | **pgvector** extension on the same Postgres Flexible Server | No new infra; cosine search via `<=>`; HNSW index |
| OCR (resume) | **`gemini-2.0-flash` vision** (Gemini reads PDFs natively) with `pdfplumber` as a tiny pre-pass to extract plain text fast for the simple cases | Skips the OCR/parser dance — Gemini handles scanned PDFs and text PDFs the same way |
| Email | **Gmail API** via `google-api-python-client` with OAuth2 refresh-token | |
| E-sign | **DocuSign Developer Sandbox** via `docusign-esign` SDK + webhook | |
| AD | **Microsoft Graph SDK for Python** (`msgraph-sdk`) using **client credentials flow** against test Entra tenant | |
| PDF generation | **WeasyPrint** for certificates from HTML/CSS template | |
| Background jobs | **APScheduler** (in-process, persistent jobstore in Postgres) + FastAPI `BackgroundTasks` | |
| Object storage | **Azure Blob Storage** (one container per env) | |
| Secrets | **Azure Key Vault** + managed identity in App Service | Local dev uses `.env` |
| Logging | **Application Insights** via `opencensus-ext-azure` | |
| CI/CD | **GitHub Actions** → ACR → App Service deploy slot | |

---

## Data model (hackathon-tuned)

Drop temporal tables, Always Encrypted, RLS — keep only what fits in Postgres flat.

```sql
users(id, email, password_hash, display_name, role, is_active, created_at)
candidates(id, full_name, email, phone, address_json, education_json, skills_json, gov_ids_json, created_at)
referrals(id, referrer_user_id, mentor_user_id, candidate_id, status, eligibility_json, project_overview, planned_start, planned_end, location, dedup_score, created_at, submitted_at)
joining_forms(id, referral_id UNIQUE, status, payload_json, locked_by, locked_at, submitted_at)
joining_attachments(id, joining_form_id, blob_url, file_name, content_type, uploaded_at)
non_worker_ids(id, candidate_id, value, status, requested_at, sla_due_at, issued_at)
ndas(id, candidate_id, template_version, esign_envelope_id, status, signed_at, archived_blob_url)
internships(id, referral_id UNIQUE, start_date, end_date, original_end_date, status)
access_accounts(id, internship_id UNIQUE, ad_user_principal_name, provisioned_at, deactivated_at, credential_delivery)
certificates(id, internship_id, requested_at, issued_at, archived_blob_url)
notification_events(id, correlation_id, type, recipient, template_id, status, attempted_at, error)
email_templates(id, name, subject, body_md, version, active)
audit_events(id BIGSERIAL, actor_user_id, entity_type, entity_id, action, before_json, after_json, ip, occurred_at)  -- DB role: INSERT only
scheduled_jobs(id, job_type, run_at, payload_json, status)  -- APScheduler reads this
workflow_state(id, referral_id, current_step, state_json, updated_at)

-- pgvector-backed (CREATE EXTENSION vector)
candidate_embeddings(candidate_id PK, fingerprint_text, embedding vector(768), updated_at)
faq_documents(id, title, source_uri, audience_roles[], created_at)
faq_chunks(id, faq_document_id, chunk_text, embedding vector(768), token_count)
chat_sessions(id, user_id, created_at)
chat_messages(id, chat_session_id, role, content, citations_json, tool_calls_json, created_at)
dedup_matches(id, new_referral_id, matched_candidate_id, score, band, decided_by, decided_at, decision)

-- AI-output tables
ai_validations(id, entity_type, entity_id, validator_kind, verdict, concerns_json, model, prompt_version, created_at)
   -- validator_kind ∈ {ELIGIBILITY, FORM_SEMANTIC, ATTACHMENT, SCOPE_ANALYZER}
sla_risks(id, workflow_instance_id, evaluated_at, heuristic_band, risk_score, predicted_breach_at, root_cause, recommended_action, auto_escalate)
ai_drafts(id, entity_type, entity_id, draft_kind, content_md, status, approved_by, approved_at, model)
   -- draft_kind ∈ {EMAIL, NDA_SUMMARY, MENTOR_BRIEF, CERT_ACHIEVEMENTS, EXEC_DIGEST}
anomaly_alerts(id, detected_at, severity, summary, details_json, acknowledged_by, acknowledged_at)
agent_tool_calls(id, chat_message_id, tool_name, arguments_json, result_json, status, called_at)
   -- audit + replay surface for the agentic chatbot's actions

-- Promoted-from-out-of-scope additions
mentor_profiles(user_id PK, expertise_text, expertise_embedding vector(768), bandwidth_max, current_intern_count, updated_at)
mentor_match_runs(id, referral_id, ranked_json, model, prompt_version, created_at)
i18n_strings(locale, key, value, source_text, translated_at)   -- LLM-batch-translated UI bundle
image_alt_text(blob_url PK, alt_text, model, generated_at)
a11y_audits(id, page_route, snapshot_html_hash, issues_json, severity, audited_at)
```

Indexes only where they pay back: `referrals(status)`, `internships(end_date)`, `audit_events(entity_type, entity_id)`, `notification_events(status)`, `scheduled_jobs(run_at, status)`, plus **HNSW indexes** on both `candidate_embeddings.embedding` and `faq_chunks.embedding` (`USING hnsw (embedding vector_cosine_ops)`).

---

## SLA risk prediction — expanded design

**Goal:** every active workflow instance gets a continuously-updated risk score with an explanation and a recommended action, surfaced to the assignee and the Program Owner.

**Hybrid pipeline (cheap-first, LLM-second):**

1. **Tick (every 5 min) — `sla_risk_job` in APScheduler.** Pulls all `workflow_state` rows where status ∉ {ARCHIVED, CLOSED}.
2. **Heuristic baseline (no LLM):**
   - For each workflow, compute `time_in_state` and `remaining_steps_avg_duration` (rolling-window historical median per stage transition, computed from `audit_events`).
   - `predicted_completion = now + remaining_steps_avg_duration`.
   - `heuristic_band` = LOW (predicted_completion < 70% of SLA), MEDIUM (70–95%), HIGH (>95%) or BREACHED.
   - LOW items skip the LLM step entirely.
3. **LLM rationale layer (only on MEDIUM/HIGH/BREACHED):**
   - Build a structured prompt with: workflow ID, current step, step entered_at, SLA target, recent audit events for this workflow, assignee's open task count, day-of-week, blocking dependencies.
   - Call `gemini-2.0-flash` with JSON schema → returns:
     ```json
     {
       "risk_score": 0-100,
       "predicted_breach_at": "ISO8601",
       "root_cause": "one-sentence narrative",
       "recommended_action": "concrete action with assignee name",
       "auto_escalate": true|false
     }
     ```
   - Persist to `sla_risks` (latest wins via index on `(workflow_instance_id, evaluated_at DESC)`).
4. **Action surfacing:**
   - **Program Owner dashboard widget** — top 10 at-risk items.
   - **Assignee email** — if `risk_score ≥ 60` and no email sent in last 4h.
   - **Auto-escalate** — if `auto_escalate = true` AND `risk_score ≥ 80`, escalation email to Program Owner immediately.
5. **Cost control:**
   - Heuristic LOW items short-circuit (no LLM call).
   - LLM call rate-limited per-workflow to once every 30 min.
   - Cache stage-transition averages per (stage, assignee) for 1h.
   - Expected: ≤ 100 LLM calls per tick at peak (200 active interns × 3 in-flight workflows) ≈ negligible $.

**Demo moment:** judges see "this referral is 87% likely to breach NDA SLA — root cause: HR contact Sarah has 5 NDA requests open and last action was 22h ago — recommended: reassign to backup HR Priya." Then we hit "Auto-escalate" and the email lands live.

---

## Workflow state machine (the heart of the demo)

A single `WorkflowService` advances `workflow_state.current_step` through:

```
DRAFT → SUBMITTED → HR_REVIEW → NWID_REQUESTED → JOINING_INVITED →
JOINING_SUBMITTED → JOINING_LOCKED → NDA_SENT → NDA_SIGNED →
AD_PROVISIONED → READY_TO_START → IN_PROGRESS → CLOSURE_PENDING →
AD_DEACTIVATED → CERT_REQUESTED → CERT_ISSUED → ARCHIVED
```

Each transition: writes audit row, emits notification(s) via `BackgroundTasks`, schedules SLA timers via APScheduler.

---

## API surface (hackathon subset)

All under `/api/v1/`.

```
POST   /auth/login                   → JWT
POST   /auth/magic-link              → candidate first-time access
GET    /auth/me

POST   /referrals                    (Referrer)
PUT    /referrals/{id}
POST   /referrals/{id}/parse-resume  → triggers AI
POST   /referrals/{id}/submit
GET    /referrals?status=...

GET    /hr/inbox                     (HR)
POST   /hr/referrals/{id}/approve
POST   /hr/joining/{id}/lock

POST   /joining-forms/{token}        (Candidate, magic-link)
PUT    /joining-forms/{token}
POST   /joining-forms/{token}/attachments
POST   /joining-forms/{token}/submit

POST   /nda/{candidate_id}/issue     (HR)
POST   /webhooks/docusign            (DocuSign callback)

POST   /access/{internship_id}/provision   (IT)
POST   /access/{internship_id}/deactivate  (system or IT)

GET    /mentor/dossier/{internship_id}   (Mentor)

POST   /internships/{id}/start-confirmation
POST   /internships/{id}/extend
POST   /internships/{id}/close

POST   /certificates/{internship_id}/request   (Candidate)
POST   /certificates/{id}/issue                (HR)

GET    /dashboards/stages       (Program Owner)
GET    /dashboards/sla
GET    /audit?entity_type=&entity_id=

POST   /dedup/check
GET    /dedup/matches/{referral_id}
POST   /dedup/matches/{id}/decide

POST   /chatbot/sessions
POST   /chatbot/sessions/{id}/messages    (RAG + tool-calling; returns answer + citations + tool_calls)
GET    /chatbot/sessions/{id}
POST   /admin/faq/documents
POST   /admin/faq/reindex

POST   /referrals/intake/conversation     (alt. flow: conversational intake)
POST   /ai/validate/eligibility
POST   /ai/validate/form
POST   /ai/validate/attachment
POST   /ai/scope/analyze
POST   /ai/nda/{nda_id}/summary
GET    /ai/mentor/dossier/{internship_id}/brief
POST   /ai/certificates/{id}/achievements
POST   /ai/communications/draft
POST   /ai/communications/{draft_id}/approve

GET    /sla/risks
POST   /sla/risks/recompute
GET    /anomalies
POST   /anomalies/{id}/acknowledge

GET    /digests/weekly/latest
POST   /digests/weekly/regenerate

POST   /ai/mentors/suggest
GET    /mentors/profiles
PUT    /mentors/profiles/{user_id}

GET    /i18n/strings/{locale}
POST   /admin/i18n/translate

POST   /ai/alt-text
POST   /ai/a11y/audit
```

FastAPI auto-generates Swagger UI at `/docs` — leave it on, judges love it.

---

## Build phases (2-4 weeks for 1-3 devs)

### Week 1 — Foundations + AI-driven referral intake
- Repo skeleton (backend + frontend + docker-compose), Alembic migrations, seed script
- Postgres with `pgvector` extension enabled
- JWT auth with 6 seeded users
- Audit table + service; `ai_validations` + `ai_drafts` tables created up front
- Google Gemini client wrapper (`integrations/gemini.py`) with helpers: `complete_json()`, `embed()`, `complete_with_tools()`, `generate_with_pdf()`, `detect_language()`
- **AI #1 Resume parser** + Blob upload + classic referral form prefill
- **AI #4 Eligibility validator** + **AI #5 Smart form validator** wired into referral submit
- **AI #3 Conversational referral intake** — chat UI calls `gemini-2.0-flash` with `submit_referral` tool; voice via Web Speech API
- React: Login, Referral New (form mode + chat mode toggle), Referral List
- Gmail OAuth + `send_email()`
- **Demo checkpoint:** referrer either fills the form (AI prefilled) OR speaks the referral aloud and AI builds it; eligibility flags surface live concerns

### Week 2 — HR review, joining, NDA, dedup, attachment intelligence
- HR inbox + approve action
- **AI #6 Hybrid duplicate detection** with HR review screen
- **AI #8 Personalized communications** — every triggered email goes through `ai_drafts` flow; HR sees draft, can edit, approve, send
- Magic-link auth for candidates
- Joining form (multi-step, save-draft, attachments)
- **AI #11 Attachment intelligence** — Gemini native vision reads uploaded transcripts/IDs (PDF/image) and cross-checks vs. declared values; verdict written to `ai_validations`
- **AI #5 Smart form validator** also runs on joining form submit
- DocuSign envelope + webhook
- **AI #13 NDA plain-language summary** — generated when envelope is created; shown to candidate before they sign
- Workflow state machine wired through these transitions
- **Demo checkpoint:** dedup catches similar candidate → HR resolves → AI-drafted personalized invite email → candidate uploads transcript → AI flags mismatch → fixes → signs NDA after reading the AI summary

### Week 3 — AD, mentor, lifecycle, closure, scope analyzer, cert text
- Microsoft Graph: create + disable user
- Credential delivery email (Gmail)
- **AI #9 Project scope analyzer** — runs when mentor saves project overview
- **AI #15 Mentor dossier brief** — generated on dossier load
- Lifecycle endpoints (start/extend/close)
- **AI #20 Personalized certificate text** — LLM drafts achievements paragraph; mentor reviews; baked into PDF
- APScheduler: closure-7-days reminder, AD-deactivation-on-end-date job
- **Demo checkpoint:** mentor enters thin project description → AI suggests scope improvements → internship runs → on closure, certificate has personalized achievements paragraph

### Week 4 — Predictive AI, agentic chatbot, dashboards, deploy, demo
- Program Owner dashboard (stage counts, breaches, cycle time)
- **AI #17 SLA risk prediction** — `sla_risk_job` ticks every 5 min; `SlaRiskWidget` on dashboard; auto-escalation emails wired
- **AI #18 Anomaly detection** — hourly job scans recent `audit_events`, calls LLM, writes `anomaly_alerts`
- **AI #19 Weekly executive digest agent** — Sunday-night APScheduler job composes narrative + emails to Program Owner
- **AI #21 Agentic FAQ chatbot** — RAG over `faq_chunks` (audience-role filtered) + **LLM reranker** (top-20 → top-5) + function-calling tools (`get_my_pending_tasks`, `get_referral_status`, `extend_internship`, `request_nda_resend`, `escalate_sla_breach`, `submit_referral`); each tool enforces RBAC server-side; tool calls logged to `agent_tool_calls`. Mantine `Drawer` widget, role-aware
- **AI #23 Mentor matchmaking** — seed `mentor_profiles` with 6 mentors; `POST /ai/mentors/suggest` returns ranked top-3 with rationale; UI in Referral New shows them when mentor field is empty
- **AI #24 Multilingual interaction** — middleware reads `Accept-Language`; `i18n_strings` table populated by LLM batch-translation script (run during build); detect-language helper added to chatbot + intake + draft prompts
- **AI #25 Alt-text + WCAG audit** — alt-text job auto-runs on every Blob upload; admin panel "Run accessibility audit" button calls `/ai/a11y/audit` on the current rendered page
- **Continuous re-embedding** — SQLAlchemy event listener on `candidates` table triggers fingerprint refresh as `BackgroundTask`
- Audit log viewer + email template management
- Application Insights + structured logs
- Deploy to Azure App Service via GitHub Actions
- Seeded demo data + recorded demo script
- **Demo checkpoints:**
  - HR opens chatbot, types "extend Jane Doe by two weeks and email her mentor" → bot calls `extend_internship` + AI-drafts mentor email + sends → audit trail shows the chain
  - Referrer types referral in Hindi via voice → bot confirms back in Hindi → submits cleanly
  - Referrer leaves mentor blank → AI suggests "Mentor Anil (skill match 0.91, bandwidth 2/3, rationale: deep ML background, available)"

---

## Critical files / modules to create

These don't exist yet — this is greenfield. The new files to scaffold first (in priority order):

1. `backend/app/main.py` — FastAPI app + static mount + scheduler bootstrap
2. `backend/app/core/config.py` — pydantic-settings reading from env / Key Vault
3. `backend/app/db.py` — SQLAlchemy engine, sessionmaker
4. `backend/app/services/workflow.py` — state machine
5. `backend/app/services/notification_service.py` — Gmail send + template render
6. `backend/app/integrations/gemini.py` — Gemini SDK wrapper: `complete_json()`, `embed()`, `complete_with_tools()`, `generate_with_pdf()` (native PDF/image input), `detect_language()`
7. `backend/app/integrations/docusign.py` — `create_envelope()` + `verify_webhook_hmac()`
8. `backend/app/integrations/ms_graph.py` — `create_user()`, `disable_user()`
9. `backend/app/services/dedup_service.py` — hybrid rules-and-cosine match
10. `backend/app/services/chatbot_service.py` — RAG + function-calling tools
11. `backend/app/services/agent_tools.py` — typed tool functions exposed to the chatbot
12. `backend/app/services/faq_ingest.py` — chunk + embed + upsert
13. `backend/app/services/ai_validation_service.py` — eligibility, semantic form, attachment, scope analyzer
14. `backend/app/services/ai_draft_service.py` — drafts EMAIL / NDA_SUMMARY / MENTOR_BRIEF / CERT_ACHIEVEMENTS / EXEC_DIGEST
15. `backend/app/services/sla_risk_service.py` — heuristic + LLM
16. `backend/app/services/sla_history.py` — rolling median per stage
17. `backend/app/services/anomaly_service.py` — periodic LLM pass on audit
18. `backend/app/services/exec_digest_service.py` — weekly autonomous narrative
19. `backend/app/services/conversational_intake.py` — multi-turn referral via tools
20. `backend/app/services/mentor_match_service.py` — score mentors, return top-3
21. `backend/app/services/i18n_service.py` — language detect + LLM batch translation
22. `backend/app/services/a11y_service.py` — alt-text + WCAG audit
23. `backend/app/services/reranker.py` — LLM rerank top-20 → top-5
24. `scripts/build_i18n.py` — one-shot LLM translation of UI strings
25. `backend/Dockerfile` — multi-stage: node build → python runtime
26. `frontend/src/api/client.ts` — axios + JWT interceptor
27. `frontend/src/pages/ReferralNew.tsx` — form mode + chat mode toggle (Web Speech API)
28. `frontend/src/pages/DedupReview.tsx` — HR side-by-side candidate comparison + decision
29. `frontend/src/pages/Dashboard.tsx` — stage counts + SLA risk widget + anomalies + latest digest
30. `frontend/src/components/ChatWidget.tsx` — floating drawer; renders citations + tool-call cards
31. `frontend/src/components/SlaRiskWidget.tsx` — top at-risk items
32. `frontend/src/components/AiDraftReview.tsx` — generic draft-edit-approve component
33. `seed/faqs/` — markdown FAQ corpus (program rules, NDA FAQ, joining checklist, certificate process)
34. `seed.py` — demo users + templates + FAQ ingestion + sample audit history (so SLA risk model has signal at demo time)

---

## Reusable libraries (pull in early, don't reinvent)

| Need | Library | Why |
|---|---|---|
| OAuth for Gmail | `google-auth` + `google-api-python-client` | Official, battle-tested |
| DocuSign | `docusign-esign` | Official SDK, has sandbox |
| Microsoft Graph | `msgraph-sdk` (async) | Official; handles auth + retries |
| HTML→PDF | `WeasyPrint` | Pure Python, good CSS support; no headless Chrome |
| Resume PDF text | `pdfplumber` | Best ergonomics for tabular resumes |
| Settings | `pydantic-settings` | Env + Key Vault |
| Scheduler | `APScheduler` with `SQLAlchemyJobStore` | Persistent jobs survive restart |
| Bcrypt + JWT | `passlib[bcrypt]` + `python-jose[cryptography]` | Standard FastAPI auth recipe |
| Blob | `azure-storage-blob` | Official |
| pgvector ORM | `pgvector` (SQLAlchemy adapter) | `Vector(768)` column type for Gemini embeddings |
| Google Gemini client | `google-genai` (the new unified SDK) | Official; one client handles chat, embeddings, vision, tools, JSON-mode |
| Phone normalization | `phonenumbers` | E.164 normalization for dedup rules |
| Markdown chunking | Simple custom token-aware splitter | Splits FAQ markdown by heading + token budget |
| Fuzzy name match | `rapidfuzz` | Levenshtein/Jaro-Winkler for the rules tier of dedup |
| Language detection | `langdetect` | Lightweight, used to set system-prompt language |

---

## Deployment

- **One** App Service for Containers (Linux, B2 SKU is enough for 200 users).
- **One** Postgres Flexible Server, B1ms, single zone, with `vector` extension enabled.
- **One** Storage Account with one Blob container (`intern-flow`).
- **Google AI Studio API key** (free tier) for `gemini-2.0-flash` + `text-embedding-004` — no Google Cloud project setup needed; AI Studio issues the key directly. Stored in Azure Key Vault.
- **One** App Insights instance.
- **One** Key Vault holding: DB connection string, DocuSign creds, Gmail refresh token, Graph client secret, JWT signing key, **Google Gemini API key**.
- **One** ACR for the image.
- App Service uses **system-assigned managed identity** with Key Vault access.
- **GitHub Actions**: on push to `main` → build image → push to ACR → `az webapp deploy` → curl health check.

Estimated monthly cost (post-hackathon, idle): **~$50–80/mo**.

---

## Verification / demo plan

End-to-end test of the **golden path** before the demo. Each step listed should pass cleanly.

1. **Local smoke test** — `docker-compose up` brings up `api` + `postgres` + `adminer`. Run `python seed.py`. Hit `http://localhost:8000/docs` — Swagger renders.
2. **Auth** — `POST /api/v1/auth/login` with seeded HR user → JWT returned → `GET /auth/me` returns role=HR.
3. **Referral + AI** — As referrer, upload sample resume PDF → response includes `parsed_fields` with name/email/skills filled. Verify `audit_events` logs override.
4. **HR approve** — As HR, `POST /hr/referrals/{id}/approve` → seeded candidate Gmail receives joining-form magic link. Verify `notification_events.status = sent`.
5. **Joining form** — Click magic link → fill form → upload attachment → verify Blob upload → submit → HR locks it.
6. **NDA** — `POST /nda/{candidate_id}/issue` → DocuSign envelope created → click sandbox link → sign → webhook fires → DB status = `signed` → `audit_events` logs.
7. **AD provisioning** — `POST /access/{id}/provision` → user appears in test Entra tenant via Graph → credential email arrives.
8. **Lifecycle** — Set internship `end_date = today` → APScheduler tick → Graph user disabled and deactivation row created.
9. **Certificate** — Candidate `POST /certificates/{internship_id}/request` → HR `POST /certificates/{id}/issue` → PDF in Blob, link emailed.
10. **Dashboard** — Program Owner login → dashboard shows 1 in each stage with non-zero cycle time.
11. **Audit** — `GET /audit?entity_type=referral&entity_id={id}` returns full event chain.
12. **Duplicate detection** — Submit second referral with same candidate email → `dedup_score ≥ 0.99`, band=LIKELY. Submit a third with paraphrased name + same skills → band=POSSIBLE. Submit a fourth unrelated → band=UNIQUE.
13. **FAQ chatbot (RAG)** — As Candidate ask "When does my NDA need to be signed?" → answer cites joining-checklist chunk. As HR ask "What's the SLA on Non-Worker ID?" → reflects HR-audience chunk. Ask off-topic → bot declines.
14. **Conversational intake** — Click "Talk to AI" on Referral New → speak: "I'd like to refer Priya Patel, priya@example.com, for a 12-week ML internship with mentor Anil starting July 1" → bot confirms each captured field then calls `submit_referral` → referral row exists.
15. **Eligibility + semantic form validators** — Submit a referral with `in_person = true` but candidate address abroad → eligibility validator returns concern; submit a joining form where phone is `+91...` but address is in Germany → semantic validator flags it.
16. **Project scope analyzer** — Mentor saves a 1-line project description for a 12-week internship → analyzer returns "scope is thin for the duration" + 3 suggested learning objectives.
17. **Attachment intelligence** — Upload a transcript declaring "B.Tech, IIT Madras" but joining form declared "M.Tech" → validator flags mismatch.
18. **NDA plain-language summary** — Click DocuSign envelope link → candidate-side page shows AI summary above the legal doc; verify it lists the actual obligations.
19. **Mentor brief** — Open `/mentor/dossier/{id}` → top of page shows AI-drafted welcome paragraph mentioning candidate's actual skills + project.
20. **Personalized certificate text** — On closure → mentor reviews achievements paragraph → approves → final PDF includes it.
21. **SLA risk prediction** — Force a tick via `POST /sla/risks/recompute` after seeding a stale workflow → dashboard shows top item with risk_score, breach time, root_cause, recommended_action; auto-escalation email lands when score ≥ 80.
22. **Anomaly detection** — Seed 8 referrals from one referrer in 24h → next anomaly tick produces alert.
23. **Weekly digest** — `POST /digests/weekly/regenerate` → narrative report contains volume, breaches, root causes; arrives in Program Owner inbox.
24. **Agentic chatbot** — As HR, type "extend Jane Doe by 2 weeks and email her mentor" → bot calls `extend_internship` (verified in DB) → drafts mentor email via `ai_draft_service` → sends → `agent_tool_calls` logs both calls.
25. **Personalized comms** — Trigger HR approval on a referral → AI draft appears in `/ai/communications/...` queue → HR edits one sentence → approves → Gmail send fires.
26. **Mentor matchmaking** — Submit a referral with mentor field blank → response includes 3 ranked mentor suggestions with skill-match scores and rationales.
27. **Multilingual** — Set browser `Accept-Language: hi` → UI labels render in Hindi from `i18n_strings`. Open chatbot, ask in Tamil "என் pending tasks என்ன?" → answer comes back in Tamil.
28. **Continuous re-embedding** — Edit a candidate's email/skills row → within 1 minute the new fingerprint embedding is in `candidate_embeddings`. Run dedup again → finds matches based on fresh data.
29. **Reranker** — Inspect chatbot logs: `reranker.py` was called, took top-20 cosine results, returned top-5 with relevance scores; final answer cites only chunks from the reranked set.
30. **Alt-text + WCAG** — Upload a profile image → `image_alt_text` row appears with a sensible caption. From admin panel, click "Run a11y audit" → returns issues for any unlabeled form input on the current page.

**Hackathon demo script (5 min):** record this happy path with two browser windows (referrer + candidate), then a third (HR) to bridge approvals. Pre-seed the AI parse with a known resume so timing is predictable.

---

## Risks & how the plan handles them

| Risk | Handling |
|---|---|
| DocuSign sandbox webhook unreachable from local | `ngrok http 8000` during dev; in prod, App Service has a public URL |
| Microsoft Graph permission setup eats a day | Day 1 of week 3, get a Global-Admin contact to consent app permissions in test tenant |
| Gmail OAuth refresh-token expiry | Use a long-lived refresh token from one shared demo Google Workspace account |
| Gemini free-tier RPM limit (15 req/min on AI Studio) bites during dev iteration | Cache LLM responses against fixture inputs in tests so prompt-tuning loops don't burn quota; if it bites in dev, upgrade to paid (still cheap, ~$5–10/month at hackathon volume). Production demo runs single-user so 15 RPM is plenty |
| Cross-cloud secret distribution (Gemini API key in Azure Key Vault) | Standard pattern — Key Vault is vendor-neutral; managed identity reads the key at startup and the Gemini SDK uses it like any other API key |
| WeasyPrint system deps in container | Use `python:3.12-slim` and `apt-get install` deps in Dockerfile — do this in week 1 |
| Single-container scheduler dies on restart and loses jobs | APScheduler `SQLAlchemyJobStore` against Postgres — jobs survive restart |
| Azure DB for Postgres Flexible Server may not have `vector` enabled by default | Enable via Azure portal *Server parameters → azure.extensions* before week 2 |
| Embedding cost grows with corpus | `text-embedding-004` is **free on AI Studio**; batch embed (100 chunks/call), re-embed only on change. Total corpus likely < 500 chunks for hackathon |
| Chatbot hallucination on compliance answers | System prompt forbids answers without citations; if no chunk ≥ similarity 0.75 → bot replies "I don't have that information, please contact HR" |
| Dedup false positives block legitimate referrals | Bands are advisory — only LIKELY auto-blocks; POSSIBLE prompts HR review; UNIQUE auto-passes |
| Total LLM spend for 20 AI surfaces | Gemini free tier (15 RPM, 1M TPM, 1500 req/day) covers the demo. Heuristic gating + caching everywhere. SLA only LLM-calls non-LOW; anomaly hourly; digest weekly; validators once per submission; chatbot caps tokens at 1k/turn. **Estimated $0** on free tier; **< $10** if paid tier is needed during dev |
| Agentic chatbot taking destructive actions | Every tool function enforces RBAC server-side and writes `agent_tool_calls`. Destructive tools (extend, escalate) confirm with user. `extend_internship` capped at +30 days. No tool deletes |
| AI drafts going out unreviewed | All EMAIL drafts to external/legal recipients require HR approval. Internal-only emails auto-send |
| LLM latency on form submit makes UX laggy | Validation calls fire as `BackgroundTasks` after 200 OK; UI polls and surfaces concerns asynchronously. Resume parse stays sync (capped at 8s) with manual-fill fallback |
| 2-4 week scope is ambitious | Cut order if slipping: anomaly → digest → conversational intake (keep classic form) → attachment intelligence → personalized cert text. Never cut chatbot, dedup, SLA prediction, eligibility/form validators |

---

## Promoted from "Out of scope" → AI-scope (5 items)

These were originally cut, but each is genuinely doable by AI inside the 2–4 week window. Adding them lifts the AI ratio further and addresses real gaps.

1. **LLM reranker on RAG retrieval** — 2-stage retrieval for the chatbot: pgvector returns top-20 by cosine, then `gemini-2.0-flash` reranks to top-5 with relevance + role-fit scores. Cheap (one extra LLM call per query, ≤500 tokens) and noticeably improves answer relevance.
2. **Continuous re-embedding on candidate edits** — when a candidate row updates (HR correction, joining-form data fills in DOB, address, etc.), recompute the fingerprint embedding via `BackgroundTasks`. Keeps dedup search "live".
3. **Multilingual interaction (i18n via AI)** — every user-typed input is auto-detected for language; chatbot, conversational intake, validators, AI-drafted emails, and NDA summaries respond in the user's language. UI labels use `Accept-Language` + LLM batch-translate at build time into JSON resource bundles for top 8 languages (en, hi, ta, te, kn, ml, es, fr).
4. **Mentor-candidate matchmaking AI** — when the referrer leaves the mentor field empty, an LLM scores all available mentors against candidate skills + project domain + mentor's current workload and returns top 3 with rationale.
5. **AI accessibility helper** — alt-text generation for any uploaded image via `gemini-2.0-flash` native vision; AI WCAG audit endpoint `POST /ai/a11y/audit` that takes a rendered HTML snippet and returns flagged issues with suggested fixes.

These bring the AI footprint from 16 / 22 (~73%) to **20 / 26 (~77%)** — and the existing #6 (dedup), #21 (chatbot) become measurably better, not just bigger.

## Still out of scope (truly not AI-doable / not worth the time)

- Read replicas, multi-region, Azure Front Door — infra, not AI
- Always-Encrypted PII columns — security, not AI
- Performance / load testing for >200 users — irrelevant at hackathon scale
- Migration from monolith to services (covered in [Architecture_Analysis.md](./Architecture_Analysis.md))
- Fine-tuning custom models — off-the-shelf `gemini-2.0-flash` is more than adequate; fine-tuning needs labeled data we can't curate in time
- LangChain / LlamaIndex — direct `google-genai` SDK calls keep dependencies minimal and demos predictable
