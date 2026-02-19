# Implementeringsplan: Rate Control, Metrics og Near-Dedupe

## Formål
Denne plan beskriver en trinvis implementering af tre høj-ROI forbedringer i scraping-platformen:
1. `aiolimiter` + `tldextract` (implementeres sammen)
2. `prometheus-client`
3. `rapidfuzz` (uden simhash i første version)

Målet er at reducere timeout/429-fejl, stabilisere runtime og løfte mention-kvaliteten.

## Nuværende problemer
- Concurrency findes allerede, men der mangler rate control pr. eTLD+1.
- Logs er detaljerede, men der mangler standardiserede runtime-metrics til KPI-styring.
- Dedupe er primært URL-baseret og fanger ikke near-duplicates på tværs af URL-varianter/kilder.

---

## Spor 1: `aiolimiter` + `tldextract` (P1)

### Hvorfor
- Concurrency alene beskytter ikke mod domain throttling.
- Rate limiting skal ske pr. eTLD+1 (fx `nyheder.tv2.dk` + `tv2.dk` familieset).

### Effekt
- Færre `429` og `timeout`.
- Mere stabil run-tid.
- Mindre risiko for at ét domæne dræner hele scraping-run.

### Dependencies
- Tilføj til `requirements.txt`:
  - `aiolimiter`
  - `tldextract`

### Implementeringsdesign
1. Ny helper til domænegruppering:
- Fil: `app/services/scraping/core/domain_utils.py`
- Funktioner:
  - `get_etld_plus_one(url_or_host: str) -> str`
  - robust fallback hvis parsing fejler.

2. Ny limiter-registry:
- Fil: `app/services/scraping/core/rate_limit.py`
- Funktioner:
  - `get_domain_limiter(etld1: str, profile: str) -> AsyncLimiter`
  - profiler for `html`, `rss`, `api`.

3. Integration i providers:
- Primært i configurable flow:
  - `app/services/scraping/providers/configurable/discovery.py`
  - `app/services/scraping/providers/configurable/fetcher.py`
- Valgfrit næste step:
  - `app/services/scraping/providers/rss.py`
  - `app/services/scraping/providers/gnews.py`
  - `app/services/scraping/providers/serpapi.py`

4. Konfigurerbare settings:
- Fil: `app/core/config.py`
- Eksempler:
  - `SCRAPING_RATE_HTML_RPS=1.5`
  - `SCRAPING_RATE_API_RPS=3.0`
  - `SCRAPING_RATE_RSS_RPS=2.0`

### Acceptance criteria
- 429-rate falder mindst 30% på sammenlignelige test-runs.
- Timeout-rate falder mindst 20%.
- p95 runtime forbedres eller bliver mere stabil (lavere variance).

---

## Spor 2: `prometheus-client` (P1)

### Hvorfor
- Uden metrics optimeres der i blinde.
- Logs er gode til debugging, men svage til trend/KPI-overvågning.

### Effekt
- Datadrevet tuning (ikke mavefornemmelse).
- Hurtigere root-cause ved regressions.

### Dependency
- Tilføj til `requirements.txt`:
  - `prometheus-client`

### Implementeringsdesign
1. Metrics endpoint:
- Eksponer `/metrics` via FastAPI app.
- Fil: `app/main.py` (eller dedikeret metrics module).

2. Metrics-definitioner:
- Fil: `app/services/scraping/core/metrics.py`
- Counters:
  - `scrape_runs_total{status}`
  - `scrape_requests_total{provider,domain,status_code}`
  - `scrape_extraction_failures_total{domain,reason}`
  - `scrape_playwright_fallback_total{domain,result}`
  - `scrape_duplicates_removed_total{stage}`
- Histograms:
  - `scrape_run_duration_seconds{brand_id}`
  - `scrape_provider_duration_seconds{provider}`
  - `scrape_request_duration_seconds{provider,domain}`
  - `scrape_extraction_content_length{provider,domain}`

3. Instrumentering:
- `app/services/scraping/orchestrator.py`
- `app/services/scraping/providers/configurable/manager.py`
- `app/services/scraping/providers/configurable/fetcher.py`
- øvrige providers (RSS/GNews/SerpAPI)

### KPI’er
- `p95` runtime pr. brand/run.
- Extraction success-rate pr. domæne.
- Timeout-rate pr. domæne.
- Playwright fallback hit-rate/success-rate.

### Acceptance criteria
- `/metrics` tilgængelig lokalt og i miljø.
- Mindst 10 centrale metrics er eksponeret med labels.
- Dashboard kan vise p50/p95 runtime + top fejlende domæner.

---

## Spor 3: `rapidfuzz` (P2)

### Hvorfor
- URL-dedupe alene giver near-duplicates i mentions.
- Samme historie kan komme fra flere URL’er med næsten identisk titel.

### Effekt
- Renere feed/digest.
- Bedre signal til frontend og fremtidige AI-opsummeringer.

### Dependency
- Tilføj til `requirements.txt`:
  - `rapidfuzz`

### Implementeringsdesign (v1 uden simhash)
1. Ny dedupe-module:
- Fil: `app/services/scraping/core/deduplication.py`
- Trin A: Blocking (billig prefilter)
  - samme eTLD+1
  - publiceringsdag ± 2 dage
  - normalized title prefix/signatur
- Trin B: Fuzzy compare på kandidater
  - `rapidfuzz.fuzz.token_set_ratio(title_a, title_b)`
  - threshold start: 92 (justeres pr. kilde)

2. Integration i orchestrator:
- Fil: `app/services/scraping/orchestrator.py`
- Flow:
  - behold eksisterende URL-dedupe først
  - anvend near-dedupe bagefter på resterende mentions

3. Konfiguration:
- Thresholds i settings:
  - `SCRAPING_FUZZY_DEDUP_THRESHOLD=92`
  - evt. source overrides senere

### Acceptance criteria
- Near-duplicate rate falder markant i test-runs med brede keywords.
- False-positive merge-rate holdes lav (manuel stikprøve).
- Dedupe-lag tilføjer ikke markant runtime-overhead.

---

## Faseplan (anbefalet rækkefølge)

### Fase 1
- Implementer `tldextract` + `aiolimiter` i configurable provider.
- Mål før/efter på timeout/429/p95.

### Fase 2
- Implementer `prometheus-client` + basal dashboard.
- Fastlæg baseline KPI’er.

### Fase 3
- Implementer `rapidfuzz` near-dedupe i orchestrator.
- Tuning af threshold på 2-3 realistiske brands.

### Fase 4
- Hardening + dokumentation + driftsoverdragelse.
- Justér rate-profiler og dedupe-threshold baseret på metrics.

---

## Risici og mitigering
- Risiko: Over-throttling reducerer coverage.
  - Mitigering: separate profiler (`html`, `api`, `rss`) + metrics-baseret tuning.
- Risiko: Fuzzy dedupe merger forskellige historier.
  - Mitigering: høj threshold i v1 + blocking-regler + manuel stikprøve.
- Risiko: Metrics-støj/for mange labels.
  - Mitigering: hold label-cardinality lav (domæne, provider, status).

---

## Done-definition
Planen er gennemført når:
1. Rate control pr. eTLD+1 er aktiv i scraping-flowet.
2. KPI-dashboard viser p95 runtime, timeout-rate, extraction success-rate og fallback-rate.
3. Near-duplicates reduceres dokumenteret uden væsentligt datatab.
