# Product Requirements Document (PRD): Multi-Inbox Cold Email Outreach Engine

**Version:** 1.0  
**Owner:** Prathamesh Patil  
**Target Capacity:** 35 emails/day (Week 1) → 70 emails/day (Week 2) → 105–120 emails/day (Week 3+)  
**Domains & Mailboxes:** 7 Zoho Mail users across 2 isolated Zoho Organizations (`prathameshpatil.is-a.dev` [3 users] & `trycrag.is-an.ai` [4 users]), routing replies to `prathamesh@pratz.is-a.dev`.

---

## 1. Executive Summary & Core Objectives

Commercial cold email sequencers (e.g., AutoMailer, Instantly, Smartlead) require live **IMAP** access to track replies and bounces, which Zoho Mail blocks on its Free Tier. Meanwhile, opt-in newsletter ESPs (Brevo, MailerLite, Loops) route through shared marketing IP pools, inject unsubscribe headers, and suspend accounts on cold lead lists.

This system replaces third-party sequencers with a **zero-IMAP, three-stage decoupled pipeline**:
1. **Stage 1 (Intake & Verification):** Python script validates email syntax, DNS MX records, and SMTP reachability before AI enrichment to keep hard bounces `< 2%`.
2. **Stage 2 (Micro-Batched AI Research):** Grok browser bot processes **5 leads per prompt** (4x throughput increase) alongside a free-tier LLM API fallback queue (Groq / Google AI Studio / Mistral) to extract 3 structured JSON personalization hooks per lead.
3. **Stage 3 (Multi-Inbox Python SMTP Worker):** A stateful Python worker reads/writes directly to Google Sheets, assembles 4-touch plain-text sequences using rotating spintax templates + AI variables, threads follow-ups via custom `Message-ID` / `In-Reply-To` headers, centralizes replies via `Reply-To`, and enforces strict Zoho anti-spam rate limits.

---

## 2. Infrastructure & Mailbox Topology

### 2.1 Account & Domain Separation
* **Warm / Primary Inbox (Never used for cold outbound):**
  * `prathamesh@pratz.is-a.dev` (Receives all `Reply-To` prospect responses; handles manual 1-to-1 closing conversations).
  * `prathamesh@crag.is-an.ai` / `support@crag.is-an.ai` (Transactional SaaS app notifications & warm support only).
* **Cold Pod A — Agency Services (`prathameshpatil.is-a.dev` | Zoho Org 1 | 3 Users):**
  * `prathamesh@prathameshpatil.is-a.dev`
  * `p.patil@prathameshpatil.is-a.dev`
  * `pratham@prathameshpatil.is-a.dev`
* **Cold Pod B — CRag AI SaaS (`trycrag.is-an.ai` | Zoho Org 2 | 4 Users):**
  * `prathamesh@trycrag.is-an.ai`
  * `p.patil@trycrag.is-an.ai`
  * `pratham@trycrag.is-an.ai`
  * `patil.p@trycrag.is-an.ai`

### 2.2 Ramp-Up & Anti-Spam Guardrails
| Phase | Daily Cap / User | Pod A (3 Users) | Pod B (4 Users) | Total Daily Sends | Hourly Cap / User | Jitter Between Sends |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Week 1 (Days 1–7)** | 5 | 15 | 20 | **35 / day** | 2 / hr | 25–45 mins |
| **Week 2 (Days 8–14)** | 10 | 30 | 40 | **70 / day** | 3 / hr | 15–25 mins |
| **Week 3+ (Day 15+)** | 15–17 | 45–51 | 60–68 | **105–119 / day** | 4 / hr | 8–18 mins |

**Mandatory Deliverability Rules:**
* **Business Hours Only:** Send only Monday–Friday, `09:30` to `17:30` in target prospect timezone.
* **Plain Text Only on Touch 1–4:** Zero HTML tags, zero tracking pixels, zero URLs on Day 0. Links are shared only after a prospect replies.
* **Organic Two-Way Traffic:** Every 2–3 days, send 1 real message from personal Gmail / `pratz.is-a.dev` to each of the 7 outreach addresses and reply back inside Zoho Webmail to maintain a 5–10% inbound reply ratio.
* **Manual Reply Stop-Switch:** When a prospect replies to `prathamesh@pratz.is-a.dev` (or bounces), update their Google Sheet `Status` to `Replied`, `Bounced`, or `Stopped` so follow-ups halt immediately.

---

## 3. Google Sheet Database Schema (`Client Leads status` → `Outreach Tracker`)

Create/align the columns in the `Outreach Tracker` tab in exact order (`A` through `T`):

| Col | Header Name | Type / Allowed Values | Description |
| :--- | :--- | :--- | :--- |
| **A** | `Lead_ID` | String (`L-001`) | Unique row identifier. |
| **B** | `Campaign` | `AGENCY` \| `CRAG` | Routes lead to Pod A (`AGENCY`) or Pod B (`CRAG`). |
| **C** | `First_Name` | String | Prospect's first name. |
| **D** | `Email` | String | Prospect's verified work email. |
| **E** | `Company` | String | Company name. |
| **F** | `Role` | String | Job title (e.g., CTO, Founder, Ops Head). |
| **G** | `Website_Or_Context` | String | URL, LinkedIn note, or raw research context for Grok. |
| **H** | `Timezone` | String (`Asia/Kolkata`, `America/New_York`) | Used to enforce 9:30 AM – 5:30 PM local send window. |
| **I** | `Email_Verified` | `PENDING` \| `VALID` \| `INVALID` | Populated by Stage 1 verification script. |
| **J** | `AI_Status` | `Queued` \| `Ongoing` \| `Done` \| `Failed` | Tracks Stage 2 Grok / LLM enrichment state. |
| **K** | `Trigger_Fact` | String (max 15 words) | Specific observation about their company/product. |
| **L** | `Pain_Hypothesis` | String (max 15 words) | Operational/engineering friction inferred from context. |
| **M** | `Custom_Question` | String (max 25 words) | Curious, non-pushy question for Touch 1. |
| **N** | `Outreach_Status` | `Ready` \| `Active` \| `Completed` \| `Replied` \| `Bounced` \| `Stopped` | Master state machine for Stage 3 SMTP worker. |
| **O** | `Touch_Stage` | Integer (`0`, `1`, `2`, `3`, `4`) | `0` = unsent; `1` = Day 0 sent; `2` = Day 4; `3` = Day 8; `4` = Day 14. |
| **P** | `Assigned_Sender` | Email String | Locked to the specific Zoho user that sent Touch 1 (ensures all follow-ups come from the exact same sender). |
| **Q** | `Thread_Message_ID` | String (`<uuid@domain>`) | Custom RFC-5322 `Message-ID` of Touch 1 for `In-Reply-To` / `References` threading. |
| **R** | `Subject_Line` | String | Exact subject line used in Touch 1 (reused as `Re: <Subject_Line>`). |
| **S** | `Last_Sent_At` | ISO-8601 Timestamp | UTC timestamp of last sent touch (used to calculate Day +4, +8, +14). |
| **T** | `Next_Due_At` | ISO-8601 Timestamp | Calculated UTC timestamp when next touch becomes eligible. |

---

## 4. Stage 2: 5-Lead Micro-Batch Grok Prompt

Feed **5 rows at a time** where `Email_Verified == VALID` and `AI_Status == Queued` into your Grok bot. Instead of writing 20 full emails, Grok returns a single compact JSON array in ~15 seconds.

### System / Task Prompt for Grok Bot
```text
You are a B2B outbound research analyst. I will give you 5 prospects in JSON format. 
For each prospect, analyze their Company, Role, Campaign ("AGENCY" = custom web/AI/automation engineering; "CRAG" = hybrid RAG & unified engineering project workspace), and Website_Or_Context.

Output ONLY a valid JSON array of 5 objects. Do not include markdown fences, explanations, or extra text.

Rules for each field:
1. "Lead_ID": Must match the exact input Lead_ID.
2. "Trigger_Fact": One specific, factual observation about their company, product, or workflow (max 15 words, plain conversational tone, zero buzzwords).
3. "Pain_Hypothesis": One concrete workflow bottleneck they likely face relevant to the Campaign (max 15 words, no jargon like "synergy", "leverage", "cutting-edge", or "streamline").
4. "Custom_Question": A natural, low-friction, peer-to-peer question asking how they currently handle that workflow (max 25 words, must end with a question mark, zero sales pitch, no mention of pricing or calls).

Input Prospects:
[
  {"Lead_ID": "L-001", "Campaign": "CRAG", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-002", "Campaign": "AGENCY", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-003", "Campaign": "CRAG", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-004", "Campaign": "AGENCY", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."},
  {"Lead_ID": "L-005", "Campaign": "CRAG", "First_Name": "...", "Company": "...", "Role": "...", "Website_Or_Context": "..."}
]
