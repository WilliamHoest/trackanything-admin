# AI Agent "Atlas" - Product Requirements & Roadmap (v3)

## 1. Vision & Objective
**Atlas** is not just a chatbot; it is an intelligent **Media Analyst Partner**. 

While TrackAnything collects data (scraping), Atlas transforms that data into **intelligence** and **action**. The goal is to move the user from "What happened?" to "What does this mean?" and "What should I do?".

### Core Value Proposition
*   **Synthesize:** Turn 100 articles into 1 executive summary.
*   **Contextualize:** Compare brand performance against competitors.
*   **Act:** Draft press releases, social posts, or internal briefings based on real-time data.

---

## 2. User Personas

| Persona | Role | Needs | Atlas Solution |
| :--- | :--- | :--- | :--- |
| **The PR Manager** | Day-to-day execution | Quick summaries, drafting responses, finding journalists. | "Draft a LinkedIn post about this article" |
| **The Comms Director** | Strategy & Crisis | Risk assessment, competitor benchmarking, trend analysis. | "Compare our sentiment vs. Novo Nordisk over the last 30 days" |
| **The Executive** | High-level overview | "Need to know" briefings, minimal noise. | "Give me a 3-bullet morning briefing on our brand reputation" |

---

## 3. Functional Capabilities (The 4 Levels)

### Level 1: Deep Insight (The Analyst)
*Capabilities that analyze existing data in Supabase.*
*   **Cross-Brand Comparison:** Compare volume, sentiment, and reach between the user's brand and a competitor.
*   **Sentiment Trend Analysis:** Visualize and explain how sentiment has changed over time (e.g., "Why did we drop last Tuesday?").
*   **Topic Clustering:** Automatically group mentions into "Narratives" (e.g., "The Sustainability Narrative" vs. "The Financial Narrative").

### Level 2: Content Engine (The Editor)
*Capabilities that generate output based on data.*
*   **Drafting Assistant:** Generate press releases, internal memos, or social media posts based on specific articles or trends.
*   **Executive Briefing:** Generate a daily or weekly PDF/Email summary format.
*   **Tone Adjustment:** Rewrite content to be "Professional," "Urgent," or "Celebratory."

### Level 3: Proactive Watchdog (The Sentinel)
*Capabilities that run automatically without user prompts.*
*   **Crisis Scoring:** Analyze incoming high-impact articles and assign a "Risk Score" (0-100).
*   **Anomaly Detection:** Alert when mention volume spikes significantly above the baseline.
*   **Smart Tagging:** Auto-classify mentions (e.g., "Job Posting," "Press Release," "User Review").

### Level 4: External Investigation (The Researcher)
*Capabilities that fetch new data via Tavily Search.*
*   **Journalist Profiling:** "Who is writing this?" (Fetch journalist background).
*   **Fact Checking:** Verify claims in an article against trusted sources or uploaded company policy documents.
*   **Market Context:** "What are competitors doing right now?" (Real-time web search).

---

## 4. Technical Architecture & RAG Design

**Status note (updated: February 21, 2026):**
For Atlas MVP (Phase 2-3), we use an **on-the-fly analysis** approach:
- No pgvector yet
- No new `mentions` columns yet (e.g., `sentiment_score`)
- Agent fetches raw mention text from Supabase and performs analysis/drafting in LLM context

### Stack
*   **Framework:** `pydantic-ai` (strong typing/validation).
*   **Model:** DeepSeek V3 (via OpenAI-compatible API).
*   **Database:** Supabase (Relational for MVP; vector store planned for later phases).
*   **Search Provider Layer:** `WebSearchProvider` interface with Tavily as primary provider (swappable backend).
*   **Orchestration:** FastAPI (async endpoints).

### RAG Strategy (Retrieval-Augmented Generation)
To fully support Level 4 and advanced Level 1 capabilities, we need a robust retrieval system in later phases.
*   **Embeddings:** Use OpenAI `text-embedding-3-small` (or equivalent open model) to embed mention `caption` + `content_teaser`.
*   **Storage:** Enable `pgvector` extension in Supabase. Add `embedding` column to `mentions`.
*   **Retrieval:** Hybrid Search (Keyword match via Full Text Search + Semantic match via Vector Cosine Similarity).
*   **Chunking:** Mentions are short; treat each mention as a single chunk. For long articles (fetched content), split by paragraphs (approx 500 tokens).

### Quality & Safety Requirements
*   **Citation Policy:** Every assertion in an analysis MUST cite a `mention_id` or `source_url`.
*   **Hallucination Guardrails:** If data is missing for a requested period, the Agent must explicitly state "No data available" rather than inventing trends.
*   **Latency SLO:**
    *   Simple Chat: < 2s TTFT (Time To First Token).
    *   Deep Analysis (Tools): < 15s total response time.
*   **Fallback:** If a tool fails (e.g., scraping error), the Agent must gracefully degrade to "I cannot access live data right now, but here is what I know...".
*   **Prompt Injection Defense:** External content must be treated as untrusted input and never override system/tool policies.
*   **Tool Permissioning:** High-impact tools (alerts, publish actions) must require explicit user confirmation or policy approval.

---

## 5. Tavily Integration Specification (External Search)

### Purpose
To provide real-time, high-quality external information (Level 4) when internal data is insufficient. Used for fact-checking, market research, and journalist profiling.

### Tool Contract
```python
def tavily_search(
    query: str, 
    max_results: int = 5, 
    recency_days: int = 7, 
    include_domains: List[str] = [], 
    exclude_domains: List[str] = []
) -> List[SearchResult]
```
*   **Input:** Natural language query, constraints.
*   **Output:** List of `SearchResult` (title, url, content, score, published_date).

### Configuration Requirements
*   **Env Var:** `TAVILY_API_KEY` (must be secured).
*   **Timeouts:** 10s max execution time per search.
*   **Rate Limits:** Implement token bucket or similar to respect Tavily tier limits (e.g., 100 req/min).
*   **Retries:** Max 2 retries with exponential backoff on 5xx errors.
*   **Fallback:** If Tavily fails/times out, degrade to "Search currently unavailable" message, do NOT hallucinate results.

### Safety & Policy
*   **Domain Allowlist:** Prioritize high-quality news sources (e.g., 'reuters.com', 'bloomberg.com', 'dr.dk', 'politiken.dk').
*   **Domain Blocklist:** Explicitly exclude known low-quality/clickbait/fake news domains.
*   **Citation Requirement:** All information retrieved via Tavily MUST be cited with a markdown link `[Source Title](url)` in the final response.

### Observability Metrics
*   **Success Rate:** % of calls returning 200 OK.
*   **Latency:** Average response time (target < 2s).
*   **Empty Results:** % of queries returning 0 results (indicates bad query formulation).
*   **Cost Tracking:** Monitor token usage/search volume vs. budget.

### UX Rules (When to use Tavily?)
*   **Internal Data First:** Always prioritize Supabase `mentions` for questions about tracked brands.
*   **Use Tavily When:**
    1.  User asks about a **non-tracked** entity/competitor.
    2.  User asks for **general market trends** or **definitions**.
    3.  User asks for **verification** of a specific fact.
    4.  User explicitly asks to "search the web".
*   **Do NOT Use Tavily When:**
    1.  User asks "How many mentions did we get yesterday?" (Internal DB query).
    2.  User asks for analysis of stored data.

---

## 6. Schema Impact Analysis
Current schema is sufficient for MVP on-the-fly analysis. The following migrations are planned for later phases:

### New Columns on `public.mentions`
| Column | Type | Purpose | Capability Level |
| :--- | :--- | :--- | :--- |
| `sentiment_score` | `float` (-1.0 to 1.0) | Trend analysis & Comparison | Level 1 |
| `reach_estimate` | `int` | Impact assessment (readers/views) | Level 1 |
| `author` | `text` | Journalist profiling | Level 4 |
| `embedding` | `vector(1536)` | RAG / Semantic Search | Level 1 & 4 |
| `crisis_score` | `int` (0-100) | Proactive alerting | Level 3 |
| `classification` | `text` | Smart Tagging (News/Noise/Job) | Level 3 |

### New Tables
*   **`generated_reports`**: Already exists (Migration 005), but check for `report_type` enum alignment.
*   **`author_profiles`** (Future): To store detailed journalist info linked to `mentions.author`.
*   **`agent_runs`** (Required): Persist run metadata (user, persona, tools called, latency, model, token usage, outcome).
*   **`agent_run_sources`** (Required): Link each run/report/alert to cited mention IDs and external URLs for auditability.

---

## 7. Detailed Tool Requirements

All tools should accept strict Pydantic models as input.
MVP currently returns text instructions/prompts for the agent flow; structured response models remain a target for later hardening.

### A. Analytical Tools

#### `compare_brands(brand_a: str, brand_b: str, days_back: int = 7)`
*   **Input:** Two brand names, time range.
*   **Operation:**
    *   **MVP (Implemented):** Fetch mention text for two brands and compare volume + inferred sentiment on-the-fly.
    *   **Future:** SQL Aggregation with stored metrics (`sentiment_score`, `reach_estimate`).
*   **Output:** MVP text analysis prompt/result; future target is `ComparisonResult`.

#### `analyze_sentiment_trend(brand_name: str, days_back: int = 14)`
*   **Input:** Brand name.
*   **Operation:** **MVP (Implemented):** trend inference from raw mention text over selected time window.
*   **Output:** MVP text analysis prompt/result; future target is `TrendResult`.

### B. Content Tools

#### `draft_response(mention_id: int, format: str, tone: str)`
*   **Input:**
    *   `mention_id`: ID of the mention to respond to (maps to `mentions` table).
    *   `format`: Enum ('linkedin', 'email', 'press_release').
    *   `tone`: Enum ('professional', 'urgent', 'casual').
*   **Operation:** **MVP (Implemented):** Fetch mention details by `mention_id` -> validate format/tone -> build drafting prompt.
*   **Output:** MVP text draft prompt/result; future target is `DraftContent`.

### C. Operational Tools

#### `classify_mention(mention_id: int)`
*   **Input:** Mention ID.
*   **Operation:** LLM analysis of title/teaser.
*   **Output:** `ClassificationResult` (category, confidence_score).

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Current Status) ✅
*   [x] Basic Chat Interface.
*   [x] `analyze_mentions` (Simple summary).
*   [x] `web_search` (Basic Tavily Implementation).

### Phase 2: The Analyst (Next Priority) 🚧
*   [x] **Refactor Context:** `UserContext` now uses `MentionContext` Pydantic model (app/services/ai/context.py).
*   [ ] **Schema Migration (Deferred for MVP):** Add `sentiment_score`, `reach_estimate`, `author` to `mentions`.
*   [x] **Tool:** Implement `compare_brands` (on-the-fly text analysis path).
*   [x] **Tool:** Implement `analyze_sentiment_trend` (on-the-fly text analysis path).
*   [x] **API Contract:** Expose tools used to frontend (`tools_used` + `X-Atlas-Tools-Used`).
*   [ ] **Tool:** Implement `get_key_influencers` (Who is talking?).
*   [ ] **UI:** Display charts generated from Agent data.

### Phase 3: The Editor
*   [x] **Tool:** Implement `draft_response` (`mention_id`, `format`, `tone`).
*   [ ] **Feature:** "Save Draft" to database.
*   [ ] **Workflow:** Add human approval state before external publishing/sending.
*   [ ] **Prompt:** Refine "PR Expert" persona for Danish nuances.

### Phase 4: The Sentinel (Proactive & RAG)
*   [ ] **Infrastructure:** Enable `pgvector` and backfill embeddings.
*   [ ] **Background Job:** Run "Crisis Check" & "Sentiment Analysis" on every scrape run.
*   [ ] **Notification:** Push alert if Risk Score > 80.
*   [ ] **Quality Loop:** Track false positives/false negatives and tune thresholds monthly.
*   [ ] **External Search:** Upgrade `web_search` to full `tavily_search` spec with policies.

### Phase 5: Enterprise Readiness
*   [ ] **Security:** Implement RBAC for tools, reports, and administrative actions.
*   [ ] **Compliance:** Implement GDPR retention/deletion workflows and PII handling policy.
*   [ ] **Auditability:** Persist full run metadata + source links (`agent_runs`, `agent_run_sources`).
*   [ ] **Reliability:** Enforce SLO dashboards and incident thresholds (latency/error/tool-failure).
*   [ ] **Release Quality:** Add offline eval suite + regression gating for prompts/tools before deploy.

---

## 9. Success Metrics
1.  **Tool Usage Rate:** % of chat sessions where a specific tool (e.g., `compare_brands`) is called.
2.  **Draft Retention Rate:** (1 - Edit Distance / Total Length). Measures how much the user *kept* of the AI draft. High retention = High quality.
3.  **Action Taken:** % of generated drafts that are "copied" or "saved" by the user.
4.  **Search Quality:** % of Tavily calls resulting in a citation used in the final answer.
5.  **Alert Precision/Recall:** Quality of crisis and anomaly alerts over time.
6.  **Operational Reliability:** P95 latency, tool success rate, and error rate per tool/persona.

---

## 10. Missing but Required Product Features (for "finished Atlas")

These are not optional if Atlas should operate as a production-grade product:

1.  **Role-Based Experience:** Different UX/tool availability for PR Manager, Comms Director, and Executive.
2.  **Approval & Escalation Flows:** Report approval, crisis escalation chain, and ownership assignment.
3.  **Traceable Citations UI:** Frontend must show exactly which sources each claim is based on.
4.  **Prompt/Tool Versioning:** Every output should be reproducible with model + prompt + tool version IDs.
5.  **Cost Governance:** Budget caps and alerts for model + Tavily usage.
6.  **Evaluation Harness:** Scheduled benchmark runs against fixed datasets before releasing prompt/tool changes.
