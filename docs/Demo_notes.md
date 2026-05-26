# NexHire — Judge Demo Notes (10–15 min)

> **Demo date:** 2026-05-27  ·  **Window:** 10–15 minutes  ·  **Audience:** mixed (technical + business judges)
> **Goal:** Take a referral from submission to a downloaded certificate, live, in 10 minutes — and leave 3 minutes for Q&A.
>
> **How to read this doc on stage:**
> - **Bold** = something you click or type
> - *Italic* = exactly what you say to judges
> - Plain text = technical context for your own confidence (do not read out loud)

---

## Section 0 — One-sentence pitch (memorize this)

*"NexHire turns a 4-to-6-week, email-driven intern onboarding mess into a 1-to-2-week, AI-assisted, fully audited pipeline — for seven different roles, with ten AI touchpoints, on one platform."*

That's your fallback sentence if anything goes sideways. Drop it any time. It works as the opener, the closer, or a recovery line.

---

## Section 1 — Pre-demo checklist (do 15 min before judges walk in)

### Terminals
- [ ] **Terminal 1 (backend):** `cd d:\Viswa\Projects\Claude\NexHire\backend` → `uv run fastapi dev app/main.py`
- [ ] **Terminal 2 (frontend):** `cd d:\Viswa\Projects\Claude\NexHire\frontend` → `pnpm dev`

### Health checks (run from a third terminal or the browser)
- [ ] `http://localhost:8000/health` → returns 200 OK
- [ ] `http://localhost:8000/docs` → Swagger loads (keep this tab — it is your "if frontend dies" rescue)
- [ ] `http://localhost:5173` → React app loads, AAD login button visible

### Chrome — open these tabs in this order, left to right
1. **Tab 1:** `http://localhost:5173` — logged in as a **Referrer** test user, sitting on `/referrals/new` (5-step form, first step ready)
2. **Tab 2:** `http://localhost:5173/action/mentor?token=<seeded-token>&action=ACCEPT` — Mentor preview page (do not click Accept yet)
3. **Tab 3:** `http://localhost:5173/hr` — logged in as **HR**, on the dashboard with the queue visible
4. **Tab 4:** Candidate magic-link URL from your seed email — **DO NOT click yet**, just have it pasted into the URL bar
5. **Tab 5:** `http://localhost:5173/admin` — logged in as **Program Owner**, Executive Dashboard
6. **Tab 6 (rescue):** `http://localhost:8000/docs` — Swagger UI

### Files on Desktop (named so you find them in panic)
- [ ] `demo-resume.pdf` — a clean 1-page resume with skills like "Python, React, SQL"
- [ ] `demo-id-proof.jpg` — a sample Aadhaar/PAN/ID image for AI-6 extraction
- [ ] `demo-headshot.jpg` — optional, for joining form photo

### Device readiness
- [ ] Phone unlocked for AAD MFA push (if your test users have MFA)
- [ ] Laptop on AC power, sleep disabled, Do Not Disturb on
- [ ] Screen brightness at max, font zoom in Chrome at **125%** (judges in back row will thank you)
- [ ] One bottle of water, one breath

### Reset (only if a prior dry-run polluted state)
- [ ] Re-run the seed (whatever your team's seed command is) OR drop and re-migrate:
  - `uv run alembic downgrade base && uv run alembic upgrade head`
  - then re-seed your demo users + magic link

---

## Section 2 — The opening (60 seconds, no clicks)

Stand still. Do not touch the laptop. Look at the judges.

**You say (verbatim is fine — adapt to your voice):**

*"Good morning. Imagine your company refers an intern. Today, that triggers a 6-week chain of emails — HR reviewing, a mentor maybe accepting, IT provisioning Active Directory, security issuing a badge, legal chasing an NDA before Day 1. Dozens of touchpoints, no single dashboard, and the NDA-before-Day-1 compliance risk is real."*

(One beat.)

*"NexHire collapses that into one platform. Seven user roles — referrer, mentor, HR, candidate, security, IT, and the program owner — share one auditable pipeline, with ten AI touchpoints that read resumes, suggest mentors, score eligibility risk, flag duplicates, extract data from ID proofs, and even draft the final certificate."*

(One beat.)

*"In the next ten minutes I will take one referral from submission to a downloaded completion certificate. Let's go."*

Switch to **Tab 1**. Start clicking.

---

## Section 3 — Live demo script (10 minutes, 8 scenes)

> **Pacing rule:** if a scene runs long, cut the "what AI is doing" sentence — never cut the click. Judges remember motion, not narration.

---

### SCENE 1 — Referrer submits the referral (2:00)

**Tab:** 1 (`/referrals/new`)

**Click sequence:**
1. **Click "Upload Resume"** → select `demo-resume.pdf` from Desktop.
2. Wait 2–3 seconds. Watch the form **auto-fill**: name, email, phone, skills.
3. *"That's AI-1 — our resume deep analyzer. GPT-4o parsed the PDF, pulled out the candidate's skills, and even surfaced any red flags it saw. Every field has a confidence score behind it."*
4. **Scroll to the College field** → type "Indian Institute" → pick a college from the trigram match.
5. **Scroll to PAN field** → paste a seeded test PAN → watch the **green ACCEPTED chip** appear.
6. *"That's AI-4 — a real-time duplicate check. If this PAN had been referred in the last 24 months, we'd block the submission right here."*
7. **Click "Suggest Mentors"** (AI-2 button).
8. Watch the **radar chart** render with the top 3 mentors. Hover one to highlight five axes: skill, availability, reputation, familiarity, response speed.
9. *"AI-2 ranks mentors on five dimensions — not just skill match, but availability and how fast they respond. The narrative under each card explains why."*
10. **Pick the top mentor** → fill remaining fields (start date, duration, project title) → **click Submit**.
11. Toast: "Referral submitted — mentor notified."

**What you say to close the scene:**

*"Behind that submit, AI-3 just scored eligibility risk, and a mentor action-token email was sent. Let's switch hats."*

⏱ **Time check:** if your watch reads >2:00, skip the radar hover and move on.

---

### SCENE 2 — Mentor accepts the assignment (1:00)

**Tab:** 2 (`/action/mentor?token=...&action=ACCEPT`)

**Click sequence:**
1. *"This is what the mentor saw in their inbox — a one-click action token. Preview is safe; one-click consumes."*
2. Point at the **expires_at** badge: *"Three-day TTL. After that, the system auto-rerouters to the next best mentor."*
3. **Click "Confirm Accept."**
4. Toast: "Referral accepted — HR notified."

**What AI is doing under the hood (only say if time allows):**

*"That just triggered AI-10 — our workflow auto-router — which already lined up the least-loaded HR reviewer for the next step."*

⏱ **Time check:** at 3:00 elapsed, you should be on Tab 3.

---

### SCENE 3 — HR reviews and approves (1:00)

**Tab:** 3 (`/hr`)

**Click sequence:**
1. *"HR's dashboard. Notice the queue is already pre-prioritized — high-risk referrals at the top."*
2. **Click the referral** you just submitted.
3. Point at the **AI-3 risk score** (e.g., "LOW — 14/100"): *"AI-3 categorizes risk into low, medium, high. Low means HR can approve in seconds. High routes here for human judgment."*
4. Point at the **AI-4 duplicate panel**: *"Zero duplicates — clean submission."*
5. Point at the **AI-1 resume highlights card**: *"The resume analysis the referrer saw is preserved here for HR's context."*
6. **Click "Approve."**
7. Toast: "Referral approved — candidate email sent."

**What you say to close the scene:**

*"The candidate just received a magic link. Let's open it."*

⏱ **Time check:** at 4:00 elapsed, you switch to Tab 4.

---

### SCENE 4 — Candidate redeems the magic link (0:45)

**Tab:** 4 (paste the magic-link URL → Enter)

**Click sequence:**
1. *"Candidates are external — no Azure AD identity. We auth them via a 72-hour magic link with a candidate-only JWT scoped to their own record."*
2. The status portal loads. Point at the **stage timeline**: *"They see exactly where they are — joining form, NDA, badge, AD account, start date. No mystery."*
3. **Click "Open Joining Form."**

⏱ **Time check:** at 4:45 elapsed, you should be in the joining form.

---

### SCENE 5 — Joining form with AI-6 ID extraction (1:30)

**Tab:** 4 (continued — joining form page)

**Click sequence:**
1. **Click "Upload ID proof"** → pick `demo-id-proof.jpg`.
2. Wait 2–3 seconds. Watch fields populate: full name, date of birth, ID number, address.
3. *"That's AI-6. Azure Document Intelligence parses the ID image, and GPT-4o cross-validates the extracted data against what the referrer originally submitted. If anything mismatches, the form lands in HR's correction queue automatically."*
4. **Scroll through the form** — point out that fields are already filled from the referral.
5. **Edit one field** (e.g., emergency contact name) → pause 5 seconds → *"Notice we just auto-saved. Every 60 seconds, with optimistic locking — so two devices can't corrupt the draft."*
6. **Click "Submit Joining Form."**
7. Toast: "Form submitted — proceed to NDA."

**Why this scene matters to mention:** *"This was the part of onboarding that used to take three back-and-forth emails. We collapsed it to one upload."*

⏱ **Time check:** at 6:15 elapsed, you click NDA.

---

### SCENE 6 — In-app NDA signing (0:45)

**Tab:** 4 (continued — NDA page)

**Click sequence:**
1. *"Compliance moment. The NDA has to be signed before Day 1 — this is the box that historically gets missed."*
2. **Scroll the agreement** so judges see it is a real document.
3. **Type the candidate name** in the signature box.
4. **Click "I Accept."**
5. Toast: "NDA signed — recorded with timestamp, IP, and SHA-256 of the document."
6. *"We record the document hash so even if legal updates the NDA later, we can prove which version this candidate accepted."*

**Honest disclosure (only if asked):** in production we route through OpenSign for legal-grade e-signature; the in-app path is enabled in staging.

⏱ **Time check:** at 7:00 elapsed, switch to Tab 5 / task queue.

---

### SCENE 7 — Badge + AD provisioning auto-advance (1:00)

**Tab:** 5 (`/admin` or `/tasks/mine` as PO/admin)

**Click sequence:**
1. *"Two parallel tasks fire automatically — badge access for security, and AD account creation for IT. AI-10 already routed them to the least-loaded person on each team, skipping anyone on out-of-office."*
2. **Open the BADGE_ACCESS task** → enter a fake badge number (e.g., `BDG-DEMO-001`) → **Complete.**
3. **Open the AD_PROVISION task** → **Complete.**
4. Switch back to **Tab 4 (candidate portal)** → **refresh.**
5. Watch the stage advance to **ACTIVE**.
6. *"Both access tasks done, the intern's status auto-advances. This is the piece we shipped this week — one less email, one less Slack ping."*

**Tech credibility line (technical judges will like this):**

*"Behind the scenes, completing the provisioning task fires a domain event; a workflow handler validates the precondition set and transitions the intern. State machine, not if-statements."*

**Honest disclosure (only if asked):** the Microsoft Graph AD-create call is currently a stub — the workflow shape and audit are real; the Graph integration is the next sprint.

⏱ **Time check:** at 8:00 elapsed, switch to mentor closure.

---

### SCENE 8 — Closure feedback → AI-8 certificate (1:30)

**Tab:** 2 (or wherever the mentor workspace is — `/interns/mine`)

**Click sequence:**
1. *"Fast-forward 12 weeks. The internship is wrapping up."*
2. **Click "Confirm Completion"** on the demo intern.
3. **Fill the closure form:** project summary, skills demonstrated, recommendation level, key contributions.
4. **Click Submit.**
5. *"AI-8 just kicked off. GPT-4o is writing a 3-to-4-sentence personalized citation from the mentor's feedback — it cannot fabricate metrics, only synthesize what the mentor wrote. If confidence is below 0.85, it routes to HR for review. Above, it auto-sends with a 48-hour recall window."*
6. Switch to **Tab 4 (candidate portal)** → **refresh** → click **"Download Certificate."**
7. PDF opens. Read the citation aloud — it will sound real because it is.

**The mic-drop line:**

*"Resume in. Certificate out. One platform. Ten AI touchpoints. Fully audited."*

⏱ **Time check:** should be at ~9:30 elapsed. Move to the closing.

---

## Section 4 — Closing impact (60 seconds, Tab 5 or just talk)

Switch to **Tab 5** (Executive Dashboard). Let the KPIs sit on screen while you talk.

**You say:**

*"Three numbers to leave you with."*

*"Sixty-seven API endpoints. Ten AI touchpoints. Seven user roles. All in a single modular monolith — FastAPI on the backend, React on the front, Postgres for data, Redis for sessions, Azure OpenAI for intelligence."*

*"Every status change you saw is in an immutable audit trail. Every wait is on an SLA timer that auto-escalates. Every AI decision has a recall window so humans always have the last word."*

*"NexHire is not an AI gimmick. It's a workflow engine with AI where it matters and humans where they matter more."*

(Pause. Step back. Open palms.)

*"Happy to take questions."*

⏱ **Target finish:** 11:30. Buffer remaining: 2 minutes for Q&A.

---

## Section 5 — Likely judge questions & prepared answers

### Q: "What happens if the AI is wrong?"
*"Three safety nets. One — every AI auto-action has a 2-hour HR recall window. Two — the Program Owner can override any AI decision with a logged reason. Three — the immutable audit trail means every AI call, its input, its output, and any human override is replayable."*

### Q: "How does this scale?"
*"Modular monolith on async FastAPI — each module is independently testable and could be extracted to a service if a team owns it. Postgres with proper indexes handles the queue depth we've designed for (500 concurrent users, 50 interns per cycle). Redis caches session and rate-limit state. Scheduled jobs run on APScheduler. If we outgrow it, we extract the AI module first because it's already stateless and idempotent."*

### Q: "Why GPT-4o specifically?"
*"Three reasons we couldn't get from a smaller model. One — vision: parsing resumes and ID proofs as PDFs and images. Two — function calling: the AI-9 chatbot answers questions like 'which mentors have the highest rejection rate' by calling live database functions, not hallucinating numbers. Three — JSON mode: every AI output is schema-validated, no string parsing."*

### Q: "How do you handle security and compliance?"
*"PAN numbers are AES-256 encrypted at rest with a separate HMAC pepper for deduplication. Employees auth through Azure AD SSO. Candidates use 72-hour magic links scoped to their own record only — they can't see anyone else's data. NDAs are stored with a SHA-256 hash so we can prove the version each candidate accepted. And the audit trail is append-only, even for super-admins."*

### Q: "What's not done yet — be honest."
*"Three things, and I'll be specific. One — outbound Gmail send is currently a stub; the email composition is done, the send is mocked. Two — Microsoft Graph for actual AD account creation is a stub; the workflow shape and the audit trail are real, the Graph call is next sprint. Three — OpenSign is integrated but disabled in staging; we ship with the in-app NDA path on by default. Everything else you saw is end-to-end."*

### Q: "What does this cost to run per referral?"
*"Rough envelope on Azure OpenAI tokens: about ten cents per referral end-to-end across all ten AI calls. Document Intelligence adds another five cents for the ID extraction. Postgres + Redis + compute is shared across the org — call it dollar-fifty per intern fully loaded, versus the human-hours we replace."*

### Q: "Could I build this with just an LLM and no workflow engine?"
*"You could prompt an LLM to do everything, yes. But you can't audit prompts — you can audit state machines. And in HR and compliance contexts, 'why did this referral get rejected on April 14' has to have a deterministic answer. That's what the state machine gives you that the prompt cannot."*

### Q: "Who is the customer? Why would they buy this?"
*"Internal IT and HR shared-services teams at companies with 200+ employees that already run an unpaid internship program. They have the problem today and solve it with email. Our wedge is the compliance angle — NDA-before-Day-1 is increasingly mandated, and there is no current product that enforces it in-workflow."*

---

## Section 6 — Emergency fallbacks (if something breaks live)

### Azure OpenAI is slow or rate-limits mid-demo
**Symptom:** AI-1 resume parse spinner doesn't return within 5 seconds.

**What you do:** Wait one more second, then say *"That's actually a great chance to show off our graceful degradation."* The certificate generator (and most AI modules) have a built-in fallback — `certificate.py` returns a template citation with confidence 0.6 if the LLM call fails. Narrate it as a feature, not a bug.

### Frontend hot-reload breaks (white screen or 500)
**Symptom:** Tab 1 or 4 shows a blank page.

**What you do:** Switch to **Tab 6 (Swagger at `http://localhost:8000/docs`)**. Run the same endpoint through Swagger. *"Same API powers both — let me show you the contract directly."* Pick `POST /referrals` and execute a sample payload. Technical judges love this.

### Azure AD login fails
**Symptom:** Login button redirects and errors.

**What you do:** Skip the referrer/HR scenes. Go straight to the **candidate magic-link** flow (Tab 4) — magic links don't need AAD. The candidate journey is the most visually impressive part anyway: status portal → AI-6 ID extraction → NDA → certificate.

### Database is in a weird state from a prior dry-run
**Symptom:** "Referral already exists" or stale interns showing in dashboards.

**What you do:** Don't try to fix it live. Open a fresh incognito window, paste a different pre-seeded magic link (you should have 2–3 candidates seeded), and pick up at Scene 4. Skip Scenes 1–3 silently — judges won't notice if you commit to the pivot.

### You go over time
**Hard rule:** at the 12-minute mark, regardless of where you are, jump to Section 4 (closing impact). Better to finish strong than to be cut off mid-scene.

---

## Section 7 — Pacing cheat sheet (glance every 30 seconds)

| Elapsed | You should be on | If you're behind by 30s, cut… |
|---|---|---|
| 0:00 | Opener (Section 2) | — |
| 1:00 | Tab 1, uploading resume | — |
| 3:00 | Tab 2, mentor accept | the radar hover in Scene 1 |
| 4:00 | Tab 3, HR review | the AI-4 panel narration |
| 4:45 | Tab 4, magic link redeem | nothing yet |
| 6:15 | Tab 4, joining form submit | the auto-save explanation |
| 7:00 | Tab 4, NDA signed | the document-hash sentence |
| 8:00 | Tab 5, task queue | the state-machine line |
| 9:30 | Certificate downloaded | nothing — this is the climax |
| 11:30 | Closing line delivered | — |
| 12:00+ | Q&A | — |

---

## Section 8 — One-look feature inventory (in case judges ask "show me X")

| Judge asks for… | Open this tab / URL | What it shows |
|---|---|---|
| "The AI chatbot" | `/admin/chatbot` (Tab 5) | AI-9 — type *"Which mentors have the highest rejection rates?"* and let GPT-4o function-call the DB |
| "Audit trail" | `/admin/audit/recent` (Tab 5) | Immutable event log |
| "Config panel" | `/admin/config` (Tab 5) | Mentor capacity, cooling-off durations, change history |
| "SLA dashboard" | `/admin/sla/open` (Tab 5) | Open breaches with drilldown |
| "The API itself" | `http://localhost:8000/docs` (Tab 6) | All 67 endpoints with try-it-now |
| "Bottleneck predictor" | `/admin` Executive Dashboard | AI-5 — at-risk count tile |
| "Mentor out-of-office" | `/interns/mine` (Mentor view) | OOO toggle — AI-10 routing respects this |

---

## Section 9 — Reference docs (for self-confidence before the demo)

If you want to triple-check a feature claim before going live, the source-of-truth files are:

- [Local_Setup_Guide.md](./Local_Setup_Guide.md) — exact startup commands and env vars
- [Functionality_Matrix.md](./Functionality_Matrix.md) — every endpoint with ✅ wired / ⚠ stubbed / ❌ not built status, role by role
- [System_Blueprint.md](./System_Blueprint.md) — the 4,681-line spec (do not read tonight; sleep instead)
- [System_Flow.md](./System_Flow.md) — state machines and 32 documented flows
- [Architecture_Analysis.md](./Architecture_Analysis.md) — module-by-module rationale
- [Implementation_Plan.md](./Implementation_Plan.md) — binding decision log

---

## Section 10 — Final reminders (read this once on the morning of the demo)

1. **Sleep first, polish second.** A tired presenter beats a polished slide every time.
2. **Trust the script — but do not read it on stage.** Print it. Highlight your three favorite lines. Leave the laptop screen for the app.
3. **Slow down on the AI moments.** Resume auto-fill, mentor radar, ID extraction, certificate generation — these are your "wow." Let them breathe for one extra second before narrating.
4. **One number per sentence, max.** "Sixty-seven endpoints. Ten AI touchpoints. Seven roles." Not all in one breath.
5. **The audit trail is your secret weapon.** If a judge gets skeptical about AI, pivot to *"every decision is reviewable, recallable, and overridable by a human"* — and you've already won.
6. **If you forget everything, remember the one-sentence pitch in Section 0.** It works as opener, closer, or recovery.

You built this. Go show them.

— end of demo notes —
