# Source Configuration Arsenal: Implementation Guide

## Purpose
This document explains how the project implements source configuration ("website recipes") and how to build a reliable arsenal of scraping recipes for new domains.

The guide covers:
- Current architecture and data flow
- How recipes are created and stored
- How recipes are used at scrape runtime
- Operational workflow to onboard new sites
- Known limitations and recommended hardening points

## What is a "recipe" in this project?
A recipe is one row in `source_configs` with:
- `domain`
- `search_url_pattern` (must contain `{keyword}`)
- `title_selector`
- `content_selector`
- `date_selector`

This recipe tells the configurable provider:
1. How to discover candidate article URLs
2. How to extract article data on those URLs

## Architecture map

### API layer
- `app/api/endpoints/admin_sources.py`
  - `POST /api/v1/admin/sources/analyze`
  - `GET /api/v1/admin/sources/configs`
  - `GET /api/v1/admin/sources/configs/{domain}`
  - `DELETE /api/v1/admin/sources/configs/{domain}`
  - `POST /api/v1/admin/sources/configs/{domain}/refresh`

### Business logic
- `app/services/source_configuration/service.py`
  - Fetches article/homepage HTML
  - Runs AI analysis
  - Persists config via CRUD
  - Refreshes config by finding a fresh article from homepage

- `app/services/source_configuration/analyzers/ai_analyzer.py`
  - Detects `search_url_pattern` from homepage HTML + verifies it with real HTTP checks
  - Tests candidate selectors from `GENERIC_SELECTORS_MAP`
  - Uses AI quality checks for title/content validity

- `app/services/source_configuration/analyzers/heuristic_analyzer.py`
  - Finds a likely article URL on homepage
  - Provides heuristic fallback selector logic (currently not used in `analyze_url`)

### Storage
- `app/crud/supabase_crud.py`
  - `get_source_config_by_domain`
  - `get_all_source_configs`
  - `create_or_update_source_config`
  - `delete_source_config_by_domain`

- Migrations:
  - `migrations/create_source_configs_table.sql`
  - `migrations/add_search_url_pattern.sql`

### Runtime scraping usage
- `app/services/scraping/providers/configurable/manager.py`
  - Loads all source configs
  - Uses only configs with valid `search_url_pattern` for discovery

- `app/services/scraping/providers/configurable/discovery.py`
  - Executes `search_url_pattern.replace("{keyword}", quote_plus(keyword))`
  - Parses result links and filters candidate article URLs

- `app/services/scraping/providers/configurable/config.py`
  - Resolves domain config with subdomain fallback candidates

- `app/services/scraping/providers/configurable/fetcher.py`
  - Uses domain recipe selectors first
  - Falls back to generic selectors and trafilatura if needed
  - Supports Scrapling/Stealthy/Playwright paths

## End-to-end lifecycle

### 1) Analyze and save a recipe
Request:
```json
POST /api/v1/admin/sources/analyze
{
  "url": "https://example.com/some-article"
}
```

Service flow (`SourceConfigService.analyze_url`):
1. Normalize domain from URL
2. Fetch article HTML
3. Fetch homepage HTML
4. Run AI analyzer for selectors + search pattern
5. Upsert row into `source_configs`

### 2) Refresh existing recipe
Request:
```json
POST /api/v1/admin/sources/configs/example.com/refresh
```

Flow:
1. Fetch homepage
2. Find one likely article URL via heuristic analyzer
3. Re-run full analyze flow and upsert

### 3) Use recipes at scrape runtime
When configurable provider runs:
1. It loads all configs
2. Keeps only configs where `search_url_pattern` contains `{keyword}`
3. Discovers URLs for each keyword using the saved pattern
4. Extracts article content using saved selectors
5. If selectors fail, falls back to generic/trafilatura/playwright strategies

## Building your "arsenal" (recommended workflow)

### Step 1: Pick a representative article URL
For each new domain, use a normal article page (not tag page, login page, or section index).

### Step 2: Run analyze endpoint
Save the suggested recipe.

### Step 3: Validate the recipe
Confirm:
- `search_url_pattern` is present and includes `{keyword}`
- `title_selector` extracts headline text
- `content_selector` extracts meaningful article body
- `date_selector` extracts parseable date

### Step 4: Smoke test in scraping run
Run a targeted scrape with 1-3 keywords and verify:
- Discovery finds URLs
- Extraction returns meaningful content
- Date is parsed confidently when cutoff is active

### Step 5: Add to domain watchlist
Track domains that degrade often (selector drift, paywall changes, heavy JS) and schedule periodic `refresh`.

## Recipe quality checklist
- Search pattern returns article results (not homepage soft-404)
- At least one keyword gives candidate URLs
- Selector output is stable across 3+ recent articles
- Content length is meaningful (> 80 chars in current extractor threshold)
- Dates parse correctly for cutoff filtering

## Troubleshooting playbook

### Symptom: "No searchable configs found"
Cause:
- Missing `search_url_pattern` or missing `{keyword}` placeholder
Fix:
- Re-run analyze or manually patch pattern in `source_configs`

### Symptom: URLs discovered but no mentions saved
Possible causes:
- Selectors stale -> empty/low content
- Date fails strict cutoff checks
- Keyword match score below threshold
Fix:
- Refresh config from homepage
- Inspect logs for `date_*_cutoff_skip` and keyword match debug lines

### Symptom: Domain works in browser but fails in scraper
Possible causes:
- JS-heavy or anti-bot behavior
Fix:
- Enable Scrapling/Stealthy/StealthySession/Playwright fallback as needed
- Re-test extraction path in logs and metrics

## Important implementation notes

1. Discovery depends on `search_url_pattern`
- Without it, a domain is not used for configurable discovery.

2. Config resolution supports subdomain fallback
- Runtime checks domain candidates from most specific to broader forms.

3. Generic fallback still exists
- Even with a stored recipe, extractor can fall back to generic selectors/trafilatura.

4. "Admin-only" note vs actual guard
- Endpoint docs say admin-only, but enforcement currently uses `get_current_user`.
- If strict admin-only is required, add explicit role check in endpoint dependencies.

5. Heuristic selector fallback exists but is not wired in `analyze_url`
- `HeuristicAnalyzer.fallback_heuristic_analysis` exists but is currently not invoked in the main analyze flow.

## Hardening roadmap for arsenal management
- Add recipe health score per domain (discovery success, extraction success, date parse success)
- Add automated stale-recipe detection and auto-refresh queue
- Add explicit admin-role guard on `admin/sources` endpoints
- Add manual override endpoint for patching selectors/patterns without full re-analysis
- Version recipes (history/audit trail) to rollback bad selector updates

## Key files reference
- `app/api/endpoints/admin_sources.py`
- `app/services/source_configuration/service.py`
- `app/services/source_configuration/analyzers/ai_analyzer.py`
- `app/services/source_configuration/analyzers/heuristic_analyzer.py`
- `app/crud/supabase_crud.py`
- `app/services/scraping/providers/configurable/manager.py`
- `app/services/scraping/providers/configurable/discovery.py`
- `app/services/scraping/providers/configurable/config.py`
- `app/services/scraping/providers/configurable/fetcher.py`
- `app/services/scraping/providers/configurable/extractor.py`
- `migrations/create_source_configs_table.sql`
- `migrations/add_search_url_pattern.sql`
