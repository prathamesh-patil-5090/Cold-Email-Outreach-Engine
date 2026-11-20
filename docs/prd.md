# Product Requirements Document (PRD): Multi-Inbox Client Outreach Engine

**Version:** 1.1  
**Owner:** Prathamesh Patil  
**Active Scope:** Client / Agency Services Outreach Only (`crag.is-an.ai` & `trycrag.is-an.ai` excluded from active rotation)  
**Target Capacity:** 35 emails/day (Week 1) → 70 emails/day (Week 2) → 105–120 emails/day (Week 3+)  
**Active Mailboxes:** 7 Zoho Mail user accounts across 2 isolated Zoho Organizations (`pratz.is-a.dev` [2 outreach users] & `prathameshpatil.is-a.dev` [5 outreach users]), routing all replies to `prathamesh@pratz.is-a.dev`.

---

## 1. Executive Summary & Core Objectives

Commercial cold email sequencers (e.g., AutoMailer, Instantly, Smartlead) require live **IMAP** access to track replies and bounces, which Zoho Mail restricts on its Free Tier. Meanwhile, opt-in newsletter ESPs (Brevo, MailerLite, Loops) route through shared marketing IP pools, inject bulk unsubscribe headers, and suspend accounts on cold prospect lists.

This system replaces third-party sequencers with a **zero-IMAP, three-stage decoupled pipeline**:
1. **Stage 1 (Intake & Verification):** Python script validates email syntax, DNS MX records, and disposable domains before AI enrichment to keep hard bounces `< 2%`.
2. **Stage 2 (Micro-Batched AI Research):** Grok browser bot processes **5 leads per prompt** (4x throughput increase) alongside an optional free-tier LLM API fallback queue (Groq / Google AI Studio / Mistral) to extract 3 structured JSON personalization hooks per lead.
3. **Stage 3 (Multi-Inbox Python SMTP Worker):** A stateful Python worker reads/writes directly to Google Sheets, assembles 4-touch plain-text sequences using rotating spintax templates + AI variables, threads follow-ups via custom RFC-5322 `Message-ID` / `In-Reply-To` headers, centralizes replies via `Reply-To`, and enforces strict Zoho anti-spam rate limits.

---

## 2. Exact Mailbox Topology (7 Outreach Users)

### 2.1 Primary Reply-To Inbox (Never Used for Cold Outbound)
* **`prathamesh@pratz.is-a.dev`** — Receives all `Reply-To` prospect responses; used strictly for manual 1-to-1 closing conversations.

### 2.2 Zoho Organization 1 — `pratz.is-a.dev` (2 Outreach Users)
1. `p.patil@pratz.is-a.dev` (Display Name: `Prathamesh Patil`)
2. `prathamesh.p@pratz.is-a.dev` (Display Name: `Prathamesh Patil`)

### 2.3 Zoho Organization 2 — `prathameshpatil.is-a.dev` (5 Outreach Users)
3. `prathamesh@prathameshpatil.is-a.dev` (Display Name: `Prathamesh Patil`)
4. `patil@prathameshpatil.is-a.dev` (Display Name: `Prathamesh Patil`)
5. `prathamesh.patil@prathameshpatil.is-a.dev` (Display Name: `Prathamesh Patil`)
6. `connect@prathameshpatil.is-a.dev` (Display Name: `Prathamesh Patil`)
7. `p.patil@prathameshpatil.is-a.dev` (Display Name: `Prathamesh Patil`)

---

## 3. Ramp-Up & Anti-Spam Guardrails

| Phase | Daily Cap / User | Org 1 (`2 users`) | Org 2 (`5 users`) | Total Daily Sends | Hourly Cap / User | Jitter Between Sends |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Week 1 (Days 1–7)** | **5** | 10 | 25 | **35 / day** | 2 / hr | 25–45 mins |
| **Week 2 (Days 8–14)** | **10** | 20 | 50 | **70 / day** | 3 / hr | 15–25 mins |
| **Week 3+ (Day 15+)** | **15–17** | 30–34 | 75–85 | **105–119 / day** | 4 / hr | 8–18 mins |

**Mandatory Deliverability & Zoho Compliance Rules:**
* **Business Hours Only:** Send only Monday–Friday, `09:30` to `17:30` in target prospect timezone.
* **Plain Text Only on Touch 1–4:** Zero HTML tags, zero tracking pixels, zero URLs on Day 0. Share portfolio/case-study links only after a prospect replies.
* **Organic Two-Way Traffic:** Every 2–3 days, send 1 real message from your personal Gmail / `prathamesh@pratz.is-a.dev` to each of the 7 outreach addresses and reply back inside Zoho Webmail so Zoho sees a healthy 5–10% two-way inbound reply ratio on Org 2 (`prathameshpatil.is-a.dev`).
* **Manual Reply Stop-Switch:** When a prospect replies to `prathamesh@pratz.is-a.dev` (or bounces), update their Google Sheet `Outreach_Status` to `Replied`, `Bounced`, or `Stopped` so follow-ups halt immediately.

---

## 4. Google Sheet Database Schema (`Client Leads status` → `Outreach Tracker`)

Align the columns in the `Outreach Tracker` tab in exact order (`A` through `S`):

| Col | Header Name | Type / Allowed Values | Description |
| :--- | :--- | :--- | :--- |
| **A** | `Lead_ID` | String (`L-001`) | Unique row identifier. |
| **B** | `First_Name` | String | Prospect's first name. |
| **C** | `Email` | String | Prospect's work email. |
| **D** | `Company` | String | Company name. |
| **E** | `Role` | String | Job title (e.g., Founder, CEO, Ops Head, Director). |
| **F** | `Website_Or_Context` | String | Website URL, LinkedIn note, or raw research context for Grok. |
| **G** | `Timezone` | String (`Asia/Kolkata`, `America/New_York`) | Used to enforce 9:30 AM – 5:30 PM local send window. |
| **H** | `Email_Verified` | `PENDING` \| `VALID` \| `INVALID` | Populated by Stage 1 verification script. |
| **I** | `AI_Status` | `Queued` \| `Ongoing` \| `Done` \| `Failed` | Tracks Stage 2 Grok / LLM enrichment state. |
| **J** | `Trigger_Fact` | String (max 15 words) | Specific observation about their company/product. |
| **K** | `Pain_Hypothesis` | String (max 15 words) | Operational/engineering bottleneck inferred from context. |
| **L** | `Custom_Question` | String (max 25 words) | Curious, non-pushy question for Touch 1. |
| **M** | `Outreach_Status` | `Ready` \| `Active` \| `Completed` \| `Replied` \| `Bounced` \| `Stopped` | Master state machine for Stage 3 SMTP worker. |
| **N** | `Touch_Stage` | Integer (`0`, `1`, `2`, `3`, `4`) | `0` = unsent; `1` = Day 0 sent; `2` = Day 4; `3` = Day 8; `4` = Day 14. |
| **O** | `Assigned_Sender` | Email String | Locked to the specific Zoho user that sent Touch 1 (ensures all follow-ups come from the exact same sender). |
| **P** | `Thread_Message_ID` | String (`<uuid@domain>`) | Custom RFC-5322 `Message-ID` of Touch 1 for `In-Reply-To` / `References` threading. |
| **Q** | `Subject_Line` | String | Exact subject line used in Touch 1 (reused as `Re: <Subject_Line>`). |
| **R** | `Last_Sent_At` | ISO-8601 Timestamp | UTC timestamp of last sent touch (used to calculate Day +4, +8, +14). |
| **S** | `Next_Due_At` | ISO-8601 Timestamp | Calculated UTC timestamp when next touch becomes eligible. |

---

## 5. Stage 2: 5-Lead Micro-Batch Grok Prompt

Feed **5 rows at a time** where `Email_Verified == VALID` and `AI_Status == Queued` into your Grok bot. Instead of writing 20 full emails, Grok returns a single compact JSON array in ~15 seconds.

### System / Task Prompt for Grok Bot
```text
You are a B2B outbound research analyst for Prathamesh Patil, a full-stack web, mobile, and AI automation engineer helping businesses replace manual bottlenecks with custom internal tools, web platforms, and AI workflows.

I will give you 5 prospects in JSON format. Analyze each prospect's Company, Role, and Website_Or_Context.

Output ONLY a valid JSON array of 5 objects. Do not include markdown fences, explanations, or extra text.

Rules for each field:
1. "Lead_ID": Must match the exact input Lead_ID.
2. "Trigger_Fact": One specific, factual observation about their company, product, or current operations (max 15 words, plain conversational tone, zero buzzwords).
3. "Pain_Hypothesis": One concrete operational, manual-data, or software workflow bottleneck they likely face at their scale (max 15 words, zero jargon like "synergy", "leverage", "cutting-edge", or "streamline").
4. "Custom_Question": A natural, low-friction, peer-to-peer question asking how they currently handle that workflow (max 25 words, must end with a question mark, zero sales pitch, no mention of pricing, agencies, or calls).

Input Prospects:
[
  {"Lead_ID": "L-001", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-002", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-003", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-004", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-005", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."}
]
