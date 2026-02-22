# Scraping Run Logic & Architecture

## 1. Overview
The scraping system in TrackAnything is a high-performance, asynchronous pipeline designed to fetch media mentions from multiple sources simultaneously. It supports both **manual triggers** (via API) and **scheduled runs** (via Cron).

### Key Features
*   **Parallel Execution:** All providers (GNews, SerpAPI, etc.) run concurrently.
*   **Resiliency:** A failure in one provider does not stop the entire run.
*   **Deduplication:** Multi-stage filtering (URL normalization + Fuzzy matching) to prevent noise.
*   **Concurrency Control:** Database-backed locking prevents overlapping runs for the same brand.
*   **Batch Processing:** Optimized database writes for high throughput.

---

## 2. The Orchestrator (`app/services/scraping/orchestrator.py`)
The heart of the system is the `fetch_all_mentions` function. It acts as the central coordinator.

### Process Flow
1.  **Input Normalization:**
    *   Cleans keywords (removes empty strings).
    *   Enforces `scraping_max_keywords_per_run` limit.
    *   Determines `from_date` (either explicit or calculated via `lookback_days`).
2.  **Provider Execution (Asyncio Gather):**
    *   Checks `settings.scraping_provider_*_enabled` flags.
    *   Launches enabled providers in parallel using `asyncio.gather(..., return_exceptions=True)`.
    *   **Providers:**
        *   `scrape_gnews`
        *   `scrape_serpapi`
        *   `scrape_rss`
        *   `scrape_configurable_sources`
3.  **Result Collection:**
    *   Aggregates results from all successful providers.
    *   Logs errors from failed providers but continues execution.
4.  **Deduplication (Stage 1: Exact URL):**
    *   Normalizes URLs (removes query params, tracking codes).
    *   Removes exact duplicates within the current batch.
5.  **Deduplication (Stage 2: Fuzzy Logic):**
    *   If enabled, uses `near_deduplicate_mentions` (Levenshtein distance) to merge similar headlines (e.g., "Crisis at Lego" vs "Lego Crisis").

---

## 3. Execution Modes

### A. Manual Trigger (API)
*   **Endpoint:** `POST /api/v1/scraping/brand/{brand_id}`
*   **Logic:**
    1.  **Auth:** Verifies user owns the brand.
    2.  **Lock:** Acquires DB lock (`scrape_in_progress=True`). Returns 409 if locked.
    3.  **Context:** Sets up per-run logging to a file.
    4.  **Query Building:**
        *   Fetches active Topics and Keywords.
        *   Constructs "Context Aware" queries (e.g., "Mærsk Regnskab" instead of just "Regnskab").
    5.  **Fetch:** Calls Orchestrator.
    6.  **Historical Dedup:** Checks new mentions against the *entire* recent history in DB.
    7.  **Smart Insert:**
        *   Pre-fetches Platforms and Keywords to minimize DB queries.
        *   Matches mentions to best Topic using `score_topic_match`.
        *   Batch inserts mentions.
    8.  **Release:** Updates `last_scraped_at` and releases lock.

### B. Scheduled Trigger (Cron)
*   **Script:** `scripts/run_scheduled_scrapes.py`
*   **Frequency:** Runs hourly (e.g., via Railway Cron).
*   **Logic:**
    1.  **Discovery:** Fetches ALL active brands.
    2.  **Filter:** Checks `last_scraped_at` vs `scrape_frequency_hours`.
        *   If `hours_since_last < frequency`, skip.
    3.  **Loop:** Iterates over due brands.
    4.  **Lock:** Tries to acquire lock. Skips if locked (assumes API or other job is running).
    5.  **Optimized Fetch:**
        *   Loads *all* keywords for the brand at once.
        *   Fetches *existing* URLs for the brand into memory (Set) for instant deduplication.
    6.  **Batch Insert:** Saves all new mentions in a single transaction.

---

## 4. Data Flow Diagram

```mermaid
graph TD
    A[Trigger (API or Cron)] --> B{Lock Available?}
    B -- No --> C[Abort / Skip]
    B -- Yes --> D[Fetch Keywords & Config]
    D --> E[Orchestrator]
    
    subgraph "Parallel Fetching"
        E --> F[GNews]
        E --> G[SerpAPI]
        E --> H[RSS Feeds]
    end
    
    F & G & H --> I[Raw Results]
    I --> J[Normalize URLs]
    J --> K[Fuzzy Deduplication]
    K --> L[Topic Matching]
    L --> M[Batch Insert to Supabase]
    M --> N[Update last_scraped_at]
    N --> O[Release Lock]
```

---

## 5. Critical Safeguards

### Concurrency Locking
To prevent race conditions (e.g., user clicks "Scrape Now" while Cron job is running), we use a database-backed lock on the `brands` table:
*   **Column:** `scrape_in_progress` (boolean)
*   **Column:** `scrape_started_at` (timestamp)
*   **Logic:**
    *   **Acquire:** `UPDATE brands SET scrape_in_progress=true WHERE id=X AND scrape_in_progress=false`
    *   **Release:** `UPDATE brands SET scrape_in_progress=false`
    *   **Timeout:** Locks are considered stale after 180 minutes (auto-release).

### Error Handling
*   **Provider Level:** Individual provider failures (timeouts, API errors) are logged but do *not* fail the run.
*   **Run Level:** If the main process crashes, the `finally` block ensures the DB lock is released.
*   **Logging:** Every run generates a unique `scrape_run_id` (e.g., `b123-abc12345`). Logs are tagged with this ID for easy debugging.

---

## 6. Optimization Techniques

1.  **Platform Caching:**
    *   Instead of querying the `platforms` table for every mention ("Is 'Politiken' in DB?"), we load all platforms into a Python dictionary at start.
    *   New platforms are created on-the-fly and added to cache.

2.  **Batch Inserts:**
    *   Mentions are not saved one-by-one.
    *   They are collected into a list and inserted via `supabase.table("mentions").insert([...])`.
    *   This reduces DB round-trips from N to 1.

3.  **Pre-Fetch Deduplication (Cron only):**
    *   The cron script fetches ALL existing URLs for the brand before scraping.
    *   New mentions are checked against this in-memory `Set`.
    *   This saves thousands of useless DB writes/constraints checks.
